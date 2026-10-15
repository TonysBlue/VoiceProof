"""Exercise the shipped CLI with synthetic, non-sensitive inputs."""
import json
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_cli(self, *args):
        return subprocess.run([sys.executable, '-m', 'voiceproof', *map(str, args)],
                              capture_output=True, text=True)

    def test_text_report_and_multiword_term(self):
        script, transcript = self.root / '稿.txt', self.root / '转写.txt'
        script.write_text('今天测试 Voice Proof，金额120元。结束。', encoding='utf-8-sig')
        transcript.write_text('今天测试 Voice Proof，金额20元。', encoding='utf-8')
        output = self.root / 'reports' / 'text.json'
        result = self.run_cli('check-text', '--script', script, '--transcript', transcript,
                              '--term', 'Voice Proof', '--output', output)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(output.read_text())
        kinds = {issue['type'] for issue in report['issues']}
        self.assertIn('number_mismatch', kinds)
        self.assertNotIn('term_mismatch', kinds)
        self.assertTrue(all(i['review_required'] for i in report['issues']))

    def test_pcm_widths_and_channels(self):
        for width in (1, 2, 3, 4):
            for channels in (1, 2):
                with self.subTest(width=width, channels=channels):
                    audio = self.root / 'input.wav'
                    # 0.5s audible signal, 1.5s silence, 0.5s clipped signal.
                    def sample(value):
                        return (bytes([value + 128]) if width == 1 else
                                value.to_bytes(width, 'little', signed=True)) * channels
                    peak = (1 << (width * 8 - 1)) - 1
                    with wave.open(str(audio), 'wb') as stream:
                        stream.setparams((channels, width, 8000, 0, 'NONE', ''))
                        stream.writeframes(sample(peak // 4) * 4000 + sample(0) * 12000 + sample(peak) * 4000)
                    output = self.root / 'audio.json'
                    result = self.run_cli('check-wav', '--audio', audio, '--output', output)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    report = json.loads(output.read_text())
                    self.assertEqual(report['duration_ms'], 2500)
                    self.assertEqual(report['channels'], channels)
                    self.assertEqual(report['issues'][0], dict(type='long_silence', start_ms=500,
                                                              end_ms=2000, review_required=True))
                    self.assertEqual({i['type'] for i in report['issues']}, {'long_silence', 'possible_clipping'})

    def test_invalid_inputs_fail_without_report_or_traceback(self):
        audio = self.root / 'bad.wav'
        output = self.root / 'report.json'
        for content in (b'not a wav', b''):
            audio.write_bytes(content)
            result = self.run_cli('check-wav', '--audio', audio, '--output', output)
            self.assertEqual(result.returncode, 1)
            self.assertNotIn('Traceback', result.stderr)
            self.assertFalse(output.exists())
        with wave.open(str(audio), 'wb') as stream:
            stream.setparams((1, 2, 8000, 0, 'NONE', ''))
            stream.writeframes(b'\0\0' * 16000)
        audio.write_bytes(audio.read_bytes()[:-100])
        result = self.run_cli('check-wav', '--audio', audio, '--output', output)
        self.assertEqual(result.returncode, 1)
        self.assertIn('truncated', result.stderr)
        self.assertFalse(output.exists())

    def test_protect_inputs_and_reject_empty_text(self):
        source = self.root / 'source.txt'
        source.write_text('测试文本', encoding='utf-8')
        result = self.run_cli('check-text', '--script', source, '--transcript', source, '--output', source)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(source.read_text(), '测试文本')
        source.write_text(' ！ ', encoding='utf-8')
        result = self.run_cli('check-text', '--script', source, '--transcript', source,
                              '--output', self.root / 'report.json')
        self.assertEqual(result.returncode, 1)
        self.assertIn('readable text', result.stderr)

    def test_healthy_wav_and_empty_wav(self):
        audio = self.root / 'input.wav'
        output = self.root / 'report.json'
        for frames in (0, 8000):
            with self.subTest(frames=frames):
                with wave.open(str(audio), 'wb') as stream:
                    stream.setparams((1, 1, 8000, 0, 'NONE', ''))
                    stream.writeframes(bytes([160, 96]) * (frames // 2))
                result = self.run_cli('check-wav', '--audio', audio, '--output', output)
                self.assertEqual(result.returncode, 0 if frames else 1, result.stderr)
                if frames:
                    self.assertEqual(json.loads(output.read_text())['issues'], [])
                else:
                    self.assertIn('no audio frames', result.stderr)
                    self.assertFalse(output.exists())
