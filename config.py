import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev")
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
