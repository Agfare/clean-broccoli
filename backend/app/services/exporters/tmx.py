from __future__ import annotations

from pathlib import Path
from typing import List

from lxml import etree

from app.services.parsers.base import Segment

XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


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
