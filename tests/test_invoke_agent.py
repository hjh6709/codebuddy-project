import unittest

from src.invoke_agent import build_code_review_prompt, parse_completion


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


if __name__ == "__main__":
    unittest.main()
