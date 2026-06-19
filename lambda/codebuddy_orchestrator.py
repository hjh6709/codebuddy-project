import base64
import hashlib
import hmac
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

ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "")
_LAMBDA_CLIENT = None
_SECRETS_CLIENT = None
_WEBHOOK_SECRET = None
SUPPORTED_PR_ACTIONS = {"opened", "reopened", "synchronize"}


class RequestError(Exception):
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def respond(status_code, body):
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Headers": "Content-Type,X-Api-Key",
        "Access-Control-Allow-Methods": "OPTIONS,POST",
    }
    if ALLOWED_ORIGIN:
        headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(body, ensure_ascii=False),
    }


def decode_body(event):
    raw = event.get("body")
    if raw is None:
        return b"{}"
    if event.get("isBase64Encoded"):
        try:
            return base64.b64decode(raw, validate=True)
        except (ValueError, TypeError) as exc:
            raise RequestError(400, "Invalid base64 request body") from exc
    if not isinstance(raw, str):
        raise RequestError(400, "Request body must be text")
    return raw.encode("utf-8")


def parse_body(event):
    return parse_body_bytes(decode_body(event))


def parse_body_bytes(raw):
    try:
        body = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
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


def get_secrets_client():
    global _SECRETS_CLIENT
    if _SECRETS_CLIENT is None:
        _SECRETS_CLIENT = boto3.client("secretsmanager")
    return _SECRETS_CLIENT


def get_webhook_secret():
    global _WEBHOOK_SECRET
    if _WEBHOOK_SECRET is not None:
        return _WEBHOOK_SECRET
    secret_arn = os.environ.get("WEBHOOK_SECRET_ARN")
    if not secret_arn:
        raise RequestError(500, "WEBHOOK_SECRET_ARN must be configured")
    try:
        response = get_secrets_client().get_secret_value(
            SecretId=secret_arn
        )
    except (BotoCoreError, ClientError) as exc:
        LOGGER.error(
            "Webhook secret lookup failed: %s",
            type(exc).__name__,
        )
        raise RequestError(
            503,
            "Webhook verification is temporarily unavailable",
        ) from exc
    secret = response.get("SecretString")
    if not secret:
        raise RequestError(500, "Webhook secret is unavailable")
    _WEBHOOK_SECRET = secret
    return secret


def dispatch_worker(payload):
    function_name = os.environ.get("WORKER_FUNCTION_NAME")
    if not function_name:
        raise RequestError(500, "WORKER_FUNCTION_NAME must be configured")
    try:
        response = get_lambda_client().invoke(
            FunctionName=function_name,
            InvocationType="Event",
            Payload=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )
    except (BotoCoreError, ClientError) as exc:
        LOGGER.error("Worker Lambda invocation failed: %s", type(exc).__name__)
        raise RequestError(503, "Worker dispatch failed, please retry") from exc
    if response.get("StatusCode") != 202:
        LOGGER.error(
            "Worker Lambda rejected async invocation: status=%s",
            response.get("StatusCode"),
        )
        raise RequestError(503, "Worker dispatch failed, please retry")


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


def get_header(event, name):
    headers = event.get("headers") or {}
    expected = name.lower()
    for key, value in headers.items():
        if str(key).lower() == expected:
            return value
    return None


def verify_github_signature(event, raw_body):
    signature = str(
        get_header(event, "X-Hub-Signature-256") or ""
    )
    expected = "sha256=" + hmac.new(
        get_webhook_secret().encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        LOGGER.warning("Rejected GitHub webhook with invalid signature")
        raise RequestError(401, "Invalid GitHub webhook signature")


def handle_github_webhook(event):
    raw_body = decode_body(event)
    verify_github_signature(event, raw_body)
    event_name = str(get_header(event, "X-GitHub-Event") or "")
    body = parse_body_bytes(raw_body)
    if event_name == "ping":
        return respond(200, {"message": "pong"})
    if event_name != "pull_request":
        return respond(202, {"status": "ignored"})

    action = body.get("action")
    if action not in SUPPORTED_PR_ACTIONS:
        return respond(202, {"status": "ignored", "action": action})
    try:
        owner = body["repository"]["owner"]["login"]
        repo = body["repository"]["name"]
        pr_number = body["pull_request"]["number"]
    except (KeyError, TypeError) as exc:
        raise RequestError(400, "Invalid pull_request payload") from exc
    dispatch_worker(
        {
            "owner": owner,
            "repo": repo,
            "pr_number": pr_number,
            "notify_slack": True,
            "source": "github-webhook",
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
        if method == "POST" and resource == "/webhook/github":
            return handle_github_webhook(event)
        raise RequestError(404, "Route not found")
    except RequestError as exc:
        return respond(exc.status_code, {"error": exc.message})
    except Exception:
        LOGGER.exception("Unexpected orchestrator error")
        return respond(500, {"error": "Internal server error"})
