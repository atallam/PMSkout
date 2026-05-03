"""
Skout — Base LLM Provider Interface
All providers implement this interface, keeping core logic LLM-agnostic.
"""
from abc import ABC, abstractmethod
from typing import Optional


class BaseLLMProvider(ABC):
    """Abstract base for all LLM providers."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system: str = "",
        mode: str = "standard",
    ) -> str:
        """
        Generate text from a prompt.

        Args:
            prompt: The user message / task description
            system: System prompt (provider role and instructions)
            mode: "standard" or "deep_research"
        Returns:
            Generated text string
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this provider can make API calls right now."""
        ...
