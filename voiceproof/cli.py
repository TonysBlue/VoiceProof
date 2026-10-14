from __future__ import annotations

import argparse
import json
from pathlib import Path

from .alignment import inspect
from .audio import inspect_wav


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
    if args.command == "check-text":
        payload = inspect(args.script.read_text(encoding="utf-8"), args.transcript.read_text(encoding="utf-8"), args.term)
    else:
        payload = inspect_wav(args.audio)
    _write(payload, args.output)
    return 0

