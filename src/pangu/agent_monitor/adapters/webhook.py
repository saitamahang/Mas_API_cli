"""Generic webhook adapter for agent platforms that expose an HTTP callback."""

from __future__ import annotations

from typing import Any

from pangu.agent_monitor.adapters.base import AdapterDeliveryError, AgentAdapter


class WebhookAdapter(AgentAdapter):
    name = "webhook"
    required_session_fields = ("session_id", "url")

    def send_message(self, session: dict[str, Any], message: str, payload: dict[str, Any]) -> None:
        self.validate_session(session)
        headers = session.get("headers") or {}
        body = {
            "session_id": session["session_id"],
            "session_title": session.get("session_title", ""),
            "message": message,
            "payload": payload,
        }
        try:
            import httpx

            response = httpx.post(session["url"], json=body, headers=headers, timeout=30)
            response.raise_for_status()
        except Exception as exc:
            raise AdapterDeliveryError(str(exc)) from exc
