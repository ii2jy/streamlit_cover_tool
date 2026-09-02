from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import streamlit as st
from PIL import Image, ImageOps


@dataclass(frozen=True)
class GridItem:
    item_id: str
    title: str
    badge: str
    image: bytes | Path
    eyebrow: str = ""


def create_cover_thumbnail(image: bytes | Path, size: tuple[int, int] = (600, 800)) -> bytes:
    """生成统一3:4中心裁剪缩略图；原图不修改，网格也不会传输超大文件。"""
    if isinstance(image, Path):
        with image.open("rb") as file:
            source = file.read()
    else:
        source = image
    with Image.open(io.BytesIO(source)) as opened:
        normalized = ImageOps.exif_transpose(opened).convert("RGB")
        fitted = ImageOps.fit(normalized, size, method=Image.Resampling.LANCZOS)
        output = io.BytesIO()
        fitted.save(output, format="JPEG", quality=84, optimize=True)
        return output.getvalue()


def render_image_grid(
    items: list[GridItem],
    *,
    grid_key: str,
    detail_renderer: Callable[[GridItem], None],
) -> None:
    """渲染可点击封面网格，并在同一页面弹窗展示选中项详情。"""
    if not items:
        return

    selection_key = f"_grid_selection_{grid_key}"
    for row_start in range(0, len(items), 3):
        # Cover browsing deliberately remains three-across on phones. This is a
        # compact visual index; full text stays in the detail dialog.
        columns = st.columns(3, gap="small", wrap=False)
        for column, item in zip(columns, items[row_start : row_start + 3]):
            title = item.title.strip() or "未命名"
            short_title = title if len(title) <= 10 else f"{title[:10]}…"
            with column.container(border=True, height="stretch"):
                st.image(create_cover_thumbnail(item.image), width="stretch")
                if item.eyebrow:
                    st.caption(item.eyebrow)
                st.markdown(f"**{short_title}**")
                st.markdown(f":violet-badge[{item.badge or '未分类'}]")
                if st.button(
                    "查看封面详情",
                    key=f"open_{grid_key}_{item.item_id}",
                    icon=":material/open_in_full:",
                    width="stretch",
                ):
                    st.session_state[selection_key] = item.item_id
                    st.rerun()

    selected_item_id = st.session_state.get(selection_key)
    if not selected_item_id:
        return
    selected_item = next(
        (item for item in items if item.item_id == selected_item_id), None
    )
    if selected_item is None:
        return

    @st.dialog(selected_item.title, width="large")
    def show_detail() -> None:
        detail_renderer(selected_item)
        if st.button(
            "关闭详情",
            key=f"close_{grid_key}_{selected_item.item_id}",
            icon=":material/close:",
            width="stretch",
        ):
            st.session_state[selection_key] = None
            st.rerun()

    show_detail()
