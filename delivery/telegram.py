"""
delivery/telegram.py — Telegram bot delivery for The Currents
"""
from __future__ import annotations
import requests
from pathlib import Path
from typing import List


def send_pdf(bot_token: str, chat_id: str, pdf_path: Path, caption: str = "") -> bool:
    """Send PDF document to Telegram chat."""
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    
    with open(pdf_path, "rb") as f:
        files = {"document": f}
        data = {"chat_id": chat_id, "caption": caption}
        response = requests.post(url, files=files, data=data, timeout=60)
    
    response.raise_for_status()
    return response.json().get("ok", False)


def send_photos(bot_token: str, chat_id: str, photo_paths: List[Path], 
                caption: str = "") -> bool:
    """Send photos to Telegram chat."""
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    
    for i, photo_path in enumerate(photo_paths):
        with open(photo_path, "rb") as f:
            files = {"photo": f}
            data = {"chat_id": chat_id}
            if i == 0 and caption:
                data["caption"] = caption
            response = requests.post(url, files=files, data=data, timeout=60)
            response.raise_for_status()
    
    return True


def send_message(bot_token: str, chat_id: str, text: str) -> bool:
    """Send text message to Telegram chat."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    response = requests.post(url, json=data, timeout=30)
    response.raise_for_status()
    return response.json().get("ok", False)
