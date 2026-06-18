"""Default CodeAgent adapter template.

This adapter reserves the stable adapter name ``codeagent``. Replace the
``CodeAgentClient`` facade with the real CodeAgent SDK integration in the
deployment environment.
"""

from __future__ import annotations

import os
from typing import Any

from pangu.agent_monitor.adapters.base import AdapterDeliveryError, AgentAdapter


class CodeAgentClient:
    """Template facade for a real CodeAgent SDK client."""

    def __init__(self, endpoint: str, api_key: str):
        self.endpoint = endpoint
        self.api_key = api_key

    def send_message(self, *, session_id: str, content: str, metadata: dict[str, Any]) -> None:
        if not self.endpoint or not self.api_key:
            raise AdapterDeliveryError("CODEAGENT_ENDPOINT and CODEAGENT_API_KEY are required")
        raise AdapterDeliveryError("codeagent adapter is a template; replace CodeAgentClient with the real SDK call")


class CodeAgentAdapter(AgentAdapter):
    name = "codeagent"
    required_session_fields = ("session_id",)

    def __init__(self) -> None:
        self.client = CodeAgentClient(
            endpoint=os.environ.get("CODEAGENT_ENDPOINT", ""),
            api_key=os.environ.get("CODEAGENT_API_KEY", ""),
        )

    def send_message(self, session: dict[str, Any], message: str, payload: dict[str, Any]) -> None:
        self.validate_session(session)
        self.client.send_message(
            session_id=session["session_id"],
            content=message,
            metadata={
                "source": "pangu-agent-monitor",
                "run_id": payload.get("run_id"),
                "kind": payload.get("kind"),
                "target_id": payload.get("target_id"),
                "terminal_status": payload.get("terminal_status"),
                "next_action": payload.get("next_action"),
            },
        )
