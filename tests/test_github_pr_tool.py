import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "lambda" / "github_pr_tool.py"
)
SPEC = importlib.util.spec_from_file_location("github_pr_tool", MODULE_PATH)
github_pr_tool = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = github_pr_tool
SPEC.loader.exec_module(github_pr_tool)


EVENT = {
    "messageVersion": "1.0",
    "actionGroup": "GitHubPRTools",
    "apiPath": "/github-pr",
    "httpMethod": "GET",
    "parameters": [
        {"name": "owner", "value": "octocat"},
        {"name": "repo", "value": "Spoon-Knife"},
        {"name": "pr_number", "value": "40222"},
    ],
}

PR_PAYLOAD = {
    "title": "Improve docs",
    "body": "Description",
    "state": "open",
    "user": {"login": "octocat"},
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-02T00:00:00Z",
    "changed_files": 2,
    "additions": 12,
    "deletions": 3,
    "html_url": "https://github.com/octocat/Spoon-Knife/pull/40222",
}

FILES_PAYLOAD = [
    {
        "filename": "README.md",
        "status": "modified",
        "additions": 10,
        "deletions": 1,
        "changes": 11,
        "patch": "@@ patch\nabcdefghijklmnop",
    },
    {
        "filename": "docs/guide.md",
        "status": "added",
        "additions": 2,
        "deletions": 2,
        "changes": 4,
        "patch": "@@ second patch",
    },
]


class ParameterTests(unittest.TestCase):
    def test_extract_parameters_validates_required_values(self):
        self.assertEqual(
            github_pr_tool.extract_parameters(EVENT),
            ("octocat", "Spoon-Knife", 40222),
        )

    def test_extract_parameters_rejects_missing_values(self):
        with self.assertRaisesRegex(
            github_pr_tool.RequestError,
            "Missing required parameters: repo, pr_number",
        ):
            github_pr_tool.extract_parameters(
                {
                    "parameters": [
                        {"name": "owner", "value": "octocat"},
                    ]
                }
            )

    def test_extract_parameters_rejects_invalid_pr_number(self):
        event = {**EVENT, "parameters": [*EVENT["parameters"]]}
        event["parameters"][2] = {"name": "pr_number", "value": "not-a-number"}

        with self.assertRaisesRegex(
            github_pr_tool.RequestError,
            "pr_number must be an integer",
        ):
            github_pr_tool.extract_parameters(event)


class ResponseTests(unittest.TestCase):
    def test_build_response_serializes_body_as_json_string(self):
        response = github_pr_tool.build_response(EVENT, 200, {"title": "PR"})

        body = response["response"]["responseBody"]["application/json"]["body"]
        self.assertEqual(json.loads(body), {"title": "PR"})
        self.assertEqual(response["response"]["httpStatusCode"], 200)
        self.assertEqual(response["response"]["actionGroup"], "GitHubPRTools")


class NormalizationTests(unittest.TestCase):
    def test_normalize_pr_limits_files_and_patch_length(self):
        result = github_pr_tool.normalize_pr(
            PR_PAYLOAD,
            FILES_PAYLOAD,
            max_files=1,
            max_patch_chars=10,
            max_total_patch_chars=30,
        )

        self.assertEqual(len(result["files"]), 1)
        self.assertTrue(result["files_truncated"])
        self.assertTrue(result["patches_truncated"])
        self.assertEqual(result["files"][0]["patch"], "@@ patch\na")
        self.assertEqual(result["author"], "octocat")

    def test_normalize_pr_handles_missing_patch(self):
        files = [{**FILES_PAYLOAD[0], "patch": None}]

        result = github_pr_tool.normalize_pr(PR_PAYLOAD, files)

        self.assertEqual(result["files"][0]["patch"], "")
        self.assertFalse(result["patches_truncated"])


class ErrorMappingTests(unittest.TestCase):
    def test_github_404_maps_to_not_found(self):
        error = HTTPError(
            "https://api.github.com/test",
            404,
            "Not Found",
            {},
            None,
        )
        self.addCleanup(error.close)

        mapped = github_pr_tool.map_github_error(error)

        self.assertEqual(mapped.status_code, 404)
        self.assertIn("찾을 수 없습니다", mapped.message)

    def test_rate_limit_maps_to_429_with_reset(self):
        error = HTTPError(
            "https://api.github.com/test",
            403,
            "Forbidden",
            {
                "x-ratelimit-remaining": "0",
                "x-ratelimit-reset": "1234",
            },
            None,
        )
        self.addCleanup(error.close)

        mapped = github_pr_tool.map_github_error(error)

        self.assertEqual(mapped.status_code, 429)
        self.assertIn("1234", mapped.message)

    def test_other_github_errors_map_to_bad_gateway(self):
        error = HTTPError(
            "https://api.github.com/test",
            500,
            "Server Error",
            {},
            None,
        )
        self.addCleanup(error.close)

        mapped = github_pr_tool.map_github_error(error)

        self.assertEqual(mapped.status_code, 502)


class HandlerTests(unittest.TestCase):
    def test_handler_returns_normalized_github_data(self):
        with patch.object(
            github_pr_tool,
            "github_get",
            side_effect=[PR_PAYLOAD, FILES_PAYLOAD],
        ):
            response = github_pr_tool.handler(EVENT, None)

        body = json.loads(
            response["response"]["responseBody"]["application/json"]["body"]
        )
        self.assertEqual(response["response"]["httpStatusCode"], 200)
        self.assertEqual(body["title"], "Improve docs")
        self.assertEqual(len(body["files"]), 2)

    def test_handler_returns_network_error_without_internal_details(self):
        with self.assertLogs(level="ERROR"):
            with patch.object(
                github_pr_tool,
                "github_get",
                side_effect=URLError("secret network detail"),
            ):
                response = github_pr_tool.handler(EVENT, None)

        body = json.loads(
            response["response"]["responseBody"]["application/json"]["body"]
        )
        self.assertEqual(response["response"]["httpStatusCode"], 502)
        self.assertNotIn("secret network detail", body["error"])


if __name__ == "__main__":
    unittest.main()
