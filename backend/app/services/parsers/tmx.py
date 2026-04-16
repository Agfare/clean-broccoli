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


def iter_tmx(
    path: Path,
    source_lang: str,
    target_lang: str,
    warnings: Optional[List[str]] = None,
    progress_callback=None,
):
    """Yield Segment objects one at a time from a TMX file.

    Appends parse warnings to *warnings* (if provided) rather than raising.
    Calls *progress_callback(n)* every 5 000 segments if provided.
    Memory: only one Segment exists at a time — safe for 100k+ segment files.
    """
    if warnings is None:
        warnings = []

    ns = _detect_tmx_namespace(path)
    tu_tag = f"{{{ns}}}tu" if ns else "tu"
    tuv_tag = f"{{{ns}}}tuv" if ns else "tuv"
    seg_tag = f"{{{ns}}}seg" if ns else "seg"

    try:
        context = etree.iterparse(str(path), events=("end",), tag=tu_tag, recover=True)
        idx = 0
        count = 0

        for _event, elem in context:
            idx += 1
            tuid = elem.get("tuid") or str(idx)

            source_text: Optional[str] = None
            target_text: Optional[str] = None

            for tuv in elem.findall(tuv_tag):
                tuv_lang = _get_tuv_lang(tuv)
                if not tuv_lang:
                    continue
                seg_elem = tuv.find(seg_tag)
                if seg_elem is None:
                    continue
                text = _serialize_seg(seg_elem)
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
                count += 1
                if progress_callback is not None and count % 5_000 == 0:
                    progress_callback(count)
                yield Segment(
                    id=tuid,
                    source=source_text,
                    target=target_text,
                    source_lang=source_lang,
                    target_lang=target_lang,
                )

            # Free the processed <tu> element immediately — keeps memory flat
            parent = elem.getparent()
            elem.clear()
            if parent is not None:
                parent.remove(elem)

    except etree.XMLSyntaxError as e:
        warnings.append(f"XML parse error: {e}")


def parse_tmx(
    path: Path,
    source_lang: str,
    target_lang: str,
    progress_callback=None,
) -> ParseResult:
    """Parse a TMX file and return all segments as a list.

    For large files prefer *iter_tmx* which yields one Segment at a time.
    """
    encoding = detect_encoding(path)
    encoding_ok = encoding == "utf-8"
    warnings: List[str] = []
    segments = list(
        iter_tmx(path, source_lang, target_lang, warnings=warnings, progress_callback=progress_callback)
    )
    return ParseResult(
        segments=segments,
        warnings=warnings,
        encoding_ok=encoding_ok,
        source_lang=source_lang,
        target_lang=target_lang,
    )
