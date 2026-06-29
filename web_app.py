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

CATEGORY_RU = {
    "asylum": "Убежище",
    "court": "Иммиграционный суд",
    "ead": "Разрешение на работу",
    "tps": "TPS",
    "parole": "Parole",
    "deportation": "Депортация / removal",
    "ice": "ICE",
    "cbp": "CBP / граница",
    "policy": "Правила и политика",
    "immigration": "Иммиграция",
    "general": "Иммиграция",
}

URGENCY_RU = {"high": "срочно", "medium": "важно", "low": "обычно"}
STATUS_RU = {
    "collected": "собрано",
    "analyzed": "проанализировано",
    "draft_ready": "готово к проверке",
    "edited": "отредактировано",
    "published": "опубликовано",
    "ignored": "игнорируется",
}
IMPORTANCE_RU = {"important": "важная", "medium": "средняя", "info": "инфо"}


def page(title: str, body: str, active: str = "dashboard", description: str = "") -> str:
    meta_description = description or "Русскоязычная платформа иммиграционной аналитики США: новости, объяснения, редакторские черновики и публикации."
    nav = [
        ("/", "Дашборд"),
        ("/newsroom", "Ньюсрум"),
        ("/search", "Поиск"),
        ("/timelines", "Темы"),
        ("/archive", "Публичный архив"),
    ]
    nav_html = "".join(f'<a href="{href}">{label}</a>' for href, label in nav)
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
    body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; background:#f3f5f8; color:#111827; margin:0; padding:0; }}
    .wrap {{ max-width: 1360px; margin: 0 auto; padding:28px; }}
    .topbar {{ display:flex; align-items:center; justify-content:space-between; gap:16px; margin-bottom:22px; }}
    .brand {{ font-weight:800; font-size:22px; }}
    .nav a {{ color:#334155; margin-left:14px; text-decoration:none; font-weight:600; }}
    .card {{ background:#ffffff; border:1px solid #e5e7eb; border-radius:8px; padding:20px; margin:14px 0; box-shadow:0 1px 2px rgba(15,23,42,.04); }}
    .metric {{ background:#ffffff; border:1px solid #e5e7eb; border-radius:8px; padding:16px; }}
    .metric b {{ display:block; font-size:28px; margin-top:6px; }}
    .metric span {{ color:#64748b; font-size:13px; font-weight:700; }}
    a.button, button {{ display:inline-block; background:#1d4ed8; color:white; padding:10px 14px; border-radius:8px; text-decoration:none; border:0; margin:6px 6px 6px 0; cursor:pointer; font-size:14px; font-weight:700; }}
    a.secondary, button.secondary {{ background:#475569; }}
    a.warn, button.warn {{ background:#b45309; }}
    pre {{ white-space:pre-wrap; background:#f8fafc; border:1px solid #e5e7eb; border-radius:8px; padding:16px; overflow:auto; color:#0f172a; }}
    textarea {{ width:100%; min-height:420px; background:#ffffff; color:#111827; border:1px solid #cbd5e1; border-radius:8px; padding:16px; font-size:15px; line-height:1.5; }}
    input, select {{ width:100%; background:#ffffff; color:#111827; border:1px solid #cbd5e1; border-radius:8px; padding:11px; }}
    label {{ display:block; color:#475569; font-size:13px; font-weight:700; }}
    .thumb {{ width:160px; height:108px; object-fit:cover; border-radius:8px; background:#e5e7eb; }}
    .thumb.placeholder {{ display:flex; align-items:center; justify-content:center; color:#94a3b8; font-weight:800; }}
    .muted {{ color:#64748b; }}
    .lead {{ font-size:18px; line-height:1.45; }}
    .headline {{ font-size:20px; margin:4px 0 8px; }}
    .explain {{ background:#f8fafc; border-left:4px solid #2563eb; padding:12px 14px; border-radius:8px; }}
    .toolbar {{ display:flex; gap:8px; flex-wrap:wrap; align-items:center; }}
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
<body><div class="wrap"><div class="topbar"><div class="brand">Иммиграционная разведка</div><div class="nav">{nav_html}</div></div>{body}</div></body>
</html>
"""


def ru_category(value: str) -> str:
    return CATEGORY_RU.get(value, value or "иммиграция")


def ru_urgency(value: str) -> str:
    return URGENCY_RU.get(value, value or "не указано")


def ru_status(value: str) -> str:
    return STATUS_RU.get(value, value or "не указано")


def ru_importance(value: str) -> str:
    return IMPORTANCE_RU.get(value, value or "инфо")


def format_date(value: str) -> str:
    return value[:10] if value else "дата не указана"


def editorial_headline(draft) -> str:
    if draft.russian_summary:
        return draft.russian_summary.split(".")[0][:180]
    return draft.title


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
          <label>Поиск
            <input name="q" value="{escape(query)}" placeholder="убежище, TPS, EAD, суд">
          </label>
          <label>Категория
            <select name="category">
              <option value="">Все</option>
              <option value="asylum" {selected("asylum", category)}>Убежище</option>
              <option value="court" {selected("court", category)}>Иммиграционный суд</option>
              <option value="ead" {selected("ead", category)}>EAD</option>
              <option value="tps" {selected("tps", category)}>TPS</option>
              <option value="parole" {selected("parole", category)}>Parole</option>
              <option value="deportation" {selected("deportation", category)}>Депортация</option>
              <option value="policy" {selected("policy", category)}>Правила</option>
            </select>
          </label>
          <label>Важность
            <select name="importance">
              <option value="">Все</option>
              <option value="important" {selected("important", importance)}>Важная</option>
              <option value="medium" {selected("medium", importance)}>Средняя</option>
              <option value="info" {selected("info", importance)}>Инфо</option>
            </select>
          </label>
          <label>Срочность
            <select name="urgency">
              <option value="">Все</option>
              <option value="high" {selected("high", urgency)}>Срочно</option>
              <option value="medium" {selected("medium", urgency)}>Важно</option>
              <option value="low" {selected("low", urgency)}>Обычно</option>
            </select>
          </label>
        </div>
        <button type="submit">Применить</button>
        <a class="button secondary" href="/check">Сбросить</a>
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
          <label>Поиск
            <input name="q" value="{escape(query)}" placeholder="заголовок, источник, тег, группа">
          </label>
          <label>Источник
            <input name="source" value="{escape(source)}" placeholder="USCIS, Federal Register">
          </label>
          <label>Категория
            <select name="category">
              <option value="">Все</option>
              <option value="asylum" {selected("asylum", category)}>Убежище</option>
              <option value="court" {selected("court", category)}>Иммиграционный суд</option>
              <option value="ead" {selected("ead", category)}>EAD</option>
              <option value="tps" {selected("tps", category)}>TPS</option>
              <option value="parole" {selected("parole", category)}>Parole</option>
              <option value="deportation" {selected("deportation", category)}>Депортация</option>
              <option value="policy" {selected("policy", category)}>Правила</option>
            </select>
          </label>
          <label>Срочность
            <select name="urgency">
              <option value="">Все</option>
              <option value="high" {selected("high", urgency)}>Срочно</option>
              <option value="medium" {selected("medium", urgency)}>Важно</option>
              <option value="low" {selected("low", urgency)}>Обычно</option>
            </select>
          </label>
          <label>Статус
            <select name="status">
              <option value="">Все</option>
              <option value="collected" {selected("collected", status)}>Собрано</option>
              <option value="analyzed" {selected("analyzed", status)}>Проанализировано</option>
              <option value="draft_ready" {selected("draft_ready", status)}>Готово к проверке</option>
              <option value="edited" {selected("edited", status)}>Отредактировано</option>
              <option value="published" {selected("published", status)}>Опубликовано</option>
              <option value="ignored" {selected("ignored", status)}>Игнорируется</option>
            </select>
          </label>
        </div>
        <button type="submit">Применить</button>
        <a class="button secondary" href="/drafts">Сбросить</a>
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
    <h1>Редакционный дашборд</h1>
    <p class="muted">Главное рабочее место для мониторинга, анализа и подготовки иммиграционных новостей США. Telegram — только канал публикации.</p>
    <div class="grid">
      <div class="metric"><span>Новые сегодня</span><b>{new_news}</b></div>
      <div class="metric"><span>Важные</span><b>{important_news}</b></div>
      <div class="metric"><span>Ждут редактора</span><b>{awaiting_review}</b></div>
      <div class="metric"><span>Опубликовано сегодня</span><b>{published_today}</b></div>
      <div class="metric"><span>Игнорируются</span><b>{ignored}</b></div>
      <div class="metric"><span>С AI-анализом</span><b>{ai_processed}</b></div>
      <div class="metric"><span>Здоровье коллектора</span><b>{collector_health}</b></div>
    </div>
    <div class="card">
      <h2>Рабочие действия</h2>
      <a class="button" href="/newsroom">Открыть ньюсрум</a>
      <a class="button secondary" href="/search">Глобальный поиск</a>
      <a class="button secondary" href="/timelines">Таймлайны тем</a>
      <a class="button secondary" href="/diagnostics">Диагностика источников</a>
      <a class="button" href="/daily-summary">Отправить daily summary</a>
    </div>

    <div class="card">
      <h2>Статус</h2>
      <p>Telegram-канал: <b>{channel}</b></p>
      <p>OpenAI: <b>{ai_status}</b></p>
      <p>Версия: <b>{version}</b></p>
      <ul>{release_rows}</ul>
      <p class="muted">Каждая новость проходит через очередь: исходник, русское объяснение, оценка влияния, текст поста и ручное подтверждение публикации.</p>
    </div>
    """.format(
        **stats,
        channel=escape(settings.telegram_channel or "not set"),
        ai_status="подключен" if settings.openai_api_key and not settings.openai_api_key.startswith("paste_") else "локальный fallback",
        version=escape(APP_VERSION),
        release_rows=release_rows,
    )
    return page("Иммиграционная разведка", body)


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
          <p><span class="pill">тип: {escape(source.type)}</span><span class="pill">приоритет: {source.priority}</span><span class="pill">группа: {escape(source.group)}</span></p>
          <p>Всего найдено: <b>{found}</b> · Свежие 60 дней: <b>{fresh}</b></p>
          <p class="muted">{escape(source.url or 'Federal Register API')}</p>
        </div>
        """)
    body = f"<h1>Коллектор источников</h1><p class='muted'>Версия: {escape(APP_VERSION)}</p>" + "".join(rows)
    return page("Коллектор", body, active="collector")


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
        status = "<span class='ok'>работает</span>" if item.ok else "<span class='warntext'>ошибка</span>"
        detail = item.error or f"Получено: {item.fetched}; релевантно: {item.relevant}"
        rows.append(f"""
        <div class="card">
          <h3>{escape(item.source)} — {status}</h3>
          <p class="muted">{escape(detail)}</p>
        </div>
        """)
    body = "<h1>Диагностика источников</h1><a class='button secondary' href='/'>Назад</a>" + "".join(rows)
    return page("Диагностика источников", body)


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
        image = f'<img class="thumb" src="{escape(draft.image_url)}" alt="">' if draft.image_url else '<div class="thumb placeholder">без фото</div>'
        can_publish = draft.status not in {"published", "ignored"} and draft.impact_score >= 35 and draft.telegram_text.strip()
        publish_button = '<button class="warn" type="submit" name="action" value="publish">Опубликовать</button>' if can_publish else '<button class="secondary" type="button" disabled>Не готово</button>'
        deadline = f'<span class="pill danger">срок: {escape(draft.deadline)}</span>' if draft.deadline else ""
        effective = f'<span class="pill warning">в силе с: {escape(draft.effective_date)}</span>' if draft.effective_date else ""
        rows.append(f"""
        <div class="card queue-card">
          <div>{image}</div>
          <div>
            <div class="toolbar">
              <span class="pill">{escape(ru_status(draft.status))}</span>
              <span class="pill">{escape(ru_category(draft.category))}</span>
              <span class="pill">{escape(ru_urgency(draft.urgency))}</span>
              <span class="pill">влияние {draft.impact_score}/100</span>
              <span class="pill">уверенность: {escape(draft.confidence)}</span>
              {deadline}{effective}
            </div>
            <h3 class="headline">{escape(editorial_headline(draft))}</h3>
            <p class="muted">Оригинал: {escape(draft.title)}</p>
            <p class="muted">{escape(draft.source)} · {escape(format_date(draft.published_at))} · {escape(ru_importance(draft.importance))}</p>
            <div class="explain">{escape(draft.russian_explanation or draft.russian_summary or "Русское объяснение пока не сформировано.")}</div>
            <p><b>Кого может касаться:</b> {escape(affected or "не определено")}</p>
            <p><b>Что проверить редактору:</b> {escape(draft.recommended_action or "Откройте источник и проверьте применимость новости.")}</p>
            <p>{''.join(f'<span class="pill">{escape(tag)}</span>' for tag in draft.tags[:8])}</p>
            <a class="button" href="/drafts/{escape(draft.id)}">Открыть</a>
            <a class="button secondary" href="/drafts/{escape(draft.id)}">Редактировать</a>
            <form method="post" action="/drafts/{escape(draft.id)}" style="display:inline">
              <input type="hidden" name="text" value="{escape(draft.telegram_text)}">
              <input type="hidden" name="image_url" value="{escape(draft.image_url)}">
              <button type="submit" name="action" value="ignore">Игнорировать</button>
              {publish_button}
            </form>
          </div>
        </div>
        """)
    body = "<h1>Ньюсрум</h1><p class='muted'>Очередь материалов: сначала понять новость, затем проверить источник, отредактировать пост и только потом публиковать.</p>" + draft_filter_controls(q, category, urgency, source, status)
    body += "".join(rows) or "<div class='card'><p>По этим фильтрам ничего не найдено.</p></div>"
    return page("Ньюсрум", body)


@app.get("/drafts/{draft_id}", response_class=HTMLResponse)
def draft_detail(draft_id: str):
    draft = DraftStore().get(draft_id)
    if not draft:
        return page("Черновик не найден", "<h1>Черновик не найден</h1><a class='button secondary' href='/drafts'>Назад</a>")
    analysis = draft.analysis
    affected = "".join(f"<li>{escape(group)}</li>" for group in draft.affected_groups)
    not_affected = "".join(f"<li>{escape(group)}</li>" for group in draft.not_affected_groups)
    actions = "".join(f"<li>{escape(step)}</li>" for step in analysis.get("action_steps_ru", []))
    image = f'<img src="{escape(draft.image_url)}" alt="" style="max-width:100%; border-radius:12px; margin-top:12px;">' if draft.image_url else "<p class='muted'>Изображение не найдено. Можно вставить URL вручную ниже.</p>"
    all_drafts = DraftStore().list_drafts()
    related = related_drafts(draft, all_drafts)
    related_html = "".join(f'<li><a href="/drafts/{escape(item.id)}">{escape(editorial_headline(item))}</a> <span class="muted">{escape(item.source)} · {escape(format_date(item.published_at))}</span></li>' for item in related) or "<li>Похожих материалов пока нет.</li>"
    body = f"""
    <h1>Редактор материала</h1>
    <p class="lead">{escape(editorial_headline(draft))}</p>
    <div class="toolbar">
      <span class="pill">{escape(ru_status(draft.status))}</span>
      <span class="pill">{escape(ru_category(draft.category))}</span>
      <span class="pill">{escape(ru_urgency(draft.urgency))}</span>
      <span class="pill">влияние {draft.impact_score}/100</span>
      <span class="pill">уверенность: {escape(draft.confidence)}</span>
    </div>
    <a class="button secondary" href="/newsroom">Назад в ньюсрум</a>
    <a class="button secondary" href="{escape(draft.url)}" target="_blank">Открыть источник</a>
    <div class="editor-grid">
      <div class="card">
        <h2>Оригинал</h2>
        <h3>{escape(draft.title)}</h3>
        <p class="muted">{escape(draft.source)} · {escape(draft.source_type)} · {escape(format_date(draft.published_at))}</p>
        {image}
        <p><b>Ссылка на источник:</b> <a href="{escape(draft.url)}" target="_blank">{escape(draft.url)}</a></p>
        <pre>{escape(draft.extracted_text or "Полный текст не извлечен. Используйте ссылку на источник выше.")}</pre>
      </div>
      <div class="card">
        <h2>AI-анализ для редактора</h2>
        <div class="explain"><b>Коротко:</b> {escape(draft.russian_summary or "Нет краткого объяснения.")}</div>
        <p><b>Простыми словами:</b> {escape(draft.russian_explanation or "Нет объяснения.")}</p>
        <p><b>Срок:</b> {escape(draft.deadline or "не найден")} · <b>Вступает в силу:</b> {escape(draft.effective_date or "не найдено")}</p>
        <p><b>Нужно действие:</b> {escape("да" if analysis.get("action_required", False) else "нет / нужно проверить")}</p>
        <p><b>Что рекомендовать читателю:</b> {escape(draft.recommended_action)}</p>
        <p><b>Что было раньше:</b> {escape(draft.previous_rule)}</p>
        <p><b>Что меняется:</b> {escape(draft.new_rule)}</p>
        <p><b>Возможные последствия:</b> {escape(draft.possible_consequences)}</p>
        <p><b>Кого касается</b></p><ul>{affected}</ul>
        <p><b>Кого, вероятно, не касается</b></p><ul>{not_affected}</ul>
        <p>{''.join(f'<span class="pill">{escape(tag)}</span>' for tag in draft.tags)}</p>
      </div>
    </div>
    <div class="card">
      <h2>Похожие материалы</h2>
      <ul>{related_html}</ul>
      <a class="button secondary" href="/timeline/{escape(draft.category)}">Открыть таймлайн: {escape(ru_category(draft.category))}</a>
    </div>
    <div class="card">
      <h2>Редактор Telegram-поста</h2>
      <form method="post" action="/drafts/{escape(draft.id)}">
        <label>URL изображения
          <input name="image_url" value="{escape(draft.image_url)}" placeholder="https://...">
        </label>
        {image}
        <textarea name="text">{escape(draft.telegram_text)}</textarea>
        <br>
        <button type="submit" name="action" value="save">Сохранить черновик</button>
        <button class="warn" type="submit" name="action" value="publish">Опубликовать в Telegram</button>
        <button type="submit" name="action" value="ignore">Игнорировать</button>
      </form>
    </div>
    """
    return page("Редактор материала", body)


@app.post("/drafts/{draft_id}", response_class=HTMLResponse)
def update_draft(draft_id: str, text: str = Form(...), action: str = Form(...), image_url: str = Form("")):
    store = DraftStore()
    if action == "publish":
        draft_for_quality = store.get(draft_id)
        if draft_for_quality and (draft_for_quality.impact_score < 35 or len(text.strip()) < 300):
            store.update(draft_id, draft_text=text, image_url=image_url)
            result = "Черновик сохранен, но не опубликован: перед публикацией нужно больше редакторского контекста."
            body = f"""
            <h1>{escape(result)}</h1>
            <a class="button" href="/drafts/{escape(draft_id)}">Вернуться к материалу</a>
            <a class="button secondary" href="/newsroom">Ньюсрум</a>
            """
            return page("Черновик обновлен", body)
        if not settings.telegram_bot_token or not settings.telegram_channel:
            result = "Telegram не настроен. Проверь .env."
            store.update(draft_id, draft_text=text, image_url=image_url)
        else:
            draft = store.update(draft_id, draft_text=text, image_url=image_url)
            if not draft:
                return page("Черновик не найден", "<h1>Черновик не найден</h1><a class='button secondary' href='/drafts'>Назад</a>")
            safe_text = ensure_publishable_text(text, draft.url)
            TelegramClient(settings.telegram_bot_token, settings.telegram_channel).send_message(safe_text)
            LocalState().mark_published(draft.url)
            store.update(draft_id, draft_text=safe_text, status="published", image_url=image_url)
            result = "Материал опубликован в Telegram."
    elif action == "ignore":
        store.update(draft_id, draft_text=text, status="ignored", image_url=image_url)
        result = "Материал помечен как игнорируемый."
    else:
        store.update(draft_id, draft_text=text, status="edited", image_url=image_url)
        result = "Черновик сохранен."
    body = f"""
    <h1>{escape(result)}</h1>
    <a class="button" href="/drafts/{escape(draft_id)}">Вернуться к материалу</a>
    <a class="button secondary" href="/drafts">Очередь</a>
    """
    return page("Черновик обновлен", body)


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
    header = "<div class='top'><div><h1>Черновики</h1><p class='muted'>Свежие неопубликованные материалы за последние 60 дней</p></div><a class='button secondary' href='/'>Дашборд</a></div>"
    if not items:
        return page("Черновики", header + controls + "<div class='card'><p>Новых свежих неопубликованных материалов нет.</p></div>", active="drafts")

    cards = []
    for item in items:
        date = item.published_at.date().isoformat() if item.published_at else "no-date"
        analysis = analyze_item(item)
        cls = importance_class(item.importance)
        cards.append(f"""
        <div class="card draft {cls}">
          <div><span class="pill {cls}">{escape(ru_importance(item.importance))}</span><span class="pill">{escape(ru_category(item.category))}</span><span class="pill">{escape(ru_urgency(analysis.urgency))}</span><span class="pill">{escape(item.source)}</span></div>
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
        return page("Материал не найден", "<h1>Материал не найден</h1><a class='button secondary' href='/check'>Назад</a>", active="drafts")
    store = DraftStore()
    store.ingest_items([item])
    draft_id = draft_id_for_url(item.url)
    stored = store.get(draft_id)
    draft = stored.telegram_text if stored else build_post(item, use_ai=True)
    date = item.published_at.date().isoformat() if item.published_at else "no-date"
    body = f"""
    <div class="top"><div><h1>Редактор</h1><p class="muted">{escape(item.source)} · {escape(date)} · {escape(ru_category(item.category))} · {escape(ru_importance(item.importance))}</p></div><a class="button secondary" href="/check">Назад</a></div>
    <a class="button secondary" href="/drafts/{escape(draft_id)}">Открыть в ньюсруме</a>
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
    body = f"<h1>Готово</h1><a class='button' href='/check'>К черновикам</a><a class='button secondary' href='/'>Дашборд</a><div class='card'><pre>{escape(result)}</pre></div>"
    return page("Отправлено", body, active="drafts")


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
    return page("Публикация без редактирования", body)


@app.post("/publish-offline", response_class=HTMLResponse)
def publish_offline_confirmed():
    if not settings.telegram_bot_token or not settings.telegram_channel:
        result = "Telegram не настроен."
    else:
        count = publish_new_items(settings.telegram_bot_token, settings.telegram_channel, limit=1, use_ai=False, days=60)
        result = f"Опубликовано: {count}"
    return page("Публикация", f"<h1>Публикация</h1><div class='card'><pre>{escape(result)}</pre></div>", active="drafts")


@app.get("/daily-summary", response_class=HTMLResponse)
def daily_summary():
    if not settings.telegram_bot_token or not settings.telegram_channel:
        result = "Telegram не настроен."
    else:
        client = TelegramClient(settings.telegram_bot_token, settings.telegram_channel)
        client.send_message(build_daily_summary_text(days=1))
        result = "Daily summary отправлен в Telegram."
    return page("Ежедневная сводка", f"<h1>Ежедневная сводка</h1><div class='card'><pre>{escape(result)}</pre></div>", active="summary")


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
          <h3><a href="/drafts/{escape(draft.id)}">{escape(editorial_headline(draft))}</a></h3>
          <p class="muted">{escape(draft.source)} · {escape(ru_category(draft.category))} · {escape(ru_status(draft.status))} · влияние {draft.impact_score}/100</p>
          <p>{escape(draft.russian_explanation or draft.russian_summary)}</p>
          <p>{''.join(f'<span class="pill">{escape(tag)}</span>' for tag in draft.tags[:8])}</p>
        </div>
        """)
    body = f"""
    <h1>Глобальный поиск</h1>
    <div class="card">
      <form method="get">
        <label>Ищет по заголовку, тексту, AI-объяснению, тегам, источнику и affected groups
          <input name="q" value="{escape(q)}" placeholder="TPS дедлайн USCIS">
        </label>
        <button type="submit">Найти</button>
      </form>
    </div>
    """ + ("".join(rows) if rows else "<div class='card'><p>Ничего не найдено.</p></div>")
    return page("Глобальный поиск", body)


@app.get("/timelines", response_class=HTMLResponse)
def timelines():
    store = DraftStore()
    store.ingest_items(collect_sources().items)
    counts = topic_counts(store.list_drafts())
    rows = "".join(
        f'<div class="metric"><span>{escape(ru_category(category))}</span><b>{count}</b><a class="button secondary" href="/timeline/{escape(category)}">Открыть</a></div>'
        for category, count in sorted(counts.items())
    )
    return page("Таймлайны", f"<h1>Таймлайны по темам</h1><div class='grid'>{rows}</div>")


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
    return page(f"Таймлайн: {ru_category(category)}", f"<h1>Таймлайн: {escape(ru_category(category))}</h1>" + ("".join(rows) if rows else "<div class='card'><p>Пока нет материалов по этой теме.</p></div>"))


@app.get("/archive", response_class=HTMLResponse)
def archive():
    store = DraftStore()
    store.ingest_items(collect_sources().items)
    rows = []
    for draft in store.list_drafts(status="published") or store.list_drafts()[:20]:
        rows.append(f"""
        <div class="card">
          <h3><a href="/archive/{escape(draft.id)}">{escape(editorial_headline(draft))}</a></h3>
          <p class="muted">{escape(draft.source)} · {escape(ru_category(draft.category))} · {escape(format_date(draft.published_at))}</p>
          <p>{escape(draft.russian_explanation)}</p>
        </div>
        """)
    return page("Публичный архив", "<h1>Публичный архив</h1><p class='muted'>Русские объяснения, ссылки на источники и похожие материалы.</p>" + "".join(rows))


@app.get("/archive/{draft_id}", response_class=HTMLResponse)
def archive_detail(draft_id: str):
    store = DraftStore()
    draft = store.get(draft_id)
    if not draft:
        return page("Не найдено", "<h1>Материал не найден</h1><a class='button secondary' href='/archive'>Архив</a>")
    related = related_drafts(draft, store.list_drafts())
    related_html = "".join(f'<li><a href="/archive/{escape(item.id)}">{escape(editorial_headline(item))}</a></li>' for item in related) or "<li>Похожих материалов пока нет.</li>"
    share_url = f"/archive/{escape(draft.id)}"
    image = f'<img src="{escape(draft.image_url)}" alt="" style="max-width:100%; border-radius:8px;">' if draft.image_url else ""
    body = f"""
    <h1>{escape(editorial_headline(draft))}</h1>
    <p class="muted">{escape(draft.source)} · {escape(ru_category(draft.category))} · {escape(format_date(draft.published_at))}</p>
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
      <h2>Похожие материалы</h2>
      <ul>{related_html}</ul>
      <p><a class="button secondary" href="https://t.me/share/url?url={share_url}">Поделиться в Telegram</a></p>
    </div>
    """
    return page(draft.russian_summary or draft.title, body, description=draft.russian_explanation[:150])
