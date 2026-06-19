import base64
import hashlib
import hmac
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

    def test_response_omits_cors_origin_when_not_configured(self):
        response = handler(
            {"resource": "/review", "httpMethod": "OPTIONS"},
            None,
        )

        self.assertNotIn(
            "Access-Control-Allow-Origin",
            response["headers"],
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

    def test_unexpected_worker_status_returns_503(self):
        class RejectedLambdaClient:
            def invoke(self, **kwargs):
                return {"StatusCode": 500}

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
                return_value=RejectedLambdaClient(),
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


class GitHubWebhookTests(unittest.TestCase):
    def build_event(self, event_name, payload, secret="webhook-secret"):
        body = json.dumps(payload, separators=(",", ":"))
        signature = hmac.new(
            secret.encode(),
            body.encode(),
            hashlib.sha256,
        ).hexdigest()
        return {
            "resource": "/webhook/github",
            "httpMethod": "POST",
            "headers": {
                "X-GitHub-Event": event_name,
                "X-Hub-Signature-256": f"sha256={signature}",
            },
            "body": body,
        }

    def test_pull_request_opened_dispatches_review_worker(self):
        payload = {
            "action": "opened",
            "repository": {
                "name": "codebuddy-project",
                "owner": {"login": "hjh6709"},
            },
            "pull_request": {"number": 7},
        }
        event = self.build_event("pull_request", payload)

        with (
            patch(
                "codebuddy_orchestrator.get_webhook_secret",
                return_value="webhook-secret",
                create=True,
            ),
            patch(
                "codebuddy_orchestrator.dispatch_worker"
            ) as dispatch_worker,
        ):
            response = handler(event, None)

        self.assertEqual(response["statusCode"], 202)
        dispatch_worker.assert_called_once_with(
            {
                "owner": "hjh6709",
                "repo": "codebuddy-project",
                "pr_number": 7,
                "notify_slack": True,
                "source": "github-webhook",
            }
        )

    def test_webhook_rejects_invalid_signature(self):
        event = self.build_event(
            "pull_request",
            {"action": "opened"},
        )
        event["headers"]["X-Hub-Signature-256"] = "sha256=invalid"

        with patch(
            "codebuddy_orchestrator.get_webhook_secret",
            return_value="webhook-secret",
            create=True,
        ):
            response = handler(event, None)

        self.assertEqual(response["statusCode"], 401)

    def test_webhook_decodes_request_body_once(self):
        event = self.build_event("ping", {"zen": "Keep it simple."})

        with (
            patch(
                "codebuddy_orchestrator.get_webhook_secret",
                return_value="webhook-secret",
            ),
            patch(
                "codebuddy_orchestrator.decode_body",
                wraps=codebuddy_orchestrator.decode_body,
            ) as decode_body,
        ):
            response = handler(event, None)

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(decode_body.call_count, 1)

    def test_webhook_returns_503_when_secret_store_is_unavailable(self):
        class FailingSecretsClient:
            def get_secret_value(self, **kwargs):
                raise ClientError(
                    {
                        "Error": {
                            "Code": "ServiceUnavailableException",
                            "Message": "temporary failure",
                        }
                    },
                    "GetSecretValue",
                )

        event = self.build_event("ping", {"zen": "Keep it simple."})
        codebuddy_orchestrator._WEBHOOK_SECRET = None

        with (
            patch(
                "codebuddy_orchestrator.get_secrets_client",
                return_value=FailingSecretsClient(),
            ),
            patch.dict(
                os.environ,
                {"WEBHOOK_SECRET_ARN": "arn:secret"},
                clear=True,
            ),
        ):
            response = handler(event, None)

        self.assertEqual(response["statusCode"], 503)

    def test_webhook_ping_returns_pong_without_dispatch(self):
        event = self.build_event("ping", {"zen": "Keep it simple."})

        with (
            patch(
                "codebuddy_orchestrator.get_webhook_secret",
                return_value="webhook-secret",
                create=True,
            ),
            patch(
                "codebuddy_orchestrator.dispatch_worker"
            ) as dispatch_worker,
        ):
            response = handler(event, None)

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(json.loads(response["body"])["message"], "pong")
        dispatch_worker.assert_not_called()

    def test_webhook_ignores_unsupported_pull_request_action(self):
        event = self.build_event(
            "pull_request",
            {"action": "closed"},
        )

        with (
            patch(
                "codebuddy_orchestrator.get_webhook_secret",
                return_value="webhook-secret",
                create=True,
            ),
            patch(
                "codebuddy_orchestrator.dispatch_worker"
            ) as dispatch_worker,
        ):
            response = handler(event, None)

        self.assertEqual(response["statusCode"], 202)
        self.assertEqual(json.loads(response["body"])["status"], "ignored")
        dispatch_worker.assert_not_called()

    def test_webhook_supports_reopened_and_synchronize_actions(self):
        for action in ("reopened", "synchronize"):
            with self.subTest(action=action):
                payload = {
                    "action": action,
                    "repository": {
                        "name": "codebuddy-project",
                        "owner": {"login": "hjh6709"},
                    },
                    "pull_request": {"number": 8},
                }
                event = self.build_event("pull_request", payload)

                with (
                    patch(
                        "codebuddy_orchestrator.get_webhook_secret",
                        return_value="webhook-secret",
                        create=True,
                    ),
                    patch(
                        "codebuddy_orchestrator.dispatch_worker"
                    ) as dispatch_worker,
                ):
                    response = handler(event, None)

                self.assertEqual(response["statusCode"], 202)
                dispatch_worker.assert_called_once()

if __name__ == "__main__":
    unittest.main()
