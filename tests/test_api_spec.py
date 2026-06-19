import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "docs" / "api-spec.yaml"


class ApiSpecificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = (
            SPEC_PATH.read_text(encoding="utf-8")
            if SPEC_PATH.exists()
            else ""
        )

    def test_submission_api_spec_exists(self):
        self.assertTrue(SPEC_PATH.exists(), "docs/api-spec.yaml must exist")

    def assert_contains_all(self, *values):
        for value in values:
            with self.subTest(value=value):
                self.assertIn(value, self.spec)

    def test_defines_openapi_document_and_both_post_routes(self):
        self.assertRegex(self.spec, r"(?m)^openapi:\s+[\"']?3\.0\.3")
        self.assert_contains_all(
            "  /review:",
            "  /webhook/github:",
        )
        self.assertEqual(2, len(re.findall(r"(?m)^    post:$", self.spec)))

    def test_review_route_documents_api_key_contract(self):
        self.assert_contains_all(
            "ApiKeyAuth:",
            "name: x-api-key",
            "ReviewRequest:",
            "pr_url:",
            "notify_slack:",
            "'202':",
            "'400':",
            "'403':",
            "'429':",
            "'503':",
        )

    def test_webhook_route_documents_hmac_headers_and_events(self):
        self.assert_contains_all(
            "GitHubWebhookSignature:",
            "name: X-Hub-Signature-256",
            "name: X-GitHub-Event",
            "HMAC-SHA256",
            "opened",
            "reopened",
            "synchronize",
            "'200':",
            "'401':",
        )

    def test_shared_schemas_match_runtime_responses(self):
        self.assert_contains_all(
            "ProcessingResponse:",
            "IgnoredResponse:",
            "PingResponse:",
            "ErrorResponse:",
            "CodeBuddy review started",
            "processing",
            "repository:",
            "pr_number:",
            "error:",
            "pong",
        )


if __name__ == "__main__":
    unittest.main()
