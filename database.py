from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


INITIAL_HOOK_TYPES = [
    ("自我诊断反常识", "“我以为是A，其实是B”的结构"),
    ("情绪化独白", "第一人称、拟人化、带请求语气"),
    ("时间反差", "极端时间对比制造效率错觉"),
    ("心理自曝", "说出一个普遍但难以启齿的心理状态"),
    ("造词+反差行为", "新词加具体又矛盾的行为细节"),
]

SIGNAL_SOURCE_TYPES = ("短视频热点", "社会话题", "电商产品", "市场变量")
SIGNAL_RELEVANCE_LEVELS = ("高相关", "中相关", "低相关")
IDEA_SOURCES = ("手动输入", "从signals转化")
IDEA_STATUSES = ("未排期", "已排期", "已发布")
COVER_CATEGORIES = ("口播封面", "故事封面", "无人物封面")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _column_names(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")}


def _add_column_if_missing(
    conn: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    if column_name not in _column_names(conn, table_name):
        conn.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )


def initialize_database(db_path: Path) -> None:
    """创建或无损升级数据库；可以在每次启动时安全重复调用。"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                description TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hook_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'seed',
                review_status TEXT NOT NULL DEFAULT 'approved',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS layout_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'seed',
                review_status TEXT NOT NULL DEFAULT 'approved',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cover_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_path TEXT NOT NULL,
                image_sha256 TEXT NOT NULL,
                original_title TEXT NOT NULL,
                layout_type TEXT NOT NULL,
                hook_type TEXT NOT NULL,
                color_style TEXT NOT NULL,
                font_style TEXT NOT NULL,
                emotional_tone TEXT NOT NULL,
                stop_reason TEXT NOT NULL,
                analysis_json TEXT NOT NULL,
                model TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        # 旧库仍保存分类名称；新增外键便于后续四个模块共享同一套分类标准。
        _add_column_if_missing(
            conn, "cover_samples", "layout_type_is_new", "INTEGER NOT NULL DEFAULT 0"
        )
        _add_column_if_missing(
            conn, "cover_samples", "hook_type_is_new", "INTEGER NOT NULL DEFAULT 0"
        )
        _add_column_if_missing(
            conn,
            "cover_samples",
            "layout_type_id",
            "INTEGER REFERENCES layout_types(id) ON UPDATE CASCADE ON DELETE SET NULL",
        )
        _add_column_if_missing(
            conn,
            "cover_samples",
            "hook_type_id",
            "INTEGER REFERENCES hook_types(id) ON UPDATE CASCADE ON DELETE SET NULL",
        )
        _add_column_if_missing(
            conn, "cover_samples", "category", "TEXT NOT NULL DEFAULT '未分类'"
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL
                    CHECK (source_type IN ('短视频热点', '社会话题', '电商产品', '市场变量')),
                raw_content TEXT NOT NULL,
                ai_summary TEXT NOT NULL,
                opportunities_json TEXT NOT NULL DEFAULT '[]',
                relevance TEXT NOT NULL
                    CHECK (relevance IN ('高相关', '中相关', '低相关')),
                tags_json TEXT NOT NULL DEFAULT '[]',
                analysis_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ideas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT '手动输入'
                    CHECK (source IN ('手动输入', '从signals转化')),
                signal_id INTEGER,
                hook_type_id INTEGER,
                status TEXT NOT NULL DEFAULT '未排期'
                    CHECK (status IN ('未排期', '已排期', '已发布')),
                planned_publish_date TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (signal_id) REFERENCES signals(id) ON DELETE SET NULL,
                FOREIGN KEY (hook_type_id) REFERENCES hook_types(id)
                    ON UPDATE CASCADE ON DELETE SET NULL
            )
            """
        )

        now = _utc_now()
        conn.executemany(
            """
            INSERT OR IGNORE INTO hook_types
                (name, description, source, review_status, created_at)
            VALUES (?, ?, 'seed', 'approved', ?)
            """,
            [(name, description, now) for name, description in INITIAL_HOOK_TYPES],
        )

        # 把旧记录中的分类名称映射到新外键；原文本字段保留，避免破坏现有功能。
        conn.execute(
            """
            UPDATE cover_samples
            SET hook_type_id = (
                SELECT id FROM hook_types WHERE hook_types.name = cover_samples.hook_type
            )
            WHERE hook_type_id IS NULL
            """
        )
        conn.execute(
            """
            UPDATE cover_samples
            SET layout_type_id = (
                SELECT id FROM layout_types WHERE layout_types.name = cover_samples.layout_type
            )
            WHERE layout_type_id IS NULL
            """
        )

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cover_samples_created_at "
            "ON cover_samples(created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cover_samples_hook_type_id "
            "ON cover_samples(hook_type_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cover_samples_layout_type_id "
            "ON cover_samples(layout_type_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_signals_source_relevance "
            "ON signals(source_type, relevance)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_signals_created_at "
            "ON signals(created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ideas_status_publish_date "
            "ON ideas(status, planned_publish_date)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ideas_signal_id ON ideas(signal_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ideas_hook_type_id ON ideas(hook_type_id)"
        )

        conn.executemany(
            """
            INSERT OR IGNORE INTO schema_migrations
                (version, description, applied_at)
            VALUES (?, ?, ?)
            """,
            [
                (1, "素材库与分类标准基础结构", now),
                (2, "新增情报雷达、灵感库与共享分类外键", now),
            ],
        )
        conn.commit()
