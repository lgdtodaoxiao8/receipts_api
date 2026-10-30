import os

from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("OPENAI_API_KEY", "")

DATABASE_URL = os.environ["DATABASE_URL"]

SECRET_KEY = os.environ["JWT_SECRET"]

REDIS_URL = os.environ["REDIS_URL"]

ACCESS_TOKEN_LIFETIME = 15  # in minutes

OPENAI_SERVICE_TIMEOUT = 30  # in seconds

OPENAI_MODEL_NAME = "gpt-4o-mini"
