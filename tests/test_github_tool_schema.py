import unittest

from src.github_tool_schema import GITHUB_PR_OPENAPI_SCHEMA


class GitHubToolSchemaTests(unittest.TestCase):
    def test_schema_defines_get_github_pr_operation(self):
        operation = GITHUB_PR_OPENAPI_SCHEMA["paths"]["/github-pr"]["get"]

        self.assertEqual(operation["operationId"], "get_github_pr")
        parameters = {
            item["name"]: item for item in operation["parameters"]
        }
        self.assertEqual(set(parameters), {"owner", "repo", "pr_number"})
        self.assertTrue(all(item["required"] for item in parameters.values()))

    def test_schema_descriptions_explain_when_to_use_tool(self):
        operation = GITHUB_PR_OPENAPI_SCHEMA["paths"]["/github-pr"]["get"]
        description = operation["description"].lower()

        self.assertIn("pull request", description)
        self.assertIn("review", description)
        self.assertIn("changes", description)

    def test_pr_number_is_an_integer_query_parameter(self):
        operation = GITHUB_PR_OPENAPI_SCHEMA["paths"]["/github-pr"]["get"]
        pr_number = next(
            item
            for item in operation["parameters"]
            if item["name"] == "pr_number"
        )

        self.assertEqual(pr_number["in"], "query")
        self.assertEqual(pr_number["schema"]["type"], "integer")
        self.assertEqual(pr_number["schema"]["minimum"], 1)


if __name__ == "__main__":
    unittest.main()
