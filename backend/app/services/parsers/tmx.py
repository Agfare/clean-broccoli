"""TMX parser.

Uses Python's stdlib ``xml.etree.ElementTree`` (expat) for iterparse instead
of lxml.  lxml's C-level iterparse with ``recover=True`` has known instability
on Windows when it encounters certain XML content (null bytes, unusual inline
tags, encoding issues in specific segments) and hard-crashes the process with
no catchable Python exception.  stdlib ET raises a proper ``ParseError`` for
malformed XML, keeps the process alive, and appends a warning so the job can
still complete with partial results.

The TMX *exporter* (TmxWriter in exporters/tmx.py) still uses lxml's xmlfile
for efficient streaming output — that is unaffected by this change.
"""
from __future__ import annotations

import xml.etree.ElementTree as _ET
from pathlib import Path
from typing import Generator, List, Optional

from app.services.parsers.base import ParseResult, Segment, detect_encoding

# xml:lang attribute name in Clark notation
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
MAX_WARNINGS = 200


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _local(tag: str) -> str:
    """Strip Clark-notation namespace from an XML tag or attribute name."""
    return tag.split("}")[-1] if "}" in tag else tag


def _lang_matches(tuv_lang: str, wanted_lang: str) -> bool:
    """Match lang codes case-insensitively, allowing primary-subtag matching.

    'en-US' matches 'en', 'en' matches 'en-US', etc.
    """
    tl = tuv_lang.lower()
    wl = wanted_lang.lower()
    if tl == wl:
        return True
    return tl.split("-")[0] == wl.split("-")[0]


def _serialize_seg(seg_elem) -> str:
    """Serialize a <seg> element including all inline tags as a string.

    Works with both lxml *and* stdlib ElementTree element objects (the tag
    local-name extraction differs between the two APIs).
    """
    parts: List[str] = []
    if seg_elem.text:
        parts.append(seg_elem.text)
    for child in seg_elem:
        tag_name = _local(child.tag)
        attribs = " ".join(f'{_local(k)}="{v}"' for k, v in child.attrib.items())
        parts.append(f"<{tag_name} {attribs}>" if attribs else f"<{tag_name}>")
        if child.text:
            parts.append(child.text)
        for grandchild in child:
            gc_name = _local(grandchild.tag)
            gc_attribs = " ".join(
                f'{_local(k)}="{v}"' for k, v in grandchild.attrib.items()
            )
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


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

KNOWN_LANG_CODES = {
    "en", "de", "fr", "es", "it", "pt", "nl", "ru", "pl", "cs", "sk", "hu",
    "ro", "bg", "hr", "sr", "uk", "tr", "ar", "zh", "ja", "ko", "th", "vi",
    "id", "ms", "hi", "fa", "he", "el", "sv", "da", "no", "fi", "et", "lv", "lt",
}


def detect_tmx_languages(path: Path, max_scan: int = 500) -> list[str]:
    """Return sorted list of unique primary language subtags found in the TMX.

    Scans at most *max_scan* ``<tuv>`` elements so detection is fast even on
    very large files.
    """
    try:
        langs: set[str] = set()
        scanned = 0
        for _event, elem in _ET.iterparse(str(path), events=("end",)):
            if _local(elem.tag) == "tuv":
                raw = elem.get(XML_LANG) or elem.get("lang") or ""
                if raw:
                    langs.add(raw.lower().split("-")[0].split("_")[0])
                elem.clear()
                scanned += 1
                if scanned >= max_scan:
                    break
        return sorted(langs)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Streaming parser
# ---------------------------------------------------------------------------

def iter_tmx(
    path: Path,
    source_lang: str,
    target_lang: str,
    warnings: Optional[List[str]] = None,
    progress_callback=None,
) -> Generator[Segment, None, None]:
    """Yield :class:`Segment` objects one at a time from a TMX file.

    Uses ``xml.etree.ElementTree.iterparse`` (expat) for stable streaming
    on all platforms.  Appends parse warnings to *warnings* instead of
    raising, so callers always get partial results on malformed files.

    Memory: only one ``<tu>`` subtree exists at a time.
    """
    if warnings is None:
        warnings = []

    try:
        context = _ET.iterparse(str(path), events=("end",))
        idx = 0
        count = 0

        for _event, elem in context:
            local = _local(elem.tag)

            # We only care about <tu> end events; skip everything else.
            # Sub-elements (tuv, seg) are still live when their parent <tu>
            # fires, so we can access them here before clearing.
            if local != "tu":
                continue

            idx += 1
            tuid = elem.get("tuid") or str(idx)

            source_text: Optional[str] = None
            target_text: Optional[str] = None

            # {*}tuv matches any namespace — requires Python ≥ 3.8
            for tuv in elem.findall("{*}tuv") or elem.findall("tuv"):
                lang = tuv.get(XML_LANG) or tuv.get("lang")
                if not lang:
                    continue
                seg_elem = tuv.find("{*}seg") or tuv.find("seg")
                if seg_elem is None:
                    continue
                text = _serialize_seg(seg_elem)
                if _lang_matches(lang, source_lang):
                    source_text = text
                elif _lang_matches(lang, target_lang):
                    target_text = text

            if source_text is None:
                if len(warnings) < MAX_WARNINGS:
                    warnings.append(
                        f"TU '{tuid}' missing source language '{source_lang}' tuv"
                    )
            elif target_text is None:
                if len(warnings) < MAX_WARNINGS:
                    warnings.append(
                        f"TU '{tuid}' missing target language '{target_lang}' tuv"
                    )
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

            # Free the processed <tu> subtree immediately — keeps memory flat
            elem.clear()

    except _ET.ParseError as e:
        warnings.append(f"XML parse error: {e}")
    except OSError as e:
        warnings.append(f"Cannot open TMX file '{path}': {e}")
    except Exception as e:
        warnings.append(f"TMX parse error ({type(e).__name__}): {e}")


# ---------------------------------------------------------------------------
# Bulk parser (wraps the streaming iterator)
# ---------------------------------------------------------------------------

def parse_tmx(
    path: Path,
    source_lang: str,
    target_lang: str,
    progress_callback=None,
) -> ParseResult:
    """Parse a TMX file and return all segments as a list.

    For large files prefer ``iter_tmx`` which yields one ``Segment`` at a time.
    """
    encoding = detect_encoding(path)
    encoding_ok = encoding == "utf-8"
    warnings: List[str] = []
    segments = list(
        iter_tmx(
            path, source_lang, target_lang,
            warnings=warnings,
            progress_callback=progress_callback,
        )
    )
    return ParseResult(
        segments=segments,
        warnings=warnings,
        encoding_ok=encoding_ok,
        source_lang=source_lang,
        target_lang=target_lang,
    )
