from __future__ import annotations

import base64
import os
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

from ai_client import create_openai_client


FONT_DIRS = [
    Path("C:/Windows/Fonts"),
    Path(os.getenv("LOCALAPPDATA", "")) / "Microsoft/Windows/Fonts",
]


def scan_fonts() -> list[Path]:
    fonts: list[Path] = []
    for directory in FONT_DIRS:
        if directory.exists():
            fonts.extend(p for p in directory.iterdir() if p.suffix.lower() in {".ttf", ".otf", ".ttc"})
    return sorted(set(fonts), key=lambda p: p.name.lower())


def choose_font(font_style: str = "") -> Path | None:
    fonts = scan_fonts()
    preferred = ["simhei", "msyhbd", "sourcehan", "notosans", "bold"]
    if any(word in font_style for word in ("手写", "书法")):
        preferred = ["好运藏在努力里", "kaiti", "stkaiti"] + preferred
    if any(word in font_style for word in ("宋体", "衬线")):
        preferred = ["simsun", "song", "stsong"] + preferred
    for keyword in preferred:
        match = next((p for p in fonts if keyword.lower() in p.stem.lower()), None)
        if match:
            return match
    return fonts[0] if fonts else None


def _font(path: Path | None, size: int) -> ImageFont.ImageFont:
    if path:
        try:
            return ImageFont.truetype(str(path), size=size)
        except OSError:
            pass
    return ImageFont.load_default()


def _cover_3x4(image_bytes: bytes) -> Image.Image:
    with Image.open(BytesIO(image_bytes)) as source:
        normalized = ImageOps.exif_transpose(source).convert("RGB")
    return ImageOps.fit(normalized, (1024, 1365), Image.Resampling.LANCZOS)


def _prepare_api_image(image_bytes: bytes, filename: str) -> BytesIO:
    """Create a compact upload copy; the original remains untouched for rendering."""
    with Image.open(BytesIO(image_bytes)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail((1536, 1536), Image.Resampling.LANCZOS)
        output = BytesIO()
        image.save(output, "JPEG", quality=86, optimize=True)
    output.seek(0)
    output.name = filename
    return output


def _palette(template_bytes: bytes | None, color_style: str) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    semantic = {
        "粉": (245, 58, 147, 255), "黄": (249, 219, 72, 255),
        "绿": (73, 174, 111, 255), "蓝": (64, 137, 219, 255),
        "红": (229, 62, 69, 255), "橙": (244, 128, 47, 255),
        "紫": (142, 92, 190, 255),
    }
    accent = next((value for key, value in semantic.items() if key in color_style), None)
    if template_bytes:
        try:
            reference = _cover_3x4(template_bytes).resize((96, 128))
            colors = reference.quantize(colors=12).convert("RGB").getcolors(96 * 128) or []
            ranked = [color for _, color in sorted(colors, reverse=True)]
            vivid = max(ranked, key=lambda c: max(c) - min(c)) if ranked else (248, 198, 42)
            accent = accent or (*vivid, 255)
        except Exception:
            pass
    accent = accent or (248, 198, 42, 255)
    foreground = (25, 25, 27, 255) if any(w in color_style for w in ("浅色", "白底", "米色")) else (255, 255, 255, 255)
    return foreground, accent


def generate_ai_base(
    *, photo_bytes: bytes, template_bytes: bytes, api_key: str, layout_type: str,
    color_style: str, font_style: str,
) -> bytes:
    # Image edits can take substantially longer than text/vision analysis.
    client = create_openai_client(api_key, timeout_seconds=300.0)
    photo = _prepare_api_image(photo_bytes, "person.jpg")
    template = _prepare_api_image(template_bytes, "reference.jpg")
    prompt = f"""
Create a polished vertical social-media cover base. The FIRST image is the person/photo
that must remain recognizable. The SECOND image is a design reference. Match its crop,
subject scale, visual hierarchy, lighting, color grade, negative space and graphic mood,
but do not copy logos or existing words. Produce NO readable text and leave clean space
for typography. Layout analysis: {layout_type}. Palette: {color_style}. Typography mood:
{font_style}. Output a premium 3:4 editorial poster base.
""".strip()
    response = client.images.edit(
        model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2"),
        image=[photo, template], prompt=prompt, input_fidelity="high",
        size="1024x1536", quality="medium", output_format="png", response_format="b64_json",
    )
    if not response.data or not response.data[0].b64_json:
        raise ValueError("图像模型没有返回图片。")
    return base64.b64decode(response.data[0].b64_json)


def render_poster(
    *, base_bytes: bytes, title: str, subtitle: str = "", badge: str = "",
    layout_type: str = "", color_style: str = "", font_style: str = "",
    template_bytes: bytes | None = None,
) -> bytes:
    image = _cover_3x4(base_bytes)
    image = ImageEnhance.Contrast(image).enhance(1.04).convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    font_path = choose_font(font_style)
    large_title = any(word in font_style for word in ("大字", "较大", "突出", "粗体"))
    title_font = _font(font_path, 112 if large_title else 86)
    sub_font = _font(font_path, 34)
    badge_font = _font(font_path, 28)
    foreground, accent = _palette(template_bytes, color_style)
    if "粉色" in font_style: foreground = (245, 58, 147, 255)
    elif "黄色" in font_style: foreground = (249, 219, 72, 255)
    elif "白色" in font_style: foreground = (255, 255, 255, 255)
    shadow = (0, 0, 0, 135)
    placement = font_style + layout_type
    top = 105 if any(w in placement for w in ("顶部", "上方", "左上")) else 820 if "下方" in placement else 610
    centered = "居中" in placement and "居左" not in placement
    left = 512 if centered else 66
    max_width = 900 if centered else 850
    lines: list[str] = []
    current = ""
    for char in title.strip():
        trial = current + char
        if current and draw.textbbox((0, 0), trial, font=title_font)[2] > max_width:
            lines.append(current); current = char
        else:
            current = trial
    if current: lines.append(current)
    lines = lines[:3]
    panel_top = top - 36
    y = top
    pink_title = foreground[:3] == (245, 58, 147)
    stroke_width = 7 if "描边" in font_style or pink_title else 3
    stroke_fill = (255, 255, 255, 245) if "白色描边" in font_style or pink_title else shadow
    anchor = "ma" if centered else None
    for line in lines:
        draw.text((left, y), line, font=title_font, fill=foreground, anchor=anchor, stroke_width=stroke_width, stroke_fill=stroke_fill)
        y += int(getattr(title_font, "size", 92) * 1.08)
    if subtitle:
        subtitle_fill = (249, 219, 72, 255) if "黄色" in font_style else accent
        draw.text((left, y + 14), subtitle, font=sub_font, fill=subtitle_fill, anchor=anchor, stroke_width=1, stroke_fill=shadow)
    if badge:
        bbox = draw.textbbox((0, 0), badge, font=badge_font)
        width = bbox[2] - bbox[0] + 44
        badge_left = 66 if centered else left
        draw.rounded_rectangle((badge_left, panel_top - 58, badge_left + width, panel_top - 10), 22, fill=accent)
        draw.text((badge_left + 22, panel_top - 52), badge, font=badge_font, fill=(30, 27, 18, 255))
    output = BytesIO(); image.convert("RGB").save(output, "PNG", optimize=True)
    return output.getvalue()
