"""Tests for notifiers: callback, cli, webhook, multi."""
from __future__ import annotations

import os

os.environ["CAPSULE_MOCK_EXTRACTOR"] = "true"

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from capsule_memory.models.events import SkillDraft, SkillTriggerEvent, SkillTriggerRule
from capsule_memory.notifier.callback import CallbackNotifier
from capsule_memory.notifier.cli import CLINotifier
from capsule_memory.notifier.multi import MultiNotifier
from capsule_memory.notifier.webhook import WebhookNotifier


@pytest.fixture
def sample_event() -> SkillTriggerEvent:
    draft = SkillDraft(
        suggested_name="test_skill",
        confidence=0.85,
        preview="This is a preview of the detected skill pattern.",
        trigger_rule=SkillTriggerRule.REPEAT_PATTERN,
        source_turns=[1, 2],
    )
    return SkillTriggerEvent(
        event_id="evt_test1234",
        session_id="sess_test",
        trigger_rule=SkillTriggerRule.REPEAT_PATTERN,
        skill_draft=draft,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# CallbackNotifier
# ═══════════════════════════════════════════════════════════════════════════════

class TestCallbackNotifier:
    async def test_sync_callback(self, sample_event: SkillTriggerEvent) -> None:
        called_with = []
        notifier = CallbackNotifier(callback=lambda evt: called_with.append(evt))
        await notifier.notify(sample_event)
        assert len(called_with) == 1
        assert called_with[0].event_id == "evt_test1234"

    async def test_async_callback(self, sample_event: SkillTriggerEvent) -> None:
        called_with = []

        async def async_cb(evt):
            called_with.append(evt)

        notifier = CallbackNotifier(callback=async_cb)
        await notifier.notify(sample_event)
        assert len(called_with) == 1

    async def test_callback_exception_does_not_raise(
        self, sample_event: SkillTriggerEvent, caplog
    ) -> None:
        def bad_callback(evt):
            raise ValueError("test error")

        notifier = CallbackNotifier(callback=bad_callback)
        with caplog.at_level(logging.WARNING):
            await notifier.notify(sample_event)
        assert "CallbackNotifier error" in caplog.text


# ═══════════════════════════════════════════════════════════════════════════════
# CLINotifier
# ═══════════════════════════════════════════════════════════════════════════════

class TestCLINotifier:
    async def test_notify_non_interactive_with_rich(
        self, sample_event: SkillTriggerEvent
    ) -> None:
        """Non-interactive (no tty): should print panel and return without blocking."""
        mock_console = MagicMock()
        notifier = CLINotifier(session_ref=None)
        notifier._console = mock_console

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            await notifier.notify(sample_event)

        # Should have printed the panel and the non-interactive message
        assert mock_console.print.call_count >= 2

    async def test_notify_non_interactive_no_rich(
        self, sample_event: SkillTriggerEvent
    ) -> None:
        """Non-interactive, no rich console: should fall back to print()."""
        notifier = CLINotifier(session_ref=None)
        notifier._console = None

        with patch("sys.stdin") as mock_stdin, patch("builtins.print") as mock_print:
            mock_stdin.isatty.return_value = False
            await notifier.notify(sample_event)

        mock_print.assert_called_once()
        assert "Skill Detected" in mock_print.call_args[0][0]

    async def test_notify_no_session_ref(
        self, sample_event: SkillTriggerEvent
    ) -> None:
        """With tty but no session ref: should return after printing."""
        mock_console = MagicMock()
        notifier = CLINotifier(session_ref=None)
        notifier._console = mock_console

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            await notifier.notify(sample_event)

        # Should print panel + non-interactive line (session is None → early return)
        assert mock_console.print.call_count >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# WebhookNotifier
# ═══════════════════════════════════════════════════════════════════════════════

class TestWebhookNotifier:
    async def test_notify_success(self, sample_event: SkillTriggerEvent) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        notifier = WebhookNotifier(
            url="https://example.com/webhook",
            headers={"X-Custom": "test"},
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            await notifier.notify(sample_event)

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert call_kwargs.kwargs["json"]["event_id"] == "evt_test1234"
        assert call_kwargs.kwargs["headers"] == {"X-Custom": "test"}
        assert call_kwargs.kwargs["timeout"] == 5.0

    async def test_notify_failure_does_not_raise(
        self, sample_event: SkillTriggerEvent, caplog
    ) -> None:
        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        notifier = WebhookNotifier(url="https://example.com/fail")

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            caplog.at_level(logging.WARNING),
        ):
            await notifier.notify(sample_event)

        assert "WebhookNotifier failed" in caplog.text


# ═══════════════════════════════════════════════════════════════════════════════
# MultiNotifier
# ═══════════════════════════════════════════════════════════════════════════════

class TestMultiNotifier:
    async def test_dispatches_to_all(self, sample_event: SkillTriggerEvent) -> None:
        n1 = AsyncMock()
        n2 = AsyncMock()
        n1.notify = AsyncMock()
        n2.notify = AsyncMock()

        multi = MultiNotifier(notifiers=[n1, n2])
        await multi.notify(sample_event)

        n1.notify.assert_called_once_with(sample_event)
        n2.notify.assert_called_once_with(sample_event)

    async def test_continues_on_failure(
        self, sample_event: SkillTriggerEvent, caplog
    ) -> None:
        n1 = MagicMock()
        n1.notify = AsyncMock(side_effect=RuntimeError("n1 failed"))
        n2 = MagicMock()
        n2.notify = AsyncMock()
        n2.__class__.__name__ = "MockNotifier"

        multi = MultiNotifier(notifiers=[n1, n2])

        with caplog.at_level(logging.WARNING):
            await multi.notify(sample_event)

        # n2 should still be called even though n1 failed
        n2.notify.assert_called_once_with(sample_event)
        assert "failed" in caplog.text

    async def test_empty_notifiers(self, sample_event: SkillTriggerEvent) -> None:
        multi = MultiNotifier(notifiers=[])
        await multi.notify(sample_event)  # should not raise
