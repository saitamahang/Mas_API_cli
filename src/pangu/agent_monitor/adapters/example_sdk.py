"""Example adapter showing how to integrate a third-party agent SDK.

Replace ``ExampleAgentClient`` with the real SDK client from the target agent
platform. The only required contract is that the SDK can send a message to an
existing session identified by ``session_id``.
"""

from __future__ import annotations

import os
from typing import Any

from pangu.agent_monitor.adapters.base import AdapterDeliveryError, AgentAdapter


class ExampleAgentClient:
    """Small illustrative SDK facade used by the sample adapter.

    Real adapters should import the vendor SDK directly and remove this class.
    """

    def __init__(self, endpoint: str, api_key: str):
        self.endpoint = endpoint
        self.api_key = api_key

    def send_message(self, *, session_id: str, content: str, metadata: dict[str, Any]) -> None:
        if not self.endpoint or not self.api_key:
            raise AdapterDeliveryError("EXAMPLE_AGENT_ENDPOINT and EXAMPLE_AGENT_API_KEY are required")
        raise AdapterDeliveryError("example_agent is a template adapter; replace it with a real SDK call")


class ExampleAgentAdapter(AgentAdapter):
    name = "example_agent"
    required_session_fields = ("session_id",)

    def __init__(self) -> None:
        self.client = ExampleAgentClient(
            endpoint=os.environ.get("EXAMPLE_AGENT_ENDPOINT", ""),
            api_key=os.environ.get("EXAMPLE_AGENT_API_KEY", ""),
        )

    def send_message(self, session: dict[str, Any], message: str, payload: dict[str, Any]) -> None:
        self.validate_session(session)
        self.client.send_message(
            session_id=session["session_id"],
            content=message,
            metadata={
                "source": "pangu-agent-monitor",
                "session_title": session.get("session_title"),
                "run_id": payload.get("run_id"),
                "kind": payload.get("kind"),
                "target_id": payload.get("target_id"),
                "terminal_status": payload.get("terminal_status"),
                "next_action": payload.get("next_action"),
            },
        )

