from sentinel.agents import analyst, auditor, executor, risk, watcher

AGENT_MODULES = [watcher, analyst, risk, executor, auditor]

__all__ = ["AGENT_MODULES", "watcher", "analyst", "risk", "executor", "auditor"]
