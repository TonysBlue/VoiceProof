import tempfile
import unittest
import wave
from pathlib import Path

from voiceproof.audio import inspect_wav


class AudioTests(unittest.TestCase):
    def test_detects_long_silence_and_low_level(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "silence.wav"
            with wave.open(str(path), "wb") as output:
                output.setnchannels(1); output.setsampwidth(2); output.setframerate(8000)
                output.writeframes(b"\0\0" * 16000)
            result = inspect_wav(path)
            kinds = {item["type"] for item in result["issues"]}
            self.assertEqual(result["duration_ms"], 2000)
            self.assertIn("long_silence", kinds)
            self.assertIn("very_low_level", kinds)


if __name__ == "__main__":
    unittest.main()

