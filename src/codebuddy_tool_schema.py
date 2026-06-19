CODEBUDDY_TOOLS_OPENAPI_SCHEMA = {
    "openapi": "3.0.0",
    "info": {
        "title": "CodeBuddy Agent Tools",
        "version": "2.0.0",
        "description": (
            "Tools for GitHub Pull Request review workflows, Slack "
            "notifications."
        ),
    },
    "paths": {
        "/github-pr": {
            "get": {
                "operationId": "get_github_pr",
                "summary": "Get a public GitHub Pull Request",
                "description": (
                    "Retrieves public GitHub Pull Request details and changed "
                    "files. Use this when the user asks to fetch, summarize, "
                    "or review a PR."
                ),
                "parameters": [
                    {
                        "name": "owner",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string", "minLength": 1},
                        "description": "Repository owner or organization.",
                    },
                    {
                        "name": "repo",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string", "minLength": 1},
                        "description": "Repository name.",
                    },
                    {
                        "name": "pr_number",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "integer", "minimum": 1},
                        "description": "Positive Pull Request number.",
                    },
                ],
                "responses": {
                    "200": {"description": "Pull Request details."},
                    "404": {"description": "Repository or PR not found."},
                },
            }
        },
        "/github/pr/comment": {
            "post": {
                "operationId": "post_pr_comment",
                "summary": "Post a comment to a GitHub Pull Request",
                "description": (
                    "Creates an actual GitHub Pull Request comment. Use this "
                    "only when the user asks to leave review feedback, an "
                    "approval note, generated tests, or analysis results on "
                    "a specific PR."
                ),
                "parameters": [
                    {
                        "name": "owner",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string", "minLength": 1},
                        "description": "Repository owner or organization.",
                    },
                    {
                        "name": "repo",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string", "minLength": 1},
                        "description": "Repository name.",
                    },
                    {
                        "name": "pr_number",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "integer", "minimum": 1},
                        "description": "Positive Pull Request number.",
                    },
                    {
                        "name": "comment",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string", "minLength": 1},
                        "description": "Markdown comment body to post.",
                    },
                ],
                "responses": {
                    "200": {"description": "Comment created successfully."},
                    "401": {"description": "GitHub authentication failed."},
                },
            }
        },
        "/slack/message": {
            "post": {
                "operationId": "send_slack_message",
                "summary": "Send a Slack notification",
                "description": (
                    "Sends an actual Slack message through an Incoming "
                    "Webhook. Use this when the user asks to notify a Slack "
                    "channel about review or analysis results."
                ),
                "parameters": [
                    {
                        "name": "message",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string", "minLength": 1},
                        "description": "Slack message text.",
                    },
                    {
                        "name": "channel",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string"},
                        "description": "Optional Slack channel hint.",
                    },
                ],
                "responses": {
                    "200": {"description": "Slack message sent."},
                },
            }
        },
    },
}
