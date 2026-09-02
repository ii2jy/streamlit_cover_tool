from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import streamlit as st
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai_client import create_openai_client, friendly_openai_error
from database import SIGNAL_RELEVANCE_LEVELS, SIGNAL_SOURCE_TYPES


class RadarAnalysis(BaseModel):
    """情报雷达 AI 输出与数据库之间的固定数据契约。"""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, description="一句话核心总结")
    opportunities: list[str] = Field(
        min_length=1, max_length=3, description="普通人可承接的1至3条具体机会"
    )
    relevance: Literal["高相关", "中相关", "低相关"]
    tags: list[str] = Field(
        min_length=1, max_length=5, description="用于后续检索的简短关联标签"
    )


RADAR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "opportunities": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {"type": "string"},
        },
        "relevance": {
            "type": "string",
            "enum": list(SIGNAL_RELEVANCE_LEVELS),
        },
        "tags": {
            "type": "array",
            "minItems": 1,
            "maxItems": 5,
            "items": {"type": "string"},
        },
    },
    "required": ["summary", "opportunities", "relevance", "tags"],
}


RADAR_PROMPT_TEMPLATE = """
你是一个面向普通内容创作者的情报分析助手。用户正在经营“自律训练营”，并持续制作小红书自我提升类内容。

请分析下面这段信息：

来源类型：{source_type}
原始内容：
{raw_content}

要求：
1. summary：只用一句中文总结这段信息的核心，不夸大、不编造原文没有的数据。
2. opportunities：给出 1—3 条具体、低门槛、能执行的承接建议。若与自律训练营、小红书内容或自我提升方向有关，优先从这些角度分析；完全无关时，从普通人或内容创作者视角分析。
3. relevance：判断它相对于“自律训练营/自我提升赛道”的相关度，只能是“高相关”“中相关”“低相关”。
4. tags：返回 1—5 个简短标签，标签应便于以后筛选，例如“自律训练营”“选题机会”“用户痛点”“产品机会”，不要写成长句。

严格按照给定 JSON Schema 返回，不要添加 Markdown、代码围栏、解释或额外字段。
""".strip()


def analyze_signal(
    *, source_type: str, raw_content: str, api_key: str, model: str
) -> RadarAnalysis:
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
                        "text": RADAR_PROMPT_TEMPLATE.format(
                            source_type=source_type,
                            raw_content=raw_content,
                        ),
                    }
                ],
            }
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "radar_analysis",
                "strict": True,
                "schema": RADAR_SCHEMA,
            }
        },
    )
    if not response.output_text:
        raise ValueError("OpenAI API 没有返回可解析的情报分析。")
    return RadarAnalysis.model_validate_json(response.output_text)


def insert_signal(
    db_path: Path,
    *,
    source_type: str,
    raw_content: str,
    analysis: RadarAnalysis,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    payload = analysis.model_dump()
    with closing(sqlite3.connect(db_path)) as conn:
        cursor = conn.execute(
            """
            INSERT INTO signals (
                source_type, raw_content, ai_summary, opportunities_json,
                relevance, tags_json, analysis_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_type,
                raw_content,
                analysis.summary,
                json.dumps(analysis.opportunities, ensure_ascii=False),
                analysis.relevance,
                json.dumps(analysis.tags, ensure_ascii=False),
                json.dumps(payload, ensure_ascii=False),
                now,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def load_signals(
    db_path: Path, *, source_type: str | None = None, relevance: str | None = None
) -> list[sqlite3.Row]:
    conditions: list[str] = []
    parameters: list[str] = []
    if source_type:
        conditions.append("source_type = ?")
        parameters.append(source_type)
    if relevance:
        conditions.append("relevance = ?")
        parameters.append(relevance)
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            f"SELECT * FROM signals {where_clause} ORDER BY id DESC",
            parameters,
        ).fetchall()


def convert_signal_to_idea(db_path: Path, signal_id: int) -> int:
    """同一条信号允许转化出多个不同灵感，因此不设置 signal_id 唯一约束。"""
    now = datetime.now(timezone.utc).isoformat()
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        signal = conn.execute(
            "SELECT ai_summary FROM signals WHERE id = ?", (signal_id,)
        ).fetchone()
        if signal is None:
            raise ValueError("这条情报已不存在，请刷新页面后重试。")
        cursor = conn.execute(
            """
            INSERT INTO ideas (
                content, source, signal_id, status, created_at, updated_at
            ) VALUES (?, '从signals转化', ?, '未排期', ?, ?)
            """,
            (signal[0], signal_id, now, now),
        )
        conn.commit()
        return int(cursor.lastrowid)


def _decode_string_list(raw_value: str) -> list[str]:
    try:
        value = json.loads(raw_value)
    except (json.JSONDecodeError, TypeError):
        return []
    return [str(item) for item in value] if isinstance(value, list) else []


def _render_signal_card(db_path: Path, row: sqlite3.Row) -> None:
    badge_color = {"高相关": "green", "中相关": "orange", "低相关": "gray"}[
        row["relevance"]
    ]
    opportunities = _decode_string_list(row["opportunities_json"])
    tags = _decode_string_list(row["tags_json"])

    with st.container(border=True):
        st.markdown(
            f"**{row['ai_summary']}**  "
            f":{badge_color}-badge[{row['relevance']}] "
            f":blue-badge[{row['source_type']}]"
        )
        if tags:
            st.caption(" · ".join(f"#{tag}" for tag in tags))
        st.markdown("**普通人可以承接：**")
        for opportunity in opportunities:
            st.markdown(f"- {opportunity}")
        with st.expander("查看原始内容"):
            st.write(row["raw_content"])
        action_col, time_col = st.columns([1, 2])
        with action_col:
            if st.button(
                "转为灵感",
                key=f"signal_to_idea_{row['id']}",
                icon=":material/lightbulb:",
                width="stretch",
            ):
                idea_id = convert_signal_to_idea(db_path, row["id"])
                st.session_state["new_idea_id"] = idea_id
                st.session_state["requested_page"] = "灵感库"
                st.rerun()
        with time_col:
            st.caption(f"录入时间：{row['created_at'][:16].replace('T', ' ')}")


def render_radar_page(db_path: Path, *, api_key_getter: Any, model: str) -> None:
    st.header("情报雷达", icon=":material/radar:")
    st.caption("粘贴一条外部信息，让 AI 判断它和自律训练营、内容创作之间的机会。")

    with st.container(border=True):
        source_type = st.selectbox("来源类型", SIGNAL_SOURCE_TYPES)
        raw_content = st.text_area(
            "原始内容",
            placeholder="粘贴短视频文案、社会热点、电商产品详情或市场信息……",
            height=180,
            max_chars=12000,
        )
        analyze_clicked = st.button(
            "分析并保存",
            type="primary",
            icon=":material/auto_awesome:",
            width="stretch",
        )

    if analyze_clicked:
        if not raw_content.strip():
            st.error("请先粘贴或输入需要分析的内容。")
        elif not (api_key := api_key_getter()):
            st.error("没有找到 OPENAI_API_KEY，请先完成 API Key 配置。")
        else:
            try:
                with st.spinner("AI 正在提炼信号与可承接机会……"):
                    analysis = analyze_signal(
                        source_type=source_type,
                        raw_content=raw_content.strip(),
                        api_key=api_key,
                        model=model,
                    )
                    insert_signal(
                        db_path,
                        source_type=source_type,
                        raw_content=raw_content.strip(),
                        analysis=analysis,
                    )
                st.success("情报已分析并保存。")
            except ValidationError as exc:
                st.error(f"AI 返回结果未通过 JSON 校验：{exc}")
            except Exception as exc:
                st.error(friendly_openai_error(exc))

    st.subheader("信号列表")
    filter_col_1, filter_col_2 = st.columns(2)
    with filter_col_1:
        selected_source = st.selectbox(
            "筛选来源", ("全部来源", *SIGNAL_SOURCE_TYPES), key="radar_source_filter"
        )
    with filter_col_2:
        selected_relevance = st.selectbox(
            "筛选相关度",
            ("全部相关度", *SIGNAL_RELEVANCE_LEVELS),
            key="radar_relevance_filter",
        )
    rows = load_signals(
        db_path,
        source_type=None if selected_source == "全部来源" else selected_source,
        relevance=None if selected_relevance == "全部相关度" else selected_relevance,
    )
    if not rows:
        st.info("当前筛选条件下还没有情报信号。")
    for row in rows:
        _render_signal_card(db_path, row)
