from __future__ import annotations

import requests

from app.services.mt.base import MTEngine

AZURE_TRANSLATE_URL = "https://api.cognitive.microsofttranslator.com/translate"


class AzureEngine(MTEngine):
    def __init__(self, api_key: str, region: str = "global") -> None:
        self._api_key = api_key
        self._region = region

    async def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """Translate text using Azure Cognitive Services Translator."""
        src = source_lang.split("-")[0].lower()
        tgt = target_lang.split("-")[0].lower()

        params = {
            "api-version": "3.0",
            "from": src,
            "to": tgt,
        }
        headers = {
            "Ocp-Apim-Subscription-Key": self._api_key,
            "Ocp-Apim-Subscription-Region": self._region,
            "Content-Type": "application/json",
        }
        body = [{"text": text}]

        response = requests.post(
            AZURE_TRANSLATE_URL,
            params=params,
            headers=headers,
            json=body,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        return data[0]["translations"][0]["text"]
