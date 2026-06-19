import base64
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
LAMBDA_DIR = ROOT / "lambda"
if str(LAMBDA_DIR) not in sys.path:
    sys.path.insert(0, str(LAMBDA_DIR))

from codebuddy_orchestrator import (  # noqa: E402
    RequestError,
    handler,
    parse_pr_url,
)


class PullRequestUrlTests(unittest.TestCase):
    def test_parse_pr_url_accepts_github_pull_request(self):
        self.assertEqual(
            parse_pr_url("https://github.com/hjh6709/codebuddy-project/pull/12"),
            ("hjh6709", "codebuddy-project", 12),
        )

    def test_parse_pr_url_rejects_non_github_host(self):
        with self.assertRaisesRegex(RequestError, "GitHub Pull Request URL"):
            parse_pr_url("https://example.com/hjh6709/repo/pull/1")


class ReviewApiTests(unittest.TestCase):
    def test_review_api_dispatches_worker_and_returns_202(self):
        calls = []

        class LambdaClient:
            def invoke(self, **kwargs):
                calls.append(kwargs)
                return {"StatusCode": 202}

        event = {
            "resource": "/review",
            "httpMethod": "POST",
            "body": json.dumps(
                {
                    "pr_url": (
                        "https://github.com/hjh6709/"
                        "codebuddy-project/pull/10"
                    ),
                    "notify_slack": True,
                }
            ),
        }

        with (
            patch(
                "codebuddy_orchestrator.boto3.client",
                return_value=LambdaClient(),
            ),
            patch.dict(
                os.environ,
                {"WORKER_FUNCTION_NAME": "codebuddy-review-worker"},
                clear=True,
            ),
        ):
            response = handler(event, None)

        body = json.loads(response["body"])
        payload = json.loads(calls[0]["Payload"])
        self.assertEqual(response["statusCode"], 202)
        self.assertEqual(body["status"], "processing")
        self.assertEqual(calls[0]["InvocationType"], "Event")
        self.assertEqual(
            calls[0]["FunctionName"],
            "codebuddy-review-worker",
        )
        self.assertEqual(payload["pr_number"], 10)
        self.assertTrue(payload["notify_slack"])

    def test_review_api_decodes_base64_body(self):
        encoded = base64.b64encode(
            json.dumps(
                {
                    "pr_url": (
                        "https://github.com/hjh6709/"
                        "codebuddy-project/pull/10"
                    )
                }
            ).encode()
        ).decode()
        event = {
            "resource": "/review",
            "httpMethod": "POST",
            "isBase64Encoded": True,
            "body": encoded,
        }

        with (
            patch("codebuddy_orchestrator.dispatch_worker"),
            patch.dict(
                os.environ,
                {"WORKER_FUNCTION_NAME": "codebuddy-review-worker"},
                clear=True,
            ),
        ):
            response = handler(event, None)

        self.assertEqual(response["statusCode"], 202)

    def test_review_api_rejects_missing_pr_url(self):
        response = handler(
            {
                "resource": "/review",
                "httpMethod": "POST",
                "body": "{}",
            },
            None,
        )

        self.assertEqual(response["statusCode"], 400)

if __name__ == "__main__":
    unittest.main()
