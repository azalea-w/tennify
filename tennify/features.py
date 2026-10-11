from __future__ import annotations

from collections.abc import Sequence
from typing import TypeAlias

from tennify.glyph import case_variants

LigatureRule: TypeAlias = tuple[int, tuple[str, ...], str]

DEFAULT_FEATURE_TAG = "liga"
LANGUAGE_SYSTEM_LINES = (
    "languagesystem DFLT dflt;",
    "languagesystem latn dflt;",
)


def build_ligature_rules(
    entries: Sequence[tuple[str, str]],
    glyph_for_char: dict[str, str],
) -> tuple[LigatureRule, ...]:
    rules = [
        (len(sources), sources, base_glyph)
        for trigger, base_glyph in entries
        for variant in case_variants(trigger)
        for sources in (tuple(glyph_for_char[char] for char in variant),)
    ]
    return tuple(sorted(rules, key=lambda rule: rule[0], reverse=True))


def build_feature_text(rules: Sequence[LigatureRule], feature_tag: str) -> str:
    lines = [
        *LANGUAGE_SYSTEM_LINES,
        f"feature {feature_tag} {{",
        *(f"    sub {' '.join(sources)} by {target};" for _, sources, target in rules),
        f"}} {feature_tag};",
    ]
    return "\n".join(lines)
