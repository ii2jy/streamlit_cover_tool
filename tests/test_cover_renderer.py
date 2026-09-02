from __future__ import annotations

import sys
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from cover_renderer import choose_template, compose_cover  # noqa: E402


class CoverRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source = Image.new("RGB", (900, 1200), (105, 130, 150))
        buffer = BytesIO()
        source.save(buffer, format="JPEG")
        cls.image_bytes = buffer.getvalue()

    def test_layout_names_map_to_three_templates(self) -> None:
        self.assertEqual(choose_template("大字报居中"), "center_poster")
        self.assertEqual(choose_template("左文右图"), "left_text")
        self.assertEqual(choose_template("九宫格文字卡"), "nine_grid")

    def test_each_template_outputs_valid_png(self) -> None:
        for layout in ("大字报居中", "左文右图", "九宫格文字卡"):
            with self.subTest(layout=layout):
                result = compose_cover(
                    image_bytes=self.image_bytes,
                    title="第40天差点放弃",
                    layout_type=layout,
                    color_advice="白字搭配橙色强调",
                )
                self.assertTrue(result.startswith(b"\x89PNG"))
                with Image.open(BytesIO(result)) as image:
                    self.assertEqual(image.size, (900, 1200))


if __name__ == "__main__":
    unittest.main()

