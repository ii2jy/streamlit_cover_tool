from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

from PIL import Image


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from grid_component import create_cover_thumbnail  # noqa: E402


class GridThumbnailTests(unittest.TestCase):
    def test_thumbnail_is_center_cropped_to_three_by_four(self) -> None:
        source = io.BytesIO()
        Image.new("RGB", (1600, 600), "#d9485f").save(source, format="PNG")
        thumbnail = create_cover_thumbnail(source.getvalue())
        with Image.open(io.BytesIO(thumbnail)) as image:
            self.assertEqual(image.size, (600, 800))
            self.assertEqual(image.format, "JPEG")


if __name__ == "__main__":
    unittest.main()
