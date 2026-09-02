from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


FONT_CANDIDATES = [
    Path("C:/Windows/Fonts/msyhbd.ttc"),
    Path("C:/Windows/Fonts/msyh.ttc"),
    Path("C:/Windows/Fonts/simhei.ttf"),
]


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONT_CANDIDATES:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def infer_accent_color(color_advice: str) -> tuple[int, int, int]:
    text = color_advice.lower()
    color_map = [
        (("黄", "yellow"), (255, 210, 45)),
        (("橙", "orange"), (255, 105, 45)),
        (("红", "red"), (235, 55, 65)),
        (("粉", "pink"), (255, 105, 160)),
        (("蓝", "blue"), (50, 135, 255)),
        (("绿", "green"), (55, 180, 115)),
        (("紫", "purple"), (145, 95, 220)),
    ]
    for keywords, color in color_map:
        if any(keyword in text for keyword in keywords):
            return color
    return (255, 92, 55)


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
    max_lines: int = 4,
) -> list[str]:
    characters = list(text.strip())
    lines: list[str] = []
    current = ""
    for character in characters:
        candidate = current + character
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if current and bbox[2] - bbox[0] > max_width:
            lines.append(current)
            current = character
            if len(lines) == max_lines - 1:
                break
        else:
            current = candidate
    remaining_start = sum(len(line) for line in lines)
    if len(lines) == max_lines - 1 and remaining_start < len(characters):
        current = "".join(characters[remaining_start:])
        while current:
            bbox = draw.textbbox((0, 0), current, font=font)
            if bbox[2] - bbox[0] <= max_width:
                break
            current = current[:-1]
        if remaining_start + len(current) < len(characters) and len(current) > 1:
            current = current[:-1] + "…"
    if current:
        lines.append(current)
    return lines or ["未填写标题"]


def fit_title(
    draw: ImageDraw.ImageDraw,
    title: str,
    max_width: int,
    max_height: int,
    start_size: int,
    max_lines: int,
) -> tuple[ImageFont.ImageFont, list[str], int]:
    minimum = max(26, start_size // 3)
    for size in range(start_size, minimum - 1, -4):
        font = load_font(size)
        lines = wrap_text(draw, title, font, max_width, max_lines)
        line_height = int(size * 1.22)
        if line_height * len(lines) <= max_height:
            return font, lines, line_height
    font = load_font(minimum)
    return font, wrap_text(draw, title, font, max_width, max_lines), int(minimum * 1.22)


def draw_text_with_shadow(
    draw: ImageDraw.ImageDraw,
    position: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    anchor: str | None = None,
) -> None:
    x, y = position
    shadow_offset = max(2, getattr(font, "size", 30) // 24)
    draw.text(
        (x + shadow_offset, y + shadow_offset),
        text,
        font=font,
        fill=(0, 0, 0, 180),
        anchor=anchor,
    )
    draw.text((x, y), text, font=font, fill=fill, anchor=anchor)


def render_center_poster(
    image: Image.Image, title: str, accent: tuple[int, int, int]
) -> Image.Image:
    canvas = image.convert("RGBA")
    width, height = canvas.size
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    box = (
        int(width * 0.07),
        int(height * 0.48),
        int(width * 0.93),
        int(height * 0.88),
    )
    overlay_draw.rounded_rectangle(
        box,
        radius=max(18, width // 35),
        fill=(10, 10, 12, 175),
        outline=accent + (255,),
        width=max(5, width // 180),
    )
    canvas = Image.alpha_composite(canvas, overlay)
    draw = ImageDraw.Draw(canvas)
    max_width = int(width * 0.76)
    font, lines, line_height = fit_title(
        draw,
        title,
        max_width=max_width,
        max_height=int(height * 0.30),
        start_size=max(60, width // 9),
        max_lines=3,
    )
    total_height = len(lines) * line_height
    y = int(height * 0.68 - total_height / 2)
    for line in lines:
        draw_text_with_shadow(
            draw,
            (width // 2, y),
            line,
            font,
            (255, 255, 255),
            anchor="ma",
        )
        y += line_height
    draw.rounded_rectangle(
        (int(width * 0.39), int(height * 0.91), int(width * 0.61), int(height * 0.925)),
        radius=20,
        fill=accent,
    )
    return canvas.convert("RGB")


def render_left_text_right_image(
    image: Image.Image, title: str, accent: tuple[int, int, int]
) -> Image.Image:
    canvas = image.convert("RGBA")
    width, height = canvas.size
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    panel_end = int(width * 0.58)
    alpha = Image.new("L", (panel_end, 1))
    alpha.putdata(
        [min(int(220 * (1 - x / panel_end) + 35), 235) for x in range(panel_end)]
    )
    alpha = alpha.resize((panel_end, height))
    panel = Image.new("RGBA", (panel_end, height), (12, 12, 16, 0))
    panel.putalpha(alpha)
    overlay.alpha_composite(panel, (0, 0))
    canvas = Image.alpha_composite(canvas, overlay)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        (int(width * 0.07), int(height * 0.17), int(width * 0.13), int(height * 0.185)),
        radius=12,
        fill=accent,
    )
    font, lines, line_height = fit_title(
        draw,
        title,
        max_width=int(width * 0.40),
        max_height=int(height * 0.56),
        start_size=max(58, width // 10),
        max_lines=4,
    )
    y = int(height * 0.24)
    for line in lines:
        draw_text_with_shadow(
            draw, (int(width * 0.07), y), line, font, (255, 255, 255)
        )
        y += line_height
    return canvas.convert("RGB")


def render_nine_grid_card(
    image: Image.Image, title: str, accent: tuple[int, int, int]
) -> Image.Image:
    canvas = image.convert("RGBA")
    width, height = canvas.size
    softened = canvas.filter(ImageFilter.GaussianBlur(radius=max(2, width // 350)))
    canvas = Image.blend(canvas, softened, 0.18)
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 45))
    draw_overlay = ImageDraw.Draw(overlay)
    line_color = accent + (170,)
    line_width = max(3, width // 250)
    for fraction in (1 / 3, 2 / 3):
        x = int(width * fraction)
        y = int(height * fraction)
        draw_overlay.line((x, 0, x, height), fill=line_color, width=line_width)
        draw_overlay.line((0, y, width, y), fill=line_color, width=line_width)
    card = (
        int(width * 0.08),
        int(height * 0.34),
        int(width * 0.92),
        int(height * 0.69),
    )
    draw_overlay.rounded_rectangle(
        card,
        radius=max(20, width // 30),
        fill=(250, 247, 240, 232),
        outline=accent + (255,),
        width=max(5, width // 180),
    )
    canvas = Image.alpha_composite(canvas, overlay)
    draw = ImageDraw.Draw(canvas)
    font, lines, line_height = fit_title(
        draw,
        title,
        max_width=int(width * 0.72),
        max_height=int(height * 0.25),
        start_size=max(56, width // 10),
        max_lines=3,
    )
    total_height = len(lines) * line_height
    y = int(height * 0.515 - total_height / 2)
    for line in lines:
        draw.text(
            (width // 2, y),
            line,
            font=font,
            fill=(25, 25, 28),
            anchor="ma",
        )
        y += line_height
    return canvas.convert("RGB")


def choose_template(layout_type: str) -> str:
    normalized = layout_type.strip().lower()
    if "九宫格" in normalized or "文字卡" in normalized:
        return "nine_grid"
    if any(keyword in normalized for keyword in ("左文右图", "文字左", "人物右")):
        return "left_text"
    return "center_poster"


def compose_cover(
    image_bytes: bytes,
    title: str,
    layout_type: str,
    color_advice: str,
) -> bytes:
    if not image_bytes:
        raise ValueError("没有可用于合成的照片。")
    with Image.open(BytesIO(image_bytes)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
    if image.width < 320 or image.height < 320:
        scale = max(320 / image.width, 320 / image.height)
        image = image.resize(
            (int(image.width * scale), int(image.height * scale)),
            Image.Resampling.LANCZOS,
        )
    accent = infer_accent_color(color_advice)
    template = choose_template(layout_type)
    if template == "left_text":
        result = render_left_text_right_image(image, title, accent)
    elif template == "nine_grid":
        result = render_nine_grid_card(image, title, accent)
    else:
        result = render_center_poster(image, title, accent)
    output = BytesIO()
    result.save(output, format="PNG", optimize=True)
    return output.getvalue()
