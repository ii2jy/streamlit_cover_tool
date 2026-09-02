from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import app  # noqa: E402
from prompts import DESIGN_SYSTEM_PROMPT  # noqa: E402


class SystemPromptInjectionTests(unittest.TestCase):
    def test_cover_analysis_sends_design_principles_as_instructions(self) -> None:
        analysis_payload = {
            "layout_type": "人物特写+大字报",
            "layout_type_status": "已有",
            "layout_type_description": "人物与大标题形成视觉中心",
            "hook_type": "心理自曝",
            "hook_type_status": "已有",
            "hook_type_description": "说出难以启齿的心理状态",
            "color_style": "高对比",
            "font_style": "粗体大字",
            "emotional_tone": "真实脆弱",
            "stop_reason": "高浓度自曝配合大字让同类用户代入。",
        }
        fake_client = SimpleNamespace(
            responses=SimpleNamespace(
                create=lambda **kwargs: SimpleNamespace(
                    output_text=json.dumps(analysis_payload, ensure_ascii=False),
                    request_kwargs=kwargs,
                )
            )
        )
        hook_rows = [
            {"name": "心理自曝", "description": "说出难以启齿的心理状态"}
        ]
        layout_rows = [
            {"name": "人物特写+大字报", "description": "人物配合大标题"}
        ]
        captured: dict = {}

        def create_response(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                output_text=json.dumps(analysis_payload, ensure_ascii=False)
            )

        fake_client.responses.create = create_response
        with patch.object(app, "OpenAI", return_value=fake_client):
            app.analyze_cover(
                image_bytes=b"image",
                mime_type="image/jpeg",
                title="我差点放弃",
                api_key="test-key",
                hook_types=hook_rows,
                layout_types=layout_rows,
            )
        self.assertEqual(captured["instructions"], DESIGN_SYSTEM_PROMPT)

    def test_title_generation_sends_same_design_instructions(self) -> None:
        suggestion = {
            "title": "第40天我想停下",
            "hook_type": "心理自曝",
            "layout_type": "人物特写+大字报",
            "text_layout": "主标题两行放右侧",
            "color_advice": "白字配橙色重点",
            "stop_reason": "真实念头让同类用户代入。",
        }
        payload = {
            "photo_observation": "人物在左侧，右侧有留白。",
            "suggestions": [suggestion, suggestion, suggestion],
        }
        captured: dict = {}

        def create_response(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(output_text=json.dumps(payload, ensure_ascii=False))

        fake_client = SimpleNamespace(
            responses=SimpleNamespace(create=create_response)
        )
        with patch.object(app, "OpenAI", return_value=fake_client):
            app.generate_cover_suggestions(
                image_bytes=b"image",
                mime_type="image/jpeg",
                topic="第40天差点放弃",
                samples=[],
                batch_number=1,
                api_key="test-key",
                preferred_hook_type="心理自曝",
                selected_template_title="人物特写模板",
                template_image_bytes=b"template",
            )
        self.assertEqual(captured["instructions"], DESIGN_SYSTEM_PROMPT)
        content = captured["input"][0]["content"]
        self.assertEqual(
            [item["type"] for item in content].count("input_image"), 2
        )


if __name__ == "__main__":
    unittest.main()
