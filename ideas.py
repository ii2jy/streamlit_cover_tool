from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

import streamlit as st
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai_client import create_openai_client, friendly_openai_error
from database import IDEA_STATUSES


class HookClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hook_type: str = Field(min_length=1)
    hook_type_status: Literal["已有", "新增"]
    hook_type_description: str = Field(min_length=1)
    reason: str = Field(min_length=1)


HOOK_CLASSIFICATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "hook_type": {"type": "string"},
        "hook_type_status": {"type": "string", "enum": ["已有", "新增"]},
        "hook_type_description": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": [
        "hook_type",
        "hook_type_status",
        "hook_type_description",
        "reason",
    ],
}


HOOK_CLASSIFICATION_PROMPT = """
你是小红书标题结构分类助手。请判断下面这条内容灵感最适合使用哪一种主要钩子结构。

灵感内容：{content}

当前钩子结构类型库：
{hook_types}

要求：
1. 必须优先从类型库选择最匹配的一项，并原样返回其名称，hook_type_status 标为“已有”。
2. 只有所有现有类型都明显不适用时，才能建立一个简短、稳定、可复用的新分类，并标为“新增”。不要因为措辞略有差异就新增近义分类。
3. hook_type_description 用一句话定义结构；已有分类沿用列表中的定义。
4. reason 用一句话说明这条灵感为什么适合该结构，不要直接替用户编造完整标题。

严格按照给定 JSON Schema 返回，不要添加 Markdown、代码围栏或额外字段。
""".strip()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_hook_types(db_path: Path) -> list[sqlite3.Row]:
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT id, name, description, review_status FROM hook_types ORDER BY id"
        ).fetchall()


def _format_hook_types(rows: list[sqlite3.Row]) -> str:
    return "\n".join(
        f"- {row['name']}：{row['description']}" for row in rows
    ) or "（当前为空，可以新增分类）"


def classify_idea(
    *, content: str, hook_types: list[sqlite3.Row], api_key: str, model: str
) -> HookClassification:
    client = create_openai_client(api_key)
    response = client.responses.create(
        model=model,
        store=False,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": HOOK_CLASSIFICATION_PROMPT.format(
                            content=content,
                            hook_types=_format_hook_types(hook_types),
                        ),
                    }
                ],
            }
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "idea_hook_classification",
                "strict": True,
                "schema": HOOK_CLASSIFICATION_SCHEMA,
            }
        },
    )
    if not response.output_text:
        raise ValueError("OpenAI API 没有返回可解析的分类结果。")
    result = HookClassification.model_validate_json(response.output_text)
    known_types = {
        row["name"].strip().casefold(): (row["name"], row["description"])
        for row in hook_types
    }
    matched = known_types.get(result.hook_type.strip().casefold())
    if matched:
        return result.model_copy(
            update={
                "hook_type": matched[0],
                "hook_type_description": matched[1],
                "hook_type_status": "已有",
            }
        )
    return result.model_copy(update={"hook_type_status": "新增"})


def insert_idea(db_path: Path, content: str) -> int:
    now = _utc_now()
    with closing(sqlite3.connect(db_path)) as conn:
        cursor = conn.execute(
            """
            INSERT INTO ideas (content, source, status, created_at, updated_at)
            VALUES (?, '手动输入', '未排期', ?, ?)
            """,
            (content.strip(), now, now),
        )
        conn.commit()
        return int(cursor.lastrowid)


def save_idea_classification(
    db_path: Path, idea_id: int, classification: HookClassification
) -> int:
    now = _utc_now()
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        if classification.hook_type_status == "新增":
            conn.execute(
                """
                INSERT OR IGNORE INTO hook_types
                    (name, description, source, review_status, created_at)
                VALUES (?, ?, 'ai', 'pending', ?)
                """,
                (
                    classification.hook_type,
                    classification.hook_type_description,
                    now,
                ),
            )
        row = conn.execute(
            "SELECT id FROM hook_types WHERE name = ?", (classification.hook_type,)
        ).fetchone()
        if row is None:
            raise ValueError("钩子分类保存失败，请重新分类。")
        hook_type_id = int(row[0])
        cursor = conn.execute(
            """
            UPDATE ideas SET hook_type_id = ?, updated_at = ? WHERE id = ?
            """,
            (hook_type_id, now, idea_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("这条灵感已不存在，请刷新后重试。")
        conn.commit()
        return hook_type_id


def update_idea_schedule(
    db_path: Path,
    idea_id: int,
    *,
    status: str,
    planned_publish_date: date | None,
) -> None:
    if status not in IDEA_STATUSES:
        raise ValueError("不支持的灵感状态。")
    with closing(sqlite3.connect(db_path)) as conn:
        cursor = conn.execute(
            """
            UPDATE ideas
            SET status = ?, planned_publish_date = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                status,
                planned_publish_date.isoformat() if planned_publish_date else None,
                _utc_now(),
                idea_id,
            ),
        )
        if cursor.rowcount != 1:
            raise ValueError("这条灵感已不存在，请刷新后重试。")
        conn.commit()


def mark_idea_published(db_path: Path, idea_id: int) -> None:
    with closing(sqlite3.connect(db_path)) as conn:
        cursor = conn.execute(
            "UPDATE ideas SET status = '已发布', updated_at = ? WHERE id = ?",
            (_utc_now(), idea_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("关联灵感已不存在，无法更新发布状态。")
        conn.commit()


def load_ideas(db_path: Path, status: str | None = None) -> list[sqlite3.Row]:
    where_clause = "WHERE ideas.status = ?" if status else ""
    parameters = (status,) if status else ()
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            f"""
            SELECT ideas.*, hook_types.name AS hook_type_name,
                   hook_types.review_status AS hook_review_status
            FROM ideas
            LEFT JOIN hook_types ON hook_types.id = ideas.hook_type_id
            {where_clause}
            ORDER BY
                CASE WHEN planned_publish_date IS NULL THEN 1 ELSE 0 END,
                planned_publish_date ASC,
                ideas.id DESC
            """,
            parameters,
        ).fetchall()


def load_idea_counts(db_path: Path) -> dict[str, int]:
    counts = {status: 0 for status in IDEA_STATUSES}
    with closing(sqlite3.connect(db_path)) as conn:
        for status, count in conn.execute(
            "SELECT status, COUNT(*) FROM ideas GROUP BY status"
        ):
            counts[status] = int(count)
    return counts


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _render_idea_card(
    db_path: Path,
    row: sqlite3.Row,
    *,
    api_key_getter: Any,
    model: str,
) -> None:
    source_label = "雷达转化" if row["source"] == "从signals转化" else "随手记录"
    with st.container(border=True):
        heading_col, source_col = st.columns([5, 1])
        with heading_col:
            st.markdown(f"### {row['content']}")
        with source_col:
            st.caption(source_label)

        if row["hook_type_name"]:
            review_badge = (
                " :orange-badge[新增待审核]"
                if row["hook_review_status"] == "pending"
                else ""
            )
            st.markdown(
                f":violet-badge[{row['hook_type_name']}]{review_badge}"
            )
        else:
            st.caption("尚未判断钩子结构")

        status_col, plan_col, save_col = st.columns([1.2, 1.4, 0.8])
        with status_col:
            status = st.selectbox(
                "状态",
                IDEA_STATUSES,
                index=IDEA_STATUSES.index(row["status"]),
                key=f"idea_status_{row['id']}",
            )
        with plan_col:
            schedule_enabled = st.checkbox(
                "设置发布日期",
                value=bool(row["planned_publish_date"]),
                key=f"idea_schedule_enabled_{row['id']}",
            )
            selected_date = st.date_input(
                "计划发布日期",
                value=_parse_date(row["planned_publish_date"]) or date.today(),
                key=f"idea_date_{row['id']}",
                disabled=not schedule_enabled,
            )
        with save_col:
            st.write("")
            st.write("")
            if st.button(
                "保存排期",
                key=f"save_idea_{row['id']}",
                icon=":material/event_available:",
                width="stretch",
            ):
                update_idea_schedule(
                    db_path,
                    row["id"],
                    status=status,
                    planned_publish_date=selected_date if schedule_enabled else None,
                )
                st.success("排期已保存")
                st.rerun()

        classify_col, generate_col = st.columns(2)
        with classify_col:
            if st.button(
                "重新 AI 分类" if row["hook_type_name"] else "AI 分类",
                key=f"classify_idea_{row['id']}",
                icon=":material/psychology:",
                width="stretch",
            ):
                api_key = api_key_getter()
                if not api_key:
                    st.error("没有找到 OPENAI_API_KEY，请先完成 API Key 配置。")
                else:
                    try:
                        with st.spinner("正在匹配钩子结构……"):
                            result = classify_idea(
                                content=row["content"],
                                hook_types=load_hook_types(db_path),
                                api_key=api_key,
                                model=model,
                            )
                            save_idea_classification(db_path, row["id"], result)
                        if result.hook_type_status == "新增":
                            st.warning(f"已建立待审核分类：{result.hook_type}")
                        else:
                            st.success(f"已归类为：{result.hook_type}")
                        st.rerun()
                    except ValidationError as exc:
                        st.error(f"AI 分类结果未通过校验：{exc}")
                    except Exception as exc:
                        st.error(friendly_openai_error(exc))
        with generate_col:
            if st.button(
                "去生成封面",
                key=f"generate_from_idea_{row['id']}",
                icon=":material/arrow_forward:",
                type="primary" if row["hook_type_name"] else "secondary",
                disabled=not bool(row["hook_type_name"]),
                width="stretch",
            ):
                st.session_state["generator_prefill"] = {
                    "idea_id": row["id"],
                    "topic": row["content"],
                    "hook_type": row["hook_type_name"],
                }
                st.session_state["requested_page"] = "封面生成器"
                st.rerun()


def render_ideas_page(db_path: Path, *, api_key_getter: Any, model: str) -> None:
    st.header("灵感库", icon=":material/lightbulb:")
    st.caption("把零散念头收进来，完成钩子分类与发布排期，再送去生成封面。")

    if st.session_state.pop("new_idea_id", None):
        st.success("情报已经转入灵感库，状态为“未排期”。")

    with st.container(border=True):
        st.markdown("#### 快速收集")
        with st.form("quick_idea_form", clear_on_submit=True, border=False):
            input_col, button_col = st.columns([5, 1])
            with input_col:
                quick_idea = st.text_input(
                    "写下一句灵感",
                    placeholder="例如：第40天差点放弃",
                    label_visibility="collapsed",
                )
            with button_col:
                add_clicked = st.form_submit_button(
                    "添加灵感",
                    type="primary",
                    icon=":material/add:",
                    width="stretch",
                )
        if add_clicked:
            if not quick_idea.strip():
                st.error("请先写下一句灵感。")
            else:
                insert_idea(db_path, quick_idea)
                st.rerun()

    counts = load_idea_counts(db_path)
    metric_cols = st.columns(3)
    for column, status in zip(metric_cols, IDEA_STATUSES):
        column.metric(status, counts[status])

    filter_value = st.segmented_control(
        "查看状态",
        ["全部", *IDEA_STATUSES],
        default="全部",
        key="idea_status_filter",
    )
    selected_status = None if filter_value in (None, "全部") else filter_value
    rows = load_ideas(db_path, selected_status)
    st.caption(f"共 {len(rows)} 条 · 已排期内容优先按发布日期排列")
    if not rows:
        st.info("当前筛选条件下还没有灵感。")
    for row in rows:
        _render_idea_card(
            db_path,
            row,
            api_key_getter=api_key_getter,
            model=model,
        )
