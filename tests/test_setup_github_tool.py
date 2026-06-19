import io
import unittest
from pathlib import Path
from zipfile import ZipFile

from src.setup_github_tool import (
    build_lambda_trust_policy,
    build_lambda_zip,
    find_action_group,
)


ROOT = Path(__file__).resolve().parents[1]


class LambdaPackageTests(unittest.TestCase):
    def test_build_lambda_zip_contains_expected_handler(self):
        archive = build_lambda_zip(ROOT / "lambda" / "github_pr_tool.py")

        with ZipFile(io.BytesIO(archive)) as zip_file:
            self.assertEqual(zip_file.namelist(), ["github_pr_tool.py"])
            source = zip_file.read("github_pr_tool.py").decode("utf-8")

        self.assertIn("def handler(event, context):", source)


class LambdaPolicyTests(unittest.TestCase):
    def test_build_lambda_trust_policy_uses_lambda_service(self):
        policy = build_lambda_trust_policy()

        self.assertEqual(
            policy["Statement"][0]["Principal"]["Service"],
            "lambda.amazonaws.com",
        )
        self.assertEqual(
            policy["Statement"][0]["Action"],
            "sts:AssumeRole",
        )


class ActionGroupSelectionTests(unittest.TestCase):
    def test_find_action_group_returns_matching_id(self):
        groups = [
            {"actionGroupName": "Other", "actionGroupId": "OTHER"},
            {"actionGroupName": "GitHubPRTools", "actionGroupId": "AG1"},
        ]

        self.assertEqual(
            find_action_group(groups, "GitHubPRTools"),
            "AG1",
        )

    def test_find_action_group_returns_none_without_match(self):
        self.assertIsNone(find_action_group([], "GitHubPRTools"))


if __name__ == "__main__":
    unittest.main()
