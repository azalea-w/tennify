from __future__ import annotations

import re
from typing import TypeAlias

from tennify.segments import (
    ClosePath,
    Contour,
    CurveTo,
    LineTo,
    MoveTo,
    Point,
    Rgba,
    Segment,
    Subpath,
)

NUMBER_PATTERN = re.compile(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?")
PATH_COMMANDS = frozenset("MmLlHhVvCcSsQqTtAaZz")
PATH_SEPARATOR_CHARS = frozenset(" ,\t\n\r")
QUADRATIC_CONTROL_FRACTION = 2 / 3

Token: TypeAlias = str | float

PATH_ELEMENT_PATTERN = re.compile(r"<path\s+([^>]*?)/>")
ATTRIBUTE_PATTERN = re.compile(r'(\w+)="([^"]*)"')
TRANSLATE_PATTERN = re.compile(r"translate\(\s*([-\d.eE+]+)\s*,\s*([-\d.eE+]+)\s*\)")
HEX_COLOR_LENGTH = 7
HEX_COLOR_CHANNELS = (1, 3, 5)


def tokenize_path_data(path_data: str) -> list[Token]:
    tokens: list[Token] = []
    position = 0
    while position < len(path_data):
        char = path_data[position]
        if char in PATH_COMMANDS:
            tokens.append(char)
            position += 1
        elif char in PATH_SEPARATOR_CHARS:
            position += 1
        else:
            match = NUMBER_PATTERN.match(path_data, position)
            if not match:
                raise ValueError(f"bad path data at {path_data[position : position + 40]!r}")
            tokens.append(float(match.group()))
            position = match.end()
    return tokens


def take_numbers(tokens: list[Token], count: int, command: str) -> tuple[list[float], list[Token]]:
    head = tokens[:count]
    rest = tokens[count:]
    if len(head) < count or any(isinstance(token, str) for token in head):
        raise ValueError(f"not enough args for {command}")
    return [float(token) for token in head], rest


def absolute_coord(origin: float, value: float, is_relative: bool) -> float:
    return origin + value if is_relative else value


def quadratic_to_cubic(
    start_x: float,
    start_y: float,
    control_x: float,
    control_y: float,
    end_x: float,
    end_y: float,
) -> tuple[float, float, float, float]:
    first_x = start_x + QUADRATIC_CONTROL_FRACTION * (control_x - start_x)
    first_y = start_y + QUADRATIC_CONTROL_FRACTION * (control_y - start_y)
    second_x = end_x + QUADRATIC_CONTROL_FRACTION * (control_x - end_x)
    second_y = end_y + QUADRATIC_CONTROL_FRACTION * (control_y - end_y)
    return first_x, first_y, second_x, second_y


def parse_path_data(path_data: str) -> tuple[Subpath, ...]:
    tokens = tokenize_path_data(path_data)
    subpaths: list[Subpath] = []
    current: list[Segment] = []
    x = y = 0.0
    start_x = start_y = 0.0
    previous_command = ""
    previous_control: Point | None = None

    while tokens:
        token = tokens[0]
        if isinstance(token, str):
            command = token
            tokens = tokens[1:]
        elif previous_command in ("M", "m"):
            command = "L" if previous_command == "M" else "l"
        elif previous_command:
            command = previous_command
        else:
            raise ValueError("path data starts with number")

        is_relative = command.islower()
        kind = command.upper()

        if kind == "Z":
            if current:
                current.append(ClosePath())
                subpaths.append(tuple(current))
                current = []
            x, y = start_x, start_y
            previous_control = None
            previous_command = command
            continue

        if kind == "M":
            values, tokens = take_numbers(tokens, 2, command)
            x = absolute_coord(x, values[0], is_relative)
            y = absolute_coord(y, values[1], is_relative)
            if current:
                subpaths.append(tuple(current))
            current = [MoveTo(x, y)]
            start_x, start_y = x, y
            previous_control = None
            previous_command = "l" if is_relative else "L"
            continue

        if not current:
            current = [MoveTo(x, y)]

        if kind == "L":
            values, tokens = take_numbers(tokens, 2, command)
            x = absolute_coord(x, values[0], is_relative)
            y = absolute_coord(y, values[1], is_relative)
            current.append(LineTo(x, y))
            previous_control = None
        elif kind == "H":
            values, tokens = take_numbers(tokens, 1, command)
            x = absolute_coord(x, values[0], is_relative)
            current.append(LineTo(x, y))
            previous_control = None
        elif kind == "V":
            values, tokens = take_numbers(tokens, 1, command)
            y = absolute_coord(y, values[0], is_relative)
            current.append(LineTo(x, y))
            previous_control = None
        elif kind == "C":
            values, tokens = take_numbers(tokens, 6, command)
            x1 = absolute_coord(x, values[0], is_relative)
            y1 = absolute_coord(y, values[1], is_relative)
            x2 = absolute_coord(x, values[2], is_relative)
            y2 = absolute_coord(y, values[3], is_relative)
            x = absolute_coord(x, values[4], is_relative)
            y = absolute_coord(y, values[5], is_relative)
            current.append(CurveTo(x1, y1, x2, y2, x, y))
            previous_control = (x2, y2)
        elif kind == "S":
            values, tokens = take_numbers(tokens, 4, command)
            if previous_control and previous_command.upper() in ("C", "S"):
                x1 = 2 * x - previous_control[0]
                y1 = 2 * y - previous_control[1]
            else:
                x1, y1 = x, y
            x2 = absolute_coord(x, values[0], is_relative)
            y2 = absolute_coord(y, values[1], is_relative)
            x = absolute_coord(x, values[2], is_relative)
            y = absolute_coord(y, values[3], is_relative)
            current.append(CurveTo(x1, y1, x2, y2, x, y))
            previous_control = (x2, y2)
        elif kind == "Q":
            values, tokens = take_numbers(tokens, 4, command)
            start_point_x, start_point_y = x, y
            control_x = absolute_coord(x, values[0], is_relative)
            control_y = absolute_coord(y, values[1], is_relative)
            x = absolute_coord(x, values[2], is_relative)
            y = absolute_coord(y, values[3], is_relative)
            first_x, first_y, second_x, second_y = quadratic_to_cubic(
                start_point_x, start_point_y, control_x, control_y, x, y
            )
            current.append(CurveTo(first_x, first_y, second_x, second_y, x, y))
            previous_control = (second_x, second_y)
        elif kind == "T":
            values, tokens = take_numbers(tokens, 2, command)
            start_point_x, start_point_y = x, y
            if previous_control and previous_command.upper() in ("Q", "T"):
                control_x = 2 * start_point_x - previous_control[0]
                control_y = 2 * start_point_y - previous_control[1]
            else:
                control_x, control_y = start_point_x, start_point_y
            x = absolute_coord(x, values[0], is_relative)
            y = absolute_coord(y, values[1], is_relative)
            first_x, first_y, second_x, second_y = quadratic_to_cubic(
                start_point_x, start_point_y, control_x, control_y, x, y
            )
            current.append(CurveTo(first_x, first_y, second_x, second_y, x, y))
            previous_control = (second_x, second_y)
        elif kind == "A":
            values, tokens = take_numbers(tokens, 7, command)
            x = absolute_coord(x, values[5], is_relative)
            y = absolute_coord(y, values[6], is_relative)
            current.append(LineTo(x, y))
            previous_control = None
        else:
            raise ValueError(f"unsupported {command}")

        previous_command = command

    if current:
        subpaths.append(tuple(current))
    return tuple(subpaths)


def parse_hex_color(fill_hex: str) -> Rgba:
    if len(fill_hex) != HEX_COLOR_LENGTH:
        raise ValueError(f"unsupported fill color: {fill_hex}")
    red, green, blue = (int(fill_hex[index : index + 2], 16) for index in HEX_COLOR_CHANNELS)
    return red, green, blue, 255


def parse_translate(transform: str) -> Point:
    stripped = transform.strip()
    match = TRANSLATE_PATTERN.match(stripped)
    if match:
        return float(match.group(1)), float(match.group(2))
    if stripped and stripped != "none" and not stripped.startswith("translate"):
        raise ValueError(f"unsupported transform: {transform}")
    return 0.0, 0.0


def contours_from_svg(svg_text: str) -> tuple[Contour, ...]:
    contours: list[Contour] = []
    for element in PATH_ELEMENT_PATTERN.finditer(svg_text):
        attributes = dict(ATTRIBUTE_PATTERN.findall(element.group(1)))
        path_data = attributes.get("d")
        if not path_data:
            continue
        fill = parse_hex_color(attributes.get("fill", "#000000"))
        dx, dy = parse_translate(attributes.get("transform", ""))
        subpaths = parse_path_data(path_data)
        segments = tuple(segment.translated(dx, dy) for subpath in subpaths for segment in subpath)
        if segments:
            contours.append(Contour(segments=segments, fill=fill))
    return tuple(contours)
