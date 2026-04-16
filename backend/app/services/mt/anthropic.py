from __future__ import annotations

import anthropic as anthropic_lib

from app.services.mt.base import MTEngine


class AnthropicEngine(MTEngine):
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = anthropic_lib.Anthropic(api_key=api_key)

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """Translate text using Claude Haiku."""
        prompt = (
            f"You are a translator. Translate the following text from {source_lang} to {target_lang}. "
            f"Return ONLY the translation, no explanation:\n\n{text}"
        )
        response = self._client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()

    def similarity_score(self, hypothesis: str, reference: str) -> float:
        """Use Claude to evaluate translation quality."""
        # Note: source and source_lang/target_lang are not available here at base level,
        # so we use the hypothesis as the MT output and reference as the stored target.
        prompt = (
            f"Rate the translation quality from 0.0 to 1.0.\n"
            f"MT Translation: {hypothesis}\n"
            f"Reference: {reference}\n"
            f"Return ONLY a float between 0.0 and 1.0."
        )
        try:
            response = self._client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=10,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            score = float(text)
            return max(0.0, min(1.0, score))
        except (ValueError, IndexError, Exception):
            # Fall back to difflib on any error
            import difflib
            return difflib.SequenceMatcher(None, hypothesis.lower(), reference.lower()).ratio()

    async def score_translation(
        self,
        source: str,
        target: str,
        reference: str,
        source_lang: str,
        target_lang: str,
    ) -> float:
        """Full Claude-based quality evaluation with context."""
        prompt = (
            f"Rate the translation quality from 0.0 to 1.0.\n"
            f"Source ({source_lang}): {source}\n"
            f"Translation ({target_lang}): {target}\n"
            f"Reference: {reference}\n"
            f"Return ONLY a float between 0.0 and 1.0."
        )
        try:
            response = self._client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=10,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            score = float(text)
            return max(0.0, min(1.0, score))
        except (ValueError, IndexError, Exception):
            import difflib
            return difflib.SequenceMatcher(None, target.lower(), reference.lower()).ratio()
