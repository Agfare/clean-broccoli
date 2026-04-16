from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from lxml import etree

from app.services.parsers.base import ParseResult, Segment, detect_encoding

XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
MAX_WARNINGS = 200


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
    return tuv_elem.get(XML_LANG) or tuv_elem.get("lang")


def _serialize_seg(seg_elem) -> str:
    """Serialize <seg> element including all inline tags as a string."""
    parts = []
    if seg_elem.text:
        parts.append(seg_elem.text)
    for child in seg_elem:
        tag_name = etree.QName(child.tag).localname
        attribs = " ".join(f'{k}="{v}"' for k, v in child.attrib.items())
        open_tag = f"<{tag_name} {attribs}>" if attribs else f"<{tag_name}>"
        parts.append(open_tag)
        if child.text:
            parts.append(child.text)
        for grandchild in child:
            gc_name = etree.QName(grandchild.tag).localname
            gc_attribs = " ".join(f'{k}="{v}"' for k, v in grandchild.attrib.items())
            parts.append(f"<{gc_name} {gc_attribs}>" if gc_attribs else f"<{gc_name}>")
            if grandchild.text:
                parts.append(grandchild.text)
            parts.append(f"</{gc_name}>")
            if grandchild.tail:
                parts.append(grandchild.tail)
        parts.append(f"</{tag_name}>")
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def _detect_tmx_namespace(path: Path) -> Optional[str]:
    """Peek at the first XML element to determine the namespace used in the file."""
    try:
        for _event, elem in etree.iterparse(str(path), events=("start",)):
            return etree.QName(elem.tag).namespace
    except Exception:
        return None


KNOWN_LANG_CODES = {
    "en", "de", "fr", "es", "it", "pt", "nl", "ru", "pl", "cs", "sk", "hu",
    "ro", "bg", "hr", "sr", "uk", "tr", "ar", "zh", "ja", "ko", "th", "vi",
    "id", "ms", "hi", "fa", "he", "el", "sv", "da", "no", "fi", "et", "lv", "lt",
}


def detect_tmx_languages(path: Path, max_scan: int = 500) -> list[str]:
    """Return sorted list of unique primary language subtags found in the TMX file.

    Scans at most *max_scan* <tuv> elements so detection stays fast even on
    very large files (100 MB+).  Language codes appear in every <tu>, so a
    few hundred elements are always enough to find all of them.
    """
    try:
        ns = _detect_tmx_namespace(path)
        tuv_tag = f"{{{ns}}}tuv" if ns else "tuv"
        langs: set[str] = set()
        scanned = 0
        for _event, elem in etree.iterparse(str(path), events=("end",), tag=tuv_tag, recover=True):
            raw = elem.get(XML_LANG) or elem.get("lang") or ""
            if raw:
                langs.add(raw.lower().split("-")[0].split("_")[0])
            parent = elem.getparent()
            elem.clear()
            if parent is not None:
                parent.remove(elem)
            scanned += 1
            if scanned >= max_scan:
                break
        return sorted(langs)
    except Exception:
        return []


def parse_tmx(
    path: Path,
    source_lang: str,
    target_lang: str,
    progress_callback=None,
) -> ParseResult:
    """Parse a TMX file and return segments.

    *progress_callback*, if provided, is called as ``callback(n_parsed: int)``
    every 5 000 segments so the caller can emit live progress updates.
    """
    warnings: List[str] = []
    encoding = detect_encoding(path)
    encoding_ok = encoding == "utf-8"
    segments: List[Segment] = []

    # Detect namespace once up front so iterparse can filter by exact tag
    ns = _detect_tmx_namespace(path)
    tu_tag = f"{{{ns}}}tu" if ns else "tu"
    tuv_tag = f"{{{ns}}}tuv" if ns else "tuv"
    seg_tag = f"{{{ns}}}seg" if ns else "seg"

    try:
        # tag= filter means lxml only fires "end" events for <tu> elements,
        # skipping every other node — much faster for large files.
        context = etree.iterparse(str(path), events=("end",), tag=tu_tag, recover=True)
        idx = 0

        for _event, elem in context:
            idx += 1
            tuid = elem.get("tuid") or str(idx)
            metadata = dict(elem.attrib)

            source_text: Optional[str] = None
            target_text: Optional[str] = None

            for tuv in elem.findall(tuv_tag):
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
                if len(warnings) < MAX_WARNINGS:
                    warnings.append(f"TU '{tuid}' missing source language '{source_lang}' tuv")
            elif target_text is None:
                if len(warnings) < MAX_WARNINGS:
                    warnings.append(f"TU '{tuid}' missing target language '{target_lang}' tuv")
            else:
                segments.append(
                    Segment(
                        id=tuid,
                        source=source_text,
                        target=target_text,
                        source_lang=source_lang,
                        target_lang=target_lang,
                        # metadata deliberately omitted — TMX attributes (~500 B/segment)
                        # are never read by any exporter and waste ~80 MB on large files.
                    )
                )
                if progress_callback is not None and len(segments) % 5_000 == 0:
                    progress_callback(len(segments))

            # Free the processed <tu> element immediately to keep memory flat
            parent = elem.getparent()
            elem.clear()
            if parent is not None:
                parent.remove(elem)

    except etree.XMLSyntaxError as e:
        return ParseResult(
            segments=[],
            warnings=[f"XML parse error: {e}"],
            encoding_ok=encoding_ok,
            source_lang=source_lang,
            target_lang=target_lang,
        )

    return ParseResult(
        segments=segments,
        warnings=warnings,
        encoding_ok=encoding_ok,
        source_lang=source_lang,
        target_lang=target_lang,
    )
