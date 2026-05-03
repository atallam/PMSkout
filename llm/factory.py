"""
Skout — LLM Provider Factory
Selects the right provider based on llm_config.yaml and available API keys.
Falls back gracefully: Claude → OpenAI → rule-based.
"""
from __future__ import annotations
import yaml
from pathlib import Path
from typing import Optional
from .base import BaseLLMProvider
from .claude_provider import ClaudeProvider
from .openai_provider import OpenAIProvider


class RuleBasedProvider(BaseLLMProvider):
    """
    No-LLM fallback — returns a message indicating LLM is unavailable.
    The research planner uses rule-based templates when this is active.
    """
    def is_available(self) -> bool:
        """Always returns True — the rule-based provider requires no API key."""
        return True

    def generate(self, prompt: str, system: str = "", mode: str = "standard") -> str:
        """
        Return the sentinel string "__RULE_BASED__" so callers know to use
        template/heuristic logic instead of parsed LLM output.
        """
        return "__RULE_BASED__"


class LLMFactory:
    """
    Returns the best available LLM provider.

    Priority order (configurable):
      1. Provider set in llm_config.yaml
      2. Fallback chain: claude → openai → rule_based
    """

    def __init__(self, config_path: str = "config/llm_config.yaml"):
        """
        Load LLM configuration from YAML.

        Args:
            config_path: Path to llm_config.yaml. Must contain `providers`,
                         `modes`, and optionally `thresholds` and `default_mode` keys.

        Raises:
            FileNotFoundError: If the config file does not exist.
        """
        p = Path(config_path)
        if not p.exists():
            raise FileNotFoundError(f"LLM config not found: {config_path}")
        with open(p, encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

    def get_provider(
        self,
        preferred: Optional[str] = None,
    ) -> BaseLLMProvider:
        """
        Get an available provider.
        preferred: force a specific provider ("claude", "openai", "rule_based")
        """
        target = preferred or self.config.get("modes", {}).get(
            self.config.get("default_mode", "standard"), {}
        ).get("provider", "claude")

        candidates = [target, "claude", "openai", "rule_based"]
        seen = set()

        for name in candidates:
            if name in seen:
                continue
            seen.add(name)

            if name == "claude":
                p = ClaudeProvider(self.config)
                if p.is_available():
                    return p

            elif name == "openai":
                p = OpenAIProvider(self.config)
                if p.is_available():
                    return p

            elif name == "rule_based":
                return RuleBasedProvider()

        return RuleBasedProvider()

    def get_mode_for_score(self, score: float) -> str:
        """Determine the LLM mode based on verdict score."""
        thresholds = self.config.get("thresholds", {})
        deep_threshold = thresholds.get("auto_deep_research", 80)
        std_threshold = thresholds.get("auto_standard", 60)

        if score >= deep_threshold:
            return "deep_research"
        elif score >= std_threshold:
            return "standard"
        else:
            return "quick_scan"
