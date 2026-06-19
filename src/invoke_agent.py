import argparse
import json
import uuid
from collections.abc import Iterable
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

try:
    from src.agent_config import AgentConfig, load_config, load_state
except ModuleNotFoundError:
    from agent_config import AgentConfig, load_config, load_state


SAMPLE_CODE = """def divide(a, b):
    return a / b

def get_user(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return execute(query)
"""


def build_code_review_prompt(code: str) -> str:
    return f"""Knowledge Base의 코드 스타일 및 OWASP 문서를 참고하여 다음 코드를 리뷰해주세요.

검사 항목:
1. 실행 중 발생할 수 있는 버그
2. 보안 취약점
3. 코드 스타일 위반
4. 문제별 심각도와 구체적인 수정 제안

```python
{code}
```"""


def parse_completion(
    events: Iterable[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    chunks = []
    traces = []
    for event in events:
        if "chunk" in event:
            chunks.append(event["chunk"]["bytes"].decode("utf-8"))
        if "trace" in event:
            trace_event = event["trace"]
            traces.append(trace_event.get("trace", trace_event))
    return "".join(chunks), traces


def invoke(
    prompt: str,
    session_id: str | None = None,
    enable_trace: bool = False,
    config: AgentConfig | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    config = config or load_config()
    state = load_state(config.state_path)
    runtime = boto3.client(
        "bedrock-agent-runtime",
        region_name=config.region,
        config=Config(
            connect_timeout=10,
            read_timeout=300,
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )
    response = runtime.invoke_agent(
        agentId=state.agent_id,
        agentAliasId=state.alias_id,
        sessionId=session_id or str(uuid.uuid4()),
        inputText=prompt,
        enableTrace=enable_trace,
    )
    return parse_completion(response["completion"])


def print_traces(traces: list[dict[str, Any]]) -> None:
    if not traces:
        print("\n🔎 Trace 이벤트가 없습니다.")
        return
    print("\n🔎 Agent Trace")
    for index, trace in enumerate(traces, start=1):
        print(f"\n--- Trace {index} ---")
        print(json.dumps(trace, ensure_ascii=False, indent=2, default=str))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="배포된 CodeBuddy Bedrock Agent를 호출합니다."
    )
    parser.add_argument("--prompt", help="Agent에게 전달할 질문")
    parser.add_argument(
        "--code-review",
        action="store_true",
        help="교재의 취약한 예제 코드 리뷰를 실행합니다.",
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Agent의 Trace 이벤트를 함께 출력합니다.",
    )
    parser.add_argument("--session-id", help="멀티턴 대화에 사용할 세션 ID")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.code_review:
        prompt = build_code_review_prompt(SAMPLE_CODE)
    elif args.prompt:
        prompt = args.prompt
    else:
        prompt = "안녕? 너의 역할을 한 문장으로 설명해줘."

    try:
        text, traces = invoke(
            prompt=prompt,
            session_id=args.session_id,
            enable_trace=args.trace,
        )
    except NoCredentialsError as exc:
        raise SystemExit(
            "❌ AWS 자격 증명을 확인하세요. aws configure 또는 AWS_PROFILE 설정이 필요합니다."
        ) from exc
    except (ClientError, FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"❌ Agent 호출 실패: {exc}") from exc
    except BotoCoreError as exc:
        raise SystemExit(f"❌ AWS SDK 연결 또는 설정 오류: {exc}") from exc

    print("🤖 CodeBuddy Agent 응답")
    print(text)
    if args.trace:
        print_traces(traces)


if __name__ == "__main__":
    main()
