from __future__ import annotations

from pathlib import Path
from typing import List

from lxml import etree

from app.services.parsers.base import Segment


def export_tmx(
    segments: List[Segment],
    path: Path,
    source_lang: str,
    target_lang: str,
) -> None:
    """Generate a valid TMX 1.4 file from a list of segments."""
    path.parent.mkdir(parents=True, exist_ok=True)

    # Build TMX document
    tmx = etree.Element("tmx", version="1.4")
    etree.SubElement(
        tmx,
        "header",
        creationtool="tmclean",
        creationtoolversion="1.0",
        datatype="PlainText",
        segtype="sentence",
        adminlang="en-US",
        srclang=source_lang,
        o_tmf="tmclean",
    )

    body = etree.SubElement(tmx, "body")

    for seg in segments:
        tu = etree.SubElement(body, "tu")
        if seg.id:
            tu.set("tuid", str(seg.id))

        # Source TUV
        tuv_src = etree.SubElement(tu, "tuv")
        tuv_src.set("{http://www.w3.org/XML/1998/namespace}lang", source_lang)
        seg_src = etree.SubElement(tuv_src, "seg")
        seg_src.text = seg.source

        # Target TUV
        tuv_tgt = etree.SubElement(tu, "tuv")
        tuv_tgt.set("{http://www.w3.org/XML/1998/namespace}lang", target_lang)
        seg_tgt = etree.SubElement(tuv_tgt, "seg")
        seg_tgt.text = seg.target

    tree = etree.ElementTree(tmx)
    tree.write(
        str(path),
        pretty_print=True,
        xml_declaration=True,
        encoding="UTF-8",
    )
