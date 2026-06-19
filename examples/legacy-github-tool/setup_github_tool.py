"""Chapter 6 legacy example: deploy the standalone GitHub PR tool."""

import io
import json
import os
import time
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

try:
    from src.agent_config import (
        AgentConfig,
        AgentState,
        load_config,
        load_state,
        save_state,
        update_tool_state,
    )
    from src.github_tool_schema import GITHUB_PR_OPENAPI_SCHEMA
    from src.setup_agent import (
        AGENT_DESCRIPTION,
        build_agent_instruction,
        ensure_alias,
        list_all,
        prepare_agent,
        wait_for_status,
    )
except ModuleNotFoundError:
    from agent_config import (
        AgentConfig,
        AgentState,
        load_config,
        load_state,
        save_state,
        update_tool_state,
    )
    from github_tool_schema import GITHUB_PR_OPENAPI_SCHEMA
    from setup_agent import (
        AGENT_DESCRIPTION,
        build_agent_instruction,
        ensure_alias,
        list_all,
        prepare_agent,
        wait_for_status,
    )


ROOT = Path(__file__).resolve().parents[1]
LAMBDA_SOURCE = ROOT / "lambda" / "github_pr_tool.py"
LAMBDA_ROLE_NAME = "CodeBuddy-Lambda-Role"
LAMBDA_FUNCTION_NAME = "codebuddy-github-pr"
LAMBDA_POLICY_ARN = (
    "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
)
ACTION_GROUP_NAME = "GitHubPRTools"
LAMBDA_PERMISSION_ID = "AllowBedrockAgentInvoke"


def build_lambda_trust_policy() -> dict[str, Any]:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "lambda.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }


def build_lambda_zip(source_path: Path) -> bytes:
    if not source_path.exists():
        raise FileNotFoundError(f"Lambda 소스 파일이 없습니다: {source_path}")
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("github_pr_tool.py", source_path.read_bytes())
    return buffer.getvalue()


def find_action_group(
    groups: list[dict[str, Any]],
    expected_name: str,
) -> str | None:
    for group in groups:
        if group.get("actionGroupName") == expected_name:
            return group.get("actionGroupId")
    return None


def ensure_lambda_role(iam_client: Any) -> str:
    trust_policy = build_lambda_trust_policy()
    created = False
    try:
        role = iam_client.get_role(RoleName=LAMBDA_ROLE_NAME)["Role"]
        iam_client.update_assume_role_policy(
            RoleName=LAMBDA_ROLE_NAME,
            PolicyDocument=json.dumps(trust_policy),
        )
        print(f"♻️ Lambda IAM 역할 재사용: {LAMBDA_ROLE_NAME}")
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "NoSuchEntity":
            raise
        role = iam_client.create_role(
            RoleName=LAMBDA_ROLE_NAME,
            Description="Execution role for the CodeBuddy GitHub PR Lambda",
            AssumeRolePolicyDocument=json.dumps(trust_policy),
        )["Role"]
        created = True
        print(f"✅ Lambda IAM 역할 생성: {LAMBDA_ROLE_NAME}")

    iam_client.attach_role_policy(
        RoleName=LAMBDA_ROLE_NAME,
        PolicyArn=LAMBDA_POLICY_ARN,
    )
    if created:
        print("⏳ Lambda IAM 역할 전파 대기 중...")
        time.sleep(10)
    return role["Arn"]


def ensure_lambda_function(
    lambda_client: Any,
    role_arn: str,
    zip_bytes: bytes,
) -> str:
    try:
        function = lambda_client.get_function(
            FunctionName=LAMBDA_FUNCTION_NAME
        )["Configuration"]
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
        function = lambda_client.create_function(
            FunctionName=LAMBDA_FUNCTION_NAME,
            Description="Fetch public GitHub Pull Request details for CodeBuddy",
            Runtime="python3.12",
            Role=role_arn,
            Handler="github_pr_tool.handler",
            Code={"ZipFile": zip_bytes},
            Timeout=30,
            MemorySize=256,
            Publish=False,
        )
        lambda_client.get_waiter("function_active_v2").wait(
            FunctionName=LAMBDA_FUNCTION_NAME,
            WaiterConfig={"Delay": 2, "MaxAttempts": 30},
        )
        print(f"✅ Lambda 함수 생성: {LAMBDA_FUNCTION_NAME}")
        return function["FunctionArn"]

    lambda_client.update_function_code(
        FunctionName=LAMBDA_FUNCTION_NAME,
        ZipFile=zip_bytes,
        Publish=False,
    )
    lambda_client.get_waiter("function_updated_v2").wait(
        FunctionName=LAMBDA_FUNCTION_NAME,
        WaiterConfig={"Delay": 2, "MaxAttempts": 30},
    )
    lambda_client.update_function_configuration(
        FunctionName=LAMBDA_FUNCTION_NAME,
        Description="Fetch public GitHub Pull Request details for CodeBuddy",
        Runtime="python3.12",
        Role=role_arn,
        Handler="github_pr_tool.handler",
        Timeout=30,
        MemorySize=256,
    )
    lambda_client.get_waiter("function_updated_v2").wait(
        FunctionName=LAMBDA_FUNCTION_NAME,
        WaiterConfig={"Delay": 2, "MaxAttempts": 30},
    )
    print(f"♻️ Lambda 함수 업데이트: {LAMBDA_FUNCTION_NAME}")
    return function["FunctionArn"]


def ensure_lambda_permission(
    lambda_client: Any,
    agent_arn: str,
    account_id: str,
) -> None:
    try:
        lambda_client.remove_permission(
            FunctionName=LAMBDA_FUNCTION_NAME,
            StatementId=LAMBDA_PERMISSION_ID,
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceNotFoundException":
            raise

    lambda_client.add_permission(
        FunctionName=LAMBDA_FUNCTION_NAME,
        StatementId=LAMBDA_PERMISSION_ID,
        Action="lambda:InvokeFunction",
        Principal="bedrock.amazonaws.com",
        SourceArn=agent_arn,
        SourceAccount=account_id,
    )
    print("✅ Lambda에 Bedrock Agent 호출 권한 적용")


def update_agent_for_github_tool(
    agent_client: Any,
    state: AgentState,
    config: AgentConfig,
) -> None:
    current = agent_client.get_agent(agentId=state.agent_id)["agent"]
    agent_client.update_agent(
        agentId=state.agent_id,
        agentName=current["agentName"],
        agentResourceRoleArn=current["agentResourceRoleArn"],
        foundationModel=current["foundationModel"],
        instruction=build_agent_instruction(include_github_tool=True),
        description=current.get("description", AGENT_DESCRIPTION),
        idleSessionTTLInSeconds=current.get("idleSessionTTLInSeconds", 1800),
    )
    wait_for_status(
        lambda: agent_client.get_agent(agentId=state.agent_id)["agent"],
        status_key="agentStatus",
        success_statuses={"NOT_PREPARED", "PREPARED"},
        failure_statuses={"FAILED", "DELETING"},
    )
    print("✅ Agent Instructions에 GitHub Tool 규칙 반영")


def ensure_action_group(
    agent_client: Any,
    agent_id: str,
    lambda_arn: str,
) -> str:
    groups = list_all(
        agent_client.list_agent_action_groups,
        "actionGroupSummaries",
        agentId=agent_id,
        agentVersion="DRAFT",
        maxResults=100,
    )
    action_group_id = find_action_group(groups, ACTION_GROUP_NAME)
    request = {
        "agentId": agent_id,
        "agentVersion": "DRAFT",
        "actionGroupName": ACTION_GROUP_NAME,
        "actionGroupExecutor": {"lambda": lambda_arn},
        "apiSchema": {
            "payload": json.dumps(
                GITHUB_PR_OPENAPI_SCHEMA,
                ensure_ascii=False,
            )
        },
        "actionGroupState": "ENABLED",
        "description": (
            "Fetch public GitHub Pull Request metadata and changed files"
        ),
    }
    if action_group_id:
        agent_client.update_agent_action_group(
            actionGroupId=action_group_id,
            **request,
        )
        print(
            f"♻️ Action Group 업데이트: "
            f"{ACTION_GROUP_NAME} ({action_group_id})"
        )
    else:
        action_group = agent_client.create_agent_action_group(**request)[
            "agentActionGroup"
        ]
        action_group_id = action_group["actionGroupId"]
        print(
            f"✅ Action Group 생성: "
            f"{ACTION_GROUP_NAME} ({action_group_id})"
        )
    return action_group_id


def deploy_github_tool(config: AgentConfig | None = None) -> AgentState:
    config = config or load_config()
    state = load_state(config.state_path)
    session = boto3.Session(region_name=config.region)
    sts_client = session.client("sts")
    iam_client = session.client("iam")
    lambda_client = session.client("lambda")
    agent_client = session.client("bedrock-agent")

    account_id = sts_client.get_caller_identity()["Account"]
    agent_arn = (
        f"arn:aws:bedrock:{config.region}:{account_id}:"
        f"agent/{state.agent_id}"
    )
    print(f"🔐 AWS 계정: {account_id}, Agent: {state.agent_id}")

    role_arn = ensure_lambda_role(iam_client)
    zip_bytes = build_lambda_zip(LAMBDA_SOURCE)
    lambda_arn = ensure_lambda_function(
        lambda_client,
        role_arn,
        zip_bytes,
    )
    ensure_lambda_permission(
        lambda_client,
        agent_arn=agent_arn,
        account_id=account_id,
    )
    update_agent_for_github_tool(agent_client, state, config)
    action_group_id = ensure_action_group(
        agent_client,
        state.agent_id,
        lambda_arn,
    )
    prepare_agent(agent_client, state.agent_id)
    alias_id = ensure_alias(agent_client, state.agent_id, config)

    updated_state = update_tool_state(
        AgentState(
            agent_id=state.agent_id,
            alias_id=alias_id,
            role_arn=state.role_arn,
            lambda_arn=state.lambda_arn,
            action_group_id=state.action_group_id,
        ),
        lambda_arn=lambda_arn,
        action_group_id=action_group_id,
    )
    save_state(config.state_path, updated_state)
    print(f"💾 GitHub Tool 상태 저장: {config.state_path}")
    print(
        f"🎉 6장 배포 완료 - Lambda: {lambda_arn}, "
        f"Action Group: {action_group_id}"
    )
    return updated_state


def main() -> None:
    try:
        deploy_github_tool()
    except NoCredentialsError as exc:
        raise SystemExit(
            "❌ AWS 자격 증명을 확인하세요. aws configure 또는 AWS_PROFILE 설정이 필요합니다."
        ) from exc
    except ClientError as exc:
        error = exc.response.get("Error", {})
        raise SystemExit(
            f"❌ AWS 오류 [{error.get('Code', 'Unknown')}]: "
            f"{error.get('Message', str(exc))}"
        ) from exc
    except BotoCoreError as exc:
        raise SystemExit(f"❌ AWS SDK 연결 또는 설정 오류: {exc}") from exc
    except (FileNotFoundError, RuntimeError, TimeoutError, ValueError) as exc:
        raise SystemExit(f"❌ GitHub Tool 배포 실패: {exc}") from exc


if __name__ == "__main__":
    main()
