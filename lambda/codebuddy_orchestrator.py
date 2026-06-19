import base64
import json
import logging
import os
from urllib.parse import urlparse

import boto3
from botocore.exceptions import BotoCoreError, ClientError


LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(
    getattr(
        logging,
        os.environ.get("LOG_LEVEL", "INFO").upper(),
        logging.INFO,
    )
)

ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "null")
_LAMBDA_CLIENT = None


class RequestError(Exception):
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def respond(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
            "Access-Control-Allow-Headers": "Content-Type,X-Api-Key",
            "Access-Control-Allow-Methods": "OPTIONS,POST",
        },
        "body": json.dumps(body, ensure_ascii=False),
    }


def parse_body(event):
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        try:
            raw = base64.b64decode(raw).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise RequestError(400, "Invalid base64 request body") from exc
    try:
        body = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RequestError(400, "Request body must be valid JSON") from exc
    if not isinstance(body, dict):
        raise RequestError(400, "Request body must be a JSON object")
    return body


def parse_pr_url(pr_url):
    parsed = urlparse(str(pr_url))
    parts = [part for part in parsed.path.split("/") if part]
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"github.com", "www.github.com"}
        or len(parts) != 4
        or parts[2] != "pull"
    ):
        raise RequestError(400, "A valid GitHub Pull Request URL is required")
    try:
        pr_number = int(parts[3])
    except ValueError as exc:
        raise RequestError(400, "Pull Request number must be an integer") from exc
    if pr_number <= 0:
        raise RequestError(400, "Pull Request number must be positive")
    return parts[0], parts[1], pr_number


def get_lambda_client():
    global _LAMBDA_CLIENT
    if _LAMBDA_CLIENT is None:
        _LAMBDA_CLIENT = boto3.client("lambda")
    return _LAMBDA_CLIENT


def dispatch_worker(payload):
    function_name = os.environ.get("WORKER_FUNCTION_NAME")
    if not function_name:
        raise RequestError(500, "WORKER_FUNCTION_NAME must be configured")
    try:
        get_lambda_client().invoke(
            FunctionName=function_name,
            InvocationType="Event",
            Payload=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )
    except (BotoCoreError, ClientError) as exc:
        LOGGER.error("Worker Lambda invocation failed: %s", type(exc).__name__)
        raise RequestError(503, "Worker dispatch failed, please retry") from exc


def handle_review(event):
    body = parse_body(event)
    if not body.get("pr_url"):
        raise RequestError(400, "Missing pr_url")
    owner, repo, pr_number = parse_pr_url(body["pr_url"])
    dispatch_worker(
        {
            "owner": owner,
            "repo": repo,
            "pr_number": pr_number,
            "notify_slack": bool(body.get("notify_slack", True)),
            "source": "review-api",
        }
    )
    return respond(
        202,
        {
            "message": "CodeBuddy review started",
            "status": "processing",
            "repository": f"{owner}/{repo}",
            "pr_number": pr_number,
        },
    )


def handler(event, context):
    try:
        method = str(event.get("httpMethod") or "").upper()
        resource = event.get("resource") or event.get("path") or ""
        if method == "OPTIONS":
            return respond(204, {})
        if method == "POST" and resource == "/review":
            return handle_review(event)
        raise RequestError(404, "Route not found")
    except RequestError as exc:
        return respond(exc.status_code, {"error": exc.message})
    except Exception:
        LOGGER.exception("Unexpected orchestrator error")
        return respond(500, {"error": "Internal server error"})
