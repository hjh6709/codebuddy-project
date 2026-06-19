import unittest
from unittest.mock import patch

from botocore.exceptions import NoCredentialsError

from src.setup_agent import (
    build_agent_instruction,
    build_role_policies,
    find_named_resource,
    list_all,
    main,
    wait_for_status,
)


class BuildPoliciesTests(unittest.TestCase):
    def test_build_role_policies_scope_account_region_and_kb(self):
        trust, permissions = build_role_policies(
            account_id="123456789012",
            region="ap-northeast-2",
            model_id="global.anthropic.claude-sonnet-4-6",
            knowledge_base_id="Q1ZYRCWLIW",
        )

        trust_statement = trust["Statement"][0]
        self.assertEqual(
            trust_statement["Principal"]["Service"],
            "bedrock.amazonaws.com",
        )
        self.assertEqual(
            trust_statement["Condition"]["StringEquals"]["aws:SourceAccount"],
            "123456789012",
        )
        self.assertEqual(
            trust_statement["Condition"]["ArnLike"]["AWS:SourceArn"],
            "arn:aws:bedrock:ap-northeast-2:123456789012:agent/*",
        )

        statements = {item["Sid"]: item for item in permissions["Statement"]}
        self.assertEqual(
            statements["AgentKnowledgeBaseQuery"]["Resource"],
            "arn:aws:bedrock:ap-northeast-2:123456789012:"
            "knowledge-base/Q1ZYRCWLIW",
        )
        self.assertIn(
            "arn:aws:bedrock:ap-northeast-2:123456789012:"
            "inference-profile/global.anthropic.claude-sonnet-4-6",
            statements["AgentModelInvocationPermissions"]["Resource"],
        )
        self.assertIn(
            "bedrock:InvokeModelWithResponseStream",
            statements["AgentModelInvocationPermissions"]["Action"],
        )
        self.assertIn(
            "bedrock:Retrieve",
            statements["AgentKnowledgeBaseQuery"]["Action"],
        )


class AgentInstructionTests(unittest.TestCase):
    def test_build_agent_instruction_adds_github_tool_rules_once(self):
        instruction = build_agent_instruction(include_github_tool=True)

        self.assertEqual(instruction.count("## GitHub PR 도구"), 1)
        self.assertIn("get_github_pr", instruction)
        self.assertIn("owner, repo, pr_number", instruction)

    def test_build_agent_instruction_omits_tool_rules_by_default(self):
        instruction = build_agent_instruction()

        self.assertNotIn("## GitHub PR 도구", instruction)

    def test_build_agent_instruction_adds_codebuddy_tool_rules_once(self):
        instruction = build_agent_instruction(include_codebuddy_tools=True)

        self.assertEqual(instruction.count("## CodeBuddy 통합 Tool"), 1)
        self.assertIn("post_pr_comment", instruction)
        self.assertIn("send_slack_message", instruction)
        self.assertIn("실제 GitHub 댓글", instruction)


class ResourceSelectionTests(unittest.TestCase):
    def test_find_named_resource_returns_matching_id(self):
        items = [
            {"agentName": "Other", "agentId": "1"},
            {"agentName": "CodeBuddy-Reviewer", "agentId": "2"},
        ]

        result = find_named_resource(
            items,
            name_key="agentName",
            expected_name="CodeBuddy-Reviewer",
            id_key="agentId",
        )

        self.assertEqual(result, "2")

    def test_find_named_resource_returns_none_without_match(self):
        self.assertIsNone(
            find_named_resource(
                [],
                name_key="agentName",
                expected_name="CodeBuddy-Reviewer",
                id_key="agentId",
            )
        )

    def test_list_all_follows_next_tokens(self):
        calls = []

        def fetch(**kwargs):
            calls.append(kwargs)
            if "nextToken" not in kwargs:
                return {"items": [1], "nextToken": "NEXT"}
            return {"items": [2]}

        self.assertEqual(list_all(fetch, "items", maxResults=100), [1, 2])
        self.assertEqual(
            calls,
            [{"maxResults": 100}, {"maxResults": 100, "nextToken": "NEXT"}],
        )


class WaitForStatusTests(unittest.TestCase):
    def test_wait_for_status_returns_on_target(self):
        statuses = iter(
            [
                {"status": "PREPARING"},
                {"status": "PREPARED"},
            ]
        )

        result = wait_for_status(
            lambda: next(statuses),
            status_key="status",
            success_statuses={"PREPARED"},
            failure_statuses={"FAILED"},
            timeout=1,
            interval=0,
        )

        self.assertEqual(result["status"], "PREPARED")

    def test_wait_for_status_raises_on_failed(self):
        with self.assertRaisesRegex(RuntimeError, "FAILED.*bad role"):
            wait_for_status(
                lambda: {
                    "status": "FAILED",
                    "failureReasons": ["bad role"],
                },
                status_key="status",
                success_statuses={"PREPARED"},
                failure_statuses={"FAILED"},
                timeout=1,
                interval=0,
            )

    def test_wait_for_status_times_out(self):
        with self.assertRaisesRegex(TimeoutError, "PREPARING"):
            wait_for_status(
                lambda: {"status": "PREPARING"},
                status_key="status",
                success_statuses={"PREPARED"},
                failure_statuses={"FAILED"},
                timeout=0,
                interval=0,
            )


class MainErrorHandlingTests(unittest.TestCase):
    def test_main_reports_missing_aws_credentials(self):
        with patch(
            "src.setup_agent.deploy_agent",
            side_effect=NoCredentialsError(),
        ):
            with self.assertRaisesRegex(
                SystemExit,
                "AWS 자격 증명을 확인",
            ):
                main()


if __name__ == "__main__":
    unittest.main()
