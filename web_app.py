from html import escape
from urllib.parse import quote

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

from app.bot_runner import build_daily_summary_text, build_post, collect_new_items, publish_new_items
from app.config import settings
from app.dashboard import dashboard_stats, importance_class
from app.draft_store import DraftStore, draft_id_for_url
from app.intelligence import analyze_item
from app.local_state import LocalState
from app.source_registry import enabled_sources
from app.search import filter_items
from app.sources import collect_sources, fetch_all_sources, fetch_source_diagnostics
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
    input, select {{ width:100%; background:#020617; color:var(--text); border:1px solid var(--line); border-radius:12px; padding:12px; }}
    label {{ display:block; color:var(--muted); font-size:14px; }}
    .ok {{ color:#86efac; }}
    .warntext {{ color:#fcd34d; }}
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


def news_payload(item):
    analysis = analyze_item(item)
    return {
        "source": item.source,
        "title": item.title,
        "url": item.url,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "category": item.category,
        "importance": item.importance,
        "urgency": analysis.urgency,
        "affected_groups": analysis.affected_groups,
        "tags": analysis.tags,
    }


def pending_payload(item):
    payload = news_payload(item)
    return {
        "title": payload["title"],
        "url": payload["url"],
        "source": payload["source"],
        "category": payload["category"],
        "importance": payload["importance"],
        "urgency": payload["urgency"],
        "affected_groups": payload["affected_groups"],
        "published_at": payload["published_at"],
    }


def filter_controls(query: str = "", category: str = "", importance: str = "", urgency: str = "") -> str:
    def selected(value: str, current: str) -> str:
        return "selected" if value == current else ""

    return f"""
    <div class="card">
      <form method="get">
        <div class="grid">
          <label>Search
            <input name="q" value="{escape(query)}" placeholder="asylum, TPS, EAD, court">
          </label>
          <label>Category
            <select name="category">
              <option value="">All</option>
              <option value="asylum" {selected("asylum", category)}>Asylum</option>
              <option value="court" {selected("court", category)}>Court</option>
              <option value="ead" {selected("ead", category)}>EAD</option>
              <option value="tps" {selected("tps", category)}>TPS</option>
              <option value="parole" {selected("parole", category)}>Parole</option>
              <option value="deportation" {selected("deportation", category)}>Deportation</option>
              <option value="policy" {selected("policy", category)}>Policy</option>
            </select>
          </label>
          <label>Importance
            <select name="importance">
              <option value="">All</option>
              <option value="important" {selected("important", importance)}>Important</option>
              <option value="medium" {selected("medium", importance)}>Medium</option>
              <option value="info" {selected("info", importance)}>Info</option>
            </select>
          </label>
          <label>Urgency
            <select name="urgency">
              <option value="">All</option>
              <option value="high" {selected("high", urgency)}>High</option>
              <option value="medium" {selected("medium", urgency)}>Medium</option>
              <option value="low" {selected("low", urgency)}>Low</option>
            </select>
          </label>
        </div>
        <button type="submit">Apply filters</button>
        <a class="button secondary" href="/check">Reset</a>
      </form>
    </div>
    """


def draft_filter_controls(query: str = "", category: str = "", urgency: str = "", source: str = "", status: str = "") -> str:
    def selected(value: str, current: str) -> str:
        return "selected" if value == current else ""

    return f"""
    <div class="card">
      <form method="get">
        <div class="grid">
          <label>Search
            <input name="q" value="{escape(query)}" placeholder="title, source, tag">
          </label>
          <label>Source
            <input name="source" value="{escape(source)}" placeholder="USCIS, Federal Register">
          </label>
          <label>Category
            <select name="category">
              <option value="">All</option>
              <option value="asylum" {selected("asylum", category)}>Asylum</option>
              <option value="court" {selected("court", category)}>Court</option>
              <option value="ead" {selected("ead", category)}>EAD</option>
              <option value="tps" {selected("tps", category)}>TPS</option>
              <option value="parole" {selected("parole", category)}>Parole</option>
              <option value="deportation" {selected("deportation", category)}>Deportation</option>
              <option value="policy" {selected("policy", category)}>Policy</option>
            </select>
          </label>
          <label>Urgency
            <select name="urgency">
              <option value="">All</option>
              <option value="high" {selected("high", urgency)}>High</option>
              <option value="medium" {selected("medium", urgency)}>Medium</option>
              <option value="low" {selected("low", urgency)}>Low</option>
            </select>
          </label>
          <label>Status
            <select name="status">
              <option value="">All</option>
              <option value="collected" {selected("collected", status)}>Collected</option>
              <option value="analyzed" {selected("analyzed", status)}>Analyzed</option>
              <option value="draft_ready" {selected("draft_ready", status)}>Draft ready</option>
              <option value="published" {selected("published", status)}>Published</option>
              <option value="ignored" {selected("ignored", status)}>Ignored</option>
            </select>
          </label>
        </div>
        <button type="submit">Apply filters</button>
        <a class="button secondary" href="/drafts">Reset</a>
      </form>
    </div>
    """


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
        <a class="button" href="/drafts">Draft queue</a>
        <a class="button secondary" href="/collector">Collector status</a>
      </div>
    </div>

    <div class="card">
      <h2>Что изменилось в последнем релизе</h2>
      <ul>{release_rows}</ul>
      <p class="muted">Редактор сохраняет структурированные черновики, показывает исходный текст, русское объяснение, изображение и предпросмотр Telegram-поста перед отправкой.</p>
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
def api_news(q: str = "", category: str = "", importance: str = "", urgency: str = ""):
    items = filter_items(collect_sources().items, query=q, category=category, importance=importance, urgency=urgency)
    return [news_payload(item) for item in items]


@app.get("/api/news-basic")
def api_news_basic():
    items = collect_sources().items
    return [
        {"source": item.source, "title": item.title, "url": item.url, "published_at": item.published_at.isoformat() if item.published_at else None, "category": item.category, "importance": item.importance}
        for item in items
    ]


@app.get("/api/diagnostics")
def api_diagnostics():
    diagnostics = fetch_source_diagnostics()
    return [
        {
            "source": item.source,
            "ok": item.ok,
            "fetched": item.fetched,
            "relevant": item.relevant,
            "error": item.error,
        }
        for item in diagnostics
    ]


@app.get("/diagnostics", response_class=HTMLResponse)
def diagnostics():
    rows = []
    for item in fetch_source_diagnostics():
        status = "<span class='ok'>OK</span>" if item.ok else "<span class='warntext'>FAILED</span>"
        detail = item.error or f"Fetched: {item.fetched}; relevant: {item.relevant}"
        rows.append(f"""
        <div class="card">
          <h3>{escape(item.source)} — {status}</h3>
          <p class="muted">{escape(detail)}</p>
        </div>
        """)
    body = "<h1>Collector diagnostics</h1><a class='button secondary' href='/'>Назад</a>" + "".join(rows)
    return page("Collector diagnostics", body)


@app.get("/drafts", response_class=HTMLResponse)
def drafts(q: str = "", category: str = "", urgency: str = "", source: str = "", status: str = ""):
    store = DraftStore()
    store.ingest_items(collect_sources().items)
    rows = []
    for draft in store.list_drafts(query=q, category=category, urgency=urgency, source=source, status=status):
        affected = ", ".join(draft.affected_groups[:3])
        rows.append(f"""
        <div class="card">
          <h3>{escape(draft.title)}</h3>
          <p class="muted">{escape(draft.source)} | {escape(draft.published_at or "no-date")} | {escape(draft.category)} | {escape(draft.status)} | urgency: {escape(draft.urgency)} | impact: {draft.impact_score}</p>
          <p>{escape(draft.russian_summary)}</p>
          <p class="muted">Affected: {escape(affected or "not detected")}</p>
          <p class="muted">Tags: {escape(", ".join(draft.tags))}</p>
          <a class="button" href="/drafts/{escape(draft.id)}">Open draft</a>
          <a class="button secondary" href="{escape(draft.url)}" target="_blank">Source</a>
        </div>
        """)
    body = "<h1>Draft queue</h1><a class='button secondary' href='/'>Назад</a>" + draft_filter_controls(q, category, urgency, source, status)
    body += "".join(rows) or "<div class='card'><p>No drafts match these filters.</p></div>"
    return page("Draft queue", body)


@app.get("/drafts/{draft_id}", response_class=HTMLResponse)
def draft_detail(draft_id: str):
    draft = DraftStore().get(draft_id)
    if not draft:
        return page("Draft not found", "<h1>Draft not found</h1><a class='button secondary' href='/drafts'>Back</a>")
    analysis = draft.analysis
    affected = "".join(f"<li>{escape(group)}</li>" for group in draft.affected_groups)
    actions = "".join(f"<li>{escape(step)}</li>" for step in analysis.get("action_steps_ru", []))
    image = f'<img src="{escape(draft.image_url)}" alt="" style="max-width:100%; border-radius:12px; margin-top:12px;">' if draft.image_url else "<p class='muted'>No image detected yet.</p>"
    body = f"""
    <h1>Draft details</h1>
    <a class="button secondary" href="/drafts">Back to queue</a>
    <a class="button secondary" href="{escape(draft.url)}" target="_blank">Open source</a>
    <div class="card">
      <h2>{escape(draft.title)}</h2>
      <p class="muted">{escape(draft.source)} | {escape(draft.source_type)} | {escape(draft.category)} | {escape(draft.status)}</p>
      <p><b>Publication date:</b> {escape(draft.published_at or "unknown")}</p>
      <p><b>Original URL:</b> <a href="{escape(draft.url)}" target="_blank">{escape(draft.url)}</a></p>
      <p><b>Urgency:</b> {escape(draft.urgency)} | <b>Impact:</b> {draft.impact_score} | <b>Deadline:</b> {escape(analysis.get("deadline", "") or "none")}</p>
      <p><b>Action required:</b> {escape(str(analysis.get("action_required", False)))}</p>
      <p><b>Russian summary:</b> {escape(draft.russian_summary)}</p>
      <p><b>Russian explanation:</b> {escape(draft.russian_explanation)}</p>
      <p><b>Recommended action:</b> {escape(draft.recommended_action)}</p>
      <p><b>Tags:</b> {escape(", ".join(draft.tags))}</p>
      <p><b>Affected groups</b></p>
      <ul>{affected}</ul>
      <p><b>Action steps</b></p>
      <ul>{actions}</ul>
    </div>
    <div class="card">
      <h2>Source text</h2>
      <pre>{escape(draft.extracted_text or "Full text was not extracted. Use the source link above.")}</pre>
    </div>
    <div class="card">
      <h2>Image</h2>
      {image}
    </div>
    <div class="card">
      <h2>Draft preview</h2>
      <form method="post" action="/drafts/{escape(draft.id)}">
        <label>Image URL
          <input name="image_url" value="{escape(draft.image_url)}" placeholder="https://...">
        </label>
        <textarea name="text">{escape(draft.telegram_text)}</textarea>
        <br>
        <button type="submit" name="action" value="save">Save draft</button>
        <button class="warn" type="submit" name="action" value="publish">Publish to Telegram</button>
        <button type="submit" name="action" value="ignore">Ignore</button>
      </form>
    </div>
    """
    return page("Draft details", body)


@app.post("/drafts/{draft_id}", response_class=HTMLResponse)
def update_draft(draft_id: str, text: str = Form(...), action: str = Form(...), image_url: str = Form("")):
    store = DraftStore()
    if action == "publish":
        if not settings.telegram_bot_token or not settings.telegram_channel:
            result = "Telegram не настроен. Проверь .env."
            store.update(draft_id, draft_text=text, image_url=image_url)
        else:
            draft = store.update(draft_id, draft_text=text, image_url=image_url)
            if not draft:
                return page("Draft not found", "<h1>Draft not found</h1><a class='button secondary' href='/drafts'>Back</a>")
            TelegramClient(settings.telegram_bot_token, settings.telegram_channel).send_message(text[:3900])
            LocalState().mark_published(draft.url)
            store.update(draft_id, draft_text=text, status="published", image_url=image_url)
            result = "Draft published to Telegram."
    elif action == "ignore":
        store.update(draft_id, draft_text=text, status="ignored", image_url=image_url)
        result = "Draft marked as ignored."
    else:
        store.update(draft_id, draft_text=text, status="edited", image_url=image_url)
        result = "Draft saved."
    body = f"""
    <h1>{escape(result)}</h1>
    <a class="button" href="/drafts/{escape(draft_id)}">Back to draft</a>
    <a class="button secondary" href="/drafts">Draft queue</a>
    """
    return page("Draft updated", body)


@app.get("/check", response_class=HTMLResponse)
def check(q: str = "", category: str = "", importance: str = "", urgency: str = ""):
    items = filter_items(
        collect_new_items(limit=30, days=60),
        query=q,
        category=category,
        importance=importance,
        urgency=urgency,
    )[:10]
    controls = filter_controls(q, category, importance, urgency)
    header = "<div class='top'><div><h1>Черновики</h1><p class='muted'>Свежие неопубликованные материалы за последние 60 дней</p></div><a class='button secondary' href='/'>Dashboard</a></div>"
    if not items:
        return page("Черновики", header + controls + "<div class='card'><p>Новых свежих неопубликованных материалов нет.</p></div>", active="drafts")

    cards = []
    for item in items:
        date = item.published_at.date().isoformat() if item.published_at else "no-date"
        analysis = analyze_item(item)
        cls = importance_class(item.importance)
        cards.append(f"""
        <div class="card draft {cls}">
          <div><span class="pill {cls}">{escape(item.importance)}</span><span class="pill">{escape(item.category)}</span><span class="pill">urgency: {escape(analysis.urgency)}</span><span class="pill">{escape(item.source)}</span></div>
          <h2>{escape(item.title)}</h2>
          <p class="muted">Дата: {escape(date)}</p>
          <p class="muted">Кого касается: {escape(", ".join(analysis.affected_groups))}</p>
          <p><a href="{escape(item.url)}" target="_blank">Открыть источник</a></p>
          <a class="button" href="/edit?url={quote(item.url)}">Открыть редактор</a>
        </div>
        """)
    return page("Черновики", header + controls + "".join(cards), active="drafts")


@app.get("/edit", response_class=HTMLResponse)
def edit(url: str):
    item = find_item_by_url(url)
    if not item:
        return page("Not found", "<h1>Материал не найден</h1><a class='button secondary' href='/check'>Назад</a>", active="drafts")
    store = DraftStore()
    store.ingest_items([item])
    draft_id = draft_id_for_url(item.url)
    stored = store.get(draft_id)
    draft = stored.telegram_text if stored else build_post(item, use_ai=True)
    date = item.published_at.date().isoformat() if item.published_at else "no-date"
    body = f"""
    <div class="top"><div><h1>Редактор</h1><p class="muted">{escape(item.source)} | {escape(date)} | {escape(item.category)} | {escape(item.importance)}</p></div><a class="button secondary" href="/check">Назад</a></div>
    <a class="button secondary" href="/drafts/{escape(draft_id)}">Открыть в Draft queue</a>
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
        DraftStore().update_by_url(url, draft_text=text, status="published")
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
    body = """
    <h1>Публикация без редактирования</h1>
    <a class="button secondary" href="/">Назад</a>
    <div class="card">
      <p>Будет опубликован один свежий материал из очереди. Автоматическая публикация без подтверждения отключена.</p>
      <form method="post" action="/publish-offline">
        <button class="warn" type="submit">Подтвердить публикацию в Telegram</button>
      </form>
    </div>
    """
    return page("Publish offline", body)


@app.post("/publish-offline", response_class=HTMLResponse)
def publish_offline_confirmed():
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
def api_pending(q: str = "", category: str = "", importance: str = "", urgency: str = ""):
    items = filter_items(
        collect_new_items(limit=30, days=60),
        query=q,
        category=category,
        importance=importance,
        urgency=urgency,
    )[:10]
    return [pending_payload(item) for item in items]


@app.get("/api/pending-basic")
def api_pending_basic():
    items = collect_new_items(limit=10, days=60)
    return [
        {"title": item.title, "url": item.url, "source": item.source, "category": item.category, "importance": item.importance, "published_at": item.published_at.isoformat() if item.published_at else None}
        for item in items
    ]
