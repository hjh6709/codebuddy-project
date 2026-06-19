import json
import os
import sys
import unittest
from pathlib import Path
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
