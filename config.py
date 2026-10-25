import os

from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("OPENAI_API_KEY", "")

DATABASE_URL = os.environ["DATABASE_URL"]

SECRET_KEY = os.environ["JWT_SECRET"]

REDIS_URL = os.environ["REDIS_URL"]
