"""Optional, lazily loaded semantic domain classifier for job text.

Set JOB_SEMANTIC_MODEL to a locally available Sentence Transformers model to enable it.
No model is imported or downloaded on the default rule-based path.
"""

import os
from typing import Sequence


class SentenceTransformerDomainMatcher:
    """Best-effort semantic classifier with deterministic fallback handled by the caller."""

    def __init__(self, model_name: str | None = None, minimum_similarity: float = 0.55) -> None:
        self.model_name = model_name if model_name is not None else os.getenv("JOB_SEMANTIC_MODEL", "").strip()
        self.minimum_similarity = minimum_similarity
        self._model = None
        self._attempted = False

    @property
    def enabled(self) -> bool:
        return bool(self.model_name)

    def classify_domain(self, text: str, candidate_domains: Sequence[str]) -> str | None:
        """Return a known domain only when an explicitly configured model has sufficient similarity."""
        if not self.enabled or not text.strip() or not candidate_domains:
            return None
        if not self._attempted:
            self._attempted = True
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.model_name)
            except Exception:
                # Model loading can fail when weights are not local or are unavailable.
                self._model = None
        if self._model is None:
            return None
        descriptions = [f"A job role in {domain}." for domain in candidate_domains]
        try:
            embeddings = self._model.encode([text, *descriptions], normalize_embeddings=True)
            text_embedding = embeddings[0]
            scores = [float(text_embedding @ embeddings[index + 1]) for index in range(len(candidate_domains))]
        except Exception:
            return None
        best = max(range(len(scores)), key=scores.__getitem__)
        if scores[best] < self.minimum_similarity:
            return None
        return candidate_domains[best]
