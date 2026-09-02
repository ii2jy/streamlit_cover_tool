from __future__ import annotations

import sys
import unittest
from pathlib import Path

from pydantic import ValidationError


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import app  # noqa: E402
from prompts import DESIGN_SYSTEM_PROMPT  # noqa: E402


class GenerationSchemaTests(unittest.TestCase):
    def test_generation_requires_exactly_three_suggestions(self) -> None:
        suggestion = {
            "title": "第40天我想停下",
            "hook_type": "心理自曝",
            "layout_type": "人物特写+大字报",
            "text_layout": "主标题两行放在人物右侧",
            "color_advice": "白字搭配橙色重点词",
            "stop_reason": "真实的放弃念头让同类用户迅速代入。",
        }
        result = app.GenerationResult.model_validate(
            {
                "photo_observation": "人物位于左侧，右侧有留白。",
                "suggestions": [suggestion, suggestion, suggestion],
            }
        )
        self.assertEqual(len(result.suggestions), 3)

        with self.assertRaises(ValidationError):
            app.GenerationResult.model_validate(
                {
                    "photo_observation": "人物位于左侧。",
                    "suggestions": [suggestion, suggestion],
                }
            )

    def test_generation_prompt_accepts_preferred_hook(self) -> None:
        prompt = app.GENERATION_PROMPT_TEMPLATE.format(
            topic="第40天差点放弃",
            preferred_hook_type="心理自曝",
            selected_template_title="人物特写模板",
            batch_number=1,
            reference_samples="[]",
        )
        self.assertIn("用户指定的钩子结构：心理自曝", prompt)
        self.assertIn("用户明确选中的对标模板：人物特写模板", prompt)

    def test_design_system_prompt_contains_fixed_principles(self) -> None:
        required_principles = [
            "0.5秒",
            "认知失调",
            "自我代入感",
            "反常识",
            "情绪浓度",
            "视觉异常点",
            "具体数字／时间锚点",
            "自我诊断反常识",
            "情绪化独白",
            "时间反差",
            "心理自曝",
            "造词＋反差行为",
        ]
        for principle in required_principles:
            self.assertIn(principle, DESIGN_SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
