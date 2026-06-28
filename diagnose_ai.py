from app.ai_editor import AIEditor
from app.config import settings
from app.sources import fetch_all_sources


def main():
    editor = AIEditor()
    print("AI enabled:", editor.enabled)
    print("Model:", settings.openai_model)

    if editor.enabled:
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
            return

    items = fetch_all_sources()
    if not items:
        print("No items found")
        return

    priority = {"important": 0, "medium": 1, "info": 2}
    items.sort(key=lambda x: (priority.get(x.importance, 9), x.published_at is None, x.published_at))
    item = items[0]
    print("Selected:", item.title)
    print("URL:", item.url)

    post = editor.build_post(item)
    print("AI last error:", editor.last_error)
    print("----- POST -----")
    print(post)
    print("----- END -----")


if __name__ == "__main__":
    main()
