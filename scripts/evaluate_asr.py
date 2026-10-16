"""Measure one synthetic audio fixture against the real installed local model."""
import argparse
import hashlib
import json
import platform
import sys
import tempfile
import time
from difflib import SequenceMatcher
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from voiceproof.workflow import decode, recognize, report, MODEL_ID, MODEL_REVISION
from voiceproof.audio import inspect_wav
from voiceproof.text import tokens
from voiceproof.numbers import normalize
from voiceproof.chinese import simplify
from make_media_fixtures import TEXT, SOURCE


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True)
    start=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='voiceproof-eval-') as temporary:
        path=Path(temporary)/'audio.wav';duration=decode(SOURCE,path)
        segments=recognize(path,args.model.resolve())
        result=report(TEXT,['麦克风'],segments,inspect_wav(path))
    normalized_expected=tokens(normalize(simplify(TEXT)));normalized_actual=tokens(normalize(simplify(''.join(s['text'] for s in segments))))
    # Similarity is diagnostic, not a claim of WER or representative accuracy.
    payload=dict(source='eSpeak NG synthetic Mandarin, not customer audio',source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                 model=MODEL_ID,model_revision=MODEL_REVISION,python=platform.python_version(),platform=platform.platform(),
                 elapsed_seconds=round(time.monotonic()-start,3),audio_seconds=duration,
                 normalized_token_similarity=round(SequenceMatcher(a=normalized_expected,b=normalized_actual,autojunk=False).ratio(),4),
                 candidate_issue_count=len(result['issues']),automatic_rerecord_count=0,report=result)
    args.output.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in payload.items() if k!='report'},ensure_ascii=False))

if __name__=='__main__':main()
