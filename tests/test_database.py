from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import app  # noqa: E402


class TaxonomyDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = app.DB_PATH
        self.original_image_dir = app.IMAGE_DIR
        temp_root = Path(self.temp_dir.name)
        app.DB_PATH = temp_root / "covers.db"
        app.IMAGE_DIR = temp_root / "images"
        app.ensure_storage()

    def tearDown(self) -> None:
        app.DB_PATH = self.original_db_path
        app.IMAGE_DIR = self.original_image_dir
        self.temp_dir.cleanup()

    def test_initial_hook_types_are_seeded(self) -> None:
        with closing(sqlite3.connect(app.DB_PATH)) as conn:
            rows = conn.execute(
                "SELECT name, review_status FROM hook_types ORDER BY id"
            ).fetchall()
        self.assertEqual(
            [row[0] for row in rows],
            [name for name, _ in app.INITIAL_HOOK_TYPES],
        )
        self.assertTrue(all(row[1] == "approved" for row in rows))

    def test_taxonomy_tables_and_sample_flags_exist(self) -> None:
        with closing(sqlite3.connect(app.DB_PATH)) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            sample_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(cover_samples)")
            }
        self.assertIn("hook_types", tables)
        self.assertIn("layout_types", tables)
        self.assertIn("layout_type_is_new", sample_columns)
        self.assertIn("hook_type_is_new", sample_columns)
        self.assertIn("layout_type_id", sample_columns)
        self.assertIn("hook_type_id", sample_columns)
        self.assertIn("category", sample_columns)

    def test_radar_and_idea_tables_are_created(self) -> None:
        with closing(sqlite3.connect(app.DB_PATH)) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            signal_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(signals)")
            }
            idea_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(ideas)")
            }
        self.assertTrue({"signals", "ideas", "schema_migrations"} <= tables)
        self.assertTrue(
            {
                "source_type",
                "raw_content",
                "ai_summary",
                "opportunities_json",
                "relevance",
                "tags_json",
                "analysis_json",
                "created_at",
            }
            <= signal_columns
        )
        self.assertTrue(
            {
                "content",
                "source",
                "signal_id",
                "hook_type_id",
                "status",
                "planned_publish_date",
                "created_at",
                "updated_at",
            }
            <= idea_columns
        )

    def test_idea_defaults_and_foreign_keys(self) -> None:
        with closing(sqlite3.connect(app.DB_PATH)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            now = "2026-09-02T00:00:00+00:00"
            signal_id = conn.execute(
                """
                INSERT INTO signals
                    (source_type, raw_content, ai_summary, relevance, created_at)
                VALUES ('短视频热点', '原始内容', '一句话总结', '高相关', ?)
                """,
                (now,),
            ).lastrowid
            hook_type_id = conn.execute(
                "SELECT id FROM hook_types WHERE name = '心理自曝'"
            ).fetchone()[0]
            idea_id = conn.execute(
                """
                INSERT INTO ideas
                    (content, source, signal_id, hook_type_id, created_at, updated_at)
                VALUES ('第40天差点放弃', '从signals转化', ?, ?, ?, ?)
                """,
                (signal_id, hook_type_id, now, now),
            ).lastrowid
            row = conn.execute(
                "SELECT source, status, signal_id, hook_type_id FROM ideas WHERE id = ?",
                (idea_id,),
            ).fetchone()
        self.assertEqual(row, ("从signals转化", "未排期", signal_id, hook_type_id))

    def test_invalid_enumeration_is_rejected(self) -> None:
        with closing(sqlite3.connect(app.DB_PATH)) as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO signals
                        (source_type, raw_content, ai_summary, relevance, created_at)
                    VALUES ('未知来源', '原文', '总结', '高相关', 'now')
                    """
                )


if __name__ == "__main__":
    unittest.main()
