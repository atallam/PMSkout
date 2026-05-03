"""
Skout — Claude Provider
Supports standard and deep_research (extended thinking) modes.
"""
from __future__ import annotations
import os
from typing import Dict, Optional
from .base import BaseLLMProvider


class ClaudeProvider(BaseLLMProvider):
    """
    Anthropic Claude provider.
    Deep research mode activates extended thinking for deeper reasoning.
    """

    def __init__(self, config: Dict):
        self.config = config
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic
                api_key = os.getenv(
                    self.config["providers"]["claude"]["api_key_env"]
                )
                self._client = anthropic.Anthropic(api_key=api_key)
            except ImportError:
                raise ImportError("anthropic package not installed. Run: pip install anthropic")
        return self._client

    def is_available(self) -> bool:
        api_key_env = self.config["providers"]["claude"]["api_key_env"]
        return bool(os.getenv(api_key_env))

    def generate(self, prompt: str, system: str = "", mode: str = "standard") -> str:
        client = self._get_client()
        mode_cfg = self.config["modes"].get(mode, self.config["modes"]["standard"])

        model = mode_cfg["model"]
        max_tokens = mode_cfg["max_tokens"]
        temperature = mode_cfg.get("temperature", 0.7)
        use_thinking = mode_cfg.get("extended_thinking", False)
        thinking_budget = mode_cfg.get("thinking_budget_tokens", 8000)

        messages = [{"role": "user", "content": prompt}]

        if use_thinking:
            # Extended thinking — Claude reasons before responding
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                thinking={
                    "type": "enabled",
                    "budget_tokens": thinking_budget,
                },
                system=system,
                messages=messages,
            )
        else:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=messages,
            )

        # Extract text blocks only (skip thinking blocks)
        text_parts = []
        for block in response.content:
            if getattr(block, "type", None) == "text":
                text_parts.append(block.text)
        return "\n".join(text_parts)
