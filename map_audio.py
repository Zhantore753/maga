#!/usr/bin/env python3
"""
Attach audio files to English listening questions and copy the mp3/wav files
into site/audio/english/ with clean ASCII names.

Mapping rules (run per extraction output):
  --source s1   variant N from split filename; questions 1-8 -> TEXT 1,
                9-16 -> TEXT 2 of "input/english/source 1/audio/N ВАРИАНТ..."
  --source s2   test N from the model's variant field; questions 1-8 -> Text 1,
                9-16 -> Text 2 of "input/english/source 2/audio/Test N"
  --source s3   folder "Listening practice N": listening_text picks the first
                or second audio in the folder; if unknown, both are attached

Usage:
    python map_audio.py output/english-s1/questions.json --source s1
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

INPUT = Path("input/english")
SITE_AUDIO = Path("site/audio/english")

_copied: dict[Path, str] = {}


def publish(src: Path, name: str) -> str:
    """Copy an audio file into the site once; return its site-relative path."""
    if src not in _copied:
        SITE_AUDIO.mkdir(parents=True, exist_ok=True)
        dest = SITE_AUDIO / f"{name}{src.suffix.lower()}"
        shutil.copy(src, dest)
        _copied[src] = f"audio/english/{dest.name}"
    return _copied[src]


def s1_audio(q: dict) -> list[str]:
    m = re.search(r"variant (\d+)", q.get("source_file", ""))
    number = q.get("number")
    if not m or not number or not 1 <= number <= 16:
        return []
    variant = int(m.group(1))
    text = 1 if number <= 8 else 2
    folders = list((INPUT / "source 1" / "audio").glob(f"{variant} ВАРИАНТ*"))
    if not folders:
        return []
    # files use global text numbering: variant N holds TEXT 2N-1 and TEXT 2N
    files = list(folders[0].glob(f"TEXT {2 * variant - 2 + text} -*"))
    return [publish(files[0], f"s1-v{variant:02d}-t{text}")] if files else []


def s2_audio(q: dict) -> list[str]:
    variant, number = q.get("variant"), q.get("number")
    if not variant or not number or not 1 <= number <= 16:
        return []
    text = q.get("listening_text") or (1 if number <= 8 else 2)
    src = INPUT / "source 2" / "audio" / f"Test {variant}" / f"Text {text}.mp3"
    return [publish(src, f"s2-test{variant:02d}-t{text}")] if src.exists() else []


def s3_audio(q: dict) -> list[str]:
    m = re.match(r"Listening practice (\d+)", q.get("source_file", ""))
    if not m:
        return []  # Questions1 etc. - no audio
    folder = INPUT / "source 3" / m.group(0)
    files = sorted(folder.glob("AUDIO *"))
    lt = q.get("listening_text")
    if lt in (1, 2) and len(files) >= 2:
        files = [files[lt - 1]]
    return [publish(f, f"s3-lp{m.group(1)}-{f.stem.replace(' ', '').lower()}")
            for f in files]


MAPPERS = {"s1": s1_audio, "s2": s2_audio, "s3": s3_audio}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("questions_file", type=Path)
    ap.add_argument("--source", choices=sorted(MAPPERS), required=True)
    args = ap.parse_args()

    questions = json.loads(args.questions_file.read_text(encoding="utf-8"))
    mapper = MAPPERS[args.source]
    with_audio = 0
    for q in questions:
        audio = mapper(q)
        if audio:
            q["audio"] = audio
            with_audio += 1

    args.questions_file.write_text(
        json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{args.questions_file}: audio attached to {with_audio} of "
          f"{len(questions)} questions ({len(_copied)} audio files published)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
