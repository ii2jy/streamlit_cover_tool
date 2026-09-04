from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

import streamlit as st
from openai import OpenAI
from PIL import Image, ImageOps
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from cover_renderer import compose_cover
from ai_client import create_openai_client, friendly_openai_error
from database import COVER_CATEGORIES, INITIAL_HOOK_TYPES, initialize_database
from direct_poster import generate_ai_base, render_poster
from grid_component import GridItem, create_cover_thumbnail, render_image_grid
from ideas import mark_idea_published, render_ideas_page
from mobile_access import render_mobile_access
from prompts import DESIGN_SYSTEM_PROMPT
from radar import render_radar_page
from ui_styles import apply_app_styles


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
IMAGE_DIR = DATA_DIR / "images"
GENERATED_DIR = DATA_DIR / "generated"
DB_PATH = DATA_DIR / "covers.db"
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")


class CoverAnalysis(BaseModel):
    """AI 拆解结果的唯一数据契约。"""

    model_config = ConfigDict(extra="forbid")

    layout_type: str = Field(description="封面的视觉版式类型")
    layout_type_status: Literal["已有", "新增"]
    layout_type_description: str = Field(description="对版式类型的简短定义")
    hook_type: str = Field(description="标题使用的钩子结构类型")
    hook_type_status: Literal["已有", "新增"]
    hook_type_description: str = Field(description="对钩子结构类型的简短定义")
    color_style: str = Field(description="主色、强调色、对比度和整体配色气质")
    font_style: str = Field(description="字体粗细、大小层级、字形和装饰效果")
    emotional_tone: str = Field(description="封面和标题共同形成的情绪基调")
    stop_reason: str = Field(description="一句话说明为什么这个封面和标题会让用户停留")


class CoverSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(description="候选封面主标题")
    hook_type: str = Field(description="使用的钩子结构类型")
    layout_type: str = Field(description="推荐的版式类型")
    text_layout: str = Field(description="字号层级、行数和文字位置的具体建议")
    color_advice: str = Field(description="主色、强调色和文字对比建议")
    stop_reason: str = Field(description="为什么这个设计能让目标用户停留")


class GenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    photo_observation: str = Field(description="对新照片构图和可放字区域的简短观察")
    suggestions: list[CoverSuggestion] = Field(min_length=3, max_length=3)


ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "layout_type": {"type": "string"},
        "layout_type_status": {"type": "string", "enum": ["已有", "新增"]},
        "layout_type_description": {"type": "string"},
        "hook_type": {"type": "string"},
        "hook_type_status": {"type": "string", "enum": ["已有", "新增"]},
        "hook_type_description": {"type": "string"},
        "color_style": {"type": "string"},
        "font_style": {"type": "string"},
        "emotional_tone": {"type": "string"},
        "stop_reason": {"type": "string"},
    },
    "required": [
        "layout_type",
        "layout_type_status",
        "layout_type_description",
        "hook_type",
        "hook_type_status",
        "hook_type_description",
        "color_style",
        "font_style",
        "emotional_tone",
        "stop_reason",
    ],
}


GENERATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "photo_observation": {"type": "string"},
        "suggestions": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "hook_type": {"type": "string"},
                    "layout_type": {"type": "string"},
                    "text_layout": {"type": "string"},
                    "color_advice": {"type": "string"},
                    "stop_reason": {"type": "string"},
                },
                "required": [
                    "title",
                    "hook_type",
                    "layout_type",
                    "text_layout",
                    "color_advice",
                    "stop_reason",
                ],
            },
        },
    },
    "required": ["photo_observation", "suggestions"],
}


PROMPT_TEMPLATE = """
你是一名专门研究小红书内容点击心理和封面视觉设计的分析师。

请结合用户提供的封面截图与原标题，拆解这条素材。你的任务是描述实际可见的设计和标题机制，不要凭空猜测作者身份、数据表现或制作工具。

分析要求：
1. layout_type：必须优先从“已有版式类型库”中选择最匹配的一项，并原样返回分类名称。只有所有已有分类都明显不匹配时，才能新建一个简短、稳定、可复用的分类名，并把 layout_type_status 标为“新增”；否则必须标为“已有”。layout_type_description 用一句话解释这个类型。
2. hook_type：必须优先从“已有钩子结构库”中选择最匹配的一项，并原样返回分类名称。只有所有已有分类都明显不匹配时，才能新建分类，并把 hook_type_status 标为“新增”；否则必须标为“已有”。只判断最主要的一种，hook_type_description 用一句话解释其结构。
3. color_style：说明主色、强调色、明暗对比和配色气质。
4. font_style：说明字体粗细、字号层级、文字位置、描边/底色/阴影等实际可见特征。
5. emotional_tone：概括封面和标题共同形成的情绪，例如“真诚脆弱”“强烈警示”“轻松治愈”“焦虑紧迫”。
6. stop_reason：只用一句中文，说明目标用户为什么可能停下来。必须把视觉线索和标题钩子联系起来，不能只说“很吸引人”。

原标题：{title}

已有钩子结构库：
{hook_types}

已有版式类型库：
{layout_types}

严格按照给定 JSON Schema 返回，不要添加 Markdown、解释、代码围栏或额外字段。
""".strip()


GENERATION_PROMPT_TEMPLATE = """
你是一名小红书封面策划师。请根据用户本次上传的新照片、主题描述，以及历史素材库中最近录入的有效设计结构，给出 3 套明显不同但都能真实兑现内容的封面方案。

本次主题描述：{topic}
用户指定的钩子结构：{preferred_hook_type}
用户明确选中的对标模板：{selected_template_title}
当前是第 {batch_number} 批方案。请避免与上一批可能出现的常规表述雷同，三套方案之间也必须使用不同的表达角度。

历史参考素材（按录入时间从近到远，仅用于学习结构，不能复制原标题）：
{reference_samples}

要求：
1. 先观察新照片中的人物/主体位置、景别、背景复杂度和适合放字的留白区域，用 photo_observation 简要说明。
2. 必须返回恰好 3 个候选标题。标题要适合小红书封面小屏阅读，默认控制在 4—12 个汉字；确有必要可以稍长，但不能写成完整正文。
3. 每个候选标题标明 hook_type，不能照抄历史标题。如果用户指定了明确的钩子结构，方案1必须使用该结构，另外两套可以从不同表达角度使用该结构或选择更适合的已有结构；如果用户选择“自动匹配”，则优先使用历史参考素材中已经出现的结构。
4. 如果用户选中了对标模板，必须优先学习该模板的构图比例、文字层级、留白、色块与视觉节奏，但不能复制模板中的原文字；再结合新照片主体位置做适配。每套方案给出 layout_type，并根据新照片具体说明文字区域、主标题行数、相对字号、是否需要副标题、描边、色块或留白。
5. color_advice 必须结合照片实际明暗和背景色，保证文字可读。
6. stop_reason 用一句话解释用户为什么可能停留，必须同时联系主题心理与视觉设计。
7. 不得承诺主题描述中没有的结果，不得编造数据、身份或经历。

严格按照给定 JSON Schema 返回，不要添加 Markdown、解释、代码围栏或额外字段。
""".strip()


def ensure_storage() -> None:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    initialize_database(DB_PATH)


def save_generated_image(image_bytes: bytes, title: str, prefix: str = "poster") -> Path:
    safe_title = "".join(c for c in title.strip() if c not in '\\/:*?\"<>|')[:36] or "untitled"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    digest = hashlib.sha256(image_bytes).hexdigest()[:8]
    path = GENERATED_DIR / f"{prefix}-{timestamp}-{safe_title}-{digest}.png"
    path.write_bytes(image_bytes)
    return path


def render_long_press_image(image_bytes: bytes, alt: str = "生成海报") -> None:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    safe_alt = html.escape(alt, quote=True)
    st.markdown(
        f'<div class="long-press-image"><img src="data:image/png;base64,{encoded}" '
        f'alt="{safe_alt}" draggable="false"></div>',
        unsafe_allow_html=True,
    )
    st.caption("手机端可长按图片，选择“保存图片”或“添加到照片”。")


def get_api_key() -> str | None:
    key = os.getenv("OPENAI_API_KEY")
    if key:
        return key
    try:
        return st.secrets.get("OPENAI_API_KEY")
    except (FileNotFoundError, KeyError):
        return None


def load_category_types(table_name: Literal["hook_types", "layout_types"]) -> list[sqlite3.Row]:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            f"SELECT id, name, description, source, review_status "
            f"FROM {table_name} ORDER BY id"
        ).fetchall()


def format_category_types(rows: list[sqlite3.Row]) -> str:
    if not rows:
        return "（当前分类库为空，本次必须新建一个准确分类并标为“新增”）"
    return "\n".join(
        f"- {row['name']}：{row['description']}" for row in rows
    )


def reconcile_category_status(
    analysis: CoverAnalysis,
    hook_types: list[sqlite3.Row],
    layout_types: list[sqlite3.Row],
) -> CoverAnalysis:
    """以后端分类库为准，防止模型错误标记已有/新增。"""

    known_hooks = {row["name"].strip().casefold() for row in hook_types}
    known_layouts = {row["name"].strip().casefold() for row in layout_types}
    payload = analysis.model_dump()
    payload["hook_type_status"] = (
        "已有" if analysis.hook_type.strip().casefold() in known_hooks else "新增"
    )
    payload["layout_type_status"] = (
        "已有" if analysis.layout_type.strip().casefold() in known_layouts else "新增"
    )
    return CoverAnalysis.model_validate(payload)


def optimize_image_for_ai(
    image_bytes: bytes, mime_type: str, max_side: int = 1600
) -> tuple[bytes, str]:
    """Normalize phone screenshots before sending them through a local proxy.

    The original file is still saved unchanged. Only the API request copy is
    resized and encoded as JPEG, which makes vision requests much more stable.
    """
    try:
        with Image.open(BytesIO(image_bytes)) as source:
            image = ImageOps.exif_transpose(source)
            image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
            if image.mode in {"RGBA", "LA"}:
                background = Image.new("RGB", image.size, "white")
                alpha = image.getchannel("A")
                background.paste(image.convert("RGB"), mask=alpha)
                image = background
            elif image.mode != "RGB":
                image = image.convert("RGB")
            output = BytesIO()
            image.save(output, format="JPEG", quality=86, optimize=True)
            return output.getvalue(), "image/jpeg"
    except Exception:
        # Keep test doubles and already-valid uncommon inputs backwards compatible.
        return image_bytes, mime_type


def image_to_data_url(image_bytes: bytes, mime_type: str) -> str:
    optimized_bytes, optimized_mime = optimize_image_for_ai(image_bytes, mime_type)
    encoded = base64.b64encode(optimized_bytes).decode("ascii")
    return f"data:{optimized_mime};base64,{encoded}"


def analyze_cover(
    *,
    image_bytes: bytes,
    mime_type: str,
    title: str,
    api_key: str,
    hook_types: list[sqlite3.Row],
    layout_types: list[sqlite3.Row],
) -> CoverAnalysis:
    client = create_openai_client(api_key, client_class=OpenAI)
    response = client.responses.create(
        model=MODEL,
        store=False,
        instructions=DESIGN_SYSTEM_PROMPT,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": PROMPT_TEMPLATE.format(
                            title=title,
                            hook_types=format_category_types(hook_types),
                            layout_types=format_category_types(layout_types),
                        ),
                    },
                    {
                        "type": "input_image",
                        "image_url": image_to_data_url(image_bytes, mime_type),
                        "detail": "high",
                    },
                ],
            }
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "cover_analysis",
                "strict": True,
                "schema": ANALYSIS_SCHEMA,
            }
        },
    )
    if not response.output_text:
        raise ValueError("OpenAI API 没有返回可解析的文本结果。")
    analysis = CoverAnalysis.model_validate_json(response.output_text)
    return reconcile_category_status(analysis, hook_types, layout_types)


def load_recent_samples(
    limit: int = 10, selected_id: int | None = None
) -> list[sqlite3.Row]:
    safe_limit = max(1, min(limit, 30))
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            """
            SELECT id, image_path, category, original_title, layout_type, hook_type,
                   color_style, font_style, emotional_tone, stop_reason
            FROM cover_samples
            ORDER BY CASE WHEN id = ? THEN 0 ELSE 1 END, id DESC
            LIMIT ?
            """,
            (selected_id, safe_limit),
        ).fetchall()


def format_reference_samples(samples: list[sqlite3.Row]) -> str:
    references = []
    for row in samples:
        references.append(
            {
                "sample_id": row["id"],
                "original_title": row["original_title"],
                "layout_type": row["layout_type"],
                "hook_type": row["hook_type"],
                "color_style": row["color_style"],
                "font_style": row["font_style"],
                "emotional_tone": row["emotional_tone"],
                "stop_reason": row["stop_reason"],
            }
        )
    return json.dumps(references, ensure_ascii=False, indent=2)


def generate_cover_suggestions(
    *,
    image_bytes: bytes,
    mime_type: str,
    topic: str,
    samples: list[sqlite3.Row],
    batch_number: int,
    api_key: str,
    preferred_hook_type: str | None = None,
    selected_template_title: str | None = None,
    template_image_bytes: bytes | None = None,
    template_mime_type: str = "image/jpeg",
) -> GenerationResult:
    client = create_openai_client(api_key, client_class=OpenAI)
    user_content: list[dict[str, str]] = [
        {
            "type": "input_text",
            "text": GENERATION_PROMPT_TEMPLATE.format(
                topic=topic,
                preferred_hook_type=preferred_hook_type or "自动匹配",
                selected_template_title=selected_template_title or "未指定",
                batch_number=batch_number,
                reference_samples=format_reference_samples(samples),
            ),
        },
        {"type": "input_text", "text": "下面第一张图片是本次要制作封面的新照片。"},
        {
            "type": "input_image",
            "image_url": image_to_data_url(image_bytes, mime_type),
            "detail": "high",
        },
    ]
    if template_image_bytes:
        user_content.extend(
            [
                {
                    "type": "input_text",
                    "text": "下面第二张图片是选中的对标模板。学习设计语言，但不要复制原文字。",
                },
                {
                    "type": "input_image",
                    "image_url": image_to_data_url(
                        template_image_bytes, template_mime_type
                    ),
                    "detail": "high",
                },
            ]
        )
    response = client.responses.create(
        model=MODEL,
        store=False,
        instructions=DESIGN_SYSTEM_PROMPT,
        input=[
            {
                "role": "user",
                "content": user_content,
            }
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "cover_generation_suggestions",
                "strict": True,
                "schema": GENERATION_SCHEMA,
            }
        },
    )
    if not response.output_text:
        raise ValueError("OpenAI API 没有返回可解析的生成建议。")
    return GenerationResult.model_validate_json(response.output_text)


def save_image(image_bytes: bytes, original_name: str) -> tuple[Path, str]:
    digest = hashlib.sha256(image_bytes).hexdigest()
    suffix = Path(original_name).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    path = IMAGE_DIR / f"{digest}{suffix}"
    if not path.exists():
        path.write_bytes(image_bytes)
    return path, digest


def insert_sample(
    *,
    image_path: Path,
    image_sha256: str,
    title: str,
    category: str,
    analysis: CoverAnalysis,
) -> int:
    relative_path = image_path.relative_to(APP_DIR).as_posix()
    payload = analysis.model_dump()
    with closing(sqlite3.connect(DB_PATH)) as conn:
        now = datetime.now(timezone.utc).isoformat()
        if analysis.hook_type_status == "新增":
            conn.execute(
                """
                INSERT OR IGNORE INTO hook_types
                    (name, description, source, review_status, created_at)
                VALUES (?, ?, 'ai', 'pending', ?)
                """,
                (analysis.hook_type, analysis.hook_type_description, now),
            )
        if analysis.layout_type_status == "新增":
            conn.execute(
                """
                INSERT OR IGNORE INTO layout_types
                    (name, description, source, review_status, created_at)
                VALUES (?, ?, 'ai', 'pending', ?)
                """,
                (analysis.layout_type, analysis.layout_type_description, now),
            )
        cursor = conn.execute(
            """
            INSERT INTO cover_samples (
                image_path, image_sha256, original_title, category,
                layout_type, layout_type_is_new,
                hook_type, hook_type_is_new, color_style, font_style,
                emotional_tone, stop_reason, analysis_json, model, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                relative_path,
                image_sha256,
                title,
                category,
                analysis.layout_type,
                int(analysis.layout_type_status == "新增"),
                analysis.hook_type,
                int(analysis.hook_type_status == "新增"),
                analysis.color_style,
                analysis.font_style,
                analysis.emotional_tone,
                analysis.stop_reason,
                json.dumps(payload, ensure_ascii=False),
                MODEL,
                now,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


@st.dialog("新增对标封面", width="large")
def render_add_template_dialog() -> None:
    st.caption("上传一张你想学习的封面。AI拆解后会自动加入风格库，并立即选中使用。")
    uploaded_file = st.file_uploader(
        "上传对标封面",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=False,
        key="generator_template_upload",
    )
    title = st.text_input(
        "封面标题或风格名称",
        placeholder="例如：极简留白人物封面",
        max_chars=200,
        key="generator_template_title",
    )
    category = st.selectbox(
        "存入栏目",
        COVER_CATEGORIES,
        key="generator_template_category",
    )
    if uploaded_file is not None:
        try:
            preview = Image.open(uploaded_file)
            st.image(preview, caption="新模板预览", width=280)
            uploaded_file.seek(0)
        except Exception:
            st.error("图片无法读取，请重新选择 JPG、PNG 或 WEBP 文件。")

    if st.button(
        "AI拆解并加入风格库",
        type="primary",
        icon=":material/add_photo_alternate:",
        width="stretch",
        key="save_generator_template",
    ):
        if uploaded_file is None:
            st.error("请先上传一张对标封面。")
        elif not title.strip():
            st.error("请填写封面标题或风格名称。")
        elif not (api_key := get_api_key()):
            st.error("没有找到 OPENAI_API_KEY，请先完成 API Key 配置。")
        else:
            try:
                with st.spinner("AI正在拆解这张对标封面……"):
                    image_bytes = uploaded_file.getvalue()
                    analysis = analyze_cover(
                        image_bytes=image_bytes,
                        mime_type=uploaded_file.type or "image/jpeg",
                        title=title.strip(),
                        api_key=api_key,
                        hook_types=load_category_types("hook_types"),
                        layout_types=load_category_types("layout_types"),
                    )
                    image_path, digest = save_image(image_bytes, uploaded_file.name)
                    sample_id = insert_sample(
                        image_path=image_path,
                        image_sha256=digest,
                        title=title.strip(),
                        category=category,
                        analysis=analysis,
                    )
                st.session_state["selected_template_id"] = sample_id
                st.session_state["generation_result"] = None
                st.session_state["generation_input"] = None
                st.session_state["cover_previews"] = {}
                st.session_state["cover_preview_paths"] = {}
                st.toast("新对标封面已加入风格库", icon=":material/check_circle:")
                st.rerun()
            except ValidationError as exc:
                st.error(f"AI返回结果未通过校验：{exc}")
            except Exception as exc:
                st.error(friendly_openai_error(exc))


def load_samples() -> list[sqlite3.Row]:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT * FROM cover_samples ORDER BY id DESC"
        ).fetchall()


def update_sample_category(sample_id: int, category: str) -> None:
    if category not in COVER_CATEGORIES:
        raise ValueError("不支持的封面栏目。")
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cursor = conn.execute(
            "UPDATE cover_samples SET category = ? WHERE id = ?",
            (category, sample_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("素材不存在，请刷新后重试。")
        conn.commit()


def render_sample_detail(row: sqlite3.Row) -> None:
    image_path = APP_DIR / row["image_path"]
    image_col, detail_col = st.columns([1.05, 1.25], gap="large")
    with image_col:
        if image_path.exists():
            st.image(str(image_path), width="stretch")
        else:
            st.warning("原图片文件不存在")
    with detail_col:
        st.caption(f"素材 #{row['id']} · {row['model']} · {row['created_at'][:10]}")
        st.markdown(f"**封面栏目：** {row['category']}")
        layout_badge = " :orange-badge[新增分类待审核]" if row["layout_type_is_new"] else ""
        hook_badge = " :orange-badge[新增分类待审核]" if row["hook_type_is_new"] else ""
        st.markdown(f"**完整标题：** {row['original_title']}")
        st.markdown(f"**版式类型：** {row['layout_type']}{layout_badge}")
        st.markdown(f"**钩子结构：** {row['hook_type']}{hook_badge}")
        st.markdown(f"**配色风格：** {row['color_style']}")
        st.markdown(f"**字体风格：** {row['font_style']}")
        st.markdown(f"**情绪基调：** {row['emotional_tone']}")
        st.info(row["stop_reason"], icon=":material/lightbulb:")
        current_category = row["category"]
        category_index = (
            COVER_CATEGORIES.index(current_category)
            if current_category in COVER_CATEGORIES
            else 0
        )
        revised_category = st.selectbox(
            "调整封面栏目",
            COVER_CATEGORIES,
            index=category_index,
            key=f"sample_category_{row['id']}",
        )
        if st.button(
            "保存栏目",
            key=f"save_sample_category_{row['id']}",
            icon=":material/save:",
            width="stretch",
        ):
            update_sample_category(row["id"], revised_category)
            st.success("栏目已更新。关闭详情后即可按栏目筛选。")


def render_sample_grid(samples: list[sqlite3.Row]) -> None:
    valid_rows: dict[str, sqlite3.Row] = {}
    items: list[GridItem] = []
    for row in samples:
        image_path = APP_DIR / row["image_path"]
        if not image_path.exists():
            continue
        item_id = str(row["id"])
        valid_rows[item_id] = row
        items.append(
            GridItem(
                item_id=item_id,
                title=row["original_title"],
                badge=row["hook_type"],
                eyebrow=row["layout_type"],
                image=image_path,
            )
        )
    render_image_grid(
        items,
        grid_key="sample_library",
        detail_renderer=lambda item: render_sample_detail(valid_rows[item.item_id]),
    )
    missing_count = len(samples) - len(items)
    if missing_count:
        st.warning(f"有 {missing_count} 条素材的原图片文件不存在，暂未显示。")


def render_category_library() -> None:
    hook_types = load_category_types("hook_types")
    layout_types = load_category_types("layout_types")
    with st.expander("查看当前分类库", icon=":material/category:"):
        hook_tab, layout_tab = st.tabs(
            [f"钩子结构（{len(hook_types)}）", f"版式类型（{len(layout_types)}）"]
        )
        with hook_tab:
            for item in hook_types:
                badge = (
                    ":orange-badge[AI 新增·待审核]"
                    if item["review_status"] == "pending"
                    else ":green-badge[已确认]"
                )
                st.markdown(f"**{item['name']}** {badge}  \n{item['description']}")
        with layout_tab:
            if not layout_types:
                st.info("版式类型库暂时为空；首次分析会自动新增并标记待审核。")
            for item in layout_types:
                badge = (
                    ":orange-badge[AI 新增·待审核]"
                    if item["review_status"] == "pending"
                    else ":green-badge[已确认]"
                )
                st.markdown(f"**{item['name']}** {badge}  \n{item['description']}")


def render_material_library_page() -> None:
    st.header("素材库", icon=":material/photo_library:")
    st.caption("上传爆款封面截图和原标题，使用视觉模型生成结构化拆解并保存到本地。")
    render_category_library()
    with st.container(border=True):
        st.subheader("录入一条封面素材")
        uploaded_file = st.file_uploader(
            "上传封面图片",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=False,
        )
        title = st.text_input(
            "对应的原标题文字",
            placeholder="例如：30岁以后，我不再逼自己自律",
            max_chars=200,
        )
        category = st.selectbox("封面栏目", COVER_CATEGORIES)

        if uploaded_file is not None:
            try:
                preview = Image.open(uploaded_file)
                st.image(preview, caption="待分析图片", width=320)
                uploaded_file.seek(0)
            except Exception:
                st.error("图片无法读取，请重新选择 JPG、PNG 或 WEBP 文件。")

        analyze_clicked = st.button(
            "分析并保存",
            type="primary",
            width="stretch",
            icon=":material/auto_awesome:",
        )

        if analyze_clicked:
            if uploaded_file is None:
                st.error("请先上传一张封面图片。")
            elif not title.strip():
                st.error("请输入与封面对应的原标题文字。")
            elif not (api_key := get_api_key()):
                st.error(
                    "没有找到 OPENAI_API_KEY。请设置环境变量，"
                    "或在 .streamlit/secrets.toml 中配置。"
                )
            else:
                image_bytes = uploaded_file.getvalue()
                mime_type = uploaded_file.type or "image/jpeg"
                hook_types = load_category_types("hook_types")
                layout_types = load_category_types("layout_types")
                try:
                    with st.spinner("AI 正在分析版式、钩子和视觉风格……"):
                        analysis = analyze_cover(
                            image_bytes=image_bytes,
                            mime_type=mime_type,
                            title=title.strip(),
                            api_key=api_key,
                            hook_types=hook_types,
                            layout_types=layout_types,
                        )
                        image_path, digest = save_image(
                            image_bytes, uploaded_file.name
                        )
                        insert_sample(
                            image_path=image_path,
                            image_sha256=digest,
                            title=title.strip(),
                            category=category,
                            analysis=analysis,
                        )
                    st.success("分析完成，素材已经保存到本地素材库。")
                    st.rerun()
                except ValidationError as exc:
                    st.error(f"AI 返回结果未通过 JSON 校验：{exc}")
                except Exception as exc:
                    st.error(friendly_openai_error(exc))

    st.divider()
    samples = load_samples()
    st.subheader(f"已录入素材（{len(samples)}）")
    if not samples:
        st.info("素材库还是空的。上传第一张封面并完成分析后，会显示在这里。")
    else:
        st.caption("点击任意缩略图查看原图和完整拆解")
        render_sample_grid(samples)


def render_suggestion_cards(result: GenerationResult) -> None:
    st.subheader("本批生成建议")
    st.info(result.photo_observation, icon=":material/image_search:")
    generation_input = st.session_state.get("generation_input")
    if not generation_input:
        st.error("没有找到本次上传的照片，请重新生成建议。")
        return
    items: list[GridItem] = []
    for index, suggestion in enumerate(result.suggestions):
        if index not in st.session_state["cover_previews"]:
            try:
                st.session_state["cover_previews"][index] = compose_cover(
                    image_bytes=generation_input["image_bytes"],
                    title=suggestion.title,
                    layout_type=suggestion.layout_type,
                    color_advice=suggestion.color_advice,
                )
            except Exception as exc:
                st.warning(f"方案 {index + 1} 预览生成失败：{exc}")
                continue
        st.session_state.setdefault("cover_preview_paths", {})
        if index not in st.session_state["cover_preview_paths"]:
            st.session_state["cover_preview_paths"][index] = str(
                save_generated_image(
                    st.session_state["cover_previews"][index],
                    suggestion.title,
                    prefix=f"suggestion-{index + 1}",
                )
            )
        items.append(
            GridItem(
                item_id=str(index),
                title=suggestion.title,
                badge=suggestion.hook_type,
                eyebrow=f"方案 {index + 1} · {suggestion.layout_type}",
                image=st.session_state["cover_previews"][index],
            )
        )

    def render_suggestion_detail(item: GridItem) -> None:
        index = int(item.item_id)
        suggestion = result.suggestions[index]
        preview_bytes = st.session_state["cover_previews"][index]
        image_col, detail_col = st.columns([1, 1.1], gap="large")
        with image_col:
            render_long_press_image(preview_bytes, suggestion.title)
        with detail_col:
            st.markdown(f":violet-badge[{suggestion.hook_type}]")
            st.markdown(f"**版式：** {suggestion.layout_type}")
            st.markdown(f"**文字排版：** {suggestion.text_layout}")
            st.markdown(f"**配色建议：** {suggestion.color_advice}")
            st.info(suggestion.stop_reason, icon=":material/visibility:")
            if st.button(
                "选择这个方案",
                key=f"select_suggestion_{index}",
                type="primary",
                icon=":material/check_circle:",
                width="stretch",
            ):
                st.session_state["selected_suggestion"] = index
            if st.session_state.get("selected_suggestion") == index:
                st.success("当前已选择这个方案")
            safe_title = "".join(
                character for character in suggestion.title if character not in '\\/:*?"<>|'
            ) or f"方案{index + 1}"
            st.download_button(
                "下载初版 PNG",
                data=preview_bytes,
                file_name=f"{safe_title}.png",
                mime="image/png",
                key=f"download_preview_{index}",
                icon=":material/download:",
                width="stretch",
                on_click="ignore",
            )

    st.caption("点击任意方案缩略图，查看完整排版建议并下载")
    render_image_grid(
        items,
        grid_key="generation_results",
        detail_renderer=render_suggestion_detail,
    )


def render_template_gallery(samples: list[sqlite3.Row]) -> None:
    st.markdown("### 先选一个对标风格")
    st.caption("像逛灵感网站一样选模板。选中后再上传本次照片和文案。")
    categories = ["全部", *COVER_CATEGORIES, "未分类"]
    selected_category = st.segmented_control(
        "模板栏目",
        categories,
        default="全部",
        key="template_category_filter",
    )
    visible_samples = [
        row
        for row in samples
        if selected_category in (None, "全部") or row["category"] == selected_category
    ]
    if not visible_samples:
        st.info("这个栏目还没有模板，可以先去素材库上传。")
        return

    for row_start in range(0, len(visible_samples), 3):
        # Keep the template shelf three-across on mobile as requested.
        columns = st.columns(3, gap="small", wrap=False)
        for column, row in zip(columns, visible_samples[row_start : row_start + 3]):
            image_path = APP_DIR / row["image_path"]
            with column.container(
                border=True,
                height="stretch",
                key=f"template-card-{row['id']}",
            ):
                if image_path.exists():
                    st.image(create_cover_thumbnail(image_path), width="stretch")
                else:
                    st.warning("模板图片缺失")
                st.caption(f"{row['id']:02d} · {row['category']}")
                st.markdown(f"**{row['layout_type']}**")
                short_title = row["original_title"]
                if len(short_title) > 16:
                    short_title = f"{short_title[:16]}…"
                st.caption(short_title)
                if st.button(
                    "选用这个风格",
                    key=f"choose_template_{row['id']}",
                    disabled=not image_path.exists(),
                    width="stretch",
                ):
                    st.session_state["selected_template_id"] = row["id"]
                    st.session_state["generation_result"] = None
                    st.session_state["generation_input"] = None
                    st.session_state["cover_previews"] = {}
                    st.session_state["cover_preview_paths"] = {}
                    st.rerun()


def render_generation_page() -> None:
    prefill = st.session_state.get("generator_prefill")
    prefill_token = prefill.get("idea_id") if prefill else None
    if prefill and st.session_state.get("consumed_generator_prefill") != prefill_token:
        st.session_state["generation_topic"] = prefill["topic"]
        st.session_state["generation_hook_type"] = prefill["hook_type"]
        st.session_state["active_generation_idea_id"] = prefill["idea_id"]
        st.session_state["consumed_generator_prefill"] = prefill_token
        st.session_state["generation_result"] = None
        st.session_state["generation_input"] = None
        st.session_state["cover_previews"] = {}
        st.session_state["cover_preview_paths"] = {}

    header_col, add_col = st.columns([4, 1], vertical_alignment="center")
    with header_col:
        st.header("封面生成器", icon=":material/auto_awesome:")
        st.caption("从内容意图出发，先选对标风格，再生成三套可执行封面方向。")
    with add_col:
        if st.button(
            "新增对标封面",
            type="primary",
            icon=":material/add_photo_alternate:",
            width="stretch",
        ):
            render_add_template_dialog()
    st.session_state.setdefault("generation_result", None)
    st.session_state.setdefault("generation_batch", 0)
    st.session_state.setdefault("selected_suggestion", None)
    st.session_state.setdefault("generation_input", None)
    st.session_state.setdefault("cover_previews", {})
    st.session_state.setdefault("selected_template_id", None)

    active_idea_id = st.session_state.get("active_generation_idea_id")
    if active_idea_id:
        with st.container(border=True):
            link_col, unlink_col = st.columns([5, 1])
            with link_col:
                st.markdown("**已连接灵感库**  :violet-badge[内容链路已保留]")
                st.caption(f"灵感 #{active_idea_id} · 生成完成后可直接标记为已发布")
            with unlink_col:
                if st.button(
                    "取消关联",
                    key="unlink_generation_idea",
                    icon=":material/link_off:",
                    width="stretch",
                ):
                    st.session_state["active_generation_idea_id"] = None
                    st.session_state["generator_prefill"] = None
                    st.rerun()

    all_samples = load_samples()
    if not all_samples:
        st.warning("素材库还没有可参考的记录，请先在“素材库”页面至少录入一条。")
        return

    selected_template_id = st.session_state.get("selected_template_id")
    selected_template = next(
        (row for row in all_samples if row["id"] == selected_template_id), None
    )
    if selected_template is None:
        render_template_gallery(all_samples)
        return

    template_image_path = APP_DIR / selected_template["image_path"]
    recent_samples = load_recent_samples(limit=10, selected_id=selected_template["id"])
    with st.container(border=True, key="selected-template-summary"):
        thumb_col, info_col, action_col = st.columns([0.65, 2.4, 0.8])
        with thumb_col:
            st.image(create_cover_thumbnail(template_image_path), width="stretch")
        with info_col:
            st.caption(f"已选模板 · {selected_template['category']} · #{selected_template['id']}")
            st.markdown(f"### {selected_template['layout_type']}")
            st.markdown(f":violet-badge[{selected_template['hook_type']}]")
            st.caption("AI 将同时查看这张模板原图和它的历史拆解结果。")
        with action_col:
            if st.button(
                "更换模板",
                key="change_selected_template",
                icon=":material/swap_horiz:",
                width="stretch",
            ):
                st.session_state["selected_template_id"] = None
                st.rerun()

    with st.container(border=True):
        st.markdown("#### 本次创作输入")
        photo_col, brief_col = st.columns([1.05, 1.4], gap="large")
        with photo_col:
            uploaded_photo = st.file_uploader(
                "上传本次使用的新照片",
                type=["jpg", "jpeg", "png", "webp"],
                accept_multiple_files=False,
                key="generation_photo",
            )
            if uploaded_photo is not None:
                try:
                    preview = Image.open(uploaded_photo)
                    st.image(preview, caption="本次照片预览", width="stretch")
                    uploaded_photo.seek(0)
                except Exception:
                    st.error("图片无法读取，请重新选择 JPG、PNG 或 WEBP 文件。")
        with brief_col:
            topic = st.text_area(
                "本次文案主题",
                placeholder="例如：第40天差点放弃",
                max_chars=300,
                height=128,
                key="generation_topic",
            )
            poster_title = st.text_input("海报主标题", value=topic[:40], key="poster_title")
            poster_subtitle = st.text_input("副标题（可选）", key="poster_subtitle")
            poster_badge = st.text_input("角标（可选）", placeholder="例如：第40天", key="poster_badge")
            hook_names = [row["name"] for row in load_category_types("hook_types")]
            hook_options = ["自动匹配", *hook_names]
            current_hook = st.session_state.get("generation_hook_type", "自动匹配")
            if current_hook not in hook_options:
                hook_options.append(current_hook)
            hook_select_args = {
                "label": "优先钩子结构",
                "options": hook_options,
                "key": "generation_hook_type",
                "help": "从灵感库进入时会自动带入，你仍然可以在这里修改。",
            }
            if "generation_hook_type" not in st.session_state:
                hook_select_args["index"] = 0
            preferred_hook_type = st.selectbox(**hook_select_args)

        generate_clicked = st.button(
            "生成建议",
            type="primary",
            icon=":material/auto_awesome:",
            width="stretch",
            disabled=not recent_samples,
        )
        poster_clicked = st.button(
            "直接生成海报",
            type="primary",
            icon=":material/image:",
            width="stretch",
        )

    if poster_clicked:
        if uploaded_photo is None:
            st.error("请先上传本次使用的人物照片。")
        elif not poster_title.strip():
            st.error("请填写海报主标题。")
        elif not (api_key := get_api_key()):
            st.error("没有找到 OPENAI_API_KEY，请先配置 API Key。")
        else:
            try:
                with st.spinner("正在匹配人物、构图、调色和文字排版，约需几十秒……"):
                    try:
                        ai_base = generate_ai_base(
                            photo_bytes=uploaded_photo.getvalue(),
                            template_bytes=template_image_path.read_bytes(), api_key=api_key,
                            layout_type=selected_template["layout_type"],
                            color_style=selected_template["color_style"],
                            font_style=selected_template["font_style"],
                        )
                        st.session_state["direct_poster_note"] = "人物、背景和设计氛围已由 AI 匹配对标模板。"
                    except Exception as image_exc:
                        ai_base = uploaded_photo.getvalue()
                        st.session_state["direct_poster_note"] = (
                            "图像重绘暂不可用，已自动改用原照片完成排版。"
                            + friendly_openai_error(image_exc)
                        )
                    st.session_state["direct_poster"] = render_poster(
                        base_bytes=ai_base, title=poster_title.strip(),
                        subtitle=poster_subtitle.strip(), badge=poster_badge.strip(),
                        layout_type=selected_template["layout_type"],
                        color_style=selected_template["color_style"],
                        font_style=selected_template["font_style"],
                        template_bytes=template_image_path.read_bytes(),
                    )
                    st.session_state["direct_poster_path"] = str(
                        save_generated_image(
                            st.session_state["direct_poster"], poster_title, prefix="poster"
                        )
                    )
                st.rerun()
            except Exception as exc:
                st.error(friendly_openai_error(exc))

    if direct_poster := st.session_state.get("direct_poster"):
        with st.container(border=True):
            st.subheader("海报初稿", icon=":material/image:")
            st.caption(st.session_state.get("direct_poster_note", "已生成可下载海报。"))
            if saved_path := st.session_state.get("direct_poster_path"):
                st.success(f"已自动保存到电脑：{saved_path}", icon=":material/save:")
            render_long_press_image(direct_poster, poster_title)
            st.download_button(
                "下载高清海报", data=direct_poster, file_name="xiaohongshu-poster.png",
                mime="image/png", icon=":material/download:", type="primary", width="stretch",
                on_click="ignore",
            )

    regenerate_clicked = False
    if st.session_state.get("generation_result") is not None:
        with st.container(horizontal=True, horizontal_alignment="right"):
            regenerate_clicked = st.button(
                "换一批",
                icon=":material/refresh:",
                key="regenerate_suggestions",
            )

    if generate_clicked:
        if uploaded_photo is None:
            st.error("请先上传一张本次使用的新照片。")
        elif not topic.strip():
            st.error("请填写本次文案主题。")
        elif not (api_key := get_api_key()):
            st.error("没有找到 OPENAI_API_KEY，请先完成 API Key 配置。")
        else:
            st.session_state["generation_batch"] = 1
            st.session_state["selected_suggestion"] = None
            st.session_state["cover_previews"] = {}
            st.session_state["cover_preview_paths"] = {}
            st.session_state["generation_input"] = {
                "image_bytes": uploaded_photo.getvalue(),
                "mime_type": uploaded_photo.type or "image/jpeg",
                "topic": topic.strip(),
                "preferred_hook_type": (
                    None if preferred_hook_type == "自动匹配" else preferred_hook_type
                ),
                "idea_id": st.session_state.get("active_generation_idea_id"),
                "selected_template_id": selected_template["id"],
                "selected_template_title": selected_template["original_title"],
                "template_image_bytes": template_image_path.read_bytes(),
                "template_mime_type": (
                    "image/png"
                    if template_image_path.suffix.lower() == ".png"
                    else "image/webp"
                    if template_image_path.suffix.lower() == ".webp"
                    else "image/jpeg"
                ),
            }
            try:
                with st.spinner("AI 正在匹配历史结构并生成三套方案……"):
                    data = st.session_state["generation_input"]
                    st.session_state["generation_result"] = generate_cover_suggestions(
                        image_bytes=data["image_bytes"],
                        mime_type=data["mime_type"],
                        topic=data["topic"],
                        samples=recent_samples,
                        batch_number=1,
                        api_key=api_key,
                        preferred_hook_type=data["preferred_hook_type"],
                        selected_template_title=data["selected_template_title"],
                        template_image_bytes=data["template_image_bytes"],
                        template_mime_type=data["template_mime_type"],
                    )
                st.rerun()
            except ValidationError as exc:
                st.error(f"AI 返回的生成建议未通过 JSON 校验：{exc}")
            except Exception as exc:
                st.error(friendly_openai_error(exc))

    if regenerate_clicked:
        data = st.session_state.get("generation_input")
        api_key = get_api_key()
        if not data:
            st.error("没有找到上一批输入，请重新上传照片并填写主题。")
        elif not api_key:
            st.error("没有找到 OPENAI_API_KEY，请先完成 API Key 配置。")
        else:
            next_batch = st.session_state["generation_batch"] + 1
            try:
                with st.spinner("AI 正在换一个角度重新生成……"):
                    st.session_state["generation_result"] = generate_cover_suggestions(
                        image_bytes=data["image_bytes"],
                        mime_type=data["mime_type"],
                        topic=data["topic"],
                        samples=recent_samples,
                        batch_number=next_batch,
                        api_key=api_key,
                        preferred_hook_type=data.get("preferred_hook_type"),
                        selected_template_title=data.get("selected_template_title"),
                        template_image_bytes=data.get("template_image_bytes"),
                        template_mime_type=data.get("template_mime_type", "image/jpeg"),
                    )
                st.session_state["generation_batch"] = next_batch
                st.session_state["selected_suggestion"] = None
                st.session_state["cover_previews"] = {}
                st.session_state["cover_preview_paths"] = {}
                st.rerun()
            except ValidationError as exc:
                st.error(f"AI 返回的生成建议未通过 JSON 校验：{exc}")
            except Exception as exc:
                st.error(friendly_openai_error(exc))

    result = st.session_state.get("generation_result")
    if result is not None:
        st.caption(f"当前为第 {st.session_state['generation_batch']} 批方案")
        render_suggestion_cards(result)
        linked_idea_id = (st.session_state.get("generation_input") or {}).get("idea_id")
        if linked_idea_id:
            with st.container(border=True):
                publish_col, note_col = st.columns([1, 2.4])
                with publish_col:
                    if st.button(
                        "保存为已发布",
                        type="primary",
                        icon=":material/publish:",
                        width="stretch",
                    ):
                        try:
                            mark_idea_published(DB_PATH, linked_idea_id)
                            st.session_state["published_idea_id"] = linked_idea_id
                            st.success("已同步更新灵感库状态为“已发布”。")
                        except Exception as exc:
                            st.error(f"状态更新失败：{exc}")
                with note_col:
                    if st.session_state.get("published_idea_id") == linked_idea_id:
                        st.markdown(":green-badge[已发布] 灵感库状态已同步")
                    else:
                        st.caption("确认完成本次内容后，再同步更新灵感库状态。")


def main() -> None:
    st.set_page_config(
        page_title="小红书封面生成工具",
        page_icon="🟥",
        layout="wide",
    )
    ensure_storage()
    apply_app_styles()
    st.title("小红书封面生成工具")
    requested_page = st.session_state.pop("requested_page", None)
    if requested_page:
        st.session_state["main_navigation"] = requested_page
    with st.sidebar:
        st.markdown(
            '<div class="sidebar-brand"><small>CONTENT STUDIO</small>'
            '<strong>封面创作台</strong><span>从情报到发布</span></div>',
            unsafe_allow_html=True,
        )
        page = st.radio(
            "主栏目",
            ["情报雷达", "灵感库", "封面生成器", "素材库"],
            key="main_navigation",
            label_visibility="collapsed",
        )
        render_mobile_access()
        st.caption("本地数据 · 统一分类 · AI辅助")

    if page == "情报雷达":
        render_radar_page(DB_PATH, api_key_getter=get_api_key, model=MODEL)
    elif page == "灵感库":
        render_ideas_page(DB_PATH, api_key_getter=get_api_key, model=MODEL)
    elif page == "封面生成器":
        render_generation_page()
    else:
        render_material_library_page()


if __name__ == "__main__":
    main()
