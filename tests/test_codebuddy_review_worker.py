import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
LAMBDA_DIR = ROOT / "lambda"
if str(LAMBDA_DIR) not in sys.path:
    sys.path.insert(0, str(LAMBDA_DIR))

from codebuddy_review_worker import (  # noqa: E402
    RequestError,
    build_review_prompt,
    handler,
)


class PromptTests(unittest.TestCase):
    def test_prompt_requires_pr_comment_and_slack_notification(self):
        prompt = build_review_prompt(
            owner="hjh6709",
            repo="codebuddy-project",
            pr_number=4,
            notify_slack=True,
        )

        self.assertIn("hjh6709/codebuddy-project", prompt)
        self.assertIn("PR 번호: 4", prompt)
        self.assertIn("PR 댓글", prompt)
        self.assertIn("Slack", prompt)
        self.assertIn("전체 리뷰라고 단정하지", prompt)

    def test_prompt_can_disable_slack_notification(self):
        prompt = build_review_prompt(
            owner="hjh6709",
            repo="codebuddy-project",
            pr_number=4,
            notify_slack=False,
        )

        self.assertIn("Slack 알림은 보내지 마세요", prompt)


class WorkerTests(unittest.TestCase):
    def test_handler_invokes_bedrock_agent(self):
        calls = []

        class RuntimeClient:
            def invoke_agent(self, **kwargs):
                calls.append(kwargs)
                return {
                    "completion": [
                        {"chunk": {"bytes": "자동 리뷰 완료".encode("utf-8")}}
                    ]
                }

        with (
            patch(
                "codebuddy_review_worker.boto3.client",
                return_value=RuntimeClient(),
            ),
            patch.dict(
                os.environ,
                {"AGENT_ID": "AGENT1", "ALIAS_ID": "ALIAS1"},
                clear=True,
            ),
        ):
            result = handler(
                {
                    "owner": "hjh6709",
                    "repo": "codebuddy-project",
                    "pr_number": 4,
                    "notify_slack": True,
                },
                None,
            )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["result"], "자동 리뷰 완료")
        self.assertEqual(calls[0]["agentId"], "AGENT1")
        self.assertEqual(calls[0]["agentAliasId"], "ALIAS1")

    def test_handler_requires_agent_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RequestError, "AGENT_ID"):
                handler(
                    {
                        "owner": "hjh6709",
                        "repo": "codebuddy-project",
                        "pr_number": 4,
                    },
                    None,
                )

    def test_handler_rejects_incomplete_job(self):
        with patch.dict(
            os.environ,
            {"AGENT_ID": "AGENT1", "ALIAS_ID": "ALIAS1"},
            clear=True,
        ):
            with self.assertRaisesRegex(RequestError, "owner"):
                handler({"repo": "codebuddy-project"}, None)


if __name__ == "__main__":
    unittest.main()
