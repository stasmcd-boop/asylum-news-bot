from html import escape
from urllib.parse import quote

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

from app.bot_runner import build_daily_summary_text, build_post, collect_new_items, publish_new_items
from app.config import settings
from app.dashboard import dashboard_stats as collector_dashboard_stats, importance_class
from app.draft_store import DraftStore, draft_id_for_url
from app.intelligence import analyze_item
from app.local_state import LocalState
from app.source_registry import enabled_sources
from app.newsroom import dashboard_stats as newsroom_dashboard_stats, related_drafts, search_drafts, timeline_for_category, topic_counts
from app.search import filter_items
from app.sources import collect_sources, fetch_all_sources, fetch_source_diagnostics
from app.telegram_client import TelegramClient
from app.version import APP_VERSION, RELEASE_NOTES

app = FastAPI(title="Asylum Intelligence")


def page(title: str, body: str, active: str = "dashboard", description: str = "") -> str:
    meta_description = description or "Russian-language US immigration intelligence, analysis, timelines, and editorial publishing workflow."
    return f"""
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <meta name="description" content="{escape(meta_description)}">
  <style>
    * {{ box-sizing:border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; background:#f5f7fb; color:#111827; margin:0; padding:0; }}
    .wrap {{ max-width: 1360px; margin: 0 auto; padding:28px; }}
    .topbar {{ display:flex; align-items:center; justify-content:space-between; gap:16px; margin-bottom:22px; }}
    .brand {{ font-weight:800; font-size:22px; }}
    .nav a {{ color:#334155; margin-left:14px; text-decoration:none; font-weight:600; }}
    .card {{ background:#ffffff; border:1px solid #e5e7eb; border-radius:8px; padding:20px; margin:14px 0; box-shadow:0 1px 2px rgba(15,23,42,.04); }}
    .metric {{ background:#ffffff; border:1px solid #e5e7eb; border-radius:8px; padding:16px; }}
    .metric b {{ display:block; font-size:28px; margin-top:6px; }}
    a.button, button {{ display:inline-block; background:#1d4ed8; color:white; padding:10px 14px; border-radius:8px; text-decoration:none; border:0; margin:6px 6px 6px 0; cursor:pointer; font-size:14px; font-weight:700; }}
    a.secondary, button.secondary {{ background:#475569; }}
    a.warn, button.warn {{ background:#b45309; }}
    pre {{ white-space:pre-wrap; background:#f8fafc; border:1px solid #e5e7eb; border-radius:8px; padding:16px; overflow:auto; color:#0f172a; }}
    textarea {{ width:100%; min-height:420px; background:#ffffff; color:#111827; border:1px solid #cbd5e1; border-radius:8px; padding:16px; font-size:15px; line-height:1.5; }}
    input, select {{ width:100%; background:#ffffff; color:#111827; border:1px solid #cbd5e1; border-radius:8px; padding:11px; }}
    label {{ display:block; color:#475569; font-size:13px; font-weight:700; }}
    img.thumb {{ width:160px; height:108px; object-fit:cover; border-radius:8px; background:#e5e7eb; }}
    .muted {{ color:#64748b; }}
    .ok {{ color:#047857; }}
    .warntext {{ color:#b45309; }}
    .grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap:14px; }}
    .queue-card {{ display:grid; grid-template-columns: 180px 1fr; gap:18px; align-items:start; }}
    .editor-grid {{ display:grid; grid-template-columns: minmax(0, 1fr) minmax(340px, .8fr); gap:18px; }}
    .pill {{ display:inline-block; background:#eef2ff; color:#3730a3; border-radius:999px; padding:5px 9px; margin:3px 4px 3px 0; font-size:12px; font-weight:700; }}
    .top {{ display:flex; justify-content:space-between; gap:16px; align-items:flex-start; margin-bottom:20px; }}
    .danger {{ background:#fee2e2; color:#991b1b; }}
    .warning {{ background:#ffedd5; color:#9a3412; }}
    .success {{ background:#dcfce7; color:#166534; }}
    @media (max-width: 820px) {{ .queue-card, .editor-grid, .topbar {{ display:block; }} img.thumb {{ width:100%; height:auto; }} }}
  </style>
</head>
<body><div class="wrap"><div class="topbar"><div class="brand">Immigration Intelligence</div><div class="nav"><a href="/">Dashboard</a><a href="/newsroom">Newsroom</a><a href="/search">Search</a><a href="/archive">Public archive</a></div></div>{body}</div></body>
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


def ensure_publishable_text(text: str, source_url: str) -> str:
    result = text.strip()
    if source_url and source_url not in result:
        result += f"\n\n<b>Официальный источник</b>\n{source_url}"
    if "Информационный пост, не юридическая консультация." not in result:
        result += "\n\nИнформационный пост, не юридическая консультация."
    return result[:3900]


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
              <option value="edited" {selected("edited", status)}>Edited</option>
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
    store = DraftStore()
    store.ingest_items(collect_sources().items)
    diagnostics = fetch_source_diagnostics()
    stats = newsroom_dashboard_stats(store.list_drafts(), diagnostics)
    release_rows = "".join(f"<li>{escape(note)}</li>" for note in RELEASE_NOTES)
    body = """
    <h1>Editorial Dashboard</h1>
    <p class="muted">Primary workspace for Russian-language US immigration intelligence. Telegram is an output channel.</p>
    <div class="grid">
      <div class="metric">New news<b>{new_news}</b></div>
      <div class="metric">Important<b>{important_news}</b></div>
      <div class="metric">Awaiting review<b>{awaiting_review}</b></div>
      <div class="metric">Published today<b>{published_today}</b></div>
      <div class="metric">Ignored<b>{ignored}</b></div>
      <div class="metric">AI processed<b>{ai_processed}</b></div>
      <div class="metric">Collector health<b>{collector_health}</b></div>
    </div>
    <div class="card">
      <h2>Workspace</h2>
      <a class="button" href="/newsroom">Open newsroom</a>
      <a class="button secondary" href="/search">Global search</a>
      <a class="button secondary" href="/timelines">Topic timelines</a>
      <a class="button secondary" href="/diagnostics">Collector diagnostics</a>
      <a class="button" href="/daily-summary">Отправить daily summary</a>
    </div>

    <div class="card">
      <h2>Статус</h2>
      <p>Telegram channel: <b>{channel}</b></p>
      <p>OpenAI: <b>{ai_status}</b></p>
      <p>Version: <b>{version}</b></p>
      <ul>{release_rows}</ul>
      <p class="muted">Редактор сохраняет структурированные черновики, показывает исходный текст, русское объяснение, изображение и предпросмотр Telegram-поста перед отправкой.</p>
    </div>
    """.format(
        **stats,
        channel=escape(settings.telegram_channel or "not set"),
        ai_status="configured" if settings.openai_api_key and not settings.openai_api_key.startswith("paste_") else "offline fallback",
        version=escape(APP_VERSION),
        release_rows=release_rows,
    )
    return page("Immigration Intelligence", body)


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
    stats = collector_dashboard_stats()
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


@app.get("/newsroom", response_class=HTMLResponse)
def newsroom(q: str = "", category: str = "", urgency: str = "", source: str = "", status: str = ""):
    return drafts(q=q, category=category, urgency=urgency, source=source, status=status)


@app.get("/drafts", response_class=HTMLResponse)
def drafts(q: str = "", category: str = "", urgency: str = "", source: str = "", status: str = ""):
    store = DraftStore()
    store.ingest_items(collect_sources().items)
    rows = []
    for draft in store.list_drafts(query=q, category=category, urgency=urgency, source=source, status=status):
        affected = ", ".join(draft.affected_groups[:3])
        image = f'<img class="thumb" src="{escape(draft.image_url)}" alt="">' if draft.image_url else '<div class="thumb"></div>'
        can_publish = draft.status not in {"published", "ignored"} and draft.impact_score >= 35 and draft.telegram_text.strip()
        publish_button = '<button class="warn" type="submit" name="action" value="publish">Publish</button>' if can_publish else '<button class="secondary" type="button" disabled>Publish</button>'
        rows.append(f"""
        <div class="card queue-card">
          <div>{image}</div>
          <div>
            <h3>{escape(draft.russian_summary or draft.title)}</h3>
            <p class="muted">{escape(draft.title)}</p>
            <p class="muted">{escape(draft.source)} | {escape(draft.published_at or "no-date")} | {escape(draft.category)} | {escape(draft.urgency)} | impact {draft.impact_score} | confidence {escape(draft.confidence)} | {escape(draft.status)}</p>
            <p>{escape(draft.russian_explanation or draft.russian_summary)}</p>
            <p class="muted">Affected: {escape(affected or "not detected")}</p>
            <p>{''.join(f'<span class="pill">{escape(tag)}</span>' for tag in draft.tags[:8])}</p>
            <a class="button" href="/drafts/{escape(draft.id)}">Open</a>
            <a class="button secondary" href="/drafts/{escape(draft.id)}">Edit</a>
            <form method="post" action="/drafts/{escape(draft.id)}" style="display:inline">
              <input type="hidden" name="text" value="{escape(draft.telegram_text)}">
              <input type="hidden" name="image_url" value="{escape(draft.image_url)}">
              <button type="submit" name="action" value="ignore">Ignore</button>
              {publish_button}
            </form>
          </div>
        </div>
        """)
    body = "<h1>Newsroom</h1><p class='muted'>Editorial queue for intelligence review, editing, and publishing.</p>" + draft_filter_controls(q, category, urgency, source, status)
    body += "".join(rows) or "<div class='card'><p>No drafts match these filters.</p></div>"
    return page("Newsroom", body)


@app.get("/drafts/{draft_id}", response_class=HTMLResponse)
def draft_detail(draft_id: str):
    draft = DraftStore().get(draft_id)
    if not draft:
        return page("Draft not found", "<h1>Draft not found</h1><a class='button secondary' href='/drafts'>Back</a>")
    analysis = draft.analysis
    affected = "".join(f"<li>{escape(group)}</li>" for group in draft.affected_groups)
    not_affected = "".join(f"<li>{escape(group)}</li>" for group in draft.not_affected_groups)
    actions = "".join(f"<li>{escape(step)}</li>" for step in analysis.get("action_steps_ru", []))
    image = f'<img src="{escape(draft.image_url)}" alt="" style="max-width:100%; border-radius:12px; margin-top:12px;">' if draft.image_url else "<p class='muted'>No image detected yet.</p>"
    all_drafts = DraftStore().list_drafts()
    related = related_drafts(draft, all_drafts)
    related_html = "".join(f'<li><a href="/drafts/{escape(item.id)}">{escape(item.title)}</a> <span class="muted">{escape(item.source)} | {escape(item.published_at or "")}</span></li>' for item in related) or "<li>No related collected news yet.</li>"
    body = f"""
    <h1>CMS Editor</h1>
    <a class="button secondary" href="/newsroom">Back to newsroom</a>
    <a class="button secondary" href="{escape(draft.url)}" target="_blank">Open source</a>
    <div class="editor-grid">
      <div class="card">
        <h2>Original article</h2>
        <h3>{escape(draft.title)}</h3>
        <p class="muted">{escape(draft.source)} | {escape(draft.source_type)} | {escape(draft.published_at or "unknown")}</p>
        {image}
        <p><b>Source URL:</b> <a href="{escape(draft.url)}" target="_blank">{escape(draft.url)}</a></p>
        <pre>{escape(draft.extracted_text or "Full text was not extracted. Use the source link above.")}</pre>
      </div>
      <div class="card">
        <h2>AI analysis</h2>
        <p><b>Russian summary:</b> {escape(draft.russian_summary)}</p>
        <p><b>Plain explanation:</b> {escape(draft.russian_explanation)}</p>
        <p><b>Urgency:</b> {escape(draft.urgency)} | <b>Impact:</b> {draft.impact_score} | <b>Confidence:</b> {escape(draft.confidence)}</p>
        <p><b>Deadline:</b> {escape(draft.deadline or "none")} | <b>Effective date:</b> {escape(draft.effective_date or "none")}</p>
        <p><b>Action required:</b> {escape(str(analysis.get("action_required", False)))}</p>
        <p><b>Recommended action:</b> {escape(draft.recommended_action)}</p>
        <p><b>Previous rule:</b> {escape(draft.previous_rule)}</p>
        <p><b>New rule:</b> {escape(draft.new_rule)}</p>
        <p><b>Possible consequences:</b> {escape(draft.possible_consequences)}</p>
        <p><b>Affected groups</b></p><ul>{affected}</ul>
        <p><b>Not affected</b></p><ul>{not_affected}</ul>
        <p>{''.join(f'<span class="pill">{escape(tag)}</span>' for tag in draft.tags)}</p>
      </div>
    </div>
    <div class="card">
      <h2>Related news</h2>
      <ul>{related_html}</ul>
      <a class="button secondary" href="/timeline/{escape(draft.category)}">Open {escape(draft.category)} timeline</a>
    </div>
    <div class="card">
      <h2>Telegram editor</h2>
      <form method="post" action="/drafts/{escape(draft.id)}">
        <label>Image URL
          <input name="image_url" value="{escape(draft.image_url)}" placeholder="https://...">
        </label>
        {image}
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
        draft_for_quality = store.get(draft_id)
        if draft_for_quality and (draft_for_quality.impact_score < 35 or len(text.strip()) < 300):
            store.update(draft_id, draft_text=text, image_url=image_url)
            result = "Draft saved, but not published: quality gate requires more editorial context before publishing."
            body = f"""
            <h1>{escape(result)}</h1>
            <a class="button" href="/drafts/{escape(draft_id)}">Back to draft</a>
            <a class="button secondary" href="/newsroom">Newsroom</a>
            """
            return page("Draft updated", body)
        if not settings.telegram_bot_token or not settings.telegram_channel:
            result = "Telegram не настроен. Проверь .env."
            store.update(draft_id, draft_text=text, image_url=image_url)
        else:
            draft = store.update(draft_id, draft_text=text, image_url=image_url)
            if not draft:
                return page("Draft not found", "<h1>Draft not found</h1><a class='button secondary' href='/drafts'>Back</a>")
            safe_text = ensure_publishable_text(text, draft.url)
            TelegramClient(settings.telegram_bot_token, settings.telegram_channel).send_message(safe_text)
            LocalState().mark_published(draft.url)
            store.update(draft_id, draft_text=safe_text, status="published", image_url=image_url)
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
        client.send_message(ensure_publishable_text(text, url))
        LocalState().mark_published(url)
        DraftStore().update_by_url(url, draft_text=ensure_publishable_text(text, url), status="published")
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
    stats = collector_dashboard_stats()
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


@app.get("/search", response_class=HTMLResponse)
def global_search(q: str = ""):
    store = DraftStore()
    store.ingest_items(collect_sources().items)
    results = search_drafts(store.list_drafts(), q)
    rows = []
    for draft in results[:50]:
        rows.append(f"""
        <div class="card">
          <h3><a href="/drafts/{escape(draft.id)}">{escape(draft.title)}</a></h3>
          <p class="muted">{escape(draft.source)} | {escape(draft.category)} | {escape(draft.status)} | impact {draft.impact_score}</p>
          <p>{escape(draft.russian_summary)}</p>
          <p>{''.join(f'<span class="pill">{escape(tag)}</span>' for tag in draft.tags[:8])}</p>
        </div>
        """)
    body = f"""
    <h1>Global search</h1>
    <div class="card">
      <form method="get">
        <label>Search title, body, AI summary, tags, source, affected group
          <input name="q" value="{escape(q)}" placeholder="TPS deadline USCIS">
        </label>
        <button type="submit">Search</button>
      </form>
    </div>
    """ + ("".join(rows) if rows else "<div class='card'><p>No results.</p></div>")
    return page("Global search", body)


@app.get("/timelines", response_class=HTMLResponse)
def timelines():
    store = DraftStore()
    store.ingest_items(collect_sources().items)
    counts = topic_counts(store.list_drafts())
    rows = "".join(
        f'<div class="metric">{escape(category.upper())}<b>{count}</b><a class="button secondary" href="/timeline/{escape(category)}">Open timeline</a></div>'
        for category, count in sorted(counts.items())
    )
    return page("Timelines", f"<h1>Topic timelines</h1><div class='grid'>{rows}</div>")


@app.get("/timeline/{category}", response_class=HTMLResponse)
def timeline(category: str):
    store = DraftStore()
    store.ingest_items(collect_sources().items)
    rows = []
    for draft in timeline_for_category(store.list_drafts(), category):
        rows.append(f"""
        <div class="card">
          <p class="muted">{escape(draft.published_at or draft.collected_at)}</p>
          <h3><a href="/drafts/{escape(draft.id)}">{escape(draft.title)}</a></h3>
          <p>{escape(draft.russian_summary)}</p>
        </div>
        """)
    return page(f"{category} timeline", f"<h1>{escape(category.upper())} timeline</h1>" + ("".join(rows) if rows else "<div class='card'><p>No timeline entries yet.</p></div>"))


@app.get("/archive", response_class=HTMLResponse)
def archive():
    store = DraftStore()
    store.ingest_items(collect_sources().items)
    rows = []
    for draft in store.list_drafts(status="published") or store.list_drafts()[:20]:
        rows.append(f"""
        <div class="card">
          <h3><a href="/archive/{escape(draft.id)}">{escape(draft.russian_summary or draft.title)}</a></h3>
          <p class="muted">{escape(draft.source)} | {escape(draft.category)} | {escape(draft.published_at or "")}</p>
          <p>{escape(draft.russian_explanation)}</p>
        </div>
        """)
    return page("Public archive", "<h1>Public archive</h1><p class='muted'>SEO-ready Russian explanations with source links and related news.</p>" + "".join(rows))


@app.get("/archive/{draft_id}", response_class=HTMLResponse)
def archive_detail(draft_id: str):
    store = DraftStore()
    draft = store.get(draft_id)
    if not draft:
        return page("Not found", "<h1>Article not found</h1><a class='button secondary' href='/archive'>Archive</a>")
    related = related_drafts(draft, store.list_drafts())
    related_html = "".join(f'<li><a href="/archive/{escape(item.id)}">{escape(item.russian_summary or item.title)}</a></li>' for item in related) or "<li>No related news yet.</li>"
    share_url = f"/archive/{escape(draft.id)}"
    image = f'<img src="{escape(draft.image_url)}" alt="" style="max-width:100%; border-radius:8px;">' if draft.image_url else ""
    body = f"""
    <h1>{escape(draft.russian_summary or draft.title)}</h1>
    <p class="muted">{escape(draft.source)} | {escape(draft.category)} | {escape(draft.published_at or "")}</p>
    {image}
    <div class="card">
      <h2>Русское объяснение</h2>
      <p>{escape(draft.russian_explanation)}</p>
      <p><b>Кого может касаться:</b> {escape(", ".join(draft.affected_groups))}</p>
      <p><b>Рекомендованное действие:</b> {escape(draft.recommended_action)}</p>
      <p><b>Источник:</b> <a href="{escape(draft.url)}" target="_blank">{escape(draft.url)}</a></p>
      <p>Информационный пост, не юридическая консультация.</p>
    </div>
    <div class="card">
      <h2>Related news</h2>
      <ul>{related_html}</ul>
      <p><a class="button secondary" href="https://t.me/share/url?url={share_url}">Share to Telegram</a></p>
    </div>
    """
    return page(draft.russian_summary or draft.title, body, description=draft.russian_explanation[:150])
