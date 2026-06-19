import unittest
from unittest.mock import patch

from botocore.exceptions import NoCredentialsError

from src.invoke_agent import build_code_review_prompt, main, parse_completion


class CompletionParserTests(unittest.TestCase):
    def test_parse_completion_collects_chunks_and_traces(self):
        events = [
            {
                "trace": {
                    "trace": {
                        "orchestrationTrace": {
                            "rationale": {"text": "search"}
                        }
                    }
                }
            },
            {"chunk": {"bytes": "안녕 ".encode()}},
            {"chunk": {"bytes": "CodeBuddy".encode()}},
        ]

        text, traces = parse_completion(events)

        self.assertEqual(text, "안녕 CodeBuddy")
        self.assertEqual(
            traces,
            [
                {
                    "orchestrationTrace": {
                        "rationale": {"text": "search"}
                    }
                }
            ],
        )

    def test_parse_completion_ignores_unknown_events(self):
        text, traces = parse_completion([{"returnControl": {"id": "1"}}])

        self.assertEqual(text, "")
        self.assertEqual(traces, [])


class PromptTests(unittest.TestCase):
    def test_build_code_review_prompt_wraps_code_and_requirements(self):
        prompt = build_code_review_prompt("def add(a, b): return a + b")

        self.assertIn("Knowledge Base", prompt)
        self.assertIn("```python", prompt)
        self.assertIn("def add(a, b)", prompt)
        self.assertIn("보안 취약점", prompt)


class MainErrorHandlingTests(unittest.TestCase):
    def test_main_reports_missing_aws_credentials(self):
        with (
            patch("src.invoke_agent.parse_args") as parse_args,
            patch(
                "src.invoke_agent.invoke",
                side_effect=NoCredentialsError(),
            ),
        ):
            parse_args.return_value.code_review = False
            parse_args.return_value.prompt = "hello"
            parse_args.return_value.session_id = None
            parse_args.return_value.trace = False

            with self.assertRaisesRegex(
                SystemExit,
                "AWS 자격 증명을 확인",
            ):
                main()


if __name__ == "__main__":
    unittest.main()
