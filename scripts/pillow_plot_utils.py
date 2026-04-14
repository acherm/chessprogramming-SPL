from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont


FONT_SANS = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
]

FONT_SANS_BOLD = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]

FONT_MONO = [
    "/System/Library/Fonts/Menlo.ttc",
    "/System/Library/Fonts/SFNSMono.ttf",
    "/System/Library/Fonts/Monaco.ttf",
]


def load_font(size: int, *, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    size = max(8, int(size))
    candidates = FONT_MONO if mono else FONT_SANS_BOLD if bold else FONT_SANS
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def rgba(value: str | tuple[int, int, int] | tuple[int, int, int, int], alpha: int | None = None) -> tuple[int, int, int, int]:
    if isinstance(value, tuple):
        if len(value) == 4:
            return value
        return value + ((255 if alpha is None else alpha),)
    rgb = ImageColor.getrgb(value)
    return rgb + ((255 if alpha is None else alpha),)


def new_canvas(width: int, height: int, background: str = "#ffffff") -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGBA", (int(width), int(height)), rgba(background))
    return image, ImageDraw.Draw(image, "RGBA")


def save_png(image: Image.Image, path: Path, *, dpi: int = 300) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(path, format="PNG", dpi=(dpi, dpi), optimize=True)


def text_bbox(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    size: int,
    bold: bool = False,
    mono: bool = False,
    anchor: str = "la",
) -> tuple[int, int, int, int]:
    font = load_font(size, bold=bold, mono=mono)
    return draw.textbbox((0, 0), text, font=font, anchor=anchor)


def draw_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    *,
    size: int,
    fill: str | tuple[int, int, int] | tuple[int, int, int, int] = "#222222",
    bold: bool = False,
    mono: bool = False,
    anchor: str = "la",
) -> None:
    font = load_font(size, bold=bold, mono=mono)
    draw.text(xy, text, font=font, fill=rgba(fill), anchor=anchor)


def draw_rotated_text(
    image: Image.Image,
    xy: tuple[float, float],
    text: str,
    *,
    size: int,
    fill: str | tuple[int, int, int] | tuple[int, int, int, int] = "#222222",
    bold: bool = False,
    mono: bool = False,
    angle: int = 90,
    anchor: str = "mm",
) -> None:
    font = load_font(size, bold=bold, mono=mono)
    left, top, right, bottom = font.getbbox(text)
    pad = max(6, size // 3)
    text_w = max(1, right - left)
    text_h = max(1, bottom - top)
    text_image = Image.new("RGBA", (text_w + pad * 2, text_h + pad * 2), (0, 0, 0, 0))
    text_draw = ImageDraw.Draw(text_image, "RGBA")
    text_draw.text((pad - left, pad - top), text, font=font, fill=rgba(fill))
    rotated = text_image.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
    x, y = xy
    if anchor == "mm":
        paste_xy = (int(round(x - rotated.width / 2)), int(round(y - rotated.height / 2)))
    elif anchor == "ma":
        paste_xy = (int(round(x - rotated.width / 2)), int(round(y)))
    else:
        paste_xy = (int(round(x)), int(round(y)))
    image.alpha_composite(rotated, dest=paste_xy)


def draw_dashed_line(
    draw: ImageDraw.ImageDraw,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    fill: str | tuple[int, int, int] | tuple[int, int, int, int] = "#999999",
    width: int = 2,
    dash: int = 10,
    gap: int = 8,
) -> None:
    x1, y1 = start
    x2, y2 = end
    if x1 == x2:
        y = y1
        while y < y2:
            segment_end = min(y + dash, y2)
            draw.line((x1, y, x2, segment_end), fill=rgba(fill), width=width)
            y += dash + gap
        return
    if y1 == y2:
        x = x1
        while x < x2:
            segment_end = min(x + dash, x2)
            draw.line((x, y1, segment_end, y2), fill=rgba(fill), width=width)
            x += dash + gap
        return
    draw.line((x1, y1, x2, y2), fill=rgba(fill), width=width)
