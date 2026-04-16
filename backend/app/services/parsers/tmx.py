from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from lxml import etree

from app.services.parsers.base import ParseResult, Segment, detect_encoding

XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


def _normalize_lang(lang: str) -> str:
    """Normalize language code: lowercase, take primary subtag for comparison."""
    return lang.lower()


def _lang_matches(tuv_lang: str, wanted_lang: str) -> bool:
    """
    Match lang codes case-insensitively.
    'en-US' matches 'en', 'en-US' matches 'en-US', 'en' matches 'en-US'.
    """
    tl = tuv_lang.lower()
    wl = wanted_lang.lower()
    if tl == wl:
        return True
    # Primary subtag match: 'en' matches 'en-us', 'en-us' matches 'en'
    if tl.split("-")[0] == wl.split("-")[0]:
        return True
    return False


def _get_tuv_lang(tuv_elem) -> Optional[str]:
    """Get lang from xml:lang or lang attribute."""
    lang = tuv_elem.get(XML_LANG)
    if lang:
        return lang
    lang = tuv_elem.get("lang")
    return lang


def _serialize_seg(seg_elem) -> str:
    """Serialize <seg> element including all inline tags as a string."""
    parts = []
    if seg_elem.text:
        parts.append(seg_elem.text)
    for child in seg_elem:
        tag_name = etree.QName(child.tag).localname
        attribs = " ".join(f'{k}="{v}"' for k, v in child.attrib.items())
        if attribs:
            open_tag = f"<{tag_name} {attribs}>"
        else:
            open_tag = f"<{tag_name}>"
        parts.append(open_tag)
        if child.text:
            parts.append(child.text)
        # Recursively handle nested children (simplified)
        for grandchild in child:
            gc_name = etree.QName(grandchild.tag).localname
            gc_attribs = " ".join(f'{k}="{v}"' for k, v in grandchild.attrib.items())
            if gc_attribs:
                parts.append(f"<{gc_name} {gc_attribs}>")
            else:
                parts.append(f"<{gc_name}>")
            if grandchild.text:
                parts.append(grandchild.text)
            parts.append(f"</{gc_name}>")
            if grandchild.tail:
                parts.append(grandchild.tail)
        parts.append(f"</{tag_name}>")
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


KNOWN_LANG_CODES = {
    "en", "de", "fr", "es", "it", "pt", "nl", "ru", "pl", "cs", "sk", "hu",
    "ro", "bg", "hr", "sr", "uk", "tr", "ar", "zh", "ja", "ko", "th", "vi",
    "id", "ms", "hi", "fa", "he", "el", "sv", "da", "no", "fi", "et", "lv", "lt",
}


def detect_tmx_languages(path: Path) -> list[str]:
    """Return sorted list of unique primary language subtags found in the TMX file."""
    try:
        tree = etree.parse(str(path))
        root = tree.getroot()
        langs: set[str] = set()
        for elem in root.iter():
            if etree.QName(elem.tag).localname == "tuv":
                raw = elem.get(XML_LANG) or elem.get("lang") or ""
                if raw:
                    langs.add(raw.lower().split("-")[0].split("_")[0])
        return sorted(langs)
    except Exception:
        return []


def parse_tmx(path: Path, source_lang: str, target_lang: str) -> ParseResult:
    warnings: List[str] = []
    encoding = detect_encoding(path)
    encoding_ok = encoding == "utf-8"

    try:
        tree = etree.parse(str(path))
    except etree.XMLSyntaxError as e:
        return ParseResult(
            segments=[],
            warnings=[f"XML parse error: {e}"],
            encoding_ok=encoding_ok,
            source_lang=source_lang,
            target_lang=target_lang,
        )

    root = tree.getroot()
    # Find all <tu> elements (handle namespace)
    ns = root.nsmap.get(None, "")
    if ns:
        tu_elements = root.findall(f".//{{{ns}}}tu")
        tuv_tag = f"{{{ns}}}tuv"
        seg_tag = f"{{{ns}}}seg"
    else:
        tu_elements = root.findall(".//tu")
        tuv_tag = "tuv"
        seg_tag = "seg"

    segments: List[Segment] = []

    for idx, tu in enumerate(tu_elements):
        tuid = tu.get("tuid") or str(idx + 1)
        metadata = dict(tu.attrib)

        # Find tuv elements for source and target
        source_text: Optional[str] = None
        target_text: Optional[str] = None

        for tuv in tu.findall(tuv_tag):
            tuv_lang = _get_tuv_lang(tuv)
            if not tuv_lang:
                continue
            seg = tuv.find(seg_tag)
            if seg is None:
                continue
            text = _serialize_seg(seg)

            if _lang_matches(tuv_lang, source_lang):
                source_text = text
            elif _lang_matches(tuv_lang, target_lang):
                target_text = text

        if source_text is None:
            warnings.append(f"TU '{tuid}' missing source language '{source_lang}' tuv")
            continue
        if target_text is None:
            warnings.append(f"TU '{tuid}' missing target language '{target_lang}' tuv")
            continue

        segments.append(
            Segment(
                id=tuid,
                source=source_text,
                target=target_text,
                source_lang=source_lang,
                target_lang=target_lang,
                metadata=metadata,
            )
        )

    return ParseResult(
        segments=segments,
        warnings=warnings,
        encoding_ok=encoding_ok,
        source_lang=source_lang,
        target_lang=target_lang,
    )
