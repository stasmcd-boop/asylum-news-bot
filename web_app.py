from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse

from app.bot_runner import build_daily_summary_text, collect_new_items, publish_new_items
from app.config import settings
from app.sources import fetch_all_sources
from app.telegram_client import TelegramClient

app = FastAPI(title="Asylum News Bot")


def page(title: str, body: str) -> str:
    return f"""
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; background:#0f172a; color:#e5e7eb; margin:0; padding:32px; }}
    .wrap {{ max-width: 980px; margin: 0 auto; }}
    .card {{ background:#111827; border:1px solid #374151; border-radius:18px; padding:24px; margin:16px 0; }}
    a.button, button {{ display:inline-block; background:#2563eb; color:white; padding:12px 16px; border-radius:12px; text-decoration:none; border:0; margin:6px 6px 6px 0; cursor:pointer; }}
    a.secondary {{ background:#374151; }}
    pre {{ white-space:pre-wrap; background:#020617; border-radius:12px; padding:16px; overflow:auto; }}
    .muted {{ color:#94a3b8; }}
    .ok {{ color:#86efac; }}
    .warn {{ color:#fcd34d; }}
  </style>
</head>
<body>
  <div class="wrap">
    {body}
  </div>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def home():
    body = """
    <h1>Asylum News Bot</h1>
    <p class="muted">Панель управления Telegram-ботом для иммиграционных новостей США.</p>
    <div class="card">
      <h2>Действия</h2>
      <a class="button" href="/check">Проверить новости</a>
      <a class="button" href="/publish-offline">Опубликовать 1 новость без AI</a>
      <a class="button" href="/daily-summary">Отправить daily summary</a>
      <a class="button secondary" href="/health">Health check</a>
    </div>
    <div class="card">
      <h2>Статус</h2>
      <p>Telegram channel: <b>{channel}</b></p>
      <p>OpenAI: <b>{ai_status}</b></p>
      <p class="muted">Когда OpenAI billing будет подключён, режим AI начнёт работать автоматически через команду publish-latest.</p>
    </div>
    """.format(
        channel=settings.telegram_channel or "not set",
        ai_status="configured" if settings.openai_api_key and not settings.openai_api_key.startswith("paste_") else "not configured",
    )
    return page("Asylum News Bot", body)


@app.get("/health")
def health():
    return {
        "ok": True,
        "telegram_configured": bool(settings.telegram_bot_token and settings.telegram_channel),
        "openai_configured": bool(settings.openai_api_key and not settings.openai_api_key.startswith("paste_")),
    }


@app.get("/api/news")
def api_news():
    items = fetch_all_sources()
    return [
        {
            "source": item.source,
            "title": item.title,
            "url": item.url,
            "published_at": item.published_at.isoformat() if item.published_at else None,
            "category": item.category,
            "importance": item.importance,
        }
        for item in items
    ]


@app.get("/check", response_class=HTMLResponse)
def check():
    items = collect_new_items(limit=10)
    lines = []
    for item in items:
        date = item.published_at.date().isoformat() if item.published_at else "no-date"
        lines.append(f"[{item.importance}] [{item.category}] {date} | {item.source} | {item.title}\n{item.url}")
    text = "\n\n".join(lines) if lines else "Новых неопубликованных материалов нет."
    body = f"""
    <h1>Проверка новостей</h1>
    <a class="button secondary" href="/">Назад</a>
    <div class="card"><pre>{text}</pre></div>
    """
    return page("Check news", body)


@app.get("/publish-offline", response_class=HTMLResponse)
def publish_offline():
    if not settings.telegram_bot_token or not settings.telegram_channel:
        result = "Telegram не настроен. Проверь .env."
    else:
        count = publish_new_items(settings.telegram_bot_token, settings.telegram_channel, limit=1, use_ai=False)
        result = f"Опубликовано: {count}"
    body = f"""
    <h1>Публикация без AI</h1>
    <a class="button secondary" href="/">Назад</a>
    <div class="card"><pre>{result}</pre></div>
    """
    return page("Publish offline", body)


@app.get("/daily-summary", response_class=HTMLResponse)
def daily_summary():
    if not settings.telegram_bot_token or not settings.telegram_channel:
        result = "Telegram не настроен. Проверь .env."
    else:
        client = TelegramClient(settings.telegram_bot_token, settings.telegram_channel)
        client.send_message(build_daily_summary_text())
        result = "Daily summary отправлен в Telegram."
    body = f"""
    <h1>Daily summary</h1>
    <a class="button secondary" href="/">Назад</a>
    <div class="card"><pre>{result}</pre></div>
    """
    return page("Daily summary", body)


@app.get("/api/pending")
def api_pending():
    items = collect_new_items(limit=10)
    return [
        {
            "title": item.title,
            "url": item.url,
            "source": item.source,
            "category": item.category,
            "importance": item.importance,
            "published_at": item.published_at.isoformat() if item.published_at else None,
        }
        for item in items
    ]
