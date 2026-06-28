#!/usr/bin/env bash
set -e
source venv/bin/activate
uvicorn web_app:app --reload --host 127.0.0.1 --port 8000
