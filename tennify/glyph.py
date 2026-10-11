from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from tennify.segments import Contour, Point

TRIGGER_OVERRIDES = {
    "over_": "over?",
    "_win!": "*win!",
}

JOIN_GROUPS = {
    "tv!!": ("T.png", "v!!.png"),
}

CHARACTER_WORDS = {
    "*": "asterisk",
    "?": "question",
    "!": "bang",
    "'": "quote",
    '"': "dquote",
    "-": "dash",
    ".": "dot",
    "&": "amp",
    "#": "hash",
    "@": "at",
}

WORDART_GLYPH_PREFIX = "wordart_"
BLANK_GLYPH_NAME = "wordart_blank"
LAYER_GLYPH_SUFFIX_PATTERN = re.compile(r"_l\d+$")
UNDERSCORE_RUN_PATTERN = re.compile(r"_+")


@dataclass(frozen=True)
class WordArtSource:
    trigger: str
    paths: tuple[Path, ...]


@dataclass(frozen=True)
class ScaledWordArt:
    trigger: str
    source_names: tuple[str, ...]
    contours: tuple[Contour, ...]
    advance: int
    base_glyph: str = ""
    layer_glyphs: tuple[str, ...] = ()


def scan_sources(png_dir: Path) -> tuple[WordArtSource, ...]:
    files = {path.name: path for path in sorted(png_dir.glob("*.png"))}
    joined_names = {name for group in JOIN_GROUPS.values() for name in group}

    sources = [
        WordArtSource(
            trigger=trigger,
            paths=tuple(_require_file(files, name) for name in names),
        )
        for trigger, names in JOIN_GROUPS.items()
    ]
    sources.extend(
        WordArtSource(trigger=TRIGGER_OVERRIDES.get(path.stem, path.stem), paths=(path,))
        for name, path in files.items()
        if name not in joined_names
    )
    return tuple(sources)


def _require_file(files: dict[str, Path], name: str) -> Path:
    if name not in files:
        raise FileNotFoundError(f"join component missing: {name}")
    return files[name]


def case_variants(text: str) -> tuple[str, ...]:
    lowercase = text.lower()
    title = _capitalize_first_alpha(lowercase)
    return tuple(dict.fromkeys((lowercase, text.upper(), title)))


def _capitalize_first_alpha(text: str) -> str:
    for index, char in enumerate(text):
        if char.isalpha():
            return text[:index] + char.upper() + text[index + 1 :]
    return text


def unique_glyph_name(trigger: str, taken: set[str]) -> str:
    slug = _slugify(trigger)
    name = f"{WORDART_GLYPH_PREFIX}{slug}" if slug else BLANK_GLYPH_NAME
    candidate = name
    suffix = 2
    while candidate in taken:
        candidate = f"{name}_{suffix}"
        suffix += 1
    taken.add(candidate)
    return candidate


def _slugify(trigger: str) -> str:
    words: list[str] = []
    current: list[str] = []
    for char in trigger.lower():
        if char.isalnum():
            current.append(char)
            continue
        if current:
            words.append("".join(current))
            current = []
        if char.isspace() or char == "-":
            words.append("_")
        else:
            words.append(CHARACTER_WORDS.get(char, "_"))
    if current:
        words.append("".join(current))
    return UNDERSCORE_RUN_PATTERN.sub("_", "".join(words)).strip("_")


def all_points(contours: Sequence[Contour]) -> list[Point]:
    return [point for contour in contours for point in contour.points]


def scale_to_height(
    contours: Sequence[Contour],
    target_height: float,
    horizontal_padding: float,
) -> tuple[Contour, ...]:
    points = all_points(contours)
    if not points:
        return ()

    min_x = min(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)
    height = max_y - min_y
    scale = target_height / height if height > 0 else target_height

    def place(point: Point) -> Point:
        x, y = point
        return (x - min_x) * scale + horizontal_padding, (max_y - y) * scale

    return tuple(contour.mapped(place) for contour in contours)


def glyph_advance(
    contours: Sequence[Contour],
    fallback: int,
    horizontal_padding: float,
) -> int:
    points = all_points(contours)
    if not points:
        return fallback
    return round(max(point[0] for point in points) + horizontal_padding)


def is_base_glyph(name: str) -> bool:
    return name.startswith(WORDART_GLYPH_PREFIX) and not LAYER_GLYPH_SUFFIX_PATTERN.search(name)
