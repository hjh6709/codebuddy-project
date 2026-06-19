import json
import os
from dataclasses import asdict, dataclass
from json import JSONDecodeError
from pathlib import Path


@dataclass(frozen=True)
class AgentConfig:
    region: str
    model_id: str
    knowledge_base_id: str
    agent_name: str
    alias_name: str
    role_name: str
    policy_name: str
    state_path: Path


@dataclass(frozen=True)
class AgentState:
    agent_id: str
    alias_id: str
    role_arn: str


def load_config() -> AgentConfig:
    return AgentConfig(
        region=os.getenv("AWS_REGION", "ap-northeast-2"),
        model_id=os.getenv(
            "CODEBUDDY_MODEL_ID",
            "global.anthropic.claude-sonnet-4-6",
        ),
        knowledge_base_id=os.getenv("CODEBUDDY_KB_ID", "Q1ZYRCWLIW"),
        agent_name=os.getenv("CODEBUDDY_AGENT_NAME", "CodeBuddy-Reviewer"),
        alias_name=os.getenv("CODEBUDDY_ALIAS_NAME", "dev"),
        role_name=os.getenv(
            "CODEBUDDY_AGENT_ROLE_NAME",
            "AmazonBedrockAgentServiceRole_CodeBuddy",
        ),
        policy_name=os.getenv(
            "CODEBUDDY_AGENT_POLICY_NAME",
            "CodeBuddyBedrockAgentPolicy",
        ),
        state_path=Path(
            os.getenv("CODEBUDDY_AGENT_STATE", ".codebuddy/agent-state.json")
        ),
    )


def save_state(path: Path, state: AgentState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(state), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_state(path: Path) -> AgentState:
    if not path.exists():
        raise FileNotFoundError(
            f"Agent 상태 파일이 없습니다: {path}. 먼저 src/setup_agent.py를 실행하세요."
        )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return AgentState(
            agent_id=data["agent_id"],
            alias_id=data["alias_id"],
            role_arn=data["role_arn"],
        )
    except (JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"Agent 상태 파일을 읽을 수 없습니다: {path}") from exc
