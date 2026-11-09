from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated

import psycopg
import redis.exceptions
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import ExpiredSignatureError, InvalidTokenError
from psycopg_pool import ConnectionPool
from pydantic import AwareDatetime, ValidationError
from starlette.concurrency import run_in_threadpool

from cache import close_cache, get_cached_parse, set_cached_parse
from config import (
    ACCESS_TOKEN_LIFETIME,
    API_KEY,
    DATABASE_URL,
    OPENAI_SERVICE_TIMEOUT,
    REFRESH_TOKEN_LIFETIME,
)
from db import (
    delete_receipt,
    fetch_categories,
    fetch_categories_stats,
    fetch_receipt,
    fetch_receipts,
    get_user_by_email,
    get_user_by_id,
    patch_receipt_fields,
    patch_receipt_items,
    pop_refresh_token,
    save_category,
    save_receipt,
    save_refresh_token,
    save_user,
)
from llm import LLMClient, LLMServiceError, ReceiptParseError
from models import (
    CategoryIn,
    CategoryOut,
    ReceiptIn,
    ReceiptOut,
    ReceiptPatch,
    ReceiptTextIn,
    RefreshIn,
    Stat,
    UserLogin,
    UserOut,
    UserRegister,
)
from security import (
    TokenInfoError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_token,
)

bearer = HTTPBearer(auto_error=False)

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


def get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> int:
    if credentials is None:
        raise HTTPException(status_code=401, detail="нет токена")

    token = credentials.credentials

    try:
        user_id = decode_token(token=token)
    except (ExpiredSignatureError, InvalidTokenError, TokenInfoError):
        raise HTTPException(status_code=401, detail="токен невалидный") from None

    return user_id


@app.get("/me")
def me(user_id: Annotated[int, Depends(get_current_user_id)]) -> UserOut:
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


def _create_and_save_token_pair(
    conn: psycopg.Connection,
    user_id: int,
) -> dict[str, str]:
    access_token = create_access_token(
        user_id=user_id,
        duration_min=ACCESS_TOKEN_LIFETIME,
    )

    refresh_token = create_refresh_token()

    hash_refresh_token = hash_token(refresh_token)

    save_refresh_token(
        conn=conn,
        token_hash=hash_refresh_token,
        expires_at=datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_LIFETIME),
        user_id=user_id,
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


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

    with pool.connection() as conn:
        auth = _create_and_save_token_pair(conn=conn, user_id=fetched_user.id)

    return auth


@app.post(
    "/auth/refresh",
    status_code=200,
    responses={401: {"description": "неверный или истекший токен"}},
)
def update_tokens(current_refresh: RefreshIn) -> dict[str, str]:
    current_token_hash = hash_token(current_refresh.refresh_token)

    with pool.connection() as conn:
        user_id = pop_refresh_token(conn=conn, token_hash=current_token_hash)

        if user_id is None:
            raise HTTPException(status_code=401, detail="неверный или истекший токен")

        auth = _create_and_save_token_pair(conn=conn, user_id=user_id)

    return auth


@app.post("/auth/logout", status_code=204)
def logout_user(current_refresh: RefreshIn) -> None:
    current_refresh_hash = hash_token(current_refresh.refresh_token)

    with pool.connection() as conn:
        pop_refresh_token(conn=conn, token_hash=current_refresh_hash)


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
    dependencies=[Depends(get_current_user_id)],
)
async def parse_receipt(payload: ReceiptTextIn) -> ReceiptIn:
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
    receipt: ReceiptIn, user_id: Annotated[int, Depends(get_current_user_id)]
) -> ReceiptOut:

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
    user_id: Annotated[int, Depends(get_current_user_id)],
    period_start: AwareDatetime | None = None,
    period_end: AwareDatetime | None = None,
) -> list[Stat]:
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
    user_id: Annotated[int, Depends(get_current_user_id)],
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[ReceiptOut]:
    with pool.connection() as conn:
        result_list = fetch_receipts(
            conn=conn, limit=limit, offset=offset, user_id=user_id
        )

    return result_list


@app.get("/receipts/{receipt_id}", responses={404: {"description": "Чек не найден"}})
def get_receipt(
    receipt_id: int, user_id: Annotated[int, Depends(get_current_user_id)]
) -> ReceiptOut:
    with pool.connection() as conn:
        receipt = fetch_receipt(conn=conn, receipt_id=receipt_id, user_id=user_id)

    if receipt is None:
        raise HTTPException(status_code=404, detail="чек не найден")

    return receipt


@app.patch(
    "/receipts/{receipt_id}",
    responses={
        404: {"description": "чек не найден"},
        400: {"description": "указанной категории не существует"},
    },
)
def edit_receipt(
    receipt_change: ReceiptPatch,
    receipt_id: int,
    user_id: Annotated[int, Depends(get_current_user_id)],
) -> ReceiptOut:
    with pool.connection() as conn:
        patched = patch_receipt_fields(
            conn=conn,
            user_id=user_id,
            receipt_id=receipt_id,
            fields=receipt_change.model_dump(exclude_unset=True, exclude={"items"}),
        )
        if not patched:
            raise HTTPException(status_code=404, detail="чек не найден")

        if receipt_change.items is not None:
            items = [
                (item.name, item.price, item.category_id)
                for item in receipt_change.items
            ]

            try:
                patch_receipt_items(conn=conn, receipt_id=receipt_id, items=items)
            except psycopg.errors.ForeignKeyViolation:
                raise HTTPException(
                    status_code=400, detail="указанной категории не существует"
                ) from None

        fetched = fetch_receipt(conn=conn, receipt_id=receipt_id, user_id=user_id)

    if fetched is None:
        raise RuntimeError("чек не найден сразу после изменения")

    return fetched


@app.delete(
    "/receipts/{receipt_id}",
    status_code=204,
    responses={404: {"description": "чек не найден"}},
)
def remove_receipt(
    receipt_id: int, user_id: Annotated[int, Depends(get_current_user_id)]
) -> None:
    with pool.connection() as conn:
        deleted = delete_receipt(
            conn=conn,
            receipt_id=receipt_id,
            user_id=user_id,
        )

        if not deleted:
            raise HTTPException(status_code=404, detail="чек не найден")


@app.get("/ping")
def ping() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/categories",
    status_code=201,
    responses={409: {"description": "категория уже существует"}},
    dependencies=[Depends(get_current_user_id)],
)
def create_category(category: CategoryIn) -> CategoryOut:
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
