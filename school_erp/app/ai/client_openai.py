from __future__ import annotations

from typing import Any

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None


class OpenAIClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = OpenAI(api_key=api_key) if api_key and OpenAI else None

    def chat(self, messages: list[dict[str, str]], model: str = "gpt-4o-mini") -> dict[str, Any]:
        if not self.client:
            content = "AI provider not configured. Returning safe fallback summary."
            return {"content": content, "tool_calls": []}

        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
        )
        choice = response.choices[0].message
        return {
            "content": choice.content or "",
            "tool_calls": choice.tool_calls or [],
        }
