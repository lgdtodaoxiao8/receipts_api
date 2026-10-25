import hashlib

import redis.asyncio

from config import REDIS_URL
from models import ReceiptIn

redis_client = redis.asyncio.from_url(REDIS_URL)


async def close_cache() -> None:
    await redis_client.aclose()


def _cache_key(text: str, categories: dict[str, int]) -> str:

    sorted_categories = sorted(categories.items())

    categories_string = "|".join(
        [f"{key}: {value}" for key, value in sorted_categories]
    )

    hashed_key = hashlib.sha256((f"{text}\n{categories_string}").encode()).hexdigest()

    return "parse:" + hashed_key


async def get_cached_parse(text: str, categories: dict[str, int]) -> ReceiptIn | None:

    key = _cache_key(text=text, categories=categories)

    result = await redis_client.get(key)

    if result is None:
        return None

    return ReceiptIn.model_validate_json(result)


async def set_cached_parse(
    text: str, categories: dict[str, int], receipt: ReceiptIn
) -> None:

    receipt_json = receipt.model_dump_json()

    key = _cache_key(text=text, categories=categories)

    await redis_client.set(key, receipt_json, ex=86400)
