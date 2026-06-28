# Asylum News Bot

Русскоязычный Telegram-бот для мониторинга иммиграционных новостей США: asylum, USCIS, EOIR, DHS, ICE, CBP, TPS, EAD, deportation, immigration court.

## Current stage

Stage 1: Telegram connection test.

## Local setup on macOS

```bash
cd ~/Documents/asylum-news-bot
git pull
python3 -m venv venv
source venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and fill in:

```bash
TELEGRAM_BOT_TOKEN=your_new_token
TELEGRAM_CHANNEL=@asylun_usa
```

Do not commit `.env`.

## Run Telegram test

```bash
python3 main.py
```

or:

```bash
python3 main.py test-telegram
```

If everything is correct, the bot will publish a test message in your Telegram channel.

## Security

If a Telegram token was pasted into any public chat, revoke it in @BotFather and create a new one.
