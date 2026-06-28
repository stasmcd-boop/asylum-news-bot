import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_channel: str = os.getenv("TELEGRAM_CHANNEL", "")
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_service_key: str = os.getenv("SUPABASE_SERVICE_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    timezone: str = os.getenv("APP_TIMEZONE", "Asia/Ho_Chi_Minh")

    def require_telegram(self) -> None:
        missing = []
        if not self.telegram_bot_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not self.telegram_channel:
            missing.append("TELEGRAM_CHANNEL")
        if missing:
            raise RuntimeError("Missing required .env values: " + ", ".join(missing))

settings = Settings()
