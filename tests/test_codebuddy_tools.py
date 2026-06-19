import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError


ROOT = Path(__file__).resolve().parents[1]
LAMBDA_DIR = ROOT / "lambda"
if str(LAMBDA_DIR) not in sys.path:
    sys.path.insert(0, str(LAMBDA_DIR))

from codebuddy_tools import (  # noqa: E402
    RequestError,
    build_response,
    extract_parameters,
    handler,
    route_operation,
)


def event_for(api_path, method, parameters):
    return {
        "messageVersion": "1.0",
        "actionGroup": "CodeBuddyTools",
        "apiPath": api_path,
        "httpMethod": method,
        "parameters": [
            {"name": name, "value": value}
            for name, value in parameters.items()
        ],
    }


class ResponseTests(unittest.TestCase):
    def test_build_response_serializes_body_as_json_string(self):
        event = event_for("/slack/message", "POST", {})

        response = build_response(event, 200, {"success": True})

        body = response["response"]["responseBody"]["application/json"]["body"]
        self.assertEqual(json.loads(body), {"success": True})
        self.assertEqual(response["response"]["actionGroup"], "CodeBuddyTools")


class ParameterTests(unittest.TestCase):
    def test_extract_parameters_requires_values(self):
        event = event_for("/github/pr/comment", "POST", {"owner": "hjh6709"})

        with self.assertRaisesRegex(RequestError, "repo, pr_number, comment"):
            extract_parameters(event, ("owner", "repo", "pr_number", "comment"))


class RoutingTests(unittest.TestCase):
    def test_route_operation_maps_bedrock_event_to_handler_name(self):
        event = event_for("/github/pr/comment", "POST", {})

        self.assertEqual(route_operation(event), "post_pr_comment")

    def test_route_operation_rejects_unknown_operation(self):
        event = event_for("/unknown", "GET", {})

        with self.assertRaisesRegex(RequestError, "지원하지 않는 Tool"):
            route_operation(event)


class GitHubCommentTests(unittest.TestCase):
    def test_handler_posts_pr_comment_with_github_token(self):
        event = event_for(
            "/github/pr/comment",
            "POST",
            {
                "owner": "hjh6709",
                "repo": "codebuddy-project",
                "pr_number": "1",
                "comment": "LGTM",
            },
        )
        calls = []

        def fake_json_request(url, method="GET", headers=None, body=None):
            calls.append((url, method, headers, body))
            return {
                "id": 123,
                "html_url": "https://github.com/hjh6709/codebuddy-project/pull/1#issuecomment-123",
                "body": "LGTM",
            }

        with patch.dict(os.environ, {"GITHUB_TOKEN": "token"}, clear=True):
            with patch("codebuddy_tools.json_request", fake_json_request):
                response = handler(event, None)

        payload = json.loads(
            response["response"]["responseBody"]["application/json"]["body"]
        )
        self.assertEqual(response["response"]["httpStatusCode"], 200)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["comment_id"], 123)
        self.assertEqual(calls[0][1], "POST")
        self.assertEqual(calls[0][3], {"body": "LGTM"})
        self.assertEqual(calls[0][2]["Authorization"], "Bearer token")

    def test_handler_rejects_comment_without_github_token(self):
        event = event_for(
            "/github/pr/comment",
            "POST",
            {
                "owner": "hjh6709",
                "repo": "codebuddy-project",
                "pr_number": "1",
                "comment": "LGTM",
            },
        )

        with patch.dict(os.environ, {}, clear=True):
            response = handler(event, None)

        payload = json.loads(
            response["response"]["responseBody"]["application/json"]["body"]
        )
        self.assertEqual(response["response"]["httpStatusCode"], 500)
        self.assertIn("GITHUB_TOKEN", payload["error"])


class SlackTests(unittest.TestCase):
    def test_handler_sends_slack_message_to_webhook(self):
        event = event_for(
            "/slack/message",
            "POST",
            {"message": "리뷰가 완료되었습니다.", "channel": "#code-review"},
        )
        calls = []

        def fake_json_request(url, method="GET", headers=None, body=None):
            calls.append((url, method, headers, body))
            return "ok"

        with patch.dict(
            os.environ,
            {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/T/A/B"},
            clear=True,
        ):
            with patch("codebuddy_tools.json_request", fake_json_request):
                response = handler(event, None)

        payload = json.loads(
            response["response"]["responseBody"]["application/json"]["body"]
        )
        self.assertEqual(response["response"]["httpStatusCode"], 200)
        self.assertTrue(payload["success"])
        self.assertEqual(calls[0][0], "https://hooks.slack.com/services/T/A/B")
        self.assertEqual(
            calls[0][3],
            {"text": "리뷰가 완료되었습니다.", "channel": "#code-review"},
        )


class ComplexityTests(unittest.TestCase):
    def test_handler_reports_function_complexity_ranks(self):
        code = """
def simple(value):
    return value

def complex_func(items):
    total = 0
    for item in items:
        if item > 0:
            total += item
        elif item == 0:
            total += 1
        else:
            total -= item
    return total
"""
        event = event_for("/complexity", "POST", {"code": code})

        response = handler(event, None)

        payload = json.loads(
            response["response"]["responseBody"]["application/json"]["body"]
        )
        self.assertEqual(response["response"]["httpStatusCode"], 200)
        self.assertEqual(payload["summary"]["total_functions"], 2)
        details = {item["name"]: item for item in payload["details"]}
        self.assertEqual(details["simple"]["complexity"], 1)
        self.assertGreater(details["complex_func"]["complexity"], 3)


class BedrockGenerationTests(unittest.TestCase):
    def test_handler_generates_pytest_unit_tests_with_bedrock(self):
        event = event_for(
            "/unittest",
            "POST",
            {
                "code": "def add(a, b):\n    return a + b\n",
                "function_name": "add",
            },
        )
        calls = []

        class BedrockClient:
            def converse(self, **kwargs):
                calls.append(kwargs)
                return {
                    "output": {
                        "message": {
                            "content": [
                                {"text": "def test_add_returns_sum():\n    assert add(1, 2) == 3"}
                            ]
                        }
                    }
                }

        fake_boto3 = SimpleNamespace(client=lambda *args, **kwargs: BedrockClient())
        with patch("codebuddy_tools.boto3", fake_boto3, create=True):
            response = handler(event, None)

        payload = json.loads(
            response["response"]["responseBody"]["application/json"]["body"]
        )
        self.assertEqual(response["response"]["httpStatusCode"], 200)
        self.assertTrue(payload["success"])
        self.assertIn("test_add_returns_sum", payload["test_code"])
        self.assertIn("pytest", calls[0]["messages"][0]["content"][0]["text"])

    def test_handler_suggests_refactor_with_focus(self):
        event = event_for(
            "/refactor",
            "POST",
            {
                "code": "def total(items):\n    return sum(items)\n",
                "focus": "readability",
            },
        )

        class BedrockClient:
            def converse(self, **kwargs):
                return {
                    "output": {
                        "message": {
                            "content": [{"text": "문제점 분석\n개선된 코드"}]
                        }
                    }
                }

        fake_boto3 = SimpleNamespace(client=lambda *args, **kwargs: BedrockClient())
        with patch("codebuddy_tools.boto3", fake_boto3, create=True):
            response = handler(event, None)

        payload = json.loads(
            response["response"]["responseBody"]["application/json"]["body"]
        )
        self.assertEqual(response["response"]["httpStatusCode"], 200)
        self.assertEqual(payload["focus"], "readability")
        self.assertIn("문제점 분석", payload["suggestion"])


class ErrorMappingTests(unittest.TestCase):
    def test_github_404_maps_to_not_found_response(self):
        event = event_for(
            "/github/pr/comment",
            "POST",
            {
                "owner": "hjh6709",
                "repo": "missing",
                "pr_number": "1",
                "comment": "LGTM",
            },
        )
        error = HTTPError("url", 404, "Not Found", {}, None)

        with patch.dict(os.environ, {"GITHUB_TOKEN": "token"}, clear=True):
            with patch("codebuddy_tools.json_request", side_effect=error):
                response = handler(event, None)

        payload = json.loads(
            response["response"]["responseBody"]["application/json"]["body"]
        )
        self.assertEqual(response["response"]["httpStatusCode"], 404)
        self.assertIn("찾을 수 없습니다", payload["error"])


if __name__ == "__main__":
    unittest.main()
