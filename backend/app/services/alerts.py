from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging

import requests

from app.config import settings


logger = logging.getLogger(__name__)


class AlertService:
    def __init__(self) -> None:
        self._last_sent_at: dict[str, datetime] = {}

    def send(self, title: str, message: str, *, key: str | None = None) -> bool:
        webhook_url = settings.discord_webhook_url
        if not webhook_url:
            return False

        alert_key = key or title
        now = datetime.now(timezone.utc)
        last_sent = self._last_sent_at.get(alert_key)
        if last_sent and now - last_sent < timedelta(seconds=settings.alert_cooldown_seconds):
            return False

        payload = {
            "embeds": [
                {
                    "title": title,
                    "description": message,
                    "timestamp": now.isoformat(),
                    "color": 15_158_355,
                }
            ]
        }
        try:
            response = requests.post(webhook_url, json=payload, timeout=5)
            response.raise_for_status()
        except Exception:
            logger.exception("failed to send Discord alert")
            return False

        self._last_sent_at[alert_key] = now
        return True
