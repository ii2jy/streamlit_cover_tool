from __future__ import annotations

import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


PROJECT_DIR = Path(__file__).resolve().parents[1]


class StreamlitSmokeTests(unittest.TestCase):
    def test_app_starts_on_radar_page_with_sidebar_navigation(self) -> None:
        app = AppTest.from_file(PROJECT_DIR / "app.py", default_timeout=10).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.sidebar.radio[0].value, "情报雷达")
        self.assertIn("来源类型", [item.label for item in app.selectbox])
        self.assertIn("原始内容", [item.label for item in app.text_area])

    def test_material_library_remains_available(self) -> None:
        app = AppTest.from_file(PROJECT_DIR / "app.py", default_timeout=10).run()
        app.sidebar.radio[0].set_value("素材库").run()
        self.assertFalse(app.exception)
        markdown = "\n".join(item.value for item in app.markdown)
        self.assertIn("自我诊断反常识", markdown)
        self.assertIn("造词+反差行为", markdown)

    def test_ideas_workspace_is_available(self) -> None:
        app = AppTest.from_file(PROJECT_DIR / "app.py", default_timeout=10).run()
        app.sidebar.radio[0].set_value("灵感库").run()
        self.assertFalse(app.exception)
        self.assertIn("例如：第40天差点放弃", [item.placeholder for item in app.text_input])
        self.assertIn("添加灵感", [item.label for item in app.button])

    def test_generator_receives_idea_prefill(self) -> None:
        app = AppTest.from_file(PROJECT_DIR / "app.py", default_timeout=10).run()
        app.session_state["generator_prefill"] = {
            "idea_id": 99,
            "topic": "第40天差点放弃",
            "hook_type": "心理自曝",
        }
        app.sidebar.radio[0].set_value("封面生成器").run()
        choose_button = next(
            item for item in app.button if item.label == "选用这个风格"
        )
        choose_button.click().run()
        self.assertFalse(app.exception)
        topic = next(item for item in app.text_area if item.label == "本次文案主题")
        hook = next(item for item in app.selectbox if item.label == "优先钩子结构")
        self.assertEqual(topic.value, "第40天差点放弃")
        self.assertEqual(hook.value, "心理自曝")


if __name__ == "__main__":
    unittest.main()
