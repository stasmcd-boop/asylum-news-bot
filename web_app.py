from html import escape
from urllib.parse import quote

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

from app.bot_runner import build_daily_summary_text, build_post, collect_new_items, publish_new_items
from app.config import settings
from app.dashboard import dashboard_stats, importance_class
from app.local_state import LocalState
from app.source_registry import enabled_sources
from app.sources import fetch_all_sources
from app.telegram_client import TelegramClient
from app.version import APP_VERSION, RELEASE_NOTES

app = FastAPI(title="Asylum Intelligence")


def page(title: str, body: str, active: str = "dashboard") -> str:
    menu = [
        ("dashboard", "/", "Dashboard"),
        ("drafts", "/check", "Черновики"),
        ("published", "/published", "Опубликовано"),
        ("sources", "/sources", "Источники"),
        ("collector", "/collector", "Collector 2.0"),
        ("summary", "/daily-summary", "Daily summary"),
        ("health", "/health", "Health"),
    ]
    nav = "".join(
        f'<a class="nav {"active" if key == active else ""}" href="{href}">{label}</a>'
        for key, href, label in menu
    )
    return f"""
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{ --bg:#0b1020; --panel:#111827; --panel2:#0f172a; --line:#263244; --text:#e5e7eb; --muted:#94a3b8; --blue:#2563eb; --red:#dc2626; --orange:#d97706; --green:#16a34a; }}
    * {{ box-sizing:border-box; }}
    body {{ font-family:-apple-system,BlinkMacSystemFont,Inter,Segoe UI,sans-serif; background:var(--bg); color:var(--text); margin:0; }}
    .layout {{ display:grid; grid-template-columns:260px 1fr; min-height:100vh; }}
    aside {{ background:#070b16; border-right:1px solid var(--line); padding:24px 18px; position:sticky; top:0; height:100vh; }}
    main {{ padding:30px; }}
    .brand {{ font-size:20px; font-weight:800; margin-bottom:6px; }}
    .tagline {{ color:var(--muted); font-size:13px; margin-bottom:28px; }}
    .nav {{ display:block; color:var(--muted); text-decoration:none; padding:12px 14px; border-radius:12px; margin:4px 0; }}
    .nav:hover,.nav.active {{ background:#172033; color:#fff; }}
    .top {{ display:flex; justify-content:space-between; gap:16px; align-items:flex-start; margin-bottom:24px; }}
    h1 {{ margin:0; font-size:30px; }}
    h2 {{ margin:0 0 12px; }}
    .muted {{ color:var(--muted); }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:16px; }}
    .card {{ background:var(--panel); border:1px solid var(--line); border-radius:18px; padding:20px; margin:16px 0; }}
    .metric {{ font-size:34px; font-weight:800; margin:4px 0; }}
    .pill {{ display:inline-flex; align-items:center; gap:6px; border-radius:999px; padding:6px 10px; background:#1f2937; color:#d1d5db; font-size:13px; margin:3px; }}
    .danger {{ background:rgba(220,38,38,.16); color:#fecaca; border:1px solid rgba(220,38,38,.35); }}
    .warning {{ background:rgba(217,119,6,.16); color:#fed7aa; border:1px solid rgba(217,119,6,.35); }}
    .success {{ background:rgba(22,163,74,.16); color:#bbf7d0; border:1px solid rgba(22,163,74,.35); }}
    a.button,button {{ display:inline-block; background:var(--blue); color:white; padding:11px 15px; border-radius:12px; text-decoration:none; border:0; margin:6px 6px 6px 0; cursor:pointer; font-size:15px; }}
    a.secondary,button.secondary {{ background:#374151; }}
    button.warn,a.warn {{ background:var(--orange); }}
    pre {{ white-space:pre-wrap; background:#020617; border-radius:12px; padding:16px; overflow:auto; border:1px solid var(--line); }}
    textarea {{ width:100%; min-height:520px; background:#020617; color:var(--text); border:1px solid var(--line); border-radius:12px; padding:16px; font-size:15px; line-height:1.45; }}
    input {{ width:100%; background:#020617; color:var(--text); border:1px solid var(--line); border-radius:12px; padding:12px; }}
    .draft {{ border-left:5px solid #64748b; }}
    .draft.danger {{ border-left-color:var(--red); background:var(--panel); }}
    .draft.warning {{ border-left-color:var(--orange); background:var(--panel); }}
    .draft.success {{ border-left-color:var(--green); background:var(--panel); }}
    @media (max-width: 820px) {{ .layout {{ grid-template-columns:1fr; }} aside {{ position:relative; height:auto; }} main {{ padding:18px; }} }}
  </style>
</head>
<body>
  <div class="layout">
    <aside>
      <div class="brand">Asylum Intelligence</div>
      <div class="tagline">{escape(APP_VERSION)}</div>
      {nav}
    </aside>
    <main>{body}</main>
  </div>
</body>
</html>
"""


def find_item_by_url(url: str):
    for item in fetch_all_sources():
        if item.url == url:
            return item
    return None


@app.get("/", response_class=HTMLResponse)
def home():
    stats = dashboard_stats()
    source_rows = "".join(f'<span class="pill">{escape(name)}: {count}</span>' for name, count in stats["sources"].most_common(8)) or '<span class="muted">Нет данных</span>'
    category_rows = "".join(f'<span class="pill">{escape(name)}: {count}</span>' for name, count in stats["categories"].most_common(8)) or '<span class="muted">Нет данных</span>'
    release_rows = "".join(f'<li>{escape(note)}</li>' for note in stats["release_notes"])
    body = f"""
    <div class="top">
      <div>
        <h1>Dashboard</h1>
        <p class="muted">Версия: <b>{escape(stats['version'])}</b> · Последнее обновление: {escape(stats['generated_at'])}</p>
      </div>
      <div>
        <a class="button" href="/check">Открыть черновики</a>
        <a class="button secondary" href="/collector">Collector status</a>
      </div>
    </div>

    <div class="card">
      <h2>Что изменилось в последнем релизе</h2>
      <ul>{release_rows}</ul>
    </div>

    <div class="grid">
      <div class="card"><div class="muted">Подключено источников</div><div class="metric">{stats['registered_sources_count']}</div></div>
      <div class="card"><div class="muted">Всего найдено</div><div class="metric">{stats['total_found']}</div></div>
      <div class="card"><div class="muted">Свежие 60 дней</div><div class="metric">{stats['fresh_60']}</div></div>
      <div class="card"><div class="muted">Ожидают проверки</div><div class="metric">{stats['pending']}</div></div>
    </div>

    <div class="grid">
      <div class="card">
        <h2>Сервисы</h2>
        <p><span class="pill {'success' if stats['telegram_online'] else 'danger'}">Telegram {'online' if stats['telegram_online'] else 'not configured'}</span></p>
        <p><span class="pill {'warning' if stats['openai_configured'] else 'danger'}">OpenAI {'configured' if stats['openai_configured'] else 'not configured'}</span></p>
      </div>
      <div class="card"><h2>Источники с найденными материалами</h2>{source_rows}</div>
      <div class="card"><h2>Категории</h2>{category_rows}</div>
    </div>
    """
    return page("Dashboard", body, active="dashboard")


@app.get("/health")
def health():
    return {
        "ok": True,
        "version": APP_VERSION,
        "telegram_configured": bool(settings.telegram_bot_token and settings.telegram_channel),
        "openai_configured": bool(settings.openai_api_key and not settings.openai_api_key.startswith("paste_")),
        "sources_count": len(enabled_sources()),
    }


@app.get("/collector", response_class=HTMLResponse)
def collector():
    stats = dashboard_stats()
    rows = []
    for source in stats["registered_sources"]:
        found = stats["sources"].get(source.name, 0)
        fresh = stats["fresh_sources"].get(source.name, 0)
        rows.append(f"""
        <div class="card">
          <h2>{escape(source.name)}</h2>
          <p><span class="pill">type: {escape(source.type)}</span><span class="pill">priority: {source.priority}</span><span class="pill">group: {escape(source.group)}</span></p>
          <p>Всего найдено: <b>{found}</b> · Свежие 60 дней: <b>{fresh}</b></p>
          <p class="muted">{escape(source.url or 'Federal Register API')}</p>
        </div>
        """)
    body = f"<h1>Collector 2.0</h1><p class='muted'>Версия: {escape(APP_VERSION)}</p>" + "".join(rows)
    return page("Collector", body, active="collector")


@app.get("/api/news")
def api_news():
    items = fetch_all_sources()
    return [
        {"source": item.source, "title": item.title, "url": item.url, "published_at": item.published_at.isoformat() if item.published_at else None, "category": item.category, "importance": item.importance}
        for item in items
    ]


@app.get("/check", response_class=HTMLResponse)
def check():
    items = collect_new_items(limit=20, days=60)
    header = "<div class='top'><div><h1>Черновики</h1><p class='muted'>Свежие неопубликованные материалы за последние 60 дней</p></div><a class='button secondary' href='/'>Dashboard</a></div>"
    if not items:
        return page("Черновики", header + "<div class='card'><p>Новых свежих неопубликованных материалов нет.</p></div>", active="drafts")
    cards = []
    for item in items:
        date = item.published_at.date().isoformat() if item.published_at else "no-date"
        cls = importance_class(item.importance)
        cards.append(f"""
        <div class="card draft {cls}">
          <div><span class="pill {cls}">{escape(item.importance)}</span><span class="pill">{escape(item.category)}</span><span class="pill">{escape(item.source)}</span></div>
          <h2>{escape(item.title)}</h2>
          <p class="muted">Дата: {escape(date)}</p>
          <p><a href="{escape(item.url)}" target="_blank">Открыть официальный источник</a></p>
          <a class="button" href="/edit?url={quote(item.url)}">Открыть редактор</a>
        </div>
        """)
    return page("Черновики", header + "".join(cards), active="drafts")


@app.get("/edit", response_class=HTMLResponse)
def edit(url: str):
    item = find_item_by_url(url)
    if not item:
        return page("Not found", "<h1>Материал не найден</h1><a class='button secondary' href='/check'>Назад</a>", active="drafts")
    draft = build_post(item, use_ai=True)
    date = item.published_at.date().isoformat() if item.published_at else "no-date"
    body = f"""
    <div class="top"><div><h1>Редактор</h1><p class="muted">{escape(item.source)} | {escape(date)} | {escape(item.category)} | {escape(item.importance)}</p></div><a class="button secondary" href="/check">Назад</a></div>
    <div class="grid">
      <div class="card"><h2>Источник</h2><p>{escape(item.title)}</p><p><a href="{escape(item.url)}" target="_blank">Открыть оригинал</a></p><pre>{escape((item.summary or 'Краткое описание отсутствует')[:1200])}</pre></div>
      <div class="card"><h2>Предпросмотр Telegram</h2><pre>{escape(draft)}</pre></div>
    </div>
    <div class="card"><h2>Пост</h2><form method="post" action="/send-edited"><input type="hidden" name="url" value="{escape(item.url)}"><textarea name="text">{escape(draft)}</textarea><br><button class="warn" type="submit">Опубликовать в Telegram</button></form></div>
    """
    return page("Редактор", body, active="drafts")


@app.post("/send-edited", response_class=HTMLResponse)
def send_edited(url: str = Form(...), text: str = Form(...)):
    if not settings.telegram_bot_token or not settings.telegram_channel:
        result = "Telegram не настроен. Проверь переменные окружения в Render."
    else:
        client = TelegramClient(settings.telegram_bot_token, settings.telegram_channel)
        client.send_message(text[:3900])
        LocalState().mark_published(url)
        result = "Пост отправлен в Telegram и помечен как опубликованный."
    body = f"<h1>Готово</h1><a class='button' href='/check'>К черновикам</a><a class='button secondary' href='/'>Dashboard</a><div class='card'><pre>{escape(result)}</pre></div>"
    return page("Sent", body, active="drafts")


@app.get("/published", response_class=HTMLResponse)
def published():
    urls = sorted(LocalState().published_urls)
    rows = "".join(f"<div class='card'><a href='{escape(url)}' target='_blank'>{escape(url)}</a></div>" for url in urls) or "<div class='card'>Пока нет опубликованных URL.</div>"
    return page("Опубликовано", f"<h1>Опубликовано</h1>{rows}", active="published")


@app.get("/sources", response_class=HTMLResponse)
def sources():
    stats = dashboard_stats()
    rows = "".join(f"<div class='card'><h2>{escape(name)}</h2><p class='muted'>Найдено материалов: {count}</p></div>" for name, count in stats["sources"].most_common()) or "<div class='card'>Нет данных по источникам.</div>"
    return page("Источники", f"<h1>Источники</h1>{rows}", active="sources")


@app.get("/publish-offline", response_class=HTMLResponse)
def publish_offline():
    if not settings.telegram_bot_token or not settings.telegram_channel:
        result = "Telegram не настроен."
    else:
        count = publish_new_items(settings.telegram_bot_token, settings.telegram_channel, limit=1, use_ai=False, days=60)
        result = f"Опубликовано: {count}"
    return page("Publish", f"<h1>Публикация</h1><div class='card'><pre>{escape(result)}</pre></div>", active="drafts")


@app.get("/daily-summary", response_class=HTMLResponse)
def daily_summary():
    if not settings.telegram_bot_token or not settings.telegram_channel:
        result = "Telegram не настроен."
    else:
        client = TelegramClient(settings.telegram_bot_token, settings.telegram_channel)
        client.send_message(build_daily_summary_text(days=1))
        result = "Daily summary отправлен в Telegram."
    return page("Daily summary", f"<h1>Daily summary</h1><div class='card'><pre>{escape(result)}</pre></div>", active="summary")


@app.get("/api/pending")
def api_pending():
    items = collect_new_items(limit=20, days=60)
    return [
        {"title": item.title, "url": item.url, "source": item.source, "category": item.category, "importance": item.importance, "published_at": item.published_at.isoformat() if item.published_at else None}
        for item in items
    ]
