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
    from src.codebuddy_tool_schema import CODEBUDDY_TOOLS_OPENAPI_SCHEMA
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
    from codebuddy_tool_schema import CODEBUDDY_TOOLS_OPENAPI_SCHEMA
    from setup_agent import (
        AGENT_DESCRIPTION,
        build_agent_instruction,
        ensure_alias,
        list_all,
        prepare_agent,
        wait_for_status,
    )


ROOT = Path(__file__).resolve().parents[1]
LAMBDA_SOURCE = ROOT / "lambda" / "codebuddy_tools.py"
LAMBDA_ROLE_NAME = "CodeBuddy-Lambda-Role"
LAMBDA_FUNCTION_NAME = "codebuddy-all-tools-executor"
LAMBDA_HANDLER = "codebuddy_tools.handler"
LAMBDA_POLICY_ARN = (
    "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
)
BEDROCK_RUNTIME_POLICY_NAME = "CodeBuddyToolBedrockRuntimePolicy"
ACTION_GROUP_NAME = "CodeBuddyTools"
LEGACY_ACTION_GROUP_NAMES = {"GitHubPRTools"}
LAMBDA_PERMISSION_ID = "AllowBedrockAgentInvokeCodeBuddyTools"


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


def build_bedrock_runtime_policy(
    account_id: str,
    region: str,
    model_id: str,
) -> dict[str, Any]:
    model_family = model_id.removeprefix("global.")
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "CodeBuddyToolBedrockRuntime",
                "Effect": "Allow",
                "Action": [
                    "bedrock:InvokeModel",
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
            }
        ],
    }


def build_lambda_zip(source_path: Path = LAMBDA_SOURCE) -> bytes:
    if not source_path.exists():
        raise FileNotFoundError(f"Lambda 소스 파일이 없습니다: {source_path}")
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("codebuddy_tools.py", source_path.read_bytes())
    return buffer.getvalue()


def collect_tool_environment(env: dict[str, str] | None = None) -> dict[str, str]:
    source = os.environ if env is None else env
    keys = (
        "GITHUB_TOKEN",
        "SLACK_WEBHOOK_URL",
        "CODEBUDDY_TOOL_MODEL_ID",
    )
    return {
        key: str(source[key])
        for key in keys
        if source.get(key)
    }


def find_action_group(
    groups: list[dict[str, Any]],
    expected_name: str,
) -> str | None:
    for group in groups:
        if group.get("actionGroupName") == expected_name:
            return group.get("actionGroupId")
    return None


def disable_legacy_action_groups(
    agent_client: Any,
    agent_id: str,
) -> None:
    groups = list_all(
        agent_client.list_agent_action_groups,
        "actionGroupSummaries",
        agentId=agent_id,
        agentVersion="DRAFT",
        maxResults=100,
    )
    for group in groups:
        name = group.get("actionGroupName")
        if (
            name not in LEGACY_ACTION_GROUP_NAMES
            or group.get("actionGroupState") == "DISABLED"
        ):
            continue
        current = agent_client.get_agent_action_group(
            agentId=agent_id,
            agentVersion="DRAFT",
            actionGroupId=group["actionGroupId"],
        )["agentActionGroup"]
        request = {
            "agentId": agent_id,
            "agentVersion": "DRAFT",
            "actionGroupId": group["actionGroupId"],
            "actionGroupName": name,
            "actionGroupState": "DISABLED",
        }
        for key in (
            "actionGroupExecutor",
            "apiSchema",
            "functionSchema",
            "parentActionGroupSignature",
            "parentActionGroupSignatureParams",
            "description",
        ):
            if key in current:
                request[key] = current[key]
        agent_client.update_agent_action_group(**request)
        print(f"✅ 기존 Action Group 비활성화: {name}")


def ensure_lambda_role(
    iam_client: Any,
    account_id: str,
    region: str,
    model_id: str,
) -> str:
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
            Description="Execution role for CodeBuddy Agent Tool Lambdas",
            AssumeRolePolicyDocument=json.dumps(trust_policy),
        )["Role"]
        created = True
        print(f"✅ Lambda IAM 역할 생성: {LAMBDA_ROLE_NAME}")

    iam_client.attach_role_policy(
        RoleName=LAMBDA_ROLE_NAME,
        PolicyArn=LAMBDA_POLICY_ARN,
    )
    iam_client.put_role_policy(
        RoleName=LAMBDA_ROLE_NAME,
        PolicyName=BEDROCK_RUNTIME_POLICY_NAME,
        PolicyDocument=json.dumps(
            build_bedrock_runtime_policy(account_id, region, model_id)
        ),
    )
    if created:
        print("⏳ Lambda IAM 역할 전파 대기 중...")
        time.sleep(10)
    return role["Arn"]


def ensure_lambda_function(
    lambda_client: Any,
    role_arn: str,
    zip_bytes: bytes,
    environment: dict[str, str],
) -> str:
    config = {
        "Description": (
            "Execute CodeBuddy GitHub, Slack, and code analysis Agent tools"
        ),
        "Runtime": "python3.12",
        "Role": role_arn,
        "Handler": LAMBDA_HANDLER,
        "Timeout": 60,
        "MemorySize": 512,
        "Environment": {"Variables": environment},
    }
    try:
        function = lambda_client.get_function(
            FunctionName=LAMBDA_FUNCTION_NAME
        )["Configuration"]
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
        function = lambda_client.create_function(
            FunctionName=LAMBDA_FUNCTION_NAME,
            Code={"ZipFile": zip_bytes},
            Publish=False,
            **config,
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
        **config,
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
    print("✅ 통합 Lambda에 Bedrock Agent 호출 권한 적용")


def update_agent_for_codebuddy_tools(
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
        instruction=build_agent_instruction(include_codebuddy_tools=True),
        description=current.get("description", AGENT_DESCRIPTION),
        idleSessionTTLInSeconds=current.get("idleSessionTTLInSeconds", 1800),
    )
    wait_for_status(
        lambda: agent_client.get_agent(agentId=state.agent_id)["agent"],
        status_key="agentStatus",
        success_statuses={"NOT_PREPARED", "PREPARED"},
        failure_statuses={"FAILED", "DELETING"},
    )
    print("✅ Agent Instructions에 CodeBuddy 통합 Tool 규칙 반영")


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
                CODEBUDDY_TOOLS_OPENAPI_SCHEMA,
                ensure_ascii=False,
            )
        },
        "actionGroupState": "ENABLED",
        "description": (
            "CodeBuddy tools for GitHub comments, Slack alerts, "
            "complexity analysis, test generation, and refactoring"
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
        return action_group_id

    created = agent_client.create_agent_action_group(**request)[
        "agentActionGroup"
    ]
    action_group_id = created["actionGroupId"]
    print(f"✅ Action Group 생성: {ACTION_GROUP_NAME} ({action_group_id})")
    return action_group_id


def deploy_codebuddy_tools(config: AgentConfig | None = None) -> AgentState:
    config = config or load_config()
    state = load_state(config.state_path)
    session = boto3.Session(region_name=config.region)
    sts_client = session.client("sts")
    iam_client = session.client("iam")
    lambda_client = session.client("lambda")
    agent_client = session.client("bedrock-agent")

    account_id = sts_client.get_caller_identity()["Account"]
    agent_arn = (
        f"arn:aws:bedrock:{config.region}:{account_id}:agent/{state.agent_id}"
    )
    print(f"🔐 AWS 계정: {account_id}, Agent: {state.agent_id}")

    environment = collect_tool_environment()
    environment.setdefault("CODEBUDDY_TOOL_MODEL_ID", config.model_id)
    if "GITHUB_TOKEN" not in environment:
        print("⚠️ GITHUB_TOKEN이 없어 PR 댓글 Tool은 실행 시 실패합니다.")
    if "SLACK_WEBHOOK_URL" not in environment:
        print("⚠️ SLACK_WEBHOOK_URL이 없어 Slack Tool은 실행 시 실패합니다.")

    role_arn = ensure_lambda_role(
        iam_client,
        account_id,
        config.region,
        config.model_id,
    )
    lambda_arn = ensure_lambda_function(
        lambda_client,
        role_arn,
        build_lambda_zip(),
        environment,
    )
    ensure_lambda_permission(lambda_client, agent_arn, account_id)
    update_agent_for_codebuddy_tools(agent_client, state, config)
    action_group_id = ensure_action_group(
        agent_client,
        state.agent_id,
        lambda_arn,
    )
    disable_legacy_action_groups(agent_client, state.agent_id)
    prepare_agent(agent_client, state.agent_id)
    alias_id = ensure_alias(agent_client, state.agent_id, config)
    updated = update_tool_state(
        state,
        lambda_arn=lambda_arn,
        action_group_id=action_group_id,
    )
    updated = AgentState(
        agent_id=updated.agent_id,
        alias_id=alias_id,
        role_arn=updated.role_arn,
        lambda_arn=updated.lambda_arn,
        action_group_id=updated.action_group_id,
    )
    save_state(config.state_path, updated)
    print(f"💾 CodeBuddy 통합 Tool 상태 저장: {config.state_path}")
    print(
        f"🎉 7/8장 배포 완료 - Lambda: {lambda_arn}, "
        f"Action Group: {action_group_id}"
    )
    return updated


def main() -> None:
    try:
        deploy_codebuddy_tools()
    except NoCredentialsError as exc:
        raise SystemExit(
            "❌ AWS 자격 증명을 찾을 수 없습니다. "
            "aws configure 또는 환경변수를 확인하세요."
        ) from exc
    except (BotoCoreError, ClientError, RuntimeError, FileNotFoundError) as exc:
        raise SystemExit(f"❌ CodeBuddy 통합 Tool 배포 실패: {exc}") from exc


if __name__ == "__main__":
    main()
