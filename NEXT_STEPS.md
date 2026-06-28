# Next steps

## Local launch

1. Open Terminal.
2. Go to the project folder:

```bash
cd ~/Documents/asylum-news-bot
```

3. Update project:

```bash
git pull
```

4. Activate environment:

```bash
source venv/bin/activate
```

5. Install packages:

```bash
python3 -m pip install -r requirements.txt
```

6. Start dashboard:

```bash
uvicorn web_app:app --reload --host 127.0.0.1 --port 8000
```

7. Open:

```text
http://127.0.0.1:8000
```

## Current workflow

- Open dashboard.
- Click fresh news.
- Open draft.
- Edit text.
- Send to Telegram.

## Product roadmap

- Improve sources.
- Add automatic scheduler.
- Add better database storage.
- Add image generation.
- Add public website archive.
