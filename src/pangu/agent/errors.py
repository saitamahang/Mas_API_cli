"""Structured errors for pangu-agent."""

from __future__ import annotations

from typing import Any


class AgentError(Exception):
    """Error with a stable code and next-action hint."""

    def __init__(
        self,
        code: str,
        message: str,
        next_action: str = "",
        details: dict[str, Any] | None = None,
    ):
        self.code = code
        self.message = message
        self.next_action = next_action
        self.details = details or {}
        super().__init__(message)
