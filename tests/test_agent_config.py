import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agent_config import AgentState, load_config, load_state, save_state


class AgentConfigTests(unittest.TestCase):
    def test_load_config_uses_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            config = load_config()

        self.assertEqual(config.region, "ap-northeast-2")
        self.assertEqual(config.knowledge_base_id, "Q1ZYRCWLIW")
        self.assertEqual(config.agent_name, "CodeBuddy-Reviewer")
        self.assertEqual(config.alias_name, "dev")

    def test_load_config_accepts_environment_overrides(self):
        with patch.dict(
            os.environ,
            {
                "AWS_REGION": "us-east-1",
                "CODEBUDDY_AGENT_NAME": "TestReviewer",
                "CODEBUDDY_KB_ID": "TESTKB1234",
            },
            clear=True,
        ):
            config = load_config()

        self.assertEqual(config.region, "us-east-1")
        self.assertEqual(config.agent_name, "TestReviewer")
        self.assertEqual(config.knowledge_base_id, "TESTKB1234")

    def test_save_and_load_state_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "state.json"
            state = AgentState(
                agent_id="AGENT1",
                alias_id="ALIAS2",
                role_arn="arn:aws:iam::123456789012:role/test",
            )

            save_state(path, state)

            self.assertEqual(load_state(path), state)

    def test_load_state_reports_invalid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text("{", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "상태 파일"):
                load_state(path)

    def test_load_state_reports_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.json"

            with self.assertRaisesRegex(FileNotFoundError, "setup_agent.py"):
                load_state(path)


if __name__ == "__main__":
    unittest.main()
