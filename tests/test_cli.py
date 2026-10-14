import tempfile
import unittest
from pathlib import Path

from voiceproof.cli import main


class CliTests(unittest.TestCase):
    def test_writes_structured_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("第一项 10 元", encoding="utf-8")
            (root / "b.txt").write_text("第一项 20 元", encoding="utf-8")
            report = root / "report.json"
            self.assertEqual(main(["check-text", "--script", str(root / "a.txt"), "--transcript", str(root / "b.txt"), "--output", str(report)]), 0)
            self.assertTrue(report.is_file())


if __name__ == "__main__":
    unittest.main()

