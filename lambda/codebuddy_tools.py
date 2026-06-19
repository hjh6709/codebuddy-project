import ast
import json
import logging
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import boto3


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

GITHUB_API = "https://api.github.com"
DEFAULT_ACTION_GROUP = "CodeBuddyTools"
MAX_FILES = 20
MAX_PATCH_CHARS = 4_000
MAX_TOTAL_PATCH_CHARS = 30_000
BEDROCK_REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
BEDROCK_MODEL_ID = os.environ.get(
    "CODEBUDDY_TOOL_MODEL_ID",
    "global.anthropic.claude-sonnet-4-6",
)
REFACTOR_FOCUS_VALUES = {"readability", "performance", "maintainability"}


class RequestError(Exception):
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def extract_parameters(event, required=()):
    try:
        values = {
            item["name"]: item.get("value")
            for item in event.get("parameters", [])
        }
    except (AttributeError, KeyError, TypeError) as exc:
        raise RequestError(400, "Invalid Bedrock Agent parameter format") from exc

    missing = [name for name in required if not values.get(name)]
    if missing:
        raise RequestError(
            400,
            f"Missing required parameters: {', '.join(missing)}",
        )
    return values


def positive_int(value, name):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise RequestError(400, f"{name} must be an integer") from exc
    if parsed <= 0:
        raise RequestError(400, f"{name} must be positive")
    return parsed


def build_response(event, status_code, body):
    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": event.get("actionGroup", DEFAULT_ACTION_GROUP),
            "apiPath": event.get("apiPath", ""),
            "httpMethod": event.get("httpMethod", ""),
            "httpStatusCode": status_code,
            "responseBody": {
                "application/json": {
                    "body": json.dumps(body, ensure_ascii=False)
                }
            },
        },
    }


def json_request(url, method="GET", headers=None, body=None):
    data = None
    request_headers = dict(headers or {})
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")

    request = Request(
        url,
        data=data,
        headers=request_headers,
        method=method,
    )
    with urlopen(request, timeout=15) as response:
        payload = response.read().decode("utf-8")
        if not payload:
            return {}
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return payload


def route_operation(event):
    method = str(event.get("httpMethod", "")).upper()
    path = event.get("apiPath", "")
    routes = {
        ("GET", "/github-pr"): "get_github_pr",
        ("GET", "/github/pr"): "get_github_pr",
        ("POST", "/github/pr/comment"): "post_pr_comment",
        ("POST", "/slack/message"): "send_slack_message",
        ("POST", "/complexity"): "analyze_complexity",
        ("POST", "/unittest"): "generate_unit_test",
        ("POST", "/refactor"): "suggest_refactor",
    }
    operation = routes.get((method, path))
    if operation is None:
        raise RequestError(
            400,
            f"지원하지 않는 Tool 요청입니다: {method} {path}",
        )
    return operation


def github_headers(token=None):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "CodeBuddy-Bedrock-Agent",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def normalize_pr(
    pr,
    files,
    max_files=MAX_FILES,
    max_patch_chars=MAX_PATCH_CHARS,
    max_total_patch_chars=MAX_TOTAL_PATCH_CHARS,
):
    normalized_files = []
    total_patch_chars = 0
    patches_truncated = False

    for item in files[:max_files]:
        patch = item.get("patch") or ""
        remaining = max(0, max_total_patch_chars - total_patch_chars)
        allowed = min(max_patch_chars, remaining)
        limited_patch = patch[:allowed]
        if len(limited_patch) < len(patch):
            patches_truncated = True
        total_patch_chars += len(limited_patch)
        normalized_files.append(
            {
                "filename": item.get("filename", ""),
                "status": item.get("status", ""),
                "additions": item.get("additions", 0),
                "deletions": item.get("deletions", 0),
                "changes": item.get("changes", 0),
                "patch": limited_patch,
            }
        )

    files_truncated = (
        len(files) > max_files
        or int(pr.get("changed_files") or 0) > len(normalized_files)
    )
    if len(files) > len(normalized_files):
        patches_truncated = patches_truncated or any(
            item.get("patch") for item in files[len(normalized_files) :]
        )

    return {
        "title": pr.get("title", ""),
        "body": pr.get("body") or "",
        "state": pr.get("state", ""),
        "author": (pr.get("user") or {}).get("login", ""),
        "created_at": pr.get("created_at", ""),
        "updated_at": pr.get("updated_at", ""),
        "changed_files": pr.get("changed_files", 0),
        "additions": pr.get("additions", 0),
        "deletions": pr.get("deletions", 0),
        "html_url": pr.get("html_url", ""),
        "files": normalized_files,
        "files_truncated": files_truncated,
        "patches_truncated": patches_truncated,
    }


def get_github_pr(event):
    values = extract_parameters(event, ("owner", "repo", "pr_number"))
    owner = str(values["owner"])
    repo = str(values["repo"])
    pr_number = positive_int(values["pr_number"], "pr_number")
    safe_owner = quote(owner, safe="")
    safe_repo = quote(repo, safe="")
    base_path = f"/repos/{safe_owner}/{safe_repo}/pulls/{pr_number}"

    pr = json_request(f"{GITHUB_API}{base_path}", headers=github_headers())
    files = json_request(
        f"{GITHUB_API}{base_path}/files?per_page=100&page=1",
        headers=github_headers(),
    )
    return normalize_pr(pr, files)


def post_pr_comment(event):
    values = extract_parameters(
        event,
        ("owner", "repo", "pr_number", "comment"),
    )
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RequestError(
            500,
            "GITHUB_TOKEN 환경변수가 설정되어 있지 않아 PR 댓글을 등록할 수 없습니다.",
        )

    owner = str(values["owner"])
    repo = str(values["repo"])
    pr_number = positive_int(values["pr_number"], "pr_number")
    comment = str(values["comment"])
    safe_owner = quote(owner, safe="")
    safe_repo = quote(repo, safe="")
    url = (
        f"{GITHUB_API}/repos/{safe_owner}/{safe_repo}"
        f"/issues/{pr_number}/comments"
    )
    created = json_request(
        url,
        method="POST",
        headers=github_headers(token),
        body={"body": comment},
    )
    return {
        "success": True,
        "message": f"Comment added to PR #{pr_number}",
        "comment_id": created.get("id"),
        "html_url": created.get("html_url"),
        "body": created.get("body", comment),
    }


def send_slack_message(event):
    values = extract_parameters(event, ("message",))
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        raise RequestError(
            500,
            "SLACK_WEBHOOK_URL 환경변수가 설정되어 있지 않아 Slack 메시지를 전송할 수 없습니다.",
        )

    payload = {"text": str(values["message"])}
    if values.get("channel"):
        payload["channel"] = str(values["channel"])

    result = json_request(
        webhook_url,
        method="POST",
        headers={"User-Agent": "CodeBuddy-Bedrock-Agent"},
        body=payload,
    )
    return {
        "success": True,
        "message": "Slack message sent",
        "slack_response": result,
    }


def complexity_rank(complexity):
    if complexity <= 5:
        return "A"
    if complexity <= 10:
        return "B"
    if complexity <= 20:
        return "C"
    return "D"


def complexity_action(rank):
    return {
        "A": "양호",
        "B": "보통, 필요 시 리팩토링 검토",
        "C": "복잡, 리팩토링 고려",
        "D": "매우 복잡, 즉시 리팩토링 권장",
    }[rank]


def cyclomatic_complexity(node):
    complexity = 1
    for child in ast.walk(node):
        if isinstance(
            child,
            (
                ast.If,
                ast.For,
                ast.AsyncFor,
                ast.While,
                ast.IfExp,
                ast.ExceptHandler,
            ),
        ):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += max(1, len(child.values) - 1)
        elif isinstance(child, ast.Try):
            complexity += len(child.handlers)
    return complexity


def analyze_complexity(code):
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise RequestError(400, f"Python 코드 구문을 분석할 수 없습니다: {exc}")

    details = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            score = cyclomatic_complexity(node)
            rank = complexity_rank(score)
            details.append(
                {
                    "name": node.name,
                    "lineno": node.lineno,
                    "complexity": score,
                    "rank": rank,
                    "action": complexity_action(rank),
                }
            )

    average = (
        sum(item["complexity"] for item in details) / len(details)
        if details
        else 0
    )
    return {
        "success": True,
        "summary": {
            "total_functions": len(details),
            "average_complexity": round(average, 2),
            "max_complexity": max(
                (item["complexity"] for item in details),
                default=0,
            ),
            "functions_above_threshold": [
                item for item in details if item["complexity"] > 10
            ],
        },
        "details": sorted(details, key=lambda item: item["lineno"]),
    }


def analyze_complexity_tool(event):
    values = extract_parameters(event, ("code",))
    return analyze_complexity(str(values["code"]))


def bedrock_client():
    return boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)


def converse_text(prompt, temperature, max_tokens):
    response = bedrock_client().converse(
        modelId=BEDROCK_MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={
            "temperature": temperature,
            "maxTokens": max_tokens,
        },
    )
    return response["output"]["message"]["content"][0]["text"]


def build_unit_test_prompt(code, function_name=None):
    target = (
        f"\n테스트 대상 함수명: {function_name}"
        if function_name
        else ""
    )
    return f"""당신은 테스트 엔지니어입니다. 다음 Python 코드에 대한 pytest 단위 테스트 코드를 작성해주세요.{target}

함수 코드:
```python
{code}
```

요구사항:
- 정상적인 입력에 대한 테스트를 포함하세요.
- 경계값 테스트를 포함하세요. 예: 빈 리스트, 0, None 등.
- 예외 상황 테스트를 포함하세요. 예: 잘못된 입력 타입 등.
- pytest 스타일을 사용하세요. assert와 pytest.raises를 활용하세요.
- 테스트 함수명은 test_<원본함수명>_<시나리오> 형식을 사용하세요.
- 테스트 코드만 출력하세요. 설명 문장은 출력하지 마세요.
"""


def generate_unit_test(event):
    values = extract_parameters(event, ("code",))
    code = str(values["code"])
    function_name = values.get("function_name")
    prompt = build_unit_test_prompt(code, function_name)
    test_code = converse_text(prompt, temperature=0.2, max_tokens=2_000)
    return {
        "success": True,
        "test_code": test_code,
    }


def build_refactor_prompt(code, focus):
    return f"""당신은 시니어 개발자입니다. 다음 Python 코드를 리팩토링하여 더 나은 구조를 제안해주세요.

코드:
```python
{code}
```

리팩토링 목표: {focus}

제안 형식:
1. 문제점 분석
2. 개선된 코드
3. 변경 이유

개선된 코드는 가능한 한 기존 동작을 유지해야 합니다.
Markdown으로 읽기 쉽게 답변하세요.
"""


def suggest_refactor(event):
    values = extract_parameters(event, ("code",))
    code = str(values["code"])
    focus = str(values.get("focus") or "maintainability")
    if focus not in REFACTOR_FOCUS_VALUES:
        raise RequestError(
            400,
            "focus는 readability, performance, maintainability 중 하나여야 합니다.",
        )
    prompt = build_refactor_prompt(code, focus)
    suggestion = converse_text(prompt, temperature=0.3, max_tokens=3_000)
    return {
        "success": True,
        "focus": focus,
        "suggestion": suggestion,
    }


def map_http_error(error):
    headers = error.headers or {}
    remaining = headers.get("x-ratelimit-remaining")
    reset = headers.get("x-ratelimit-reset", "unknown")
    if error.code == 401:
        return RequestError(401, "GitHub 인증에 실패했습니다.")
    if error.code == 403 and remaining == "0":
        return RequestError(
            429,
            f"GitHub API 요청 한도를 초과했습니다. reset={reset}",
        )
    if error.code == 404:
        return RequestError(
            404,
            "GitHub 저장소 또는 Pull Request를 찾을 수 없습니다.",
        )
    if error.code == 422:
        return RequestError(422, "GitHub 요청 검증에 실패했습니다.")
    return RequestError(
        502,
        f"외부 API가 오류 상태 {error.code}를 반환했습니다.",
    )


def handler(event, context):
    started = time.monotonic()
    try:
        operation = route_operation(event)
        handlers = {
            "get_github_pr": get_github_pr,
            "post_pr_comment": post_pr_comment,
            "send_slack_message": send_slack_message,
            "analyze_complexity": analyze_complexity_tool,
            "generate_unit_test": generate_unit_test,
            "suggest_refactor": suggest_refactor,
        }
        if operation not in handlers:
            raise RequestError(501, f"{operation} Tool은 아직 구현되지 않았습니다.")
        result = handlers[operation](event)
        LOGGER.info(
            "CodeBuddy Tool completed operation=%s elapsed_ms=%s",
            operation,
            int((time.monotonic() - started) * 1000),
        )
        return build_response(event, 200, result)
    except RequestError as exc:
        LOGGER.warning("CodeBuddy Tool request failed status=%s", exc.status_code)
        return build_response(event, exc.status_code, {"error": exc.message})
    except HTTPError as exc:
        mapped = map_http_error(exc)
        LOGGER.warning("External API error status=%s", exc.code)
        return build_response(
            event,
            mapped.status_code,
            {"error": mapped.message},
        )
    except URLError:
        LOGGER.exception("External API network error")
        return build_response(
            event,
            502,
            {"error": "외부 API에 연결할 수 없습니다."},
        )
    except Exception:
        LOGGER.exception("Unexpected CodeBuddy Tool error")
        return build_response(
            event,
            500,
            {"error": "Tool 처리 중 예상하지 못한 오류가 발생했습니다."},
        )
