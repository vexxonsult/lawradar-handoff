import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from scripts.manage_motor_queue import advance, effective_batch_size, empty_queue, stage_prepared


def candidate(number):
    return {"source_id": f"jorf:{number}", "source_kind": "JORF", "change": "NEW", "evidence": {"text_id": str(number)}}


class ManageMotorQueueTests(unittest.TestCase):
    def test_active_batch_keeps_its_original_size_during_cap_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "batch.json"
            state_path.write_text(json.dumps({
                "processing_status": "in_progress", "request_count": 10, "ready": False,
            }))
            self.assertEqual(effective_batch_size(250, state_path), 10)
            state_path.write_text(json.dumps({
                "processing_status": "ended", "request_count": 10, "ready": False,
            }))
            self.assertEqual(effective_batch_size(250, state_path), 10)
            state_path.write_text(json.dumps({
                "processing_status": "ended", "request_count": 10, "ready": True,
            }))
            self.assertEqual(effective_batch_size(250, state_path), 250)

    def test_stages_only_a_bounded_batch_without_losing_the_remainder(self):
        prepared = {"schema": "lawradar-motor-input-v1", "candidates": [candidate(number) for number in range(178)]}
        queue, batch = stage_prepared(prepared, empty_queue(), 10)
        self.assertEqual(len(queue["pending"]), 178)
        self.assertEqual(len(batch["candidates"]), 10)
        self.assertEqual(batch["candidates"][0]["source_id"], "jorf:0")

    def test_successful_batch_is_removed_and_cannot_be_reintroduced(self):
        prepared = {"schema": "lawradar-motor-input-v1", "candidates": [candidate(number) for number in range(3)]}
        queue, batch = stage_prepared(prepared, empty_queue(), 2)
        advanced = advance(queue, batch, now=datetime(2026, 9, 2, tzinfo=UTC))
        self.assertEqual(len(advanced["pending"]), 1)
        self.assertEqual(len(advanced["processed"]), 2)
        repeated, next_batch = stage_prepared(prepared, advanced, 2)
        self.assertEqual(len(repeated["pending"]), 1)
        self.assertEqual(next_batch["candidates"][0]["source_id"], "jorf:2")

    def test_failed_batch_stays_at_the_front_of_the_queue(self):
        prepared = {"schema": "lawradar-motor-input-v1", "candidates": [candidate(number) for number in range(3)]}
        queue, first_batch = stage_prepared(prepared, empty_queue(), 2)
        same_queue, retry_batch = stage_prepared({"schema": "lawradar-motor-input-v1", "candidates": []}, queue, 2)
        self.assertEqual(same_queue, queue)
        self.assertEqual(retry_batch["candidates"], first_batch["candidates"])

    def test_replaces_pending_title_only_candidate_when_evidence_improves(self):
        queue, _ = stage_prepared({"candidates": [candidate(1)]}, empty_queue(), 10)
        enriched = candidate(1)
        enriched["evidence"]["official_text_excerpt"] = "Texte officiel."
        queue, batch = stage_prepared({"candidates": [enriched]}, queue, 10)
        self.assertEqual(len(queue["pending"]), 1)
        self.assertEqual(batch["candidates"][0]["evidence"]["official_text_excerpt"], "Texte officiel.")

    def test_marks_empty_primary_jorf_text_unresolved_without_model_input(self):
        incomplete = candidate(1)
        incomplete["evidence"]["content_status"] = "UNAVAILABLE"
        queue, batch = stage_prepared({"candidates": [incomplete]}, empty_queue(), 10)
        self.assertEqual(queue["pending"], [])
        self.assertEqual(batch["candidates"], [])
        self.assertEqual(batch["deterministically_unresolved_candidates"][0]["reason"], "PRIMARY_TEXT_EMPTY")
        self.assertEqual(queue["processed"][0]["deterministic_status"], "UNRESOLVED")
