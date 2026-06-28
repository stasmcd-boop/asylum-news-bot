from html import escape
from urllib.parse import quote

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

from app.bot_runner import build_daily_summary_text, build_post, collect_new_items, publish_new_items
from app.config import settings
from app.local_state import LocalState
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
  <title>{escape(title)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; background:#0f172a; color:#e5e7eb; margin:0; padding:32px; }}
    .wrap {{ max-width: 1080px; margin: 0 auto; }}
    .card {{ background:#111827; border:1px solid #374151; border-radius:18px; padding:24px; margin:16px 0; }}
    a.button, button {{ display:inline-block; background:#2563eb; color:white; padding:12px 16px; border-radius:12px; text-decoration:none; border:0; margin:6px 6px 6px 0; cursor:pointer; font-size:15px; }}
    a.secondary {{ background:#374151; }}
    a.warn, button.warn {{ background:#b45309; }}
    pre {{ white-space:pre-wrap; background:#020617; border-radius:12px; padding:16px; overflow:auto; }}
    textarea {{ width:100%; min-height:520px; background:#020617; color:#e5e7eb; border:1px solid #374151; border-radius:12px; padding:16px; font-size:15px; line-height:1.45; }}
    input {{ width:100%; background:#020617; color:#e5e7eb; border:1px solid #374151; border-radius:12px; padding:12px; }}
    .muted {{ color:#94a3b8; }}
    .ok {{ color:#86efac; }}
    .warntext {{ color:#fcd34d; }}
    .grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:16px; }}
  </style>
</head>
<body><div class="wrap">{body}</div></body>
</html>
"""


def find_item_by_url(url: str):
    for item in fetch_all_sources():
        if item.url == url:
            return item
    return None


@app.get("/", response_class=HTMLResponse)
def home():
    body = """
    <h1>Asylum News Bot</h1>
    <p class="muted">Панель управления Telegram-ботом для иммиграционных новостей США.</p>
    <div class="card">
      <h2>Действия</h2>
      <a class="button" href="/check">Свежие новости и черновики</a>
      <a class="button" href="/publish-offline">Опубликовать 1 свежую без редактирования</a>
      <a class="button" href="/daily-summary">Отправить daily summary</a>
      <a class="button secondary" href="/health">Health check</a>
    </div>
    <div class="card">
      <h2>Статус</h2>
      <p>Telegram channel: <b>{channel}</b></p>
      <p>OpenAI: <b>{ai_status}</b></p>
      <p>Fresh filter: <b>последние 60 дней для публикаций; 1 день для daily summary</b></p>
      <p class="muted">Пока OpenAI billing не подключён, редактор формирует осторожный русский шаблон. Текст можно вручную поправить перед отправкой.</p>
    </div>
    """.format(
        channel=escape(settings.telegram_channel or "not set"),
        ai_status="configured, no quota yet" if settings.openai_api_key and not settings.openai_api_key.startswith("paste_") else "not configured",
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
    items = collect_new_items(limit=10, days=60)
    if not items:
        body = """
        <h1>Свежие новости</h1>
        <a class="button secondary" href="/">Назад</a>
        <div class="card"><p>Новых свежих неопубликованных материалов за последние 60 дней нет.</p></div>
        """
        return page("Check news", body)

    cards = []
    for item in items:
        date = item.published_at.date().isoformat() if item.published_at else "no-date"
        cards.append(f"""
        <div class="card">
          <h3>{escape(item.title)}</h3>
          <p class="muted">{escape(item.source)} | {escape(date)} | {escape(item.importance)} | {escape(item.category)}</p>
          <p><a href="{escape(item.url)}" target="_blank">Открыть источник</a></p>
          <a class="button" href="/edit?url={quote(item.url)}">Редактировать и отправить</a>
        </div>
        """)
    body = "<h1>Свежие новости и черновики</h1><a class='button secondary' href='/'>Назад</a>" + "".join(cards)
    return page("Check news", body)


@app.get("/edit", response_class=HTMLResponse)
def edit(url: str):
    item = find_item_by_url(url)
    if not item:
        return page("Not found", "<h1>Материал не найден</h1><a class='button secondary' href='/check'>Назад</a>")
    draft = build_post(item, use_ai=True)
    body = f"""
    <h1>Редактирование поста</h1>
    <a class="button secondary" href="/check">Назад</a>
    <div class="card">
      <p class="muted">Источник: {escape(item.source)} | URL: <a href="{escape(item.url)}" target="_blank">открыть</a></p>
      <form method="post" action="/send-edited">
        <input type="hidden" name="url" value="{escape(item.url)}">
        <textarea name="text">{escape(draft)}</textarea>
        <br>
        <button class="warn" type="submit">Отправить отредактированный пост в Telegram</button>
      </form>
    </div>
    """
    return page("Edit post", body)


@app.post("/send-edited", response_class=HTMLResponse)
def send_edited(url: str = Form(...), text: str = Form(...)):
    if not settings.telegram_bot_token or not settings.telegram_channel:
        result = "Telegram не настроен. Проверь .env."
    else:
        client = TelegramClient(settings.telegram_bot_token, settings.telegram_channel)
        client.send_message(text[:3900])
        LocalState().mark_published(url)
        result = "Пост отправлен в Telegram и помечен как опубликованный."
    body = f"""
    <h1>Готово</h1>
    <a class="button secondary" href="/check">К списку новостей</a>
    <a class="button secondary" href="/">На главную</a>
    <div class="card"><pre>{escape(result)}</pre></div>
    """
    return page("Sent", body)


@app.get("/publish-offline", response_class=HTMLResponse)
def publish_offline():
    if not settings.telegram_bot_token or not settings.telegram_channel:
        result = "Telegram не настроен. Проверь .env."
    else:
        count = publish_new_items(settings.telegram_bot_token, settings.telegram_channel, limit=1, use_ai=False, days=60)
        result = f"Опубликовано: {count}"
    body = f"""
    <h1>Публикация без редактирования</h1>
    <a class="button secondary" href="/">Назад</a>
    <div class="card"><pre>{escape(result)}</pre></div>
    """
    return page("Publish offline", body)


@app.get("/daily-summary", response_class=HTMLResponse)
def daily_summary():
    if not settings.telegram_bot_token or not settings.telegram_channel:
        result = "Telegram не настроен. Проверь .env."
    else:
        client = TelegramClient(settings.telegram_bot_token, settings.telegram_channel)
        client.send_message(build_daily_summary_text(days=1))
        result = "Daily summary отправлен в Telegram."
    body = f"""
    <h1>Daily summary</h1>
    <a class="button secondary" href="/">Назад</a>
    <div class="card"><pre>{escape(result)}</pre></div>
    """
    return page("Daily summary", body)


@app.get("/api/pending")
def api_pending():
    items = collect_new_items(limit=10, days=60)
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
