from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from fontTools.colorLib.builder import buildCOLR, buildCPAL
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont
from PIL import Image

from tennify.features import DEFAULT_FEATURE_TAG, build_feature_text, build_ligature_rules
from tennify.glyph import (
    ScaledWordArt,
    WordArtSource,
    all_points,
    glyph_advance,
    scale_to_height,
    scan_sources,
    unique_glyph_name,
)
from tennify.imaging import compose_images, posterize, trace_to_svg
from tennify.palette import Palette
from tennify.pathdata import contours_from_svg
from tennify.segments import Contour

DEFAULT_PALETTE_SIZE = 12
DEFAULT_HEIGHT_EM = 1.0
X_PADDING_EM_FRACTION = 0.03
NON_CFF_MESSAGE = "TTF/glyf input not supported yet; pass an OTF (CFF)"
MULTI_FD_MESSAGE = "CID fonts with multiple Font DICTs are not supported"


class BuildError(Exception):
    pass


@dataclass(frozen=True)
class BuildConfig:
    palette_size: int = DEFAULT_PALETTE_SIZE
    height_em: float = DEFAULT_HEIGHT_EM
    feature_tag: str = DEFAULT_FEATURE_TAG
    horizontal_padding_em_fraction: float = X_PADDING_EM_FRACTION


@dataclass(frozen=True)
class TraceRecord:
    trigger: str
    source_names: tuple[str, ...]
    contour_count: int
    advance: int


@dataclass(frozen=True)
class SkippedRecord:
    trigger: str
    source_names: tuple[str, ...]


@dataclass(frozen=True)
class GlyphRecord:
    base_glyph: str
    layer_count: int


@dataclass(frozen=True)
class BuildReport:
    traces: tuple[TraceRecord, ...]
    skipped: tuple[SkippedRecord, ...]
    glyphs: tuple[GlyphRecord, ...]
    color_glyph_count: int
    palette_size: int
    ligature_rule_count: int
    feature_tag: str
    output_path: Path


def reverse_cmap(font: TTFont) -> dict[str, str]:
    best_cmap = font.getBestCmap()
    glyph_for_char: dict[str, str] = {}
    for codepoint, glyph_name in best_cmap.items():
        glyph_for_char.setdefault(chr(codepoint), glyph_name)
    return glyph_for_char


MISSING_CHAR_PREVIEW_COUNT = 3


def missing_characters(
    triggers: Sequence[str],
    glyph_for_char: dict[str, str],
) -> tuple[str, ...]:
    return tuple(
        sorted({char for trigger in triggers for char in trigger if char not in glyph_for_char})
    )


def affected_triggers(
    triggers: Sequence[str],
    glyph_for_char: dict[str, str],
) -> tuple[str, ...]:
    return tuple(
        trigger for trigger in triggers if any(char not in glyph_for_char for char in trigger)
    )


def format_missing_characters_error(
    triggers: Sequence[str],
    glyph_for_char: dict[str, str],
) -> str:
    missing = missing_characters(triggers, glyph_for_char)
    affected = affected_triggers(triggers, glyph_for_char)
    characters = " ".join(repr(char) for char in missing)
    if len(affected) <= MISSING_CHAR_PREVIEW_COUNT:
        where = ", ".join(repr(trigger) for trigger in affected)
        return f"font cmap missing {len(missing)} character(s): {characters} (in {where})"
    preview = ", ".join(repr(trigger) for trigger in affected[:MISSING_CHAR_PREVIEW_COUNT])
    return (
        f"font cmap missing {len(missing)} character(s): {characters} ; "
        f"used by {len(affected)} wordart triggers (e.g. {preview})"
    )


def source_image(source: WordArtSource, palette_size: int) -> Image.Image:
    base = compose_images(source.paths) if len(source.paths) > 1 else Image.open(source.paths[0])
    return posterize(base, palette_size)


def trace_source(source: WordArtSource, palette_size: int) -> tuple[Contour, ...]:
    svg_text = trace_to_svg(source_image(source, palette_size))
    return contours_from_svg(svg_text)


def scale_sources(
    sources: Sequence[WordArtSource],
    palette_size: int,
    target_height: float,
    horizontal_padding: float,
) -> tuple[tuple[ScaledWordArt, ...], tuple[SkippedRecord, ...]]:
    scaled_arts: list[ScaledWordArt] = []
    skipped: list[SkippedRecord] = []
    for source in sources:
        contours = trace_source(source, palette_size)
        source_names = tuple(path.name for path in source.paths)
        if not contours:
            skipped.append(SkippedRecord(trigger=source.trigger, source_names=source_names))
            continue
        placed = scale_to_height(contours, target_height, horizontal_padding)
        advance = glyph_advance(placed, int(target_height), horizontal_padding)
        scaled_arts.append(
            ScaledWordArt(
                trigger=source.trigger,
                source_names=source_names,
                contours=placed,
                advance=advance,
            )
        )
    return tuple(scaled_arts), tuple(skipped)


def flatten_cid_cff(font: TTFont) -> None:
    cff = font["CFF "].cff
    top_level = cff[cff.fontNames[0]]
    if "ROS" not in top_level.rawDict:
        return

    _ = top_level.charset
    _ = top_level.getGlyphOrder()
    _ = font.getGlyphOrder()

    font_dicts = top_level.FDArray
    if len(font_dicts) != 1:
        raise BuildError(MULTI_FD_MESSAGE)
    private = font_dicts[0].Private

    for key in ("ROS", "FDArray", "FDSelect"):
        top_level.rawDict.pop(key, None)
        top_level.__dict__.pop(key, None)
    top_level.Private = private


def add_glyph(font: TTFont, name: str, contours: Sequence[Contour], advance: int) -> None:
    glyph_order = font.getGlyphOrder()
    if name in glyph_order:
        raise BuildError(f"glyph exists: {name}")
    font.setGlyphOrder([*glyph_order, name])

    left_side_bearing = 0
    points = all_points(contours)
    if points:
        left_side_bearing = round(min(point[0] for point in points))
    font["hmtx"].metrics[name] = (advance, left_side_bearing)
    font["hhea"].numberOfHMetrics = len(font["hmtx"].metrics)    # noqa

    cff = font["CFF "].cff
    top_level = cff[cff.fontNames[0]]
    pen = T2CharStringPen(advance, None)
    for contour in contours:
        contour.draw(pen)
    pen.closePath()
    charstring = pen.getCharString(
        private=top_level.Private,
        globalSubrs=cff.GlobalSubrs,
    )
    char_strings = top_level.CharStrings
    if char_strings.charStringsAreIndexed:
        char_index = len(char_strings.charStringsIndex.items)
        char_strings.charStringsIndex.items.append(charstring)
        char_strings.charStrings[name] = char_index
    else:
        char_strings.charStrings[name] = charstring
    top_level.charset.append(name)
    top_level.numGlyphs = len(top_level.charset)


def install_color_tables(
    font: TTFont,
    arts: Sequence[ScaledWordArt],
    palette: Palette,
) -> dict[str, list[tuple[str, int]]]:
    color_glyphs: dict[str, list[tuple[str, int]]] = {}
    for art in arts:
        color_glyphs[art.base_glyph] = [
            (layer_name, palette.index(contour.fill))
            for contour, layer_name in zip(art.contours, art.layer_glyphs, strict=True)
        ]
    font["CPAL"] = buildCPAL([list(palette.colors)])
    font["COLR"] = buildCOLR(color_glyphs, version=0, glyphMap=font.getReverseGlyphMap())
    return color_glyphs


def install_ligatures(
    font: TTFont,
    arts: Sequence[ScaledWordArt],
    glyph_for_char: dict[str, str],
    feature_tag: str,
) -> int:
    rules = build_ligature_rules(
        [(art.trigger, art.base_glyph) for art in arts],
        glyph_for_char,
    )
    addOpenTypeFeaturesFromString(font, build_feature_text(rules, feature_tag))
    return len(rules)


def build_font(
    input_path: Path,
    png_dir: Path,
    output_path: Path,
    config: BuildConfig,
) -> BuildReport:
    font = TTFont(str(input_path))
    if "CFF " not in font:
        raise NotImplementedError(NON_CFF_MESSAGE)
    flatten_cid_cff(font)
    if "DSIG" in font:
        del font["DSIG"]

    units_per_em = font["head"].unitsPerEm
    target_height = config.height_em * units_per_em
    horizontal_padding = units_per_em * config.horizontal_padding_em_fraction
    glyph_for_char = reverse_cmap(font)

    sources = scan_sources(png_dir)
    triggers = [source.trigger for source in sources]
    if missing_characters(triggers, glyph_for_char):
        raise BuildError(format_missing_characters_error(triggers, glyph_for_char))

    scaled_arts, skipped = scale_sources(
        sources,
        config.palette_size,
        target_height,
        horizontal_padding,
    )
    if not scaled_arts:
        raise BuildError("nothing traced")

    palette = Palette()
    for art in scaled_arts:
        for contour in art.contours:
            palette.index(contour.fill)

    taken = set(font.getGlyphOrder())
    placed_arts: list[ScaledWordArt] = []
    glyph_records: list[GlyphRecord] = []
    for art_index, art in enumerate(scaled_arts):
        base_glyph = unique_glyph_name(art.trigger, taken)
        add_glyph(font, base_glyph, art.contours, art.advance)

        layer_names: list[str] = []
        for contour_index, contour in enumerate(art.contours):
            layer_name = f"{base_glyph}_l{contour_index}"
            if layer_name in taken:
                layer_name = f"{layer_name}_{art_index}"
            layer_advance = glyph_advance((contour,), art.advance, horizontal_padding)
            add_glyph(font, layer_name, (contour,), layer_advance)
            taken.add(layer_name)
            layer_names.append(layer_name)

        placed_arts.append(
            ScaledWordArt(
                trigger=art.trigger,
                source_names=art.source_names,
                contours=art.contours,
                advance=art.advance,
                base_glyph=base_glyph,
                layer_glyphs=tuple(layer_names),
            )
        )
        glyph_records.append(GlyphRecord(base_glyph=base_glyph, layer_count=len(layer_names)))

    color_glyphs = install_color_tables(font, placed_arts, palette)
    rule_count = install_ligatures(font, placed_arts, glyph_for_char, config.feature_tag)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    font.save(str(output_path))

    return BuildReport(
        traces=tuple(
            TraceRecord(
                trigger=art.trigger,
                source_names=art.source_names,
                contour_count=len(art.contours),
                advance=art.advance,
            )
            for art in placed_arts
        ),
        skipped=skipped,
        glyphs=tuple(glyph_records),
        color_glyph_count=len(color_glyphs),
        palette_size=len(palette),
        ligature_rule_count=rule_count,
        feature_tag=config.feature_tag,
        output_path=output_path,
    )
