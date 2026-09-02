import unittest

from scripts.build_motor_backlog import build


class MotorBacklogTests(unittest.TestCase):
    def test_marks_an_empty_queue_clear(self):
        result = build({"pending": [], "processed": []}, 30)
        self.assertEqual(result["status"], "CLEAR")
        self.assertEqual(result["next_action"], "NO_ACTION")

    def test_marks_remaining_candidates_as_backlog(self):
        result = build({"pending": [{"fingerprint": "a"}], "processed": [{"fingerprint": "b"}]}, 30)
        self.assertEqual(result["status"], "BACKLOG")
        self.assertEqual(result["pending_count"], 1)
        self.assertEqual(result["next_action"], "PRIORITIZE_PENDING_NEXT_DAILY_WINDOW")
