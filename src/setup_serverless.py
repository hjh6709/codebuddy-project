import hashlib
import io
import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zipfile import ZIP_DEFLATED, ZipFile

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

try:
    from src.agent_config import load_config, load_state
except ModuleNotFoundError:
    from agent_config import load_config, load_state


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "cloudformation" / "codebuddy-serverless.yaml"
ORCHESTRATOR_SOURCE = ROOT / "lambda" / "codebuddy_orchestrator.py"
WORKER_SOURCE = ROOT / "lambda" / "codebuddy_review_worker.py"
STACK_NAME = "CodeBuddyServerless"
STATE_PATH = ROOT / ".codebuddy" / "serverless-state.json"
GITHUB_API = "https://api.github.com"


def build_lambda_zip(source_path: Path) -> bytes:
    if not source_path.exists():
        raise FileNotFoundError(f"Lambda 소스 파일이 없습니다: {source_path}")
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr(source_path.name, source_path.read_bytes())
    return buffer.getvalue()


def build_deployment_artifacts() -> dict[str, bytes]:
    return {
        "orchestrator": build_lambda_zip(ORCHESTRATOR_SOURCE),
        "review-worker": build_lambda_zip(WORKER_SOURCE),
    }


def load_template(path: Path = TEMPLATE_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_stack_parameters(
    artifact_bucket: str,
    orchestrator_key: str,
    worker_key: str,
    agent_id: str,
    alias_id: str,
) -> list[dict[str, str]]:
    values = (
        ("ArtifactBucket", artifact_bucket),
        ("OrchestratorCodeKey", orchestrator_key),
        ("WorkerCodeKey", worker_key),
        ("AgentId", agent_id),
        ("AliasId", alias_id),
    )
    return [
        {"ParameterKey": key, "ParameterValue": value}
        for key, value in values
    ]


def save_serverless_state(path: Path, outputs: dict[str, str]) -> None:
    state = {
        "review_api_url": outputs["ReviewApiUrl"],
        "api_key_id": outputs["ApiKeyId"],
        "github_webhook_url": outputs["GitHubWebhookUrl"],
        "webhook_secret_arn": outputs["WebhookSecretArn"],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_github_webhook_payload(
    webhook_url: str,
    secret: str,
) -> dict[str, Any]:
    return {
        "name": "web",
        "active": True,
        "events": ["pull_request"],
        "config": {
            "url": webhook_url,
            "content_type": "json",
            "insecure_ssl": "0",
            "secret": secret,
        },
    }


def ensure_github_webhook(
    request_json: Any,
    owner: str,
    repo: str,
    webhook_url: str,
    secret: str,
) -> int:
    hooks_path = f"/repos/{owner}/{repo}/hooks"
    hooks = request_json("GET", hooks_path)
    matching_hook = next(
        (
            hook
            for hook in hooks
            if hook.get("config", {}).get("url") == webhook_url
        ),
        None,
    )
    payload = build_github_webhook_payload(webhook_url, secret)
    if matching_hook:
        hook_id = int(matching_hook["id"])
        response = request_json(
            "PATCH",
            f"{hooks_path}/{hook_id}",
            payload,
        )
    else:
        response = request_json("POST", hooks_path, payload)
    return int(response["id"])


def configure_github_webhook(
    secrets_client: Any,
    request_json: Any,
    repository: str,
    outputs: dict[str, str],
) -> int:
    parts = repository.split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError(
            "CODEBUDDY_GITHUB_REPOSITORY must use owner/repository"
        )
    secret = secrets_client.get_secret_value(
        SecretId=outputs["WebhookSecretArn"]
    ).get("SecretString")
    if not secret:
        raise ValueError("GitHub webhook secret is unavailable")
    return ensure_github_webhook(
        request_json,
        parts[0],
        parts[1],
        outputs["GitHubWebhookUrl"],
        secret,
    )


def build_github_request_json(token: str):
    def request_json(
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        body = (
            json.dumps(payload).encode("utf-8")
            if payload is not None
            else None
        )
        request = Request(
            f"{GITHUB_API}{path}",
            data=body,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "CodeBuddy-Serverless-Setup",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(
                f"GitHub API request failed with HTTP {exc.code}"
            ) from exc
        except URLError as exc:
            raise RuntimeError("GitHub API request failed") from exc

    return request_json


def ensure_artifact_bucket(s3_client: Any, bucket_name: str, region: str) -> None:
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        return
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in {"404", "NoSuchBucket"}:
            raise
    request: dict[str, Any] = {"Bucket": bucket_name}
    if region != "us-east-1":
        request["CreateBucketConfiguration"] = {
            "LocationConstraint": region
        }
    s3_client.create_bucket(**request)


def upload_artifact(s3_client: Any, bucket: str, name: str, body: bytes) -> str:
    digest = hashlib.sha256(body).hexdigest()[:16]
    key = f"codebuddy/{name}-{digest}.zip"
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType="application/zip",
        ServerSideEncryption="AES256",
    )
    return key


def stack_exists(cfn_client: Any, stack_name: str) -> bool:
    try:
        response = cfn_client.describe_stacks(StackName=stack_name)
    except ClientError as exc:
        if "does not exist" in str(exc):
            return False
        raise
    status = response["Stacks"][0]["StackStatus"]
    failed_states = {
        "CREATE_FAILED",
        "ROLLBACK_COMPLETE",
        "ROLLBACK_FAILED",
        "DELETE_FAILED",
        "UPDATE_ROLLBACK_FAILED",
    }
    if status in failed_states:
        raise RuntimeError(
            f"CloudFormation stack requires manual recovery: {status}"
        )
    return True


def wait_for_stack(cfn_client: Any, stack_name: str, created: bool) -> None:
    waiter_name = (
        "stack_create_complete" if created else "stack_update_complete"
    )
    cfn_client.get_waiter(waiter_name).wait(
        StackName=stack_name,
        WaiterConfig={"Delay": 5, "MaxAttempts": 120},
    )


def deploy_serverless() -> dict[str, str]:
    config = load_config()
    state = load_state(config.state_path)
    session = boto3.Session(region_name=config.region)
    sts_client = session.client("sts")
    s3_client = session.client("s3")
    cfn_client = session.client("cloudformation")
    secrets_client = session.client("secretsmanager")

    account_id = sts_client.get_caller_identity()["Account"]
    bucket = f"codebuddy-artifacts-{account_id}-{config.region}"
    ensure_artifact_bucket(s3_client, bucket, config.region)
    artifacts = build_deployment_artifacts()
    orchestrator_key = upload_artifact(
        s3_client,
        bucket,
        "orchestrator",
        artifacts["orchestrator"],
    )
    worker_key = upload_artifact(
        s3_client,
        bucket,
        "review-worker",
        artifacts["review-worker"],
    )
    template_body = json.dumps(load_template())
    parameters = build_stack_parameters(
        bucket,
        orchestrator_key,
        worker_key,
        state.agent_id,
        state.alias_id,
    )
    request = {
        "StackName": STACK_NAME,
        "TemplateBody": template_body,
        "Parameters": parameters,
        "Capabilities": ["CAPABILITY_NAMED_IAM"],
    }
    created = not stack_exists(cfn_client, STACK_NAME)
    if created:
        cfn_client.create_stack(**request)
    else:
        try:
            cfn_client.update_stack(**request)
        except ClientError as exc:
            if "No updates are to be performed" not in str(exc):
                raise
        else:
            wait_for_stack(cfn_client, STACK_NAME, created=False)
    if created:
        wait_for_stack(cfn_client, STACK_NAME, created=True)

    stack = cfn_client.describe_stacks(StackName=STACK_NAME)["Stacks"][0]
    outputs = {
        item["OutputKey"]: item["OutputValue"]
        for item in stack.get("Outputs", [])
    }
    save_serverless_state(STATE_PATH, outputs)
    repository = os.environ.get("CODEBUDDY_GITHUB_REPOSITORY")
    github_token = os.environ.get("GITHUB_TOKEN")
    if repository and github_token:
        hook_id = configure_github_webhook(
            secrets_client,
            build_github_request_json(github_token),
            repository,
            outputs,
        )
        print(f"✅ GitHub webhook 연결 완료: hook {hook_id}")
    else:
        print(
            "ℹ️ GitHub webhook 연결 생략: "
            "CODEBUDDY_GITHUB_REPOSITORY와 GITHUB_TOKEN을 설정하세요."
        )
    print(f"✅ CodeBuddy 서버리스 API 배포: {outputs['ReviewApiUrl']}")
    print(f"💾 API 상태 저장: {STATE_PATH}")
    return outputs


def main() -> None:
    try:
        deploy_serverless()
    except NoCredentialsError as exc:
        raise SystemExit("❌ AWS 자격 증명을 확인하세요.") from exc
    except (
        BotoCoreError,
        ClientError,
        FileNotFoundError,
        KeyError,
        RuntimeError,
        ValueError,
    ) as exc:
        raise SystemExit(f"❌ 서버리스 API 배포 실패: {exc}") from exc


if __name__ == "__main__":
    main()
