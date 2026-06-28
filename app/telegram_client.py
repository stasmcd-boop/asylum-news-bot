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

    def send_photo(self, image_url: str, caption: str = "") -> dict:
        response = requests.post(
            f"{self.base_url}/sendPhoto",
            json={
                "chat_id": self.channel,
                "photo": image_url,
                "caption": caption[:1024],
                "parse_mode": "HTML",
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
