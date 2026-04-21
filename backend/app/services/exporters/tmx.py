from __future__ import annotations

from pathlib import Path
from typing import List

from lxml import etree

from app.services.parsers.base import Segment

XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

_TMX_HEADER_ATTRIB = {
    "creationtool": "tmclean",
    "creationtoolversion": "1.0",
    "datatype": "PlainText",
    "segtype": "sentence",
    "adminlang": "en-US",
    "o-tmf": "tmclean",
}


class TmxWriter:
    """Context-manager streaming TMX writer.

    Keeps the output file open and writes one <tu> at a time, so memory stays
    flat no matter how many segments are written.

    Usage::

        with TmxWriter(path, "en", "de") as w:
            for seg in segments:
                w.write(seg)
    """

    def __init__(self, path: Path, source_lang: str, target_lang: str) -> None:
        self._path = path
        self._source_lang = source_lang
        self._target_lang = target_lang
        # Internal lxml context-manager handles
        self._xf_cm = None
        self._tmx_cm = None
        self._body_cm = None
        self._xf = None

    def __enter__(self) -> "TmxWriter":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._xf_cm = etree.xmlfile(str(self._path), encoding="UTF-8", buffered=True)
        self._xf = self._xf_cm.__enter__()
        self._xf.write_declaration()

        self._tmx_cm = self._xf.element("tmx", attrib={"version": "1.4"})
        self._tmx_cm.__enter__()

        header = etree.Element(
            "header",
            attrib={**_TMX_HEADER_ATTRIB, "srclang": self._source_lang},
        )
        self._xf.write(header, pretty_print=True)

        self._body_cm = self._xf.element("body")
        self._body_cm.__enter__()
        return self

    def write(self, seg: Segment) -> None:
        tu = etree.Element("tu")
        if seg.id:
            tu.set("tuid", str(seg.id))

        tuv_src = etree.SubElement(tu, "tuv")
        tuv_src.set(XML_LANG, self._source_lang)
        etree.SubElement(tuv_src, "seg").text = seg.source

        tuv_tgt = etree.SubElement(tu, "tuv")
        tuv_tgt.set(XML_LANG, self._target_lang)
        etree.SubElement(tuv_tgt, "seg").text = seg.target

        self._xf.write(tu, pretty_print=True)

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Close in reverse order; suppress nothing
        if self._body_cm is not None:
            self._body_cm.__exit__(exc_type, exc_val, exc_tb)
        if self._tmx_cm is not None:
            self._tmx_cm.__exit__(exc_type, exc_val, exc_tb)
        if self._xf_cm is not None:
            self._xf_cm.__exit__(exc_type, exc_val, exc_tb)
        return False


def merge_bilingual_tmxs(
    source_lang: str,
    tmx_paths: List[Path],
    output_path: Path,
) -> None:
    """Merge N bilingual clean TMX files into one multi-language TMX.

    Each *tmx_paths* entry is expected to be a bilingual TMX whose filename
    encodes the target language as the last ``_``-separated component before
    the extension (e.g. ``clean_en_de.tmx`` → target ``de``).

    Algorithm
    ---------
    Pass 1 — collect: for each bilingual TMX, stream segments via
        ``iter_tmx`` and populate::

            segments[source_text][target_lang] = target_text

        Only the **first** occurrence of each (source, lang) pair is kept,
        which is consistent with how ``TmxWriter`` handles duplicates during
        the cleaning pass.

    Pass 2 — write: iterate ``segments`` in insertion order, emitting one
        ``<tu>`` per unique source text with one ``<tuv>`` per available
        target language.

    Memory
    ------
    O(total unique source strings + all target translations).  For typical
    TM sizes (up to ~500 K segments, ~50 chars average) peak usage is
    100–200 MB — well within the available worker RAM.  If *tmx_paths* is
    empty the function returns immediately without creating any file.
    """
    if not tmx_paths:
        return

    from app.services.parsers.tmx import iter_tmx  # avoid circular at module level

    # Pass 1 — collect all segments, keyed by source text
    # segments[source_text] = {target_lang: target_text}
    # Ordered dict preserves first-seen source ordering.
    segments: dict[str, dict[str, str]] = {}

    for path in tmx_paths:
        # Derive the target language from the filename stem.
        # _build_output_paths produces names like "clean_en_de" or
        # "proj_clean_en_de"; in both cases the target lang is the last
        # underscore-delimited token before the extension.
        stem = path.stem
        target_lang = stem.rsplit("_", 1)[-1]

        for seg in iter_tmx(path, source_lang, target_lang):
            row = segments.setdefault(seg.source, {})
            if target_lang not in row:  # keep first occurrence per lang
                row[target_lang] = seg.target

    if not segments:
        return

    # Collect target languages in file order (deterministic output column order)
    seen_target_langs: list[str] = []
    for row in segments.values():
        for lang in row:
            if lang not in seen_target_langs:
                seen_target_langs.append(lang)

    # Pass 2 — write multi-language TMX
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with etree.xmlfile(str(output_path), encoding="UTF-8", buffered=True) as xf:
        xf.write_declaration()

        with xf.element("tmx", attrib={"version": "1.4"}):
            header = etree.Element(
                "header",
                attrib={**_TMX_HEADER_ATTRIB, "srclang": source_lang},
            )
            xf.write(header, pretty_print=True)

            with xf.element("body"):
                for src_text, translations in segments.items():
                    tu = etree.Element("tu")

                    tuv_src = etree.SubElement(tu, "tuv")
                    tuv_src.set(XML_LANG, source_lang)
                    etree.SubElement(tuv_src, "seg").text = src_text

                    for lang in seen_target_langs:
                        tgt_text = translations.get(lang)
                        if tgt_text is None:
                            continue
                        tuv_tgt = etree.SubElement(tu, "tuv")
                        tuv_tgt.set(XML_LANG, lang)
                        etree.SubElement(tuv_tgt, "seg").text = tgt_text

                    xf.write(tu, pretty_print=True)
