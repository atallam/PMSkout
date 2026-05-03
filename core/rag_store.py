"""
Skout — Pattern #4: Domain Knowledge RAG Store
================================================
Keyword-based retrieval from domain_knowledge/ files.
Returns relevant knowledge chunks that the evaluation agents can cite.

No vector DB required — designed for v1 with easy upgrade path to
sentence-transformers or ChromaDB later.

Usage:
    store = RAGStore()
    chunks = store.query("reduce safety stock lean inventory")
    for chunk in chunks:
        print(chunk.source, chunk.content)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

_KNOWLEDGE_DIR = Path(__file__).parent.parent / "domain_knowledge"


@dataclass
class KnowledgeChunk:
    chunk_id: str
    source: str           # filename or logical source name
    category: str         # "scor", "kpi", "failure_pattern", "general"
    content: str          # The actual knowledge text
    keywords: List[str]   # Keywords that make this chunk findable
    relevance: float = 0.0  # Score assigned during retrieval

    def to_dict(self) -> Dict:
        return {
            "chunk_id": self.chunk_id,
            "source": self.source,
            "category": self.category,
            "content": self.content,
            "keywords": self.keywords,
            "relevance": round(self.relevance, 3),
        }


class RAGStore:
    """
    Lightweight keyword-based knowledge retrieval store.
    Loads domain_knowledge/ files on first query (lazy load).

    Upgrade path:
      - Replace _score_chunk() with cosine similarity over sentence embeddings
      - Replace _chunks with a ChromaDB or Qdrant collection
    """

    def __init__(self, knowledge_dir: Optional[Path] = None):
        self._dir = knowledge_dir or _KNOWLEDGE_DIR
        self._chunks: List[KnowledgeChunk] = []
        self._loaded = False

    # ---------------------------------------------------------------- #
    # Loading
    # ---------------------------------------------------------------- #

    def load(self) -> None:
        """Load all knowledge files into chunks."""
        self._chunks = []
        self._load_scor_framework()
        self._load_kpi_benchmarks()
        self._load_failure_patterns()
        self._loaded = True

    def _load_scor_framework(self) -> None:
        """Parse scor_framework.md into per-domain chunks."""
        path = self._dir / "scor_framework.md"
        if not path.exists():
            return

        with open(path, encoding="utf-8") as f:
            content = f.read()

        # Split by ## headings (PLAN, SOURCE, MAKE, etc.)
        sections = re.split(r"\n## ", content)
        for i, section in enumerate(sections):
            if not section.strip():
                continue
            lines = section.strip().splitlines()
            domain = lines[0].strip().split()[0].rstrip(":") if lines else f"section_{i}"
            chunk_text = section.strip()[:800]  # Cap at 800 chars per chunk

            keywords = self._extract_keywords_from_text(chunk_text)
            # Add domain-specific keywords
            domain_keywords = {
                "PLAN": ["planning", "forecast", "s&op", "demand", "inventory", "capacity"],
                "SOURCE": ["procurement", "supplier", "sourcing", "contract", "spend", "purchasing"],
                "MAKE": ["manufacturing", "production", "quality", "oee", "assembly", "wip"],
                "DELIVER": ["logistics", "delivery", "warehouse", "transport", "customs", "last mile"],
                "RETURN": ["return", "reverse", "warranty", "repair", "refurbish", "mro"],
                "ENABLE": ["compliance", "risk", "fraud", "governance", "data", "regulation"],
            }
            keywords += domain_keywords.get(domain.upper(), [])

            self._chunks.append(KnowledgeChunk(
                chunk_id=f"scor_{domain.lower()}",
                source="SCOR Framework (APICS v12)",
                category="scor",
                content=chunk_text,
                keywords=list(set(keywords)),
            ))

    def _load_kpi_benchmarks(self) -> None:
        """Load KPI benchmarks as queryable chunks."""
        path = self._dir / "kpi_benchmarks.json"
        if not path.exists():
            return

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        for kpi_id, kpi_data in data.get("kpis", {}).items():
            kpi_name = kpi_id.replace("_", " ").title()
            # Build a human-readable summary
            ranges = kpi_data.get("industry_ranges", {})
            default_range = ranges.get("default", {})
            red_flags = "\n".join(f"  - {r}" for r in kpi_data.get("red_flag_changes", []))

            content = (
                f"KPI: {kpi_name}\n"
                f"Description: {kpi_data.get('description', '')}\n"
                f"Unit: {kpi_data.get('unit', '')}\n"
                f"Direction: {kpi_data.get('direction', '')}\n"
                f"Default safe range: {default_range.get('min', '?')}-{default_range.get('max', '?')}"
                f" (ideal: {default_range.get('ideal', '?')})\n"
            )
            if red_flags:
                content += f"Red flag signals:\n{red_flags}\n"

            self._chunks.append(KnowledgeChunk(
                chunk_id=f"kpi_{kpi_id}",
                source="APICS/ASCM KPI Benchmarks",
                category="kpi",
                content=content,
                keywords=kpi_data.get("keywords", []) + [kpi_name.lower(), kpi_id],
            ))

    def _load_failure_patterns(self) -> None:
        """Load failure patterns as knowledge chunks."""
        path = self._dir / "failure_patterns.json"
        if not path.exists():
            return

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        for pattern in data.get("failure_patterns", []):
            content = (
                f"Failure Pattern: {pattern['name']}\n"
                f"Severity: {pattern.get('severity', 'MEDIUM')}\n"
                f"Description: {pattern['description']}\n"
                f"Real-world example: {pattern.get('example_failure', '')}\n"
                f"Safe conditions: {'; '.join(pattern.get('safe_conditions', []))}\n"
            )

            self._chunks.append(KnowledgeChunk(
                chunk_id=f"fp_{pattern['id']}",
                source="Supply Chain Failure Pattern Library",
                category="failure_pattern",
                content=content,
                keywords=pattern.get("triggers", []) + [pattern["name"].lower()],
            ))

    # ---------------------------------------------------------------- #
    # Retrieval
    # ---------------------------------------------------------------- #

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        category_filter: Optional[str] = None,
        min_relevance: float = 0.1,
    ) -> List[KnowledgeChunk]:
        """
        Find the most relevant knowledge chunks for a query.

        Args:
            query_text: Free-text query (e.g. the recommendation text)
            top_k: Max number of results
            category_filter: Optional filter by category ("scor", "kpi", "failure_pattern")
            min_relevance: Minimum relevance threshold (0-1)

        Returns:
            List of KnowledgeChunk objects sorted by relevance (highest first)
        """
        if not self._loaded:
            self.load()

        if not query_text.strip():
            return []

        query_tokens = set(re.findall(r"\b\w{3,}\b", query_text.lower()))
        scored: List[KnowledgeChunk] = []

        for chunk in self._chunks:
            if category_filter and chunk.category != category_filter:
                continue
            score = self._score_chunk(chunk, query_tokens, query_text)
            if score >= min_relevance:
                chunk.relevance = score
                scored.append(chunk)

        scored.sort(key=lambda c: c.relevance, reverse=True)
        return scored[:top_k]

    def _score_chunk(
        self,
        chunk: KnowledgeChunk,
        query_tokens: set,
        raw_query: str,
    ) -> float:
        """
        Score a chunk's relevance to the query.
        Higher = more relevant (0.0 - 1.0 scale).

        Scoring weights:
          - Keyword match (exact): 0.6
          - Content token overlap: 0.3
          - Phrase match bonus: 0.1
        """
        score = 0.0

        # Keyword matching
        chunk_keywords_lower = [k.lower() for k in chunk.keywords]
        kw_matches = sum(
            1 for token in query_tokens
            if any(token in kw for kw in chunk_keywords_lower)
        )
        if chunk_keywords_lower:
            score += 0.6 * min(1.0, kw_matches / max(1, len(chunk_keywords_lower) * 0.3))

        # Content token overlap
        content_tokens = set(re.findall(r"\b\w{3,}\b", chunk.content.lower()))
        overlap = len(query_tokens & content_tokens)
        if content_tokens:
            score += 0.3 * min(1.0, overlap / max(1, len(query_tokens)))

        # Phrase match bonus
        raw_lower = raw_query.lower()
        for kw in chunk.keywords:
            if len(kw) > 5 and kw.lower() in raw_lower:
                score += 0.1
                break

        return min(1.0, score)

    @staticmethod
    def _extract_keywords_from_text(text: str) -> List[str]:
        """Extract meaningful keywords from text."""
        stop_words = {
            "the", "and", "for", "are", "but", "not", "with", "this",
            "that", "from", "have", "been", "will", "their", "more",
            "when", "than", "into", "its", "can", "all", "any", "may"
        }
        tokens = re.findall(r"\b[a-z]{4,}\b", text.lower())
        return list(set(t for t in tokens if t not in stop_words))[:20]

    def get_chunks_by_category(self, category: str) -> List[KnowledgeChunk]:
        """Get all chunks of a specific category."""
        if not self._loaded:
            self.load()
        return [c for c in self._chunks if c.category == category]

    def stats(self) -> Dict:
        """Return store statistics."""
        if not self._loaded:
            self.load()
        by_cat: Dict[str, int] = {}
        for c in self._chunks:
            by_cat[c.category] = by_cat.get(c.category, 0) + 1
        return {
            "total_chunks": len(self._chunks),
            "by_category": by_cat,
            "knowledge_dir": str(self._dir),
        }
