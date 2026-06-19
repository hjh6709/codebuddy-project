import base64
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from botocore.exceptions import ClientError


ROOT = Path(__file__).resolve().parents[1]
LAMBDA_DIR = ROOT / "lambda"
if str(LAMBDA_DIR) not in sys.path:
    sys.path.insert(0, str(LAMBDA_DIR))

import codebuddy_orchestrator  # noqa: E402
from codebuddy_orchestrator import (  # noqa: E402
    RequestError,
    dispatch_worker,
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
    def setUp(self):
        codebuddy_orchestrator._LAMBDA_CLIENT = None

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

    def test_response_does_not_allow_every_cors_origin_by_default(self):
        response = handler(
            {"resource": "/review", "httpMethod": "OPTIONS"},
            None,
        )

        self.assertNotEqual(
            response["headers"]["Access-Control-Allow-Origin"],
            "*",
        )

    def test_dispatch_worker_reuses_lambda_client(self):
        class LambdaClient:
            def invoke(self, **kwargs):
                return {"StatusCode": 202}

        with (
            patch(
                "codebuddy_orchestrator.boto3.client",
                return_value=LambdaClient(),
            ) as client_factory,
            patch.dict(
                os.environ,
                {"WORKER_FUNCTION_NAME": "codebuddy-review-worker"},
                clear=True,
            ),
        ):
            dispatch_worker({"pr_number": 1})
            dispatch_worker({"pr_number": 2})

        self.assertEqual(client_factory.call_count, 1)

    def test_worker_dispatch_failure_returns_503(self):
        class FailingLambdaClient:
            def invoke(self, **kwargs):
                raise ClientError(
                    {
                        "Error": {
                            "Code": "ServiceException",
                            "Message": "temporary failure",
                        }
                    },
                    "Invoke",
                )

        event = {
            "resource": "/review",
            "httpMethod": "POST",
            "body": json.dumps(
                {
                    "pr_url": (
                        "https://github.com/hjh6709/"
                        "codebuddy-project/pull/10"
                    )
                }
            ),
        }

        with (
            patch(
                "codebuddy_orchestrator.boto3.client",
                return_value=FailingLambdaClient(),
            ),
            patch.dict(
                os.environ,
                {"WORKER_FUNCTION_NAME": "codebuddy-review-worker"},
                clear=True,
            ),
        ):
            response = handler(event, None)

        self.assertEqual(response["statusCode"], 503)

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

    def test_options_preflight_returns_204(self):
        response = handler(
            {"httpMethod": "OPTIONS", "resource": "/review"},
            None,
        )

        self.assertEqual(response["statusCode"], 204)

    def test_unknown_route_returns_404(self):
        response = handler(
            {"httpMethod": "GET", "resource": "/review"},
            None,
        )

        self.assertEqual(response["statusCode"], 404)

    def test_invalid_json_body_returns_400(self):
        response = handler(
            {
                "httpMethod": "POST",
                "resource": "/review",
                "body": "not-json",
            },
            None,
        )

        self.assertEqual(response["statusCode"], 400)

    def test_parse_pr_url_rejects_zero_pr_number(self):
        with self.assertRaisesRegex(RequestError, "positive"):
            parse_pr_url("https://github.com/owner/repo/pull/0")

if __name__ == "__main__":
    unittest.main()
