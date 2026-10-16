import io
import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch
from voiceproof.workflow import report, decode, UserError, run
from voiceproof.text import tokens


def segments(text, probability=.95):
    words = tokens(text)
    return [dict(text=text, start=0, end=len(words)*.2,
                 words=[dict(text=t,start=i*.2,end=(i+1)*.2,probability=probability) for i,t in enumerate(words)])]


class WorkflowTests(unittest.TestCase):
    def test_representative_synthetic_scenarios_and_false_positive_budget(self):
        scenarios = json.loads((Path(__file__).parent/'fixtures/scenarios.json').read_text())
        clean_count = 0
        for scenario in scenarios:
            with self.subTest(scenario=scenario['name']):
                result=report(scenario['script'],scenario.get('terms',[]),segments(scenario['spoken'],scenario.get('probability',.95)),dict(duration_ms=30000,issues=[]))
                self.assertEqual(set(scenario['types']),{i['type'] for i in result['issues']})
                self.assertTrue(all(i['state']=='review' for i in result['issues']))
                self.assertTrue(all(0<=i['start']<=i['end']<=30 for i in result['issues']))
                if not scenario['types']:
                    clean_count+=1
                    self.assertEqual(result['issues'],[])
        self.assertEqual(clean_count,3)

    def test_empty_invalid_or_inconsistent_asr_cannot_pass(self):
        for value in ([],[dict(text='你好',start=0,end=1,words=[])],segments('你好')):
            if value and value[0]['words']:
                value[0]['words'][0]['start']=float('nan')
            with self.assertRaises(UserError):
                report('你好',[],value,dict(duration_ms=30000,issues=[]))

    def test_audio_issues_are_review_only(self):
        result=report('你好',[],segments('你好'),dict(duration_ms=3000,issues=[dict(type='long_silence',start_ms=400,end_ms=1800),dict(type='possible_clipping')]))
        self.assertEqual(result['issues'][0]['start'],.4)
        self.assertEqual(result['issues'][1]['end'],3)
        self.assertTrue(all(i['state']=='review' for i in result['issues']))

    def test_local_decoder_and_full_pipeline_with_stubbed_recognition(self):
        try:
            import av
        except ImportError:
            self.skipTest('Install .[local] for media integration')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with wave.open(str(root/'source'),'wb') as out:
                out.setparams((1,2,16000,0,'NONE',''))
                out.writeframes(b'\x00\x10\x00\xf0'*16000)
            (root/'request.json').write_text(json.dumps(dict(script='你好',terms=[])))
            messages=[]
            with patch('voiceproof.workflow.recognize',return_value=segments('你好')):
                result=run(root,root/'model',messages.append)
            self.assertEqual(result['issues'],[])
            self.assertEqual(result['duration'],2)
            self.assertEqual(len(messages),3)
            (root/'bad').write_bytes(b'not media')
            with self.assertRaises(UserError):
                decode(root/'bad',root/'out.wav')

class NumberNormalizationTests(unittest.TestCase):
    def test_conservative_readings(self):
        from voiceproof.numbers import normalize
        for before,after in [('一百二十元','120元'),('二零二六年','2026年'),('三点五米','3.5米'),('万一失败','万一失败'),('一百二元','一百二元'),('十十','十十')]:
            with self.subTest(before=before): self.assertEqual(normalize(before),after)

class MediaBoundaryTests(unittest.TestCase):
    def test_all_compressed_fixtures_decode_with_real_video(self):
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
        from make_media_fixtures import convert
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for extension,codec,video in [('mp3','libmp3lame',False),('m4a','aac',False),('mp4','aac',True),('flac','flac',False)]:
                with self.subTest(extension=extension):
                    source=root/('input.'+extension)
                    convert(source,codec,video)
                    self.assertGreater(decode(source,root/'decoded.wav'),10)

    def test_decoded_duration_limit_and_no_audio(self):
        import av
        import numpy as np
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source=Path(__file__).parent/'fixtures/mandarin-synthetic.wav'
            with patch('voiceproof.workflow.MAX_SECONDS',1):
                with self.assertRaisesRegex(UserError,'超过10分钟'):
                    decode(source,root/'out.wav')
            with av.open(str(root/'silent.mp4'),'w') as out:
                stream=out.add_stream('mpeg4',rate=10);stream.width=32;stream.height=32;stream.pix_fmt='yuv420p'
                frame=av.VideoFrame.from_ndarray(np.zeros((32,32,3),dtype=np.uint8),format='rgb24')
                for packet in stream.encode(frame):out.mux(packet)
                for packet in stream.encode():out.mux(packet)
            with self.assertRaisesRegex(UserError,'没有音轨'):
                decode(root/'silent.mp4',root/'out.wav')

class RealWorkerFailureTests(unittest.TestCase):
    def test_bad_media_returns_chinese_recovery_without_stack_or_json_input_from_user(self):
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'request.json').write_text(json.dumps(dict(script='这是内部合成原稿',terms=[])))
            (root/'source').write_bytes(b'broken movie')
            process=subprocess.run([sys.executable,'-m','voiceproof.worker',str(root),str(root/'missing-model')],capture_output=True,text=True,timeout=30)
            self.assertEqual(process.returncode,0)
            result=json.loads((root/'result.json').read_text())
            self.assertIn('重新导出',result['error'])
            self.assertNotIn('Traceback',process.stderr)
            self.assertEqual(process.stdout,'')

class WordBoundaryRegressionTests(unittest.TestCase):
    def test_split_number_and_latin_word_timestamps_reassemble(self):
        value=[dict(text='金额120.5元使用VoiceProof',start=0,end=3,words=[
            dict(text='金额',start=0,end=.4,probability=.9),
            dict(text='1',start=.4,end=.5,probability=.9),
            dict(text='20',start=.5,end=.7,probability=.9),
            dict(text='.',start=.7,end=.8,probability=.9),
            dict(text='5元使用',start=.8,end=1.5,probability=.9),
            dict(text='Voice',start=1.5,end=2,probability=.9),
            dict(text='Proof',start=2,end=3,probability=.9)])]
        result=report('金额120.5元使用VoiceProof',[],value,dict(duration_ms=3000,issues=[]))
        self.assertEqual(result['issues'],[])
        result=report('金额120.6元使用VoiceProof',[],value,dict(duration_ms=3000,issues=[]))
        issue=result['issues'][0]
        self.assertAlmostEqual(issue['start'],.4)
        self.assertLess(issue['end'],1.1)

class WrittenVariantTests(unittest.TestCase):
    def test_traditional_script_and_terms_do_not_cause_false_alarms(self):
        result=report('我们介绍录音技巧距离麦克风二十厘米',['麦克风'],segments('我們介紹錄音技巧距離麥克風二十厘米'),dict(duration_ms=30000,issues=[]))
        self.assertEqual(result['issues'],[])
        self.assertIn('我們',result['transcript'][0]['text'])
