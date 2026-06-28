import requests

class TelegramClient:
    def __init__(self, bot_token: str, channel: str) -> None:
        self.bot_token = bot_token
        self.channel = channel
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    def send_message(self, text: str) -> dict:
        response = requests.post(
            f"{self.base_url}/sendMessage",
            json={
                "chat_id": self.channel,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
