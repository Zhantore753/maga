#!/usr/bin/env python3
"""
Apply the printed answer key of "source 1" (Магистратура тесттер жинағы 2022,
answer-key pages 226-230) to the extracted questions.

The key maps (variant, question number) -> letter A-E. Letters correspond to
option order as printed, which is the order the extraction preserves.
Questions answered from the key get answer_source="key" (ground truth).

Usage:
    python apply_keys.py "input/english/source 1/Магистратура_тесттер_жинағы_2022_АҒЫЛШЫН_1.pdf" output/english-s1/questions.json
"""

import json
import re
import sys
from pathlib import Path

from pypdf import PdfReader

LETTER_INDEX = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}
KEY_PAGES = range(225, 230)  # 0-based indices of pages 226-230


def parse_keys(pdf_path: Path) -> dict[int, dict[int, str]]:
    reader = PdfReader(pdf_path)
    text = "\n".join(reader.pages[i].extract_text() or "" for i in KEY_PAGES)
    keys: dict[int, dict[int, str]] = {}
    current = None
    # split into tokens of either variant headers or "N. L" answers
    for m in re.finditer(r"(\d+)\)\s*[-–—]\s*ВАРИАНТ|(\d{1,2})\.\s*([A-E])\b",
                         text):
        if m.group(1):
            current = int(m.group(1))
            keys[current] = {}
        elif current is not None:
            keys[current][int(m.group(2))] = m.group(3)
    return keys


def main() -> int:
    pdf_path, questions_file = Path(sys.argv[1]), Path(sys.argv[2])
    keys = parse_keys(pdf_path)
    counts = {v: len(k) for v, k in sorted(keys.items())}
    print(f"parsed keys for {len(keys)} variants "
          f"({min(counts.values())}-{max(counts.values())} answers each)")

    questions = json.loads(questions_file.read_text(encoding="utf-8"))
    applied = conflicts = missing = 0
    for q in questions:
        # variant from the split filename is authoritative
        m = re.search(r"variant (\d+)", q.get("source_file", ""))
        variant = int(m.group(1)) if m else q.get("variant")
        number = q.get("number")
        letter = keys.get(variant, {}).get(number) if number else None
        if letter is None:
            missing += 1
            continue
        idx = LETTER_INDEX[letter]
        if idx >= len(q["options"]):
            q["needs_review"] = True
            missing += 1
            continue
        if q["correct_answer_indices"] and q["correct_answer_indices"] != [idx]:
            conflicts += 1
            q["needs_review"] = True
        q["correct_answer_indices"] = [idx]
        q["answer_source"] = "key"
        q["variant"] = variant
        applied += 1

    questions_file.write_text(
        json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(questions)} questions: key applied to {applied}, "
          f"no key match {missing}, extraction/key conflicts {conflicts} "
          f"(key wins, flagged)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
