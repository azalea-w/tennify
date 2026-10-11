from __future__ import annotations

from tennify.segments import FloatRgba, Rgb, Rgba

COLOR_QUANTIZATION_BITS = 4
OPAQUE_ALPHA = 255
FULL_CHANNEL_MAX = 255
CHANNEL_SHIFT_BITS = 8


def quantize_color(fill: Rgba, bits: int = COLOR_QUANTIZATION_BITS) -> Rgba:
    shift = max(0, CHANNEL_SHIFT_BITS - bits)
    if shift == 0:
        return fill[0], fill[1], fill[2], OPAQUE_ALPHA
    step = 1 << shift
    max_level = (1 << bits) - 1

    def quantize_channel(channel: int) -> int:
        level = (channel + step // 2) // step
        return min(max_level, level) * step

    return (
        quantize_channel(fill[0]),
        quantize_channel(fill[1]),
        quantize_channel(fill[2]),
        OPAQUE_ALPHA,
    )


def normalized_rgba(fill: Rgba) -> FloatRgba:
    red, green, blue, alpha = quantize_color(fill)
    return (
        red / FULL_CHANNEL_MAX,
        green / FULL_CHANNEL_MAX,
        blue / FULL_CHANNEL_MAX,
        alpha / FULL_CHANNEL_MAX,
    )


class Palette:
    def __init__(self) -> None:
        self._index_by_rgb: dict[Rgb, int] = {}
        self._colors: list[FloatRgba] = []

    def index(self, fill: Rgba) -> int:
        key = quantize_color(fill)[:3]
        if key not in self._index_by_rgb:
            self._index_by_rgb[key] = len(self._colors)
            self._colors.append(normalized_rgba(fill))
        return self._index_by_rgb[key]

    @property
    def colors(self) -> tuple[FloatRgba, ...]:
        return tuple(self._colors)

    def __len__(self) -> int:
        return len(self._colors)
