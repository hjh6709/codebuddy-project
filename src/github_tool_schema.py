GITHUB_PR_OPENAPI_SCHEMA = {
    "openapi": "3.0.0",
    "info": {
        "title": "GitHub Pull Request Tools",
        "version": "1.0.0",
        "description": "Tools for reading public GitHub Pull Requests.",
    },
    "paths": {
        "/github-pr": {
            "get": {
                "operationId": "get_github_pr",
                "summary": "Get a public GitHub Pull Request",
                "description": (
                    "Retrieves public GitHub Pull Request details and file "
                    "changes. Use this operation when the user asks to fetch "
                    "a pull request, inspect its changes, summarize code "
                    "updates, or review a PR."
                ),
                "parameters": [
                    {
                        "name": "owner",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string", "minLength": 1},
                        "description": (
                            "GitHub repository owner or organization, "
                            "for example 'octocat'."
                        ),
                    },
                    {
                        "name": "repo",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string", "minLength": 1},
                        "description": (
                            "GitHub repository name, for example "
                            "'Spoon-Knife'."
                        ),
                    },
                    {
                        "name": "pr_number",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "integer", "minimum": 1},
                        "description": (
                            "Positive Pull Request number to retrieve."
                        ),
                    },
                ],
                "responses": {
                    "200": {
                        "description": (
                            "Pull Request metadata and changed files."
                        ),
                        "content": {
                            "application/json": {
                                "schema": {"type": "object"}
                            }
                        },
                    },
                    "400": {"description": "Invalid parameters."},
                    "404": {
                        "description": (
                            "Repository or Pull Request was not found."
                        )
                    },
                    "429": {
                        "description": "GitHub API rate limit exceeded."
                    },
                    "502": {"description": "GitHub API unavailable."},
                },
            }
        }
    },
}
