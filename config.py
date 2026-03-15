import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY       = os.getenv("GROQ_API_KEY", "")
EMAIL_SENDER       = os.getenv("EMAIL_SENDER", "")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD", "")
APP_URL            = os.getenv("APP_URL", "http://localhost:8000")
ADMIN_EMAIL        = os.getenv("ADMIN_EMAIL", "admin@expensetracker.com")
ADMIN_PASSWORD     = os.getenv("ADMIN_PASSWORD", "haider123")