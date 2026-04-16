from __future__ import annotations

import deepl

from app.services.mt.base import MTEngine


def _map_lang_code(lang: str, is_target: bool = False) -> str:
    """Map generic lang codes to DeepL format."""
    primary = lang.split("-")[0].upper()
    # DeepL uses EN-US or EN-GB for target English; use EN-US as default
    if primary == "EN" and is_target:
        return "EN-US"
    if primary == "PT" and is_target:
        return "PT-BR"
    return primary


class DeepLEngine(MTEngine):
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._translator = deepl.Translator(api_key)

    async def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """Translate text using DeepL."""
        src = _map_lang_code(source_lang, is_target=False)
        tgt = _map_lang_code(target_lang, is_target=True)
        result = self._translator.translate_text(text, source_lang=src, target_lang=tgt)
        return result.text
