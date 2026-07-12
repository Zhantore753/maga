#!/usr/bin/env python3
"""
Attach source screenshots to questions that reference a figure, so the site
can show the original picture. Screenshots are recompressed (JPEG, max width
1400px) into site/img/<topic>/. Questions whose screenshot reveals a marked
answer are skipped.

Usage:
    python attach_images.py output/math-final.json input/math/images --topic math
"""

import argparse
import io
import json
import re
import sys
import zipfile
from pathlib import Path

from PIL import Image

FIGURE_MARKER = re.compile(
    r"\[(Сурет|Рисунок|Фигура|График|Диаграмма|Figure)", re.I)
MAX_WIDTH = 1400
JPEG_QUALITY = 80


def load_source(q: dict, images_dir: Path, docs_dir: Path | None):
    """Locate the source image for a question: a screenshot file, an image
    embedded in a DOCX, or a merged duplicate's screenshot."""
    m = re.match(r"(.+\.docx) \((image[^)]+)\)", q["source_file"])
    if m and docs_dir and (docs_dir / m.group(1)).exists():
        with zipfile.ZipFile(docs_dir / m.group(1)) as zf:
            entry = f"word/media/{m.group(2)}"
            if entry in zf.namelist():
                return Image.open(io.BytesIO(zf.read(entry)))
    for name in [q["source_file"], *(q.get("duplicate_sources") or [])]:
        if (images_dir / name).exists():
            return Image.open(images_dir / name)
    return None


def compress(src: Path, dest: Path) -> None:
    img = Image.open(src)
    if img.width > MAX_WIDTH:
        img = img.resize((MAX_WIDTH, round(img.height * MAX_WIDTH / img.width)))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, format="JPEG", quality=JPEG_QUALITY)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("questions_file", type=Path)
    ap.add_argument("images_dir", type=Path)
    ap.add_argument("--topic", required=True)
    ap.add_argument("--all", action="store_true",
                    help="attach to every question, not only figure-marked ones")
    ap.add_argument("--include-marked", action="store_true",
                    help="also attach screenshots that reveal the marked answer")
    ap.add_argument("--docs-dir", type=Path, default=None,
                    help="folder with DOCX files to pull embedded images from")
    args = ap.parse_args()

    questions = json.loads(args.questions_file.read_text(encoding="utf-8"))
    site_dir = Path("site/img") / args.topic
    attached = skipped_marked = missing = 0

    for q in questions:
        text = (q.get("question") or "") + (q.get("question_ru") or "")
        if not args.all and not FIGURE_MARKER.search(text):
            continue
        if q.get("image"):
            continue
        if q.get("answer_source") == "marked" and not args.include_marked:
            skipped_marked += 1  # screenshot would reveal the correct answer
            continue
        img = load_source(q, args.images_dir, args.docs_dir)
        if img is None:
            missing += 1
            continue
        if img.width > MAX_WIDTH:
            img = img.resize((MAX_WIDTH, round(img.height * MAX_WIDTH / img.width)))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        dest = site_dir / f"q{q['id']}.jpg"
        dest.parent.mkdir(parents=True, exist_ok=True)
        img.save(dest, format="JPEG", quality=JPEG_QUALITY)
        q["image"] = f"img/{args.topic}/{dest.name}"
        attached += 1

    args.questions_file.write_text(
        json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8")
    total_mb = sum(f.stat().st_size for f in site_dir.glob("*.jpg")) / 1e6
    print(f"attached {attached} images ({total_mb:.1f} MB), "
          f"skipped {skipped_marked} with marked answers, {missing} missing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
