"""Structured errors for pangu-agent."""

from __future__ import annotations


class AgentError(Exception):
    """Error with a stable code and next-action hint."""

    def __init__(self, code: str, message: str, next_action: str = ""):
        self.code = code
        self.message = message
        self.next_action = next_action
        super().__init__(message)

