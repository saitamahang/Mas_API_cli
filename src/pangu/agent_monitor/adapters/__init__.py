"""Agent message delivery adapters."""

from pangu.agent_monitor.adapters.base import AgentAdapter, AdapterDeliveryError


ADAPTERS = {
    "codeagent": "pangu.agent_monitor.adapters.codeagent.CodeAgentAdapter",
    "example_agent": "pangu.agent_monitor.adapters.example_sdk.ExampleAgentAdapter",
    "webhook": "pangu.agent_monitor.adapters.webhook.WebhookAdapter",
}


def create_adapter(name: str) -> AgentAdapter:
    import importlib

    adapter_path = ADAPTERS.get(name)
    if not adapter_path:
        raise AdapterDeliveryError(f"unknown adapter: {name}")
    module_name, class_name = adapter_path.rsplit(".", 1)
    adapter_cls = getattr(importlib.import_module(module_name), class_name)
    return adapter_cls()


__all__ = ["AgentAdapter", "AdapterDeliveryError", "create_adapter"]
