#!/usr/bin/env python3
"""
Independently re-solve every answered question with Opus and reconcile:

  - agreement + high confidence   -> answer confirmed, needs_review cleared
  - disagreement, stored was AI   -> adopt the new answer
  - disagreement, stored was a mark/key -> adopt only on high confidence,
    keeping the old answer in "previous_answer_indices"; always flag
  - questions with audio are never auto-changed (model can't hear them)

Usage:
    python verify_answers.py output/algorithms-final.json
"""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import anthropic

from solve_answers import SYSTEM_PROMPT, OUTPUT_SCHEMA, build_request

POLL_SECONDS = 30


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("questions_file", type=Path)
    ap.add_argument("--model", default="claude-opus-4-8")
    args = ap.parse_args()

    questions = json.loads(args.questions_file.read_text(encoding="utf-8"))
    by_id = {q["id"]: q for q in questions}
    todo = [q for q in questions
            if q["correct_answer_indices"] and len(q.get("options", [])) >= 2
            and not q.get("audio")]
    print(f"{len(questions)} questions, verifying {len(todo)} with {args.model}.")

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

    confirmed = adopted = flagged = errors = 0
    changed_ids = []
    for result in client.messages.batches.results(batch.id):
        q = by_id[int(result.custom_id[1:])]
        if result.result.type != "succeeded":
            errors += 1
            continue
        msg = result.result.message
        text = next((b.text for b in msg.content if b.type == "text"), "")
        try:
            answer = json.loads(text)
        except json.JSONDecodeError:
            errors += 1
            continue
        indices = sorted(i for i in answer["correct_answer_indices"]
                         if 0 <= i < len(q["options"]))
        conf = answer["confidence"]
        stored = sorted(q["correct_answer_indices"])

        if indices == stored:
            confirmed += 1
            if conf == "high":
                q["needs_review"] = False
            continue

        # disagreement
        was_ai = q.get("answer_source") == "ai"
        if was_ai or (indices and conf == "high"):
            q["previous_answer_indices"] = stored
            q["correct_answer_indices"] = indices or stored
            q["answer_source"] = "ai"
            q["ai_confidence"] = conf
            q["needs_review"] = True
            adopted += 1
            changed_ids.append(q["id"])
        else:
            q["needs_review"] = True
            flagged += 1
            changed_ids.append(-q["id"])  # negative = flagged only

    shutil.copy(args.questions_file,
                args.questions_file.with_suffix(".json.bak"))
    args.questions_file.write_text(
        json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print(f"confirmed unchanged: {confirmed}")
    print(f"answers changed:     {adopted} -> ids {[i for i in changed_ids if i > 0]}")
    print(f"flagged only:        {flagged} -> ids {[-i for i in changed_ids if i < 0]}")
    print(f"errors:              {errors}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
