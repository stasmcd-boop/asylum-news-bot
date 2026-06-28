import argparse
from datetime import datetime

from app.ai_editor import AIEditor
from app.bot_runner import build_daily_summary_text, publish_new_items
from app.config import settings
from app.database import Database
from app.sources import fetch_all_sources
from app.telegram_client import TelegramClient


def test_telegram() -> None:
    settings.require_telegram()
    client = TelegramClient(settings.telegram_bot_token, settings.telegram_channel)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    text = "✅ <b>Asylum News Bot</b>\n\nTelegram connected.\n" + f"Time: <code>{now}</code>"
    result = client.send_message(text)
    print("Telegram response:", result)


def test_ai() -> None:
    editor = AIEditor()
    print("AI enabled:", editor.enabled)
    print("Model:", settings.openai_model)
    if not editor.enabled:
        return
    try:
        response = editor.client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": "Reply with one word: OK"}],
            temperature=0,
            max_tokens=20,
        )
        print("AI response:", response.choices[0].message.content)
    except Exception as exc:
        print("AI error:", repr(exc))


def run_once() -> None:
    print("Fetching news from official sources...")
    items = fetch_all_sources()
    db = Database()
    new_count = 0
    for item in items:
        exists = db.news_exists(item.url) if db.enabled() else False
        if not exists:
            new_count += 1
            if db.enabled():
                db.save_news(item)
        status = "NEW" if not exists else "OLD"
        date = item.published_at.date().isoformat() if item.published_at else "no-date"
        print(f"[{status}] [{item.importance}] [{item.category}] {date} | {item.source} | {item.title}")
        print(f"      {item.url}")
    print(f"\nFound relevant items: {len(items)}")
    print(f"New items saved: {new_count if db.enabled() else 'database disabled'}")
    if db.error:
        print(db.error)


def publish_latest() -> None:
    settings.require_telegram()
    publish_new_items(settings.telegram_bot_token, settings.telegram_channel, limit=1, use_ai=True)


def publish_offline() -> None:
    settings.require_telegram()
    publish_new_items(settings.telegram_bot_token, settings.telegram_channel, limit=1, use_ai=False)


def daily_summary() -> None:
    settings.require_telegram()
    client = TelegramClient(settings.telegram_bot_token, settings.telegram_channel)
    result = client.send_message(build_daily_summary_text())
    print("Daily summary sent:", result)


def main() -> None:
    parser = argparse.ArgumentParser(description="Asylum News Bot")
    parser.add_argument(
        "command",
        nargs="?",
        default="test-telegram",
        choices=["test-telegram", "test-ai", "run-once", "publish-latest", "publish-offline", "daily-summary"],
        help="Command to run",
    )
    args = parser.parse_args()
    if args.command == "test-telegram":
        test_telegram()
    elif args.command == "test-ai":
        test_ai()
    elif args.command == "run-once":
        run_once()
    elif args.command == "publish-latest":
        publish_latest()
    elif args.command == "publish-offline":
        publish_offline()
    elif args.command == "daily-summary":
        daily_summary()


if __name__ == "__main__":
    main()
