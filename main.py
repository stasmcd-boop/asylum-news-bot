import argparse
from datetime import datetime

from app.config import settings
from app.database import Database
from app.sources import fetch_all_sources
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


def run_once() -> None:
    print("Fetching news from official sources...")
    items = fetch_all_sources()
    db = Database()

    new_count = 0
    for item in items:
        exists = db.news_exists(item.url) if db.enabled() else False
        if not exists:
            new_count += 1
            db.save_news(item) if db.enabled() else None

        status = "NEW" if not exists else "OLD"
        date = item.published_at.date().isoformat() if item.published_at else "no-date"
        print(f"[{status}] [{item.importance}] [{item.category}] {date} | {item.source} | {item.title}")
        print(f"      {item.url}")

    print(f"\nFound relevant items: {len(items)}")
    print(f"New items saved: {new_count if db.enabled() else 'database disabled'}")
    if not db.enabled():
        print("Supabase is not configured. Add SUPABASE_URL and SUPABASE_SERVICE_KEY to .env to save items.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Asylum News Bot")
    parser.add_argument(
        "command",
        nargs="?",
        default="test-telegram",
        choices=["test-telegram", "run-once"],
        help="Command to run",
    )
    args = parser.parse_args()

    if args.command == "test-telegram":
        test_telegram()
    elif args.command == "run-once":
        run_once()


if __name__ == "__main__":
    main()
