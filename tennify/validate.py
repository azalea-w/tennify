from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import uharfbuzz as hb
from fontTools.ttLib import TTFont

from tennify.glyph import case_variants, is_base_glyph

EXTRA_VALIDATION_STRINGS = (
    "lovely",
    "LOVES",
    "gamer",
    "round 1!",
    "bonus round",
    "overflow",
    "love",
    "tv!!",
    "TV!!",
    "T",
)

REQUIRED_TABLES = ("COLR", "CPAL", "GSUB")


@dataclass(frozen=True)
class ShapingResult:
    text: str
    glyph_names: tuple[str, ...]
    is_wordart: bool


def build_test_strings(triggers: Sequence[str]) -> tuple[str, ...]:
    strings: list[str] = []
    for trigger in triggers:
        strings.extend(case_variants(trigger))
    for extra in EXTRA_VALIDATION_STRINGS:
        if extra not in strings:
            strings.append(extra)
    return tuple(strings)


def shape_text(
    font: hb.Font,
    glyph_name_by_id: dict[int, str],
    text: str,
) -> ShapingResult:
    buffer = hb.Buffer()
    buffer.add_str(text)
    buffer.guess_segment_properties()
    hb.shape(font, buffer)
    glyph_names = tuple(
        glyph_name_by_id.get(info.codepoint, f"gid{info.codepoint}") for info in buffer.glyph_infos
    )
    return ShapingResult(
        text=text,
        glyph_names=glyph_names,
        is_wordart=any(is_base_glyph(name) for name in glyph_names),
    )


def validate_font(path: Path, triggers: Sequence[str]) -> tuple[ShapingResult, ...]:
    blob = hb.Blob.from_file_path(str(path))
    face = hb.Face(blob)
    shaping_font = hb.Font(face)
    tt_font = TTFont(str(path))
    for table in REQUIRED_TABLES:
        if table not in tt_font:
            raise ValueError(f"missing {table}")

    glyph_name_by_id = {glyph_id: name for name, glyph_id in tt_font.getReverseGlyphMap().items()}
    return tuple(
        shape_text(shaping_font, glyph_name_by_id, text) for text in build_test_strings(triggers)
    )
