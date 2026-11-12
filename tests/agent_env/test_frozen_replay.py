"""Frozen-replay regression, two-sided.

Positive fixtures: 15 frozen real-Qwen trajectories from nw001-20261031-v1 (reward 1).
Negative fixtures: 6 scripted reward-hack attempts (reward 0), made by fixtures/make_negative.py.
Replaying the same actions in a fresh container must reproduce the initial state, every
observation, the final state and the verdict summary (completion, compliance, job behaviour,
evidence freshness, unauthorized attempts and effects, reward). A verifier that becomes stricter
fails the positive set; one that becomes more lenient fails the negative set.
E04 is excluded from the positive set: its definition changed in nw-config-cases@2.
"""

import copy
import json
import unittest
from pathlib import Path

from agent_env.runner import Environment, digest

HERE = Path(__file__).parent / "fixtures"
POSITIVE = sorted((HERE / "frozen_nw001_v1").glob("*.json"))
NEGATIVE = sorted((HERE / "frozen_negative").glob("*.json"))


def replay(record):
    env = Environment(record["scenario_id"])
    try:
        env.reset(record["seed"])
        initial = env.initial_digest == record["initial_state_digest"]
        observations = [digest(env.step(step["action"])) == digest(step["observation"]) for step in record["steps"]]
        verdict = env.verify()
    finally:
        env.close()
    summary = {key: verdict[key] for key in record["verifier"]["summary"]}
    return {"initial_state_equal": initial, "observations_equal": all(observations),
            "final_state_equal": verdict["state_digest"] == record["verifier"]["state_digest"],
            "summary_equal": summary == record["verifier"]["summary"], "summary": summary}


class FrozenReplayTests(unittest.TestCase):
    def test_fixture_sets_are_present_and_two_sided(self):
        self.assertGreaterEqual(len(POSITIVE), 15)
        self.assertGreaterEqual(len(NEGATIVE), 6)
        rewards = {json.loads(p.read_text())["verifier"]["summary"]["reward"] for p in POSITIVE + NEGATIVE}
        self.assertEqual(rewards, {0, 1})

    def test_every_frozen_trajectory_replays_exactly(self):
        for path in POSITIVE + NEGATIVE:
            with self.subTest(fixture=path.name):
                result = replay(json.loads(path.read_text()))
                self.assertTrue(all(v for k, v in result.items() if k != "summary"), result)

    def test_replay_detects_a_changed_observation(self):
        record = copy.deepcopy(json.loads(POSITIVE[0].read_text()))
        record["steps"][0]["observation"] = {"ok": True, "result": "forged"}
        self.assertFalse(replay(record)["observations_equal"])


if __name__ == "__main__":
    unittest.main()
