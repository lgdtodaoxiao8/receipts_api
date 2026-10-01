import asyncio
import json
import os

import httpx
from dotenv import load_dotenv
from pydantic import ValidationError

from models import ItemIn, ReceiptIn

SYSTEM_PROMPT = """
    разбери текст чека и верни JSON строго такой формы:
    {
        "shop": "название магазина или null",
        "total": число или null,
        "items": [
            {"name": "название позиции", "price": число, "category": "имя категории или null"}
        ]
    }

    цены только числами, без валюты; строку с итогом не включать в items;
    если магазин или итог не найдет, ставь null; лишнее не включай в ответ.
    total брать только из явной строки с итогом или суммой в тексте;
    не вычислять и не складывать самостоятельно;если такой строки нет, ставить null;

    У каждой товарной позиции должно быть поле category с названием категории, 
    названия можно брать только из предложенного списка существующих катеогрий,
    а если ни одна не подходит, то null. Придумывать свои категории не из списка запрещено;
    если список категорий пуст, то всем позициям ставь null.
"""

RECEIPT_TEXT = """
супермаркет magnum
молоко 450
хлеб 180
сыр 1200
творог 650
яйца 600
куриное филе 1850
макароны 350
гречка 400
томаты 950
огурцы 800
яблоки 700
бананы 650
сок 550
вода 300
шоколад 500
чай 750
кофе 2100
печенье 400
салфетки 250
пакет 50
итог 13380
"""

URL = "https://api.openai.com/v1/chat/completions"


class ReceiptParseError(Exception):
    """Текст не удалось разобрать как чек"""


class LLMServiceError(Exception):
    """Сервис модели недоступен или вернул ошибку"""


async def parse_receipt_text(text: str, categories: dict[str, int]) -> ReceiptIn:

    api_key = os.environ["OPENAI_API_KEY"]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    categories_line = ", ".join(categories.keys())
    system_prompt = f"{SYSTEM_PROMPT}\n\nДоступные категории: {categories_line}"

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.post(URL, headers=headers, json=payload)
            response.raise_for_status()
        except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
            raise LLMServiceError("сервис модели недоступен или вернул ошибку") from e

    content = response.json()["choices"][0]["message"]["content"]

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise ReceiptParseError("не удалось разобрать текст как чек") from e

    items: list[ItemIn] = []

    try:
        for item in data["items"]:
            category_id = None

            if item["category"] in categories:
                category_id = categories[item.get("category")]

            items.append(
                ItemIn(
                    name=item["name"],
                    price=item["price"],
                    category_id=category_id,
                )
            )

        return ReceiptIn(total=data["total"], shop=data["shop"], items=items)

    except (ValidationError, KeyError, TypeError) as e:
        raise ReceiptParseError("не удалось разобрать текст как чек") from e


if __name__ == "__main__":
    load_dotenv()

    try:
        result = asyncio.run(
            parse_receipt_text(
                text=RECEIPT_TEXT,
                categories={
                    "Молочные продукты": 1,
                    "Хлеб и выпечка": 2,
                    "Мясные изделия": 3,
                    "Овощи и фрукты": 4,
                    "Бакалея": 5,
                    "Напитки": 6,
                    "Сладости и снеки": 7,
                    "Бытовая химия": 8,
                    "Гигиена и уход": 9,
                    "Товары для дома": 10,
                },
            )
        )
    except (ReceiptParseError, LLMServiceError) as e:
        print("ошибка:", e)
    else:
        print(result)
