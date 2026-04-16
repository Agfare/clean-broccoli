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


def export_tmx(
    segments: List[Segment],
    path: Path,
    source_lang: str,
    target_lang: str,
) -> None:
    """Write a valid TMX 1.4 file using lxml's incremental writer.

    Each <tu> is written and freed immediately — memory stays flat regardless
    of how many segments are passed, making this safe for 100k+ segment files.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    with etree.xmlfile(str(path), encoding="UTF-8", buffered=True) as xf:
        xf.write_declaration()

        with xf.element("tmx", attrib={"version": "1.4"}):
            header = etree.Element(
                "header",
                attrib={
                    "creationtool": "tmclean",
                    "creationtoolversion": "1.0",
                    "datatype": "PlainText",
                    "segtype": "sentence",
                    "adminlang": "en-US",
                    "srclang": source_lang,
                    "o-tmf": "tmclean",
                },
            )
            xf.write(header, pretty_print=True)

            with xf.element("body"):
                for seg in segments:
                    tu = etree.Element("tu")
                    if seg.id:
                        tu.set("tuid", str(seg.id))

                    tuv_src = etree.SubElement(tu, "tuv")
                    tuv_src.set(XML_LANG, source_lang)
                    etree.SubElement(tuv_src, "seg").text = seg.source

                    tuv_tgt = etree.SubElement(tu, "tuv")
                    tuv_tgt.set(XML_LANG, target_lang)
                    etree.SubElement(tuv_tgt, "seg").text = seg.target

                    xf.write(tu, pretty_print=True)
                    # tu is written to disk and can be GC'd immediately
