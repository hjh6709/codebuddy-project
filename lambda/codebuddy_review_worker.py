import logging
import os
import uuid

import boto3
from botocore.config import Config


LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)


class RequestError(Exception):
    pass


def build_review_prompt(owner, repo, pr_number, notify_slack=True):
    slack_instruction = (
        "리뷰 완료 후 핵심 결과와 PR URL을 Slack에도 반드시 알려주세요."
        if notify_slack
        else "Slack 알림은 보내지 마세요."
    )
    return f"""다음 GitHub Pull Request를 자동 리뷰해주세요.

저장소: {owner}/{repo}
PR 번호: {pr_number}

요구사항:
- 버그, 보안, 스타일, 복잡도, 테스트 누락을 검토합니다.
- 결과를 읽기 쉬운 Markdown으로 PR 댓글에 실제 등록합니다.
- Tool 결과가 잘렸다면 전체 리뷰라고 단정하지 않고 제한을 표시합니다.
- {slack_instruction}
"""


def validate_job(event):
    missing = [
        name
        for name in ("owner", "repo", "pr_number")
        if not event.get(name)
    ]
    if missing:
        raise RequestError(
            f"Missing review job fields: {', '.join(missing)}"
        )
    try:
        pr_number = int(event["pr_number"])
    except (TypeError, ValueError) as exc:
        raise RequestError("pr_number must be an integer") from exc
    if pr_number <= 0:
        raise RequestError("pr_number must be positive")
    return str(event["owner"]), str(event["repo"]), pr_number


def collect_completion(events):
    chunks = []
    for item in events:
        if "chunk" in item:
            chunks.append(item["chunk"]["bytes"].decode("utf-8"))
    return "".join(chunks)


def handler(event, context):
    agent_id = os.environ.get("AGENT_ID")
    alias_id = os.environ.get("ALIAS_ID")
    if not agent_id or not alias_id:
        raise RequestError("AGENT_ID and ALIAS_ID must be configured")

    owner, repo, pr_number = validate_job(event)
    runtime = boto3.client(
        "bedrock-agent-runtime",
        config=Config(
            connect_timeout=10,
            read_timeout=280,
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )
    response = runtime.invoke_agent(
        agentId=agent_id,
        agentAliasId=alias_id,
        sessionId=event.get("session_id") or str(uuid.uuid4()),
        inputText=build_review_prompt(
            owner,
            repo,
            pr_number,
            bool(event.get("notify_slack", True)),
        ),
        enableTrace=False,
    )
    result = collect_completion(response["completion"])
    LOGGER.info(
        "CodeBuddy review completed repo=%s/%s pr=%s source=%s",
        owner,
        repo,
        pr_number,
        event.get("source", "unknown"),
    )
    return {"status": "completed", "result": result}
