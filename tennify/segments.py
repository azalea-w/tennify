from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import NamedTuple, Protocol, TypeAlias

Point: TypeAlias = tuple[float, float]
Rgb: TypeAlias = tuple[int, int, int]
Rgba: TypeAlias = tuple[int, int, int, int]
FloatRgba: TypeAlias = tuple[float, float, float, float]
PointMapper: TypeAlias = Callable[[Point], Point]


class ContourPen(Protocol):
    def moveTo(self, point: Point) -> None: ...

    def lineTo(self, point: Point) -> None: ...

    def curveTo(self, *points: Point) -> None: ...

    def closePath(self) -> None: ...


class MoveTo(NamedTuple):
    x: float
    y: float

    def points(self) -> list[Point]:
        return [(self.x, self.y)]

    def translated(self, dx: float, dy: float) -> MoveTo:
        return MoveTo(self.x + dx, self.y + dy)

    def mapped(self, fn: PointMapper) -> MoveTo:
        x, y = fn((self.x, self.y))
        return MoveTo(x, y)

    def draw(self, pen: ContourPen) -> None:
        pen.moveTo((self.x, self.y))


class LineTo(NamedTuple):
    x: float
    y: float

    def points(self) -> list[Point]:
        return [(self.x, self.y)]

    def translated(self, dx: float, dy: float) -> LineTo:
        return LineTo(self.x + dx, self.y + dy)

    def mapped(self, fn: PointMapper) -> LineTo:
        x, y = fn((self.x, self.y))
        return LineTo(x, y)

    def draw(self, pen: ContourPen) -> None:
        pen.lineTo((self.x, self.y))


class CurveTo(NamedTuple):
    x1: float
    y1: float
    x2: float
    y2: float
    x: float
    y: float

    def points(self) -> list[Point]:
        return [(self.x1, self.y1), (self.x2, self.y2), (self.x, self.y)]

    def translated(self, dx: float, dy: float) -> CurveTo:
        return CurveTo(
            self.x1 + dx,
            self.y1 + dy,
            self.x2 + dx,
            self.y2 + dy,
            self.x + dx,
            self.y + dy,
        )

    def mapped(self, fn: PointMapper) -> CurveTo:
        x1, y1 = fn((self.x1, self.y1))
        x2, y2 = fn((self.x2, self.y2))
        x, y = fn((self.x, self.y))
        return CurveTo(x1, y1, x2, y2, x, y)

    def draw(self, pen: ContourPen) -> None:
        pen.curveTo((self.x1, self.y1), (self.x2, self.y2), (self.x, self.y))


class ClosePath(NamedTuple):
    def points(self) -> list[Point]:
        return []

    def translated(self, dx: float, dy: float) -> ClosePath:
        return ClosePath()

    def mapped(self, fn: PointMapper) -> ClosePath:
        return ClosePath()

    def draw(self, pen: ContourPen) -> None:
        pen.closePath()


Segment: TypeAlias = MoveTo | LineTo | CurveTo | ClosePath
Subpath: TypeAlias = tuple[Segment, ...]


@dataclass(frozen=True)
class Contour:
    segments: tuple[Segment, ...]
    fill: Rgba

    @property
    def points(self) -> tuple[Point, ...]:
        return tuple(point for segment in self.segments for point in segment.points())

    def translated(self, dx: float, dy: float) -> Contour:
        return Contour(
            segments=tuple(segment.translated(dx, dy) for segment in self.segments),
            fill=self.fill,
        )

    def mapped(self, fn: PointMapper) -> Contour:
        return Contour(
            segments=tuple(segment.mapped(fn) for segment in self.segments),
            fill=self.fill,
        )

    def draw(self, pen: ContourPen) -> None:
        for segment in self.segments:
            segment.draw(pen)
