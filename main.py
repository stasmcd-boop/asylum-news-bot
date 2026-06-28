import argparse
from datetime import datetime

from app.config import settings
from app.telegram_client import TelegramClient


def test_telegram() -> None:
    settings.require_telegram()
    client = TelegramClient(settings.telegram_bot_token, settings.telegram_channel)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    text = (
        "✅ <b>Тест Asylum News Bot</b>\n\n"
        "Бот подключен и может публиковать сообщения в канал.\n"
        f"Время запуска: <code>{now}</code>"
    )
    result = client.send_message(text)
    print("Telegram response:", result)


def main() -> None:
    parser = argparse.ArgumentParser(description="Asylum News Bot")
    parser.add_argument(
        "command",
        nargs="?",
        default="test-telegram",
        choices=["test-telegram"],
        help="Command to run",
    )
    args = parser.parse_args()

    if args.command == "test-telegram":
        test_telegram()


if __name__ == "__main__":
    main()
