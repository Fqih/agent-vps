"""Task kinds the worker knows. Each handler returns (text, model)."""
from __future__ import annotations

from hub import llm


def llm_prompt(task: dict, ctx: dict) -> tuple:
    payload = task["payload"]
    messages = [{"role": "system", "content": payload["system"]}] if payload.get("system") else []
    messages.append({"role": "user", "content": payload["prompt"]})
    return llm.chat(task["chain"], messages, ctx["cfg"])


HANDLERS = {"llm.prompt": llm_prompt}
