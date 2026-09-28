
import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()  

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'change-this-secret-key')

    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL',
        'postgresql://postgres:W230604@localhost:5432/CampusHire'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  

    # OpenAI
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4.1-mini')

