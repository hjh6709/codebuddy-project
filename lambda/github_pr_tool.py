import json
import logging
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

GITHUB_API = "https://api.github.com"
MAX_FILES = 20
MAX_PATCH_CHARS = 4_000
MAX_TOTAL_PATCH_CHARS = 30_000


class RequestError(Exception):
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def extract_parameters(event):
    try:
        values = {
            item["name"]: item.get("value")
            for item in event.get("parameters", [])
        }
    except (AttributeError, KeyError, TypeError) as exc:
        raise RequestError(400, "Invalid Bedrock Agent parameter format") from exc

    required = ("owner", "repo", "pr_number")
    missing = [name for name in required if not values.get(name)]
    if missing:
        raise RequestError(
            400,
            f"Missing required parameters: {', '.join(missing)}",
        )

    try:
        pr_number = int(values["pr_number"])
    except (TypeError, ValueError) as exc:
        raise RequestError(400, "pr_number must be an integer") from exc
    if pr_number <= 0:
        raise RequestError(400, "pr_number must be positive")

    return str(values["owner"]), str(values["repo"]), pr_number


def build_response(event, status_code, body):
    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": event.get("actionGroup", "GitHubPRTools"),
            "apiPath": event.get("apiPath", "/github-pr"),
            "httpMethod": event.get("httpMethod", "GET"),
            "httpStatusCode": status_code,
            "responseBody": {
                "application/json": {
                    "body": json.dumps(body, ensure_ascii=False)
                }
            },
        },
    }


def github_get(path):
    request = Request(
        f"{GITHUB_API}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "CodeBuddy-Bedrock-Agent",
        },
        method="GET",
    )
    with urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


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


def map_github_error(error):
    headers = error.headers or {}
    remaining = headers.get("x-ratelimit-remaining")
    reset = headers.get("x-ratelimit-reset", "unknown")

    if error.code == 404:
        return RequestError(
            404,
            "공개 저장소 또는 Pull Request를 찾을 수 없습니다.",
        )
    if error.code == 429 or (error.code == 403 and remaining == "0"):
        return RequestError(
            429,
            f"GitHub API 요청 한도를 초과했습니다. reset={reset}",
        )
    return RequestError(
        502,
        f"GitHub API가 오류 상태 {error.code}를 반환했습니다.",
    )


def handler(event, context):
    started = time.monotonic()
    try:
        owner, repo, pr_number = extract_parameters(event)
        safe_owner = quote(owner, safe="")
        safe_repo = quote(repo, safe="")
        base_path = f"/repos/{safe_owner}/{safe_repo}/pulls/{pr_number}"

        LOGGER.info(
            "Fetching public GitHub PR owner=%s repo=%s pr=%s",
            owner,
            repo,
            pr_number,
        )
        pr = github_get(base_path)
        files = github_get(f"{base_path}/files?per_page=100&page=1")
        result = normalize_pr(pr, files)
        LOGGER.info(
            "GitHub PR fetched status=200 files=%s elapsed_ms=%s",
            len(result["files"]),
            int((time.monotonic() - started) * 1000),
        )
        return build_response(event, 200, result)
    except RequestError as exc:
        LOGGER.warning("Request rejected status=%s", exc.status_code)
        return build_response(event, exc.status_code, {"error": exc.message})
    except HTTPError as exc:
        mapped = map_github_error(exc)
        LOGGER.warning("GitHub API error status=%s", exc.code)
        return build_response(
            event,
            mapped.status_code,
            {"error": mapped.message},
        )
    except URLError:
        LOGGER.exception("GitHub API network error")
        return build_response(
            event,
            502,
            {"error": "GitHub API에 연결할 수 없습니다."},
        )
    except Exception:
        LOGGER.exception("Unexpected GitHub PR Tool error")
        return build_response(
            event,
            500,
            {"error": "GitHub PR 처리 중 예상하지 못한 오류가 발생했습니다."},
        )
