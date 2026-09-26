import asyncio
import json
import os

import httpx
from dotenv import load_dotenv
from pydantic import ValidationError

from models import ReceiptIn

SYSTEM_PROMPT = """
    разбери текст чека и верни JSON строго такой формы:
    {
        "shop": "название магазина или null",
        "total": число или null,
        "items": [
            {"name": "название позиции", "price": число}
        ]
    }

    цены только числами, без валюты; строку с итогом не включать в items;
    если магазин или итог не найдет, ставь null; лишнее не включай в ответ.
    total брать только из явной строки с итогом или суммой в тексте;
    не вычислять и не складывать самостоятельно;если такой строки нет, ставить null;
"""

RECEIPT_TEXT = """
магнум
кофе 100
"""

URL = "https://api.openai.com/v1/chat/completions"


class ReceiptParseError(Exception):
    """Текст не удалось разобрать как чек"""


class LLMServiceError(Exception):
    """Сервис модели недоступен или вернул ошибку"""


async def parse_receipt_text(text: str) -> ReceiptIn:

    api_key = os.environ["OPENAI_API_KEY"]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "response_format": {"type": "json_object"},
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

    try:
        return ReceiptIn(**data)
    except ValidationError as e:
        raise ReceiptParseError("не удалось разобрать текст как чек") from e


if __name__ == "__main__":
    load_dotenv()

    try:
        result = asyncio.run(parse_receipt_text(RECEIPT_TEXT))
    except (ReceiptParseError, LLMServiceError) as e:
        print("ошибка:", e)
    else:
        print(result)
