import json

import httpx
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


class ReceiptParseError(Exception):
    """Текст не удалось разобрать как чек"""


class LLMServiceError(Exception):
    """Сервис модели недоступен или вернул ошибку"""


class LLMClient:
    URL = "https://api.openai.com/v1/chat/completions"

    headers: dict
    api_key: str
    client: httpx.AsyncClient

    def __init__(self, api_key: str, timeout: int):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self.client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self):
        await self.client.aclose()

    async def parse_receipt_text(
        self, text: str, categories: dict[str, int]
    ) -> ReceiptIn:

        if not self.api_key:
            raise LLMServiceError("ключ OpenAI не настроен")

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

        try:
            response = await self.client.post(
                self.URL, headers=self.headers, json=payload
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise LLMServiceError("сервис модели недоступен или вернул ошибку") from e

        try:
            content = response.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
        except (json.JSONDecodeError, KeyError, IndexError) as e:
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
