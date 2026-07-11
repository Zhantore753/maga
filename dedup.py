#!/usr/bin/env python3
"""
Merge one or more questions.json files and drop duplicate questions — no AI,
pure text matching. Run this BEFORE solve_answers.py so you don't pay to
answer the same question twice.

Duplicates are detected by normalized question text (case, punctuation,
whitespace, ё/е differences ignored), then a fuzzy pass catches near-identical
wording (OCR variations). When duplicates merge:
  - the copy with a marked answer wins;
  - if only a duplicate has the answer, it is carried over (options are
    matched by text, since option order may differ between copies);
  - if two copies disagree on the answer, the question is flagged needs_review.

Usage:
    python dedup.py output/algorithms/questions.json output/algorithms-docs/questions.json -o output/combined.json
"""

import argparse
import difflib
import json
import re
import sys
import unicodedata
from pathlib import Path

FUZZY_THRESHOLD = 0.92


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower().replace("ё", "е")
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def score(q: dict) -> tuple:
    """Higher = better copy to keep."""
    return (
        bool(q["correct_answer_indices"]),
        not q.get("needs_review", False),
        len(q.get("options", [])),
        len(q.get("question", "")),
    )


def map_answer(src: dict, dst: dict) -> list | None:
    """Translate src's answer indices into dst's option order via option text."""
    dst_by_text = {normalize(opt): i for i, opt in enumerate(dst["options"])}
    mapped = []
    for i in src["correct_answer_indices"]:
        if not (0 <= i < len(src["options"])):
            return None
        j = dst_by_text.get(normalize(src["options"][i]))
        if j is None:
            return None
        mapped.append(j)
    return sorted(mapped)


def merge_group(group: list[dict]) -> dict:
    group = sorted(group, key=score, reverse=True)
    keeper = group[0]
    keeper["duplicate_count"] = len(group) - 1
    dup_sources = sorted({q["source_file"] for q in group[1:]}
                         - {keeper["source_file"]})
    if dup_sources:
        keeper["duplicate_sources"] = dup_sources

    for other in group[1:]:
        if not other["correct_answer_indices"]:
            continue
        mapped = map_answer(other, keeper)
        if mapped is None:
            continue
        if not keeper["correct_answer_indices"]:
            keeper["correct_answer_indices"] = mapped
        elif sorted(keeper["correct_answer_indices"]) != mapped:
            keeper["needs_review"] = True  # copies disagree on the answer
    return keeper


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("inputs", type=Path, nargs="+",
                    help="one or more questions.json files")
    ap.add_argument("-o", "--output", type=Path, required=True,
                    help="merged, deduplicated output file")
    args = ap.parse_args()

    questions = []
    for path in args.inputs:
        data = json.loads(path.read_text(encoding="utf-8"))
        questions.extend(data)
        print(f"{path}: {len(data)} questions")

    # Pass 1: group by (attached audio, exact normalized question text).
    # Questions tied to different recordings never merge, even if the text
    # is identical ("What is the main idea of the text?").
    exact: dict[tuple, list[dict]] = {}
    for q in questions:
        key = (",".join(q.get("audio", [])), normalize(q["question"]))
        exact.setdefault(key, []).append(q)

    # Pass 2: fuzzy-merge groups whose question text is nearly identical
    keys = sorted(exact)
    merged_into: dict[tuple, tuple] = {}
    for i, key in enumerate(keys):
        if key in merged_into:
            continue
        matcher = difflib.SequenceMatcher(a=key[1])
        for other in keys[i + 1:]:
            if (other in merged_into or other[0] != key[0]
                    or abs(len(other[1]) - len(key[1])) > 20):
                continue
            matcher.set_seq2(other[1])
            if (matcher.quick_ratio() >= FUZZY_THRESHOLD
                    and matcher.ratio() >= FUZZY_THRESHOLD):
                exact[key].extend(exact[other])
                merged_into[other] = key

    result = [merge_group(exact[k]) for k in keys if k not in merged_into]
    result.sort(key=lambda q: (q["source_file"], q["id"]))
    for new_id, q in enumerate(result, start=1):
        q["id"] = new_id

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    dropped = len(questions) - len(result)
    with_answer = sum(1 for q in result if q["correct_answer_indices"])
    print()
    print(f"{len(questions)} in -> {len(result)} out "
          f"({dropped} duplicates dropped)")
    print(f"  with answer: {with_answer}, "
          f"still unanswered: {len(result) - with_answer}")
    print(f"Written to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
