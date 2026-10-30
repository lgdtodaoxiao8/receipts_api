from contextlib import asynccontextmanager

import psycopg
import redis.exceptions
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import FastAPI, Header, HTTPException, Query
from jwt import ExpiredSignatureError, InvalidTokenError
from psycopg_pool import ConnectionPool
from pydantic import AwareDatetime, ValidationError
from starlette.concurrency import run_in_threadpool

from cache import close_cache, get_cached_parse, set_cached_parse
from config import ACCESS_TOKEN_LIFETIME, API_KEY, DATABASE_URL, OPENAI_SERVICE_TIMEOUT
from db import (
    fetch_categories,
    fetch_categories_stats,
    fetch_receipt,
    fetch_receipts,
    get_user_by_email,
    get_user_by_id,
    save_category,
    save_receipt,
    save_user,
)
from llm import LLMClient, LLMServiceError, ReceiptParseError
from models import (
    CategoryIn,
    CategoryOut,
    ReceiptIn,
    ReceiptOut,
    ReceiptTextIn,
    Stat,
    UserLogin,
    UserOut,
    UserRegister,
)
from security import TokenInfoError, create_access_token, decode_token

hasher = PasswordHasher()

pool = ConnectionPool(DATABASE_URL, open=False)

llm_client = LLMClient(API_KEY, OPENAI_SERVICE_TIMEOUT)


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool.open()
    yield
    await llm_client.aclose()
    await close_cache()
    pool.close()


app = FastAPI(lifespan=lifespan)


def get_current_user_id(authorization: str | None) -> int:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="нет токена")

    token = authorization.removeprefix("Bearer ")

    try:
        user_id = decode_token(token=token)
    except (ExpiredSignatureError, InvalidTokenError, TokenInfoError):
        raise HTTPException(status_code=401, detail="токен невалидный") from None

    return user_id


@app.get("/me")
def me(authorization: str | None = Header(default=None)) -> UserOut:
    user_id = get_current_user_id(authorization=authorization)
    with pool.connection() as conn:
        try:
            response = get_user_by_id(conn=conn, user_id=user_id)
        except LookupError:
            raise HTTPException(
                status_code=401, detail="пользователь не найден"
            ) from None

    return response


@app.post(
    "/auth/register",
    status_code=201,
    responses={409: {"description": "пользователь с такой почтой уже существует"}},
)
def create_user(user: UserRegister) -> UserOut:
    password_hash = hasher.hash(user.password)
    with pool.connection() as conn:
        try:
            user_out = save_user(conn, email=user.email, password_hash=password_hash)
        except psycopg.errors.UniqueViolation:
            raise HTTPException(
                status_code=409, detail="пользователь с такой почтой уже существует"
            ) from None

    return user_out


@app.post(
    "/auth/login",
    status_code=200,
    responses={401: {"description": "неверный email или пароль"}},
)
def login_user(user: UserLogin) -> dict[str, str]:
    with pool.connection() as conn:
        try:
            fetched_user = get_user_by_email(conn=conn, email=user.email)
        except LookupError:
            raise HTTPException(
                status_code=401, detail="неверный email или пароль"
            ) from None

    try:
        hasher.verify(fetched_user.password_hash, user.password)
    except (VerificationError, InvalidHashError):
        raise HTTPException(
            status_code=401, detail="неверный email или пароль"
        ) from None

    token = create_access_token(
        user_id=fetched_user.id, duration_min=ACCESS_TOKEN_LIFETIME
    )

    return {"access_token": token, "token_type": "bearer"}


def read_categories() -> list[CategoryOut]:
    with pool.connection() as conn:
        categories = fetch_categories(conn=conn)
    return categories


@app.post(
    "/receipts/parse",
    responses={
        422: {"description": "не удалось разобрать текст как чек"},
        503: {"description": "сервис модели недоступен или вернул ошибку"},
    },
)
async def parse_receipt(
    payload: ReceiptTextIn,
    authorization: str | None = Header(default=None),
) -> ReceiptIn:

    get_current_user_id(authorization=authorization)

    categories = await run_in_threadpool(read_categories)

    categories_dict: dict[str, int] = {
        category.name: category.id for category in categories
    }

    try:
        cached_response = await get_cached_parse(
            text=payload.text, categories=categories_dict
        )

        if cached_response is not None:
            return cached_response
    except (redis.exceptions.RedisError, ValidationError):
        pass

    try:
        response = await llm_client.parse_receipt_text(
            payload.text, categories=categories_dict
        )
    except ReceiptParseError as e:
        raise HTTPException(
            status_code=422, detail="не удалось разобрать текст как чек"
        ) from e
    except LLMServiceError as e:
        raise HTTPException(
            status_code=503, detail="сервис модели недоступен или вернул ошибку"
        ) from e
    else:
        try:
            await set_cached_parse(
                text=payload.text, categories=categories_dict, receipt=response
            )
        except redis.exceptions.RedisError:
            pass

        return response


@app.post(
    "/receipts",
    status_code=201,
    responses={
        400: {"description": "указанной категории не существует"},
        401: {"description": "пользователь не найден"},
    },
)
def create_receipt(
    receipt: ReceiptIn,
    authorization: str | None = Header(default=None),
) -> ReceiptOut:

    user_id = get_current_user_id(authorization=authorization)

    items = [(item.name, item.price, item.category_id) for item in receipt.items]

    with pool.connection() as conn:
        try:
            receipt_id = save_receipt(
                conn=conn,
                items=items,
                total=receipt.total,
                shop=receipt.shop,
                purchased_at=receipt.purchased_at,
                user_id=user_id,
            )
        except psycopg.errors.ForeignKeyViolation as e:
            if e.diag.constraint_name == "fk_receipts_users":
                raise HTTPException(
                    status_code=401,
                    detail="пользователь не найден",
                ) from None

            raise HTTPException(
                status_code=400,
                detail="указанной категории не существует",
            ) from None
        created_receipt = fetch_receipt(
            conn=conn, receipt_id=receipt_id, user_id=user_id
        )

    if created_receipt is None:
        raise RuntimeError("чек не найден сразу после создания")

    return created_receipt


@app.get("/receipts/stats", responses={422: {"description": "указан неверный период"}})
def list_categories_stats(
    period_start: AwareDatetime | None = None,
    period_end: AwareDatetime | None = None,
    authorization: str | None = Header(default=None),
) -> list[Stat]:

    user_id = get_current_user_id(authorization=authorization)

    if (
        period_start is not None
        and period_end is not None
        and period_end < period_start
    ):
        raise HTTPException(422, detail="указан неверный период")

    with pool.connection() as conn:
        result = fetch_categories_stats(
            conn=conn, period_start=period_start, period_end=period_end, user_id=user_id
        )

    return result


@app.get("/receipts")
def list_receipts(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    authorization: str | None = Header(default=None),
) -> list[ReceiptOut]:

    user_id = get_current_user_id(authorization=authorization)

    with pool.connection() as conn:
        result_list = fetch_receipts(
            conn=conn, limit=limit, offset=offset, user_id=user_id
        )

    return result_list


@app.get("/receipts/{receipt_id}", responses={404: {"description": "Чек не найден"}})
def get_receipt(
    receipt_id: int,
    authorization: str | None = Header(default=None),
) -> ReceiptOut:

    user_id = get_current_user_id(authorization=authorization)

    with pool.connection() as conn:
        receipt = fetch_receipt(conn=conn, receipt_id=receipt_id, user_id=user_id)

    if receipt is None:
        raise HTTPException(status_code=404, detail="чек не найден")

    return receipt


@app.get("/ping")
def ping() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/categories",
    status_code=201,
    responses={409: {"description": "категория уже существует"}},
)
def create_category(
    category: CategoryIn, authorization: str | None = Header(default=None)
) -> CategoryOut:
    get_current_user_id(authorization=authorization)

    with pool.connection() as conn:
        try:
            return save_category(conn=conn, name=category.name)
        except psycopg.errors.UniqueViolation:
            raise HTTPException(
                status_code=409, detail="категория уже существует"
            ) from None


@app.get("/categories")
def list_categories() -> list[CategoryOut]:
    with pool.connection() as conn:
        result = fetch_categories(conn=conn)

    return result
