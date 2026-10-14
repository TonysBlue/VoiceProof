import unittest

from voiceproof.alignment import inspect


class AlignmentTests(unittest.TestCase):
    def test_reports_number_term_and_text_differences(self):
        result = inspect("金额 120 元，由 OpenAI 检查", "金额 20 元，由系统检查检查", ["OpenAI"])
        kinds = {item["type"] for item in result["issues"]}
        self.assertIn("number_mismatch", kinds)
        self.assertIn("term_mismatch", kinds)
        self.assertTrue(kinds & {"omission", "repetition", "substitution"})


if __name__ == "__main__":
    unittest.main()

