import json
import unittest
from io import BytesIO
from zipfile import ZipFile

import src.setup_codebuddy_tools as setup_codebuddy_tools
from src.setup_codebuddy_tools import (
    build_bedrock_runtime_policy,
    build_lambda_zip,
    collect_tool_environment,
    find_action_group,
)


class LambdaPackageTests(unittest.TestCase):
    def test_build_lambda_zip_contains_unified_executor(self):
        archive = build_lambda_zip()

        with ZipFile(BytesIO(archive)) as zip_file:
            self.assertEqual(zip_file.namelist(), ["codebuddy_tools.py"])


class EnvironmentTests(unittest.TestCase):
    def test_collect_tool_environment_includes_only_present_secrets(self):
        values = collect_tool_environment(
            {
                "GITHUB_TOKEN": "ghp_test",
                "SLACK_WEBHOOK_URL": "",
                "CODEBUDDY_TOOL_MODEL_ID": "global.model",
                "AWS_REGION": "ap-northeast-2",
            }
        )

        self.assertEqual(
            values,
            {
                "GITHUB_TOKEN": "ghp_test",
                "CODEBUDDY_TOOL_MODEL_ID": "global.model",
            },
        )


class PolicyTests(unittest.TestCase):
    def test_build_bedrock_runtime_policy_scopes_model_resources(self):
        policy = build_bedrock_runtime_policy(
            account_id="123456789012",
            region="ap-northeast-2",
            model_id="global.anthropic.claude-sonnet-4-6",
        )

        statements = {item["Sid"]: item for item in policy["Statement"]}
        self.assertIn(
            "bedrock:InvokeModel",
            statements["CodeBuddyToolBedrockRuntime"]["Action"],
        )
        self.assertNotIn(
            "bedrock:Converse",
            statements["CodeBuddyToolBedrockRuntime"]["Action"],
        )
        self.assertIn(
            "arn:aws:bedrock:ap-northeast-2:123456789012:"
            "inference-profile/global.anthropic.claude-sonnet-4-6",
            statements["CodeBuddyToolBedrockRuntime"]["Resource"],
        )


class ActionGroupSelectionTests(unittest.TestCase):
    def test_find_action_group_returns_matching_id(self):
        groups = [{"actionGroupName": "CodeBuddyTools", "actionGroupId": "AG1"}]

        self.assertEqual(find_action_group(groups, "CodeBuddyTools"), "AG1")

    def test_find_action_group_returns_none_without_match(self):
        self.assertIsNone(find_action_group([], "CodeBuddyTools"))

    def test_disable_legacy_github_action_group(self):
        self.assertTrue(
            hasattr(setup_codebuddy_tools, "disable_legacy_action_groups")
        )
        updates = []

        class AgentClient:
            def list_agent_action_groups(self, **kwargs):
                return {
                    "actionGroupSummaries": [
                        {
                            "actionGroupName": "GitHubPRTools",
                            "actionGroupId": "OLD1",
                            "actionGroupState": "ENABLED",
                        },
                        {
                            "actionGroupName": "CodeBuddyTools",
                            "actionGroupId": "NEW1",
                            "actionGroupState": "ENABLED",
                        },
                    ]
                }

            def update_agent_action_group(self, **kwargs):
                updates.append(kwargs)

        setup_codebuddy_tools.disable_legacy_action_groups(
            AgentClient(),
            "AGENT1",
        )

        self.assertEqual(
            updates,
            [
                {
                    "agentId": "AGENT1",
                    "agentVersion": "DRAFT",
                    "actionGroupId": "OLD1",
                    "actionGroupName": "GitHubPRTools",
                    "actionGroupState": "DISABLED",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
