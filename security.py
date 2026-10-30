from datetime import UTC, datetime, timedelta

import jwt

from config import ACCESS_TOKEN_LIFETIME, SECRET_KEY


class TokenInfoError(Exception):
    """Неверная информация о пользователе"""


def create_access_token(user_id: int, duration_min: int = ACCESS_TOKEN_LIFETIME) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(UTC) + timedelta(minutes=duration_min),
    }

    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")

    return token


def decode_token(token: str) -> int:

    data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])

    try:
        user_id = int(data["sub"])
    except (KeyError, ValueError):
        raise TokenInfoError()

    return user_id
