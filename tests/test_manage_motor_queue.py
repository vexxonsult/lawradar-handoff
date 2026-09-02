import unittest
from datetime import UTC, datetime

from scripts.manage_motor_queue import advance, empty_queue, stage_prepared


def candidate(number):
    return {"source_id": f"jorf:{number}", "source_kind": "JORF", "change": "NEW", "evidence": {"text_id": str(number)}}


class ManageMotorQueueTests(unittest.TestCase):
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
