"""
Skout — OpenAI Provider
Standard mode uses gpt-4o-mini; deep_research uses gpt-4o with chain-of-thought.
"""
from __future__ import annotations
import os
from typing import Dict
from .base import BaseLLMProvider


class OpenAIProvider(BaseLLMProvider):

    def __init__(self, config: Dict):
        self.config = config
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                api_key = os.getenv(
                    self.config["providers"]["openai"]["api_key_env"]
                )
                self._client = OpenAI(api_key=api_key)
            except ImportError:
                raise ImportError("openai package not installed. Run: pip install openai")
        return self._client

    def is_available(self) -> bool:
        api_key_env = self.config["providers"]["openai"]["api_key_env"]
        return bool(os.getenv(api_key_env))

    def generate(self, prompt: str, system: str = "", mode: str = "standard") -> str:
        client = self._get_client()
        mode_cfg = self.config["modes"].get(mode, self.config["modes"]["standard"])

        # Use model overrides for OpenAI if specified
        overrides = self.config["providers"]["openai"].get("model_overrides", {})
        model = overrides.get(mode, mode_cfg["model"])
        max_tokens = mode_cfg["max_tokens"]
        temperature = mode_cfg.get("temperature", 0.7)

        messages = []
        if system:
            messages.append({"role": "system", "content": system})

        # For deep_research mode: prepend chain-of-thought instruction
        if mode == "deep_research":
            cot_prefix = (
                "Think step by step. Generate multiple competing hypotheses. "
                "Consider counter-arguments. Evaluate second-order effects. "
                "Then provide your structured response.\n\n"
            )
            messages.append({"role": "user", "content": cot_prefix + prompt})
        else:
            messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=messages,
        )
        return response.choices[0].message.content or ""
