#!/usr/bin/env python3
"""
Add Russian translations to Kazakh questions (question_ru / options_ru fields,
originals kept). Uses Opus via the Batches API.

Usage:
    python translate_questions.py output/math-final.json
    python translate_questions.py output/math-final.json --limit 5
"""

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

import anthropic

POLL_SECONDS = 30
KZ_LETTERS = re.compile(r"[әғқңөұүһі]", re.I)

SYSTEM_PROMPT = """\
You translate Kazakh exam questions into Russian for a study site.

Rules:
- Translate naturally into the formal Russian used in test materials.
- Keep ALL numbers, LaTeX fragments ($...$), units, variable names, and
  bracketed figure/table descriptions ([Сурет: ...] -> [Рисунок: ...],
  translating only the words inside) exactly equivalent.
- Translate every answer option, preserving order. If an option is just a
  number or formula, copy it unchanged.
- Return the same number of options as given.
- Output only the translated text itself - no "Вопрос:" or other labels.
"""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "question_ru": {"type": "string"},
        "options_ru": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["question_ru", "options_ru"],
    "additionalProperties": False,
}


def is_kazakh(q: dict) -> bool:
    return bool(KZ_LETTERS.search(q["question"] + " ".join(q["options"])))


def build_request(q: dict, model: str) -> dict:
    options = "\n".join(f"{i}. {opt}" for i, opt in enumerate(q["options"]))
    return {
        "custom_id": f"q{q['id']}",
        "params": {
            "model": model,
            "max_tokens": 8000,
            "system": SYSTEM_PROMPT,
            "messages": [{
                "role": "user",
                "content": f"Сұрақ: {q['question']}\n\nЖауап нұсқалары:\n{options}",
            }],
            "output_config": {
                "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}
            },
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("questions_file", type=Path)
    ap.add_argument("--model", default="claude-opus-4-8")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    questions = json.loads(args.questions_file.read_text(encoding="utf-8"))
    by_id = {q["id"]: q for q in questions}
    todo = [q for q in questions if is_kazakh(q) and "question_ru" not in q]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(questions)} questions, {len(todo)} Kazakh to translate "
          f"with {args.model}.")
    if not todo:
        return 0

    client = anthropic.Anthropic()
    batch = client.messages.batches.create(
        requests=[build_request(q, args.model) for q in todo])
    print(f"Submitted batch {batch.id} ({len(todo)} requests).")

    while True:
        batch = client.messages.batches.retrieve(batch.id)
        c = batch.request_counts
        print(f"  {batch.id}: {batch.processing_status} "
              f"(ok={c.succeeded} err={c.errored} processing={c.processing})",
              flush=True)
        if batch.processing_status == "ended":
            break
        time.sleep(POLL_SECONDS)

    done = skipped = 0
    for result in client.messages.batches.results(batch.id):
        q = by_id[int(result.custom_id[1:])]
        if result.result.type != "succeeded":
            skipped += 1
            continue
        msg = result.result.message
        text = next((b.text for b in msg.content if b.type == "text"), "")
        try:
            tr = json.loads(text)
        except json.JSONDecodeError:
            skipped += 1  # truncated/invalid response - keep original only
            continue
        if len(tr.get("options_ru", [])) != len(q["options"]):
            skipped += 1  # option count mismatch - keep original only
            continue
        q["question_ru"] = re.sub(r"^\s*Вопрос:\s*", "", tr["question_ru"])
        q["options_ru"] = tr["options_ru"]
        done += 1

    shutil.copy(args.questions_file,
                args.questions_file.with_suffix(".json.bak"))
    args.questions_file.write_text(
        json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"translated {done}, skipped {skipped} -> {args.questions_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
