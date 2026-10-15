from __future__ import annotations

import argparse
import json
import sys
import wave
from pathlib import Path

from .alignment import inspect
from .audio import inspect_wav
from .text import tokens


def _write(payload: dict, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="voiceproof")
    sub = parser.add_subparsers(dest="command", required=True)
    text = sub.add_parser("check-text")
    text.add_argument("--script", type=Path, required=True)
    text.add_argument("--transcript", type=Path, required=True)
    text.add_argument("--term", action="append", default=[])
    text.add_argument("--output", type=Path, required=True)
    wav = sub.add_parser("check-wav")
    wav.add_argument("--audio", type=Path, required=True)
    wav.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        inputs = [args.script, args.transcript] if args.command == "check-text" else [args.audio]
        if any(args.output.resolve() == path.resolve() or
               (args.output.exists() and path.exists() and args.output.samefile(path))
               for path in inputs):
            raise ValueError("output must not overwrite an input file")
        if args.command == "check-text":
            script = args.script.read_text(encoding="utf-8-sig")
            transcript = args.transcript.read_text(encoding="utf-8-sig")
            if not tokens(script) or not tokens(transcript):
                raise ValueError("script and transcript must contain readable text")
            payload = inspect(script, transcript, args.term)
        else:
            payload = inspect_wav(args.audio)
        _write(payload, args.output)
    except (OSError, UnicodeError, ValueError, wave.Error, EOFError) as error:
        print(f"voiceproof: {error}", file=sys.stderr)
        return 1
    return 0

