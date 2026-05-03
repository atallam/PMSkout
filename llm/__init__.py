"""
Skout — LLM Abstraction Layer
==============================
Provider-agnostic, config-driven LLM interface for Product Skout.

Exports:
  BaseLLMProvider   — Abstract base class all providers must implement.
  ClaudeProvider    — Anthropic Claude (standard + extended-thinking modes).
  OpenAIProvider    — OpenAI GPT-4o / GPT-4o-mini with chain-of-thought.
  RuleBasedProvider — Offline fallback; returns sentinel "__RULE_BASED__".
  LLMFactory        — Reads llm_config.yaml and returns the best available provider.

Usage:
    from llm.factory import LLMFactory
    factory  = LLMFactory("config/llm_config.yaml")
    provider = factory.get_provider()          # auto-selects best available
    text     = provider.generate(prompt, system=sys_prompt, mode="standard")

Provider selection priority (configurable in llm_config.yaml):
  Claude → OpenAI → RuleBased (always available)
"""
