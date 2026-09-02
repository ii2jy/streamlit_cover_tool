from __future__ import annotations

import sys
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from app import optimize_image_for_ai  # noqa: E402


class AIImageInputTests(unittest.TestCase):
    def test_large_phone_image_is_resized_and_encoded_as_jpeg(self) -> None:
        source = BytesIO()
        Image.new("RGB", (3000, 4000), "#cc3355").save(source, format="PNG")

        output, mime_type = optimize_image_for_ai(source.getvalue(), "image/png")

        self.assertEqual(mime_type, "image/jpeg")
        self.assertLess(len(output), len(source.getvalue()))
        with Image.open(BytesIO(output)) as image:
            self.assertLessEqual(max(image.size), 1600)


if __name__ == "__main__":
    unittest.main()
