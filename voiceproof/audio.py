from __future__ import annotations

import audioop
import wave
from pathlib import Path


def inspect_wav(path: Path, silence_ms: int = 1200, threshold_rms: int = 150) -> dict:
    issues: list[dict] = []
    with wave.open(str(path), "rb") as stream:
        channels, width, rate, frames = stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getnframes()
        if stream.getcomptype() != "NONE" or width not in (1, 2, 3, 4):
            raise ValueError("only uncompressed PCM WAV is supported")
        window_frames = max(1, rate // 10)
        silent_start = None
        index = 0
        peak = 0
        while True:
            chunk = stream.readframes(window_frames)
            if not chunk:
                break
            rms = audioop.rms(chunk, width)
            peak = max(peak, audioop.max(chunk, width))
            at_ms = int(index * 1000 / rate)
            if rms < threshold_rms and silent_start is None:
                silent_start = at_ms
            if rms >= threshold_rms and silent_start is not None:
                if at_ms - silent_start >= silence_ms:
                    issues.append({"type": "long_silence", "start_ms": silent_start, "end_ms": at_ms, "review_required": True})
                silent_start = None
            index += len(chunk) // (width * channels)
        duration_ms = int(frames * 1000 / rate)
        if silent_start is not None and duration_ms - silent_start >= silence_ms:
            issues.append({"type": "long_silence", "start_ms": silent_start, "end_ms": duration_ms, "review_required": True})
        max_value = (1 << (width * 8 - 1)) - 1
        if peak >= max_value * 0.99:
            issues.append({"type": "possible_clipping", "peak": peak, "review_required": True})
        if peak < max_value * 0.02:
            issues.append({"type": "very_low_level", "peak": peak, "review_required": True})
    return {"schema_version": "voiceproof-report/v1", "check": "wav_audio", "duration_ms": duration_ms, "sample_rate": rate, "channels": channels, "issues": issues, "disclaimer": "音频指标是复核线索，不代表内容或听感结论。"}

