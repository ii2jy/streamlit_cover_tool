from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from database import initialize_database  # noqa: E402
from radar import RadarAnalysis, convert_signal_to_idea, insert_signal, load_signals  # noqa: E402


class RadarDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "covers.db"
        initialize_database(self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_signal_can_be_saved_filtered_and_converted_to_idea(self) -> None:
        analysis = RadarAnalysis(
            summary="连续打卡内容正在受到关注",
            opportunities=["制作一次第40天复盘", "设计低门槛打卡挑战"],
            relevance="高相关",
            tags=["自律训练营", "选题机会"],
        )
        signal_id = insert_signal(
            self.db_path,
            source_type="短视频热点",
            raw_content="某条连续打卡短视频获得大量讨论",
            analysis=analysis,
        )
        rows = load_signals(
            self.db_path, source_type="短视频热点", relevance="高相关"
        )
        self.assertEqual([row["id"] for row in rows], [signal_id])
        self.assertEqual(rows[0]["ai_summary"], analysis.summary)

        idea_id = convert_signal_to_idea(self.db_path, signal_id)
        with closing(sqlite3.connect(self.db_path)) as conn:
            idea = conn.execute(
                "SELECT content, source, signal_id, status FROM ideas WHERE id = ?",
                (idea_id,),
            ).fetchone()
        self.assertEqual(
            idea,
            (analysis.summary, "从signals转化", signal_id, "未排期"),
        )

    def test_signal_filters_can_return_no_results(self) -> None:
        self.assertEqual(
            load_signals(self.db_path, source_type="电商产品", relevance="低相关"),
            [],
        )


if __name__ == "__main__":
    unittest.main()
