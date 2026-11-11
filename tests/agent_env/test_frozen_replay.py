"""Frozen-replay regression: recorded real-Qwen trajectories must reproduce exactly.

Each fixture holds the actions and observations of one frozen nw001-20261031-v1 trial.
Replaying the same actions in a fresh container must give the same initial state, the same
observation at every step, the same final state and the same reward. A change to the task,
the container code or the verifier's verdict on these trajectories fails this test.
E04 is excluded: its definition changed in nw-config-cases@2 (real timeout fault).
"""

import copy
import json
import unittest
from pathlib import Path

from agent_env.cli import replay
from agent_env.runner import IMAGE

FIXTURES = sorted((Path(__file__).parent / "fixtures/frozen_nw001_v1").glob("*.json"))


def load(path):
    return {**json.loads(path.read_text()), "image_id": IMAGE}


class FrozenReplayTests(unittest.TestCase):
    def test_fixture_set_is_present(self):
        self.assertGreaterEqual(len(FIXTURES), 15)

    def test_every_frozen_trajectory_replays_exactly(self):
        for path in FIXTURES:
            with self.subTest(fixture=path.name):
                result = replay(load(path))
                self.assertTrue(result["passed"], result)

    def test_replay_detects_a_changed_observation(self):
        record = load(FIXTURES[0])
        tampered = copy.deepcopy(record)
        tampered["steps"][0]["observation"] = {"ok": True, "result": "forged"}
        self.assertFalse(replay(tampered)["observations_equal"])


if __name__ == "__main__":
    unittest.main()
