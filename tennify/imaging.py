from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import vtracer
from PIL import Image

ALPHA_CUTOFF = 127
OPAQUE_ALPHA = 255
MIN_PALETTE_SIZE = 2
JOIN_GAP_FRACTION = 0.08
MIN_JOIN_GAP_PIXELS = 4


@dataclass(frozen=True)
class TracerSettings:
    colormode: str = "color"
    hierarchical: str = "stacked"
    mode: str = "spline"
    filter_speckle: int = 4
    color_precision: int = 6
    layer_difference: int = 32
    corner_threshold: int = 60
    length_threshold: float = 4.0
    splice_threshold: int = 45
    path_precision: int = 3


DEFAULT_TRACER_SETTINGS = TracerSettings()


def posterize(image: Image.Image, palette_size: int) -> Image.Image:
    rgba = np.array(image.convert("RGBA"))
    rgba[..., 3] = np.where(rgba[..., 3] > ALPHA_CUTOFF, OPAQUE_ALPHA, 0)
    opaque = rgba[..., 3] > 0
    if not opaque.any():
        return Image.fromarray(rgba)

    rgb_image = Image.fromarray(rgba[..., :3])
    quantized = rgb_image.quantize(
        colors=max(MIN_PALETTE_SIZE, palette_size),
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.NONE,
    )
    palette = np.array(quantized.getpalette() or [], dtype=np.uint8).reshape(-1, 3)
    indices = np.array(quantized, dtype=np.int32)
    colors = np.zeros((*indices.shape, 3), dtype=np.uint8)
    valid = indices < len(palette)
    colors[valid] = palette[indices[valid]]

    result = np.concatenate([colors, rgba[..., 3:4]], axis=-1)
    result[result[..., 3] == 0] = 0
    return Image.fromarray(result)


def compose_images(paths: Sequence[Path], gap_fraction: float = JOIN_GAP_FRACTION) -> Image.Image:
    images = [Image.open(path).convert("RGBA") for path in paths]
    target_height = max(image.height for image in images)
    scaled = [
        image.resize(
            (max(1, round(image.width * target_height / image.height)), target_height),
            Image.Resampling.LANCZOS,
        )
        for image in images
    ]
    gap = max(MIN_JOIN_GAP_PIXELS, round(target_height * gap_fraction))
    total_width = sum(image.width for image in scaled) + gap * (len(scaled) - 1)
    canvas = Image.new("RGBA", (total_width, target_height), (0, 0, 0, 0))
    offset = 0
    for image in scaled:
        canvas.paste(image, (offset, 0), image)
        offset += image.width + gap
    bounding_box = canvas.getbbox()
    return canvas.crop(bounding_box) if bounding_box else canvas


def trace_to_svg(
    image: Image.Image,
    settings: TracerSettings = DEFAULT_TRACER_SETTINGS,
) -> str:
    with TemporaryDirectory() as temp_dir:
        png_path = Path(temp_dir) / "input.png"
        svg_path = Path(temp_dir) / "output.svg"
        image.save(png_path)
        vtracer.convert_image_to_svg_py(
            str(png_path),
            str(svg_path),
            colormode=settings.colormode,
            hierarchical=settings.hierarchical,
            mode=settings.mode,
            filter_speckle=settings.filter_speckle,
            color_precision=settings.color_precision,
            layer_difference=settings.layer_difference,
            corner_threshold=settings.corner_threshold,
            length_threshold=settings.length_threshold,
            splice_threshold=settings.splice_threshold,
            path_precision=settings.path_precision,
        )
        return svg_path.read_text()
