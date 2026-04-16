from __future__ import annotations

import difflib
from abc import ABC, abstractmethod


class MTEngine(ABC):
    @abstractmethod
    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """Translate text from source_lang to target_lang."""
        ...

    def similarity_score(self, hypothesis: str, reference: str) -> float:
        """
        Compute similarity between hypothesis and reference translation.
        Default implementation uses difflib.SequenceMatcher.
        Returns a float between 0.0 and 1.0.
        """
        return difflib.SequenceMatcher(
            None, hypothesis.lower(), reference.lower()
        ).ratio()
