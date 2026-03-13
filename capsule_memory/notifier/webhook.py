from __future__ import annotations
import logging
from capsule_memory.models.events import SkillTriggerEvent
from capsule_memory.notifier.base import BaseNotifier

logger = logging.getLogger(__name__)


class WebhookNotifier(BaseNotifier):
    """Notifier that sends skill trigger events to a webhook URL."""

    def __init__(self, url: str, headers: dict[str, str] | None = None) -> None:
        self._url = url
        self._headers = headers or {}

    async def notify(self, event: SkillTriggerEvent) -> None:
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    self._url,
                    json={
                        "event_id": event.event_id,
                        "session_id": event.session_id,
                        "trigger_rule": event.trigger_rule.value,
                        "skill_draft": {
                            "suggested_name": event.skill_draft.suggested_name,
                            "confidence": event.skill_draft.confidence,
                            "preview": event.skill_draft.preview,
                        },
                    },
                    headers=self._headers,
                    timeout=5.0,
                )
                logger.debug("Webhook response: %s %s", resp.status_code, resp.text[:100])
        except Exception as e:
            logger.warning("WebhookNotifier failed: %s", e)
