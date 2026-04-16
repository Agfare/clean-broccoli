from __future__ import annotations

from google.cloud import translate_v2 as google_translate

from app.services.mt.base import MTEngine


class GoogleEngine(MTEngine):
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = google_translate.Client(
            client_options={"api_key": api_key}
        )

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """Translate text using Google Cloud Translation."""
        result = self._client.translate(
            text,
            source_language=source_lang.split("-")[0].lower(),
            target_language=target_lang.split("-")[0].lower(),
        )
        return result["translatedText"]
