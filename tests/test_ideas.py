from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from database import initialize_database  # noqa: E402
from ideas import (  # noqa: E402
    HookClassification,
    insert_idea,
    load_idea_counts,
    load_ideas,
    mark_idea_published,
    save_idea_classification,
    update_idea_schedule,
)


class IdeasDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "covers.db"
        initialize_database(self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_manual_idea_can_be_scheduled_and_filtered(self) -> None:
        idea_id = insert_idea(self.db_path, "第40天差点放弃")
        update_idea_schedule(
            self.db_path,
            idea_id,
            status="已排期",
            planned_publish_date=date(2026, 9, 8),
        )
        rows = load_ideas(self.db_path, "已排期")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["planned_publish_date"], "2026-09-08")
        self.assertEqual(load_idea_counts(self.db_path)["已排期"], 1)

    def test_existing_hook_classification_is_linked(self) -> None:
        idea_id = insert_idea(self.db_path, "我以为坚持靠意志")
        result = HookClassification(
            hook_type="自我诊断反常识",
            hook_type_status="已有",
            hook_type_description="我以为是A，其实是B",
            reason="内容天然包含认知纠正。",
        )
        hook_id = save_idea_classification(self.db_path, idea_id, result)
        row = load_ideas(self.db_path)[0]
        self.assertEqual(row["hook_type_id"], hook_id)
        self.assertEqual(row["hook_type_name"], "自我诊断反常识")

    def test_new_hook_classification_is_pending_review(self) -> None:
        idea_id = insert_idea(self.db_path, "一个全新的叙事结构")
        result = HookClassification(
            hook_type="微小胜利累积",
            hook_type_status="新增",
            hook_type_description="用微小进步累积成改变",
            reason="强调连续微小行动。",
        )
        save_idea_classification(self.db_path, idea_id, result)
        row = load_ideas(self.db_path)[0]
        self.assertEqual(row["hook_type_name"], "微小胜利累积")
        self.assertEqual(row["hook_review_status"], "pending")

    def test_idea_can_be_marked_published(self) -> None:
        idea_id = insert_idea(self.db_path, "今天完成发布")
        mark_idea_published(self.db_path, idea_id)
        rows = load_ideas(self.db_path, "已发布")
        self.assertEqual([row["id"] for row in rows], [idea_id])


if __name__ == "__main__":
    unittest.main()
