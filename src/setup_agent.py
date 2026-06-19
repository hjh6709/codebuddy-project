import json
import time
from collections.abc import Callable
from typing import Any

import boto3
from botocore.exceptions import ClientError

try:
    from src.agent_config import AgentConfig, AgentState, load_config, save_state
except ModuleNotFoundError:
    from agent_config import AgentConfig, AgentState, load_config, save_state


AGENT_DESCRIPTION = "Knowledge Base 기반 코드 리뷰 및 보안 분석 에이전트"
KB_DESCRIPTION = (
    "코드 스타일 검사에는 언어별 스타일 가이드를, 보안 검사에는 OWASP 문서를 "
    "검색하여 근거로 사용합니다."
)
AGENT_INSTRUCTION = """당신은 시니어 개발자이자 코드 리뷰 전문가입니다.

## 역할
- Python, JavaScript, TypeScript, Java, Go 코드를 리뷰합니다.
- 버그, 보안 취약점, 스타일 위반을 찾습니다.

## 행동 규칙
1. 코드 또는 개발 규칙을 검토할 때 Knowledge Base를 먼저 참고합니다.
2. 스타일 검사는 해당 언어의 스타일 가이드를 근거로 합니다.
3. 보안 검사는 OWASP 문서를 근거로 취약점을 식별합니다.
4. 발견한 문제에는 심각도(높음/중간/낮음)를 표시합니다.
5. 수정 제안에는 가능한 경우 구체적인 코드 예시를 포함합니다.
6. 근거 문서를 찾지 못하면 "관련 문서를 찾을 수 없습니다"라고 알립니다.

## 출력 형식
### 높은 심각도
- [라인번호] 문제: 설명
  - 근거: 적용한 규칙 또는 취약점 유형
  - 수정 제안: 구체적인 해결 방법

### 중간 심각도
- 같은 형식을 사용합니다.

### 낮은 심각도
- 같은 형식을 사용합니다.

문제가 없으면 검사한 범위와 함께 "통과"라고 답변합니다."""


def build_role_policies(
    account_id: str,
    region: str,
    model_id: str,
    knowledge_base_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "bedrock.amazonaws.com"},
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {"aws:SourceAccount": account_id},
                    "ArnLike": {
                        "AWS:SourceArn": (
                            f"arn:aws:bedrock:{region}:{account_id}:agent/*"
                        )
                    },
                },
            }
        ],
    }

    model_family = model_id.removeprefix("global.")
    permissions_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AgentModelInvocationPermissions",
                "Effect": "Allow",
                "Action": [
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                    "bedrock:GetInferenceProfile",
                    "bedrock:GetFoundationModel",
                ],
                "Resource": [
                    (
                        f"arn:aws:bedrock:{region}:{account_id}:"
                        f"inference-profile/{model_id}"
                    ),
                    f"arn:aws:bedrock:*::foundation-model/{model_family}*",
                ],
            },
            {
                "Sid": "AgentKnowledgeBaseQuery",
                "Effect": "Allow",
                "Action": [
                    "bedrock:Retrieve",
                    "bedrock:RetrieveAndGenerate",
                ],
                "Resource": (
                    f"arn:aws:bedrock:{region}:{account_id}:"
                    f"knowledge-base/{knowledge_base_id}"
                ),
            },
        ],
    }
    return trust_policy, permissions_policy


def find_named_resource(
    items: list[dict[str, Any]],
    name_key: str,
    expected_name: str,
    id_key: str,
) -> str | None:
    for item in items:
        if item.get(name_key) == expected_name:
            return item.get(id_key)
    return None


def list_all(
    fetch: Callable[..., dict[str, Any]],
    result_key: str,
    **kwargs: Any,
) -> list[Any]:
    results = []
    next_token = None
    while True:
        request = dict(kwargs)
        if next_token:
            request["nextToken"] = next_token
        response = fetch(**request)
        results.extend(response.get(result_key, []))
        next_token = response.get("nextToken")
        if not next_token:
            return results


def wait_for_status(
    fetch: Callable[[], dict[str, Any]],
    status_key: str,
    success_statuses: set[str],
    failure_statuses: set[str],
    timeout: float = 120,
    interval: float = 2,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_result: dict[str, Any] = {}
    while True:
        last_result = fetch()
        status = last_result.get(status_key, "UNKNOWN")
        if status in success_statuses:
            return last_result
        if status in failure_statuses:
            reasons = last_result.get("failureReasons") or []
            recommended = last_result.get("recommendedActions") or []
            details = "; ".join([*reasons, *recommended]) or "상세 사유 없음"
            raise RuntimeError(f"AWS 리소스 상태가 {status}입니다: {details}")
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"AWS 리소스 준비 시간이 초과되었습니다. 마지막 상태: {status}"
            )
        time.sleep(interval)


def validate_knowledge_base(client: Any, knowledge_base_id: str) -> None:
    knowledge_base = client.get_knowledge_base(
        knowledgeBaseId=knowledge_base_id
    )["knowledgeBase"]
    if knowledge_base["status"] != "ACTIVE":
        raise RuntimeError(
            f"Knowledge Base {knowledge_base_id} 상태가 "
            f"{knowledge_base['status']}입니다."
        )
    print(
        f"✅ Knowledge Base 확인: {knowledge_base['name']} "
        f"({knowledge_base_id}, ACTIVE)"
    )


def ensure_agent_role(
    iam_client: Any,
    account_id: str,
    config: AgentConfig,
) -> str:
    trust_policy, permissions_policy = build_role_policies(
        account_id=account_id,
        region=config.region,
        model_id=config.model_id,
        knowledge_base_id=config.knowledge_base_id,
    )
    created = False
    try:
        role = iam_client.get_role(RoleName=config.role_name)["Role"]
        iam_client.update_assume_role_policy(
            RoleName=config.role_name,
            PolicyDocument=json.dumps(trust_policy),
        )
        print(f"♻️ Agent IAM 역할 재사용: {config.role_name}")
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "NoSuchEntity":
            raise
        role = iam_client.create_role(
            RoleName=config.role_name,
            Description="Service role for the CodeBuddy Bedrock Agent",
            AssumeRolePolicyDocument=json.dumps(trust_policy),
        )["Role"]
        created = True
        print(f"✅ Agent IAM 역할 생성: {config.role_name}")

    iam_client.put_role_policy(
        RoleName=config.role_name,
        PolicyName=config.policy_name,
        PolicyDocument=json.dumps(permissions_policy),
    )
    print(f"✅ IAM 인라인 정책 적용: {config.policy_name}")
    if created:
        print("⏳ IAM 역할 전파 대기 중...")
        time.sleep(10)
    return role["Arn"]


def ensure_agent(client: Any, config: AgentConfig, role_arn: str) -> str:
    agents = list_all(client.list_agents, "agentSummaries", maxResults=100)
    agent_id = find_named_resource(
        agents,
        name_key="agentName",
        expected_name=config.agent_name,
        id_key="agentId",
    )
    request = {
        "agentName": config.agent_name,
        "agentResourceRoleArn": role_arn,
        "instruction": AGENT_INSTRUCTION,
        "foundationModel": config.model_id,
        "description": AGENT_DESCRIPTION,
        "idleSessionTTLInSeconds": 1800,
    }

    if agent_id:
        client.update_agent(agentId=agent_id, **request)
        print(f"♻️ Agent 업데이트: {config.agent_name} ({agent_id})")
    else:
        agent_id = client.create_agent(**request)["agent"]["agentId"]
        print(f"✅ Agent 생성: {config.agent_name} ({agent_id})")

    wait_for_status(
        lambda: client.get_agent(agentId=agent_id)["agent"],
        status_key="agentStatus",
        success_statuses={"NOT_PREPARED", "PREPARED"},
        failure_statuses={"FAILED", "DELETING"},
    )
    return agent_id


def ensure_knowledge_base_association(
    client: Any,
    agent_id: str,
    config: AgentConfig,
) -> None:
    associations = list_all(
        client.list_agent_knowledge_bases,
        "agentKnowledgeBaseSummaries",
        agentId=agent_id,
        agentVersion="DRAFT",
        maxResults=100,
    )
    existing = next(
        (
            association
            for association in associations
            if association["knowledgeBaseId"] == config.knowledge_base_id
        ),
        None,
    )
    request = {
        "agentId": agent_id,
        "agentVersion": "DRAFT",
        "knowledgeBaseId": config.knowledge_base_id,
        "description": KB_DESCRIPTION,
        "knowledgeBaseState": "ENABLED",
    }
    if existing:
        client.update_agent_knowledge_base(**request)
        print(f"♻️ Knowledge Base 연결 갱신: {config.knowledge_base_id}")
    else:
        client.associate_agent_knowledge_base(**request)
        print(f"✅ Knowledge Base 연결: {config.knowledge_base_id}")


def prepare_agent(client: Any, agent_id: str) -> None:
    response = client.prepare_agent(agentId=agent_id)
    print(f"⏳ Agent Prepare 요청: {response['agentStatus']}")
    wait_for_status(
        lambda: client.get_agent(agentId=agent_id)["agent"],
        status_key="agentStatus",
        success_statuses={"PREPARED"},
        failure_statuses={"FAILED", "DELETING"},
        timeout=180,
    )
    print("✅ Agent PREPARED")


def ensure_alias(client: Any, agent_id: str, config: AgentConfig) -> str:
    aliases = list_all(
        client.list_agent_aliases,
        "agentAliasSummaries",
        agentId=agent_id,
        maxResults=100,
    )
    alias_id = find_named_resource(
        aliases,
        name_key="agentAliasName",
        expected_name=config.alias_name,
        id_key="agentAliasId",
    )
    if alias_id:
        client.update_agent_alias(
            agentId=agent_id,
            agentAliasId=alias_id,
            agentAliasName=config.alias_name,
            description="CodeBuddy 개발 및 시연용 Alias",
        )
        print(f"♻️ Agent Alias 업데이트: {config.alias_name} ({alias_id})")
    else:
        alias = client.create_agent_alias(
            agentId=agent_id,
            agentAliasName=config.alias_name,
            description="CodeBuddy 개발 및 시연용 Alias",
        )["agentAlias"]
        alias_id = alias["agentAliasId"]
        print(f"✅ Agent Alias 생성: {config.alias_name} ({alias_id})")

    wait_for_status(
        lambda: client.get_agent_alias(
            agentId=agent_id,
            agentAliasId=alias_id,
        )["agentAlias"],
        status_key="agentAliasStatus",
        success_statuses={"PREPARED"},
        failure_statuses={"FAILED", "DISSOCIATED"},
        timeout=180,
    )
    print("✅ Agent Alias PREPARED")
    return alias_id


def deploy_agent(config: AgentConfig | None = None) -> AgentState:
    config = config or load_config()
    session = boto3.Session(region_name=config.region)
    sts_client = session.client("sts")
    iam_client = session.client("iam")
    agent_client = session.client("bedrock-agent")

    account_id = sts_client.get_caller_identity()["Account"]
    print(f"🔐 AWS 계정: {account_id}, 리전: {config.region}")
    validate_knowledge_base(agent_client, config.knowledge_base_id)
    role_arn = ensure_agent_role(iam_client, account_id, config)
    agent_id = ensure_agent(agent_client, config, role_arn)
    ensure_knowledge_base_association(agent_client, agent_id, config)
    prepare_agent(agent_client, agent_id)
    alias_id = ensure_alias(agent_client, agent_id, config)

    state = AgentState(
        agent_id=agent_id,
        alias_id=alias_id,
        role_arn=role_arn,
    )
    save_state(config.state_path, state)
    print(f"💾 Agent 상태 저장: {config.state_path}")
    print(f"🎉 배포 완료 - Agent ID: {agent_id}, Alias ID: {alias_id}")
    return state


def main() -> None:
    try:
        deploy_agent()
    except ClientError as exc:
        error = exc.response.get("Error", {})
        raise SystemExit(
            f"❌ AWS 오류 [{error.get('Code', 'Unknown')}]: "
            f"{error.get('Message', str(exc))}"
        ) from exc
    except (RuntimeError, TimeoutError) as exc:
        raise SystemExit(f"❌ 배포 실패: {exc}") from exc


if __name__ == "__main__":
    main()
