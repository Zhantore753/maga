#!/usr/bin/env python3
"""
Second pass: answer questions that had no correct answer marked in the source
material. Uses a stronger model (Opus 4.8 by default) via the Batches API.

Reads questions.json produced by extract_questions.py, finds questions with an
empty correct_answer_indices, asks the model to solve them, and updates the
same file in place (a .bak backup is written first).

Every question gets an "answer_source" field:
    "marked" - answer was visually marked in the source material
    "ai"     - answered by the model in this pass (check ai_confidence)
    "none"   - still unanswered (model refused / failed)

Usage:
    python solve_answers.py output/algorithms/questions.json
    python solve_answers.py output/algorithms/questions.json --limit 10
"""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import anthropic

POLL_SECONDS = 30

SYSTEM_PROMPT = """\
You are an expert in computer science, algorithms, and programming, answering
exam questions from КТ (комплексное тестирование) for a CS degree program.
Questions are in Russian or Kazakh.

You are given a question and its answer options (0-indexed). Determine which
option(s) are correct. Most questions have exactly one correct answer; select
several indices only when the question explicitly asks for multiple answers
or several options are unambiguously correct.

Set "confidence":
- "high"   - you are certain
- "medium" - the question is ambiguous or poorly worded but one option is best
- "low"    - you are genuinely unsure; such questions will be reviewed by a human
"""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "correct_answer_indices": {
            "type": "array",
            "items": {"type": "integer"},
        },
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["correct_answer_indices", "confidence"],
    "additionalProperties": False,
}


def build_request(q: dict, model: str) -> dict:
    options = "\n".join(f"{i}. {opt}" for i, opt in enumerate(q["options"]))
    return {
        "custom_id": f"q{q['id']}",
        "params": {
            "model": model,
            "max_tokens": 2000,
            "system": SYSTEM_PROMPT,
            "messages": [{
                "role": "user",
                "content": f"Вопрос: {q['question']}\n\nВарианты ответа:\n{options}",
            }],
            "output_config": {
                "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}
            },
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("questions_file", type=Path,
                    help="questions.json from extract_questions.py")
    ap.add_argument("--model", default="claude-opus-4-8",
                    help="model ID (default: claude-opus-4-8)")
    ap.add_argument("--limit", type=int, default=None,
                    help="solve only the first N unanswered (for a trial run)")
    args = ap.parse_args()

    questions = json.loads(args.questions_file.read_text(encoding="utf-8"))
    by_id = {q["id"]: q for q in questions}

    unanswered = [q for q in questions
                  if not q["correct_answer_indices"] and q["options"]]
    if args.limit:
        unanswered = unanswered[:args.limit]

    print(f"{len(questions)} questions total, "
          f"{len(unanswered)} unanswered to solve with {args.model}.")
    if not unanswered:
        for q in questions:
            q.setdefault("answer_source",
                         "marked" if q["correct_answer_indices"] else "none")
        args.questions_file.write_text(
            json.dumps(questions, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print("Nothing to solve.")
        return 0

    client = anthropic.Anthropic()
    batch = client.messages.batches.create(
        requests=[build_request(q, args.model) for q in unanswered])
    print(f"Submitted batch {batch.id} ({len(unanswered)} requests).")

    while True:
        batch = client.messages.batches.retrieve(batch.id)
        counts = batch.request_counts
        print(f"  {batch.id}: {batch.processing_status} "
              f"(ok={counts.succeeded} err={counts.errored} "
              f"processing={counts.processing})")
        if batch.processing_status == "ended":
            break
        time.sleep(POLL_SECONDS)

    solved = failed = 0
    for result in client.messages.batches.results(batch.id):
        qid = int(result.custom_id[1:])
        q = by_id[qid]
        if result.result.type == "succeeded":
            msg = result.result.message
            text = next((b.text for b in msg.content if b.type == "text"), "")
            answer = json.loads(text)
            indices = [i for i in answer["correct_answer_indices"]
                       if 0 <= i < len(q["options"])]
            if indices:
                q["correct_answer_indices"] = indices
                q["answer_source"] = "ai"
                q["ai_confidence"] = answer["confidence"]
                if answer["confidence"] == "low":
                    q["needs_review"] = True
                solved += 1
                continue
        q["answer_source"] = "none"
        q["needs_review"] = True
        failed += 1

    for q in questions:
        q.setdefault("answer_source",
                     "marked" if q["correct_answer_indices"] else "none")

    backup = args.questions_file.with_suffix(".json.bak")
    shutil.copy(args.questions_file, backup)
    args.questions_file.write_text(
        json.dumps(questions, ensure_ascii=False, indent=2),
        encoding="utf-8")

    low_conf = sum(1 for q in questions if q.get("ai_confidence") == "low")
    print()
    print(f"Done. Updated {args.questions_file} (backup: {backup})")
    print(f"  solved by AI:        {solved}")
    print(f"  low-confidence:      {low_conf} (flagged needs_review)")
    print(f"  failed/unanswerable: {failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
