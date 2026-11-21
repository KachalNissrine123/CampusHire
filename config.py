import os

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    # Override both of these in .env; the defaults only exist so a fresh
    # clone boots against a local Postgres with no extra setup.
    SECRET_KEY = os.getenv("SECRET_KEY", "campushire-local-dev")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "postgresql+psycopg2://postgres@localhost:5432/campushire"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # CVs and department logos live outside git (see .gitignore).
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    CV_EXTENSIONS = {".pdf", ".docx"}
    LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

    # Leave OPENAI_API_KEY empty to run without the CV screener; applications
    # are then scored from the profile fields alone.
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
