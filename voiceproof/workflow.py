"""Local media pipeline. No network or reference-script prompting during recognition."""
from __future__ import annotations
import math
import re
import wave
from pathlib import Path
from .alignment import inspect
from .audio import inspect_wav
from .text import tokens
from .numbers import normalize, normalize_timed
from .chinese import simplify, simplify_timed

MODEL_ID = 'Systran/faster-whisper-small'
MODEL_REVISION = '536b0662742c02347bc0e980a01041f333bce120'
MAX_SECONDS = 600
LABELS = {'omission': '漏读', 'repetition': '多读', 'substitution': '错读',
          'number_mismatch': '数字差异', 'term_mismatch': '术语差异',
          'long_silence': '长静音', 'possible_clipping': '疑似削波', 'very_low_level': '音量过低'}

class UserError(ValueError):
    pass


def decode(source: Path, target: Path) -> float:
    import av
    try:
        with av.open(str(source)) as container, wave.open(str(target), 'wb') as out:
            out.setparams((1, 2, 16000, 0, 'NONE', ''))
            if not container.streams.audio:
                raise UserError('该视频没有音轨，请重新导出带声音的视频。')
            resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)
            count = 0
            for frame in container.decode(audio=0):
                for part in resampler.resample(frame):
                    count += part.samples
                    if count > MAX_SECONDS * 16000:
                        raise UserError('素材超过10分钟，请在剪辑软件中分段导出。')
                    out.writeframes(part.to_ndarray().tobytes())
            for part in resampler.resample(None):
                count += part.samples
                if count > MAX_SECONDS * 16000:
                    raise UserError('素材超过10分钟，请分段导出。')
                out.writeframes(part.to_ndarray().tobytes())
            if count < 16000:
                raise UserError('素材不足1秒或没有可解码声音，请重新选择。')
        return count / 16000
    except UserError:
        raise
    except Exception as exc:
        raise UserError('无法读取音视频，请重新导出 WAV、MP3、M4A 或 MP4 后重试。') from exc


def recognize(path: Path, model_dir: Path) -> list[dict]:
    from faster_whisper import WhisperModel
    if not (model_dir / 'model.bin').is_file():
        raise UserError('本地语音引擎尚未安装，请先点击安装语音引擎。')
    model = WhisperModel(str(model_dir), device='cpu', compute_type='int8', local_files_only=True, cpu_threads=4)
    segments, _ = model.transcribe(str(path), language='zh', word_timestamps=True,
                                   vad_filter=True, condition_on_previous_text=False, beam_size=5)
    return [dict(text=s.text, start=s.start, end=s.end,
                 words=[dict(text=w.word, start=w.start, end=w.end, probability=w.probability)
                        for w in (s.words or [])]) for s in segments]


def report(script: str, terms: list[str], segments: list[dict], audio: dict) -> dict:
    duration = audio['duration_ms'] / 1000
    timed = []
    clean_segments = []
    for segment in segments:
        start, end = float(segment['start']), float(segment['end'])
        if not math.isfinite(start + end) or not 0 <= start <= end <= duration + .1:
            raise UserError('转写时间点异常，请重新检查素材。')
        clean_segments.append(dict(text=segment['text'], start=min(start, duration), end=min(end, duration)))
        characters = []
        for word in segment.get('words', []):
            content = ''.join(tokens(word['text'])).replace('.', '')
            ws, we, prob = float(word['start']), float(word['end']), float(word['probability'])
            if not math.isfinite(ws + we + prob) or not 0 <= ws <= we <= duration + .1 or not 0 <= prob <= 1:
                raise UserError('转写时间点异常，请重试。')
            for index, character in enumerate(content):
                characters.append(dict(text=character, start=min(duration, ws+(we-ws)*index/len(content)),
                                       end=min(duration, ws+(we-ws)*(index+1)/len(content)), probability=prob))
        segment_tokens = tokens(segment['text'])
        if ''.join(t.replace('.', '') for t in segment_tokens) != ''.join(c['text'] for c in characters):
            raise UserError('转写与词时间点不一致，请重试或分段检查。')
        offset = 0
        for token in segment_tokens:
            length = len(token.replace('.', ''))
            selected = characters[offset:offset+length]
            timed.append(dict(text=token, start=selected[0]['start'], end=selected[-1]['end'],
                              probability=min(c['probability'] for c in selected)))
            offset += length
    text = ''.join(s['text'] for s in clean_segments)
    if not tokens(text) or not timed:
        raise UserError('未识别到可靠语音，请确认有普通话口播、提高音量后重试。')
    if ''.join(w['text'] for w in timed) != ''.join(tokens(text)):
        raise UserError('转写与词时间点不一致，请重试或分段检查。')
    timed = normalize_timed(simplify_timed(timed))
    alignment = inspect(normalize(simplify(script)), ' '.join(w['text'] for w in timed), [normalize(simplify(t)) for t in terms])
    issues = []
    for issue in alignment['issues']:
        # Numeric and terminology evidence use the enclosing text edit; no fictitious exact timing.
        scope = issue.get('transcript_range')
        if scope is None:
            if issue['type'] == 'term_mismatch':
                needle = tokens(issue['term'])
                expected = tokens(normalize(simplify(script)))
                pos = next((i for i in range(len(expected)) if expected[i:i+len(needle)] == needle), 0)
                edits = [i for i in alignment['issues'] if 'script_range' in i and i['script_range'][0] <= pos < i['script_range'][1]]
            else:
                edits = [i for i in alignment['issues'] if 'transcript_range' in i and
                         (any(re.search(r'\d', t) for t in i['script_tokens'] + i['transcript_tokens']))]
            scope = edits[0]['transcript_range'] if edits else [0, 0]
        j1, j2 = scope
        anchor = timed[min(j1, len(timed)-1)]
        selected = timed[j1:j2] or [anchor]
        issues.append(dict(id=len(issues), type=issue['type'], label=LABELS[issue['type']],
                           start=anchor['start'], end=selected[-1]['end'],
                           expected=''.join(issue.get('script_tokens', [])) or issue.get('term') or '、'.join(issue.get('expected', [])),
                           observed=''.join(issue.get('transcript_tokens', [])) or '、'.join(issue.get('observed', [])),
                           confidence=None if j1 == j2 else round(min(w['probability'] for w in selected), 3),
                           timing='相邻词锚点（漏读无对应声音）' if j1 == j2 else '模型词区间估计',
                           state='review'))
    for issue in audio['issues']:
        issues.append(dict(id=len(issues), type=issue['type'], label=LABELS[issue['type']],
                           start=issue.get('start_ms', 0)/1000, end=issue.get('end_ms', audio['duration_ms'])/1000,
                           expected='', observed='', confidence=None,
                           timing='音量峰值线索，定位为全片' if 'start_ms' not in issue else '音量窗口', state='review'))
    return dict(duration=duration, transcript=clean_segments, issues=issues, similarity=alignment['similarity'],
                warning='识别结果可能有误；低相似度，请先完整回听核对原稿。' if alignment['similarity'] < .65 else '同音字、中文数字语义和专有名词可能误判或漏检；发布前请完整回听。',
                conclusion='建议复核' if issues else '可忽略（仍需完整回听）')


def run(directory: Path, model_dir: Path, progress=lambda message: None) -> dict:
    import json
    request = json.loads((directory/'request.json').read_text())
    progress('正在本机解码音视频')
    decode(directory/'source', directory/'audio.wav')
    progress('正在本机转写，首次处理可能较慢')
    segments = recognize(directory/'audio.wav', model_dir)
    progress('正在对齐原稿并检查音质')
    return report(request['script'], request['terms'], segments, inspect_wav(directory/'audio.wav'))
