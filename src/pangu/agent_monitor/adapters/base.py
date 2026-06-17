"""Base interface for third-party agent message adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AdapterDeliveryError(RuntimeError):
    """Raised when an adapter cannot deliver a message."""


class AgentAdapter(ABC):
    name = "base"
    required_session_fields = ("session_id",)

    def validate_session(self, session: dict[str, Any]) -> None:
        missing = [key for key in self.required_session_fields if not session.get(key)]
        if missing:
            raise AdapterDeliveryError(f"missing session fields: {missing}")

    @abstractmethod
    def send_message(self, session: dict[str, Any], message: str, payload: dict[str, Any]) -> None:
        """Send a user-like message into an existing agent session."""

