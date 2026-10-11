from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from tennify.fontbuild import BuildConfig, BuildError, build_font
from tennify.glyph import scan_sources
from tennify.validate import validate_font

DEFAULT_PNG_DIR = Path("clean")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inject wordart PNG ligatures (GSUB liga + COLR/CPAL) into an OTF"
    )
    parser.add_argument("input_otf", type=Path, help="input OTF/TTF")
    parser.add_argument("-o", "--output", type=Path, required=True, help="output font path")
    parser.add_argument("--png-dir", type=Path, default=DEFAULT_PNG_DIR)
    parser.add_argument(
        "--colors",
        type=int,
        default=BuildConfig.palette_size,
        help="posterize palette size before tracing",
    )
    parser.add_argument(
        "--height-em",
        type=float,
        default=BuildConfig.height_em,
        help="wordart height in em units",
    )
    parser.add_argument(
        "--feature",
        default=BuildConfig.feature_tag,
        help="GSUB feature tag",
    )
    parser.add_argument("--skip-validate", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.input_otf.exists():
        parser.error(f"not found: {args.input_otf}")
    if not args.png_dir.is_dir():
        parser.error(f"not a dir: {args.png_dir}")

    config = BuildConfig(
        palette_size=args.colors,
        height_em=args.height_em,
        feature_tag=args.feature,
    )

    print(f"Building wordart font from {args.input_otf} + {args.png_dir}/")
    try:
        report = build_font(args.input_otf, args.png_dir, args.output, config)
    except (BuildError, FileNotFoundError, NotImplementedError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)

    for skipped in report.skipped:
        print(
            f"WARN: no contours traced for {skipped.trigger!r} ({list(skipped.source_names)})",
            file=sys.stderr,
        )
    for trace in report.traces:
        print(
            f"  traced {trace.trigger!r}: {trace.contour_count} paths, "
            f"advance={trace.advance} from {list(trace.source_names)}"
        )
    for glyph in report.glyphs:
        print(f"  glyphs: {glyph.base_glyph} + {glyph.layer_count} layers")
    print(f"  COLR: {report.color_glyph_count} base glyphs, CPAL: {report.palette_size} colors")
    print(f"  GSUB {report.feature_tag}: {report.ligature_rule_count} rules")
    print(f"wrote {report.output_path}")

    if args.skip_validate:
        return

    triggers = [source.trigger for source in scan_sources(args.png_dir)]
    results = validate_font(args.output, triggers)
    print("\nValidation (uharfbuzz):")
    for result in results:
        status = "WORDART" if result.is_wordart else "plain"
        print(f"  {result.text!r:30} -> {list(result.glyph_names)} [{status}]")
    print("  tables: COLR/CPAL/GSUB present")


if __name__ == "__main__":
    main()
