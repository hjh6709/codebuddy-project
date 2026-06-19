import unittest

from src.codebuddy_tool_schema import CODEBUDDY_TOOLS_OPENAPI_SCHEMA


class CodeBuddyToolSchemaTests(unittest.TestCase):
    def test_schema_defines_chapter7_agent_tool_operations(self):
        paths = CODEBUDDY_TOOLS_OPENAPI_SCHEMA["paths"]

        operations = {
            paths["/github-pr"]["get"]["operationId"],
            paths["/github/pr/comment"]["post"]["operationId"],
            paths["/slack/message"]["post"]["operationId"],
        }

        self.assertEqual(
            operations,
            {
                "get_github_pr",
                "post_pr_comment",
                "send_slack_message",
            },
        )

    def test_comment_and_slack_tools_describe_real_external_writes(self):
        paths = CODEBUDDY_TOOLS_OPENAPI_SCHEMA["paths"]

        comment_description = paths["/github/pr/comment"]["post"]["description"]
        slack_description = paths["/slack/message"]["post"]["description"]

        self.assertIn("actual GitHub Pull Request comment", comment_description)
        self.assertIn("actual Slack message", slack_description)

if __name__ == "__main__":
    unittest.main()
