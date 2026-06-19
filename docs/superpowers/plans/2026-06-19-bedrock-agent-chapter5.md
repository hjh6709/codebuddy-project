# Bedrock Agent Chapter 5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 코드 스타일 Knowledge Base를 연결한 `CodeBuddy-Reviewer` Bedrock Agent를 멱등적으로 배포하고 호출·Trace까지 검증한다.

**Architecture:** AWS API 호출은 `src/setup_agent.py`에 집중시키되, 정책 생성·상태 직렬화·이벤트 파싱은 순수 함수로 분리해 로컬 단위 테스트가 가능하게 한다. 배포 결과는 Git에서 제외되는 `.codebuddy/agent-state.json`에 저장하고 `src/invoke_agent.py`가 이를 읽어 Agent Runtime을 호출한다.

**Tech Stack:** Python 3, boto3, botocore, unittest, Amazon Bedrock Agents, IAM, STS

---

## 파일 구조

- Create: `src/agent_config.py` - 환경변수 기반 설정과 상태 파일 입출력
- Create: `src/setup_agent.py` - IAM, Agent, KB 연결, Prepare, Alias 배포
- Create: `src/invoke_agent.py` - Agent 호출 및 Trace 이벤트 출력
- Create: `tests/test_agent_config.py` - 설정·상태 파일 테스트
- Create: `tests/test_setup_agent.py` - 정책·리소스 선택·폴링 테스트
- Create: `tests/test_invoke_agent.py` - completion 이벤트 파싱 테스트
- Modify: `.gitignore` - 로컬 Agent 상태 파일 제외
- Modify: `requirements.txt` - 실행 및 테스트 의존성 명시
- Modify: `README.md` - 5장 실행 방법과 산출물 기록

### Task 1: Agent 설정과 상태 저장

**Files:**
- Create: `tests/test_agent_config.py`
- Create: `src/agent_config.py`
- Modify: `.gitignore`
- Modify: `requirements.txt`

- [ ] **Step 1: 기본값과 환경변수 덮어쓰기 실패 테스트 작성**

```python
def test_load_config_uses_defaults(monkeypatch):
    for name in CONFIG_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    config = load_config()
    assert config.region == "ap-northeast-2"
    assert config.knowledge_base_id == "Q1ZYRCWLIW"
    assert config.agent_name == "CodeBuddy-Reviewer"

def test_load_config_accepts_environment_overrides(monkeypatch):
    monkeypatch.setenv("CODEBUDDY_AGENT_NAME", "TestReviewer")
    assert load_config().agent_name == "TestReviewer"
```

- [ ] **Step 2: 테스트가 모듈 부재로 실패하는지 확인**

Run: `.venv/bin/python -m unittest tests.test_agent_config -v`

Expected: `ModuleNotFoundError: No module named 'src.agent_config'`

- [ ] **Step 3: 최소 설정 객체와 로더 구현**

```python
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

def load_config() -> AgentConfig:
    return AgentConfig(
        region=os.getenv("AWS_REGION", "ap-northeast-2"),
        model_id=os.getenv("CODEBUDDY_MODEL_ID", "global.anthropic.claude-sonnet-4-6"),
        knowledge_base_id=os.getenv("CODEBUDDY_KB_ID", "Q1ZYRCWLIW"),
        agent_name=os.getenv("CODEBUDDY_AGENT_NAME", "CodeBuddy-Reviewer"),
        alias_name=os.getenv("CODEBUDDY_ALIAS_NAME", "dev"),
        role_name=os.getenv("CODEBUDDY_AGENT_ROLE_NAME", "AmazonBedrockAgentServiceRole_CodeBuddy"),
        policy_name=os.getenv("CODEBUDDY_AGENT_POLICY_NAME", "CodeBuddyBedrockAgentPolicy"),
        state_path=Path(os.getenv("CODEBUDDY_AGENT_STATE", ".codebuddy/agent-state.json")),
    )
```

- [ ] **Step 4: 상태 저장·로드 실패 테스트 작성**

```python
def test_save_and_load_state_round_trip(tmp_path):
    path = tmp_path / "state.json"
    state = AgentState(agent_id="A1", alias_id="B2", role_arn="arn:test")
    save_state(path, state)
    assert load_state(path) == state

def test_load_state_reports_invalid_json(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="상태 파일"):
        load_state(path)
```

- [ ] **Step 5: 상태 직렬화 구현 후 테스트 통과**

Run: `.venv/bin/python -m unittest tests.test_agent_config -v`

Expected: 모든 설정·상태 테스트 `OK`

- [ ] **Step 6: 로컬 상태 파일과 의존성 설정**

`.gitignore`에 `.codebuddy/`를 추가하고 `requirements.txt`에 다음을 기록한다.

```text
boto3>=1.42,<2
```

- [ ] **Step 7: 첫 번째 단위 커밋**

```bash
git add src/agent_config.py tests/test_agent_config.py .gitignore requirements.txt
git commit -m "feat: add Bedrock Agent configuration state"
```

### Task 2: IAM과 Bedrock Agent 멱등 배포

**Files:**
- Create: `tests/test_setup_agent.py`
- Create: `src/setup_agent.py`

- [ ] **Step 1: IAM 정책 생성 실패 테스트 작성**

```python
def test_build_role_policies_scope_account_region_and_kb():
    trust, permissions = build_role_policies(
        account_id="123456789012",
        region="ap-northeast-2",
        model_id="global.anthropic.claude-sonnet-4-6",
        knowledge_base_id="Q1ZYRCWLIW",
    )
    assert trust["Statement"][0]["Principal"]["Service"] == "bedrock.amazonaws.com"
    assert trust["Statement"][0]["Condition"]["StringEquals"]["aws:SourceAccount"] == "123456789012"
    actions = {action for statement in permissions["Statement"] for action in statement["Action"]}
    assert "bedrock:InvokeModel" in actions
    assert "bedrock:Retrieve" in actions
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m unittest tests.test_setup_agent.BuildPoliciesTests -v`

Expected: `ImportError` 또는 `NameError`로 실패

- [ ] **Step 3: 정책 순수 함수 구현**

모델 호출 리소스는 global inference profile과 서울 리전 foundation model 패턴을
허용하고, Retrieve 리소스는 현재 계정의 지정 KB ARN 하나로 제한한다.

- [ ] **Step 4: 기존 Agent/Alias 선택 실패 테스트 작성**

```python
def test_find_named_resource_returns_matching_id():
    items = [{"agentName": "Other", "agentId": "1"}, {"agentName": "CodeBuddy-Reviewer", "agentId": "2"}]
    assert find_named_resource(items, "agentName", "CodeBuddy-Reviewer", "agentId") == "2"

def test_find_named_resource_returns_none_without_match():
    assert find_named_resource([], "agentName", "CodeBuddy-Reviewer", "agentId") is None
```

- [ ] **Step 5: 선택 함수 구현과 통과 확인**

Run: `.venv/bin/python -m unittest tests.test_setup_agent -v`

Expected: 정책·선택 테스트 `OK`

- [ ] **Step 6: 상태 폴링 실패 테스트 작성**

```python
def test_wait_for_status_returns_on_target():
    statuses = iter([{"status": "PREPARING"}, {"status": "PREPARED"}])
    result = wait_for_status(lambda: next(statuses), "status", {"PREPARED"}, {"FAILED"}, timeout=1, interval=0)
    assert result["status"] == "PREPARED"

def test_wait_for_status_raises_on_failed():
    with pytest.raises(RuntimeError, match="FAILED"):
        wait_for_status(lambda: {"status": "FAILED", "failureReasons": ["bad role"]},
                        "status", {"PREPARED"}, {"FAILED"}, timeout=1, interval=0)
```

- [ ] **Step 7: 제한 시간 폴링 구현**

`time.monotonic()`으로 마감 시간을 계산하고 성공·실패·시간 초과를 구분한다.

- [ ] **Step 8: AWS 배포 오케스트레이션 구현**

다음 책임을 각각 함수로 구현한다.

```python
def validate_knowledge_base(client, kb_id): ...
def ensure_agent_role(iam, sts, config) -> str: ...
def ensure_agent(client, config, role_arn) -> str: ...
def ensure_knowledge_base_association(client, agent_id, config): ...
def prepare_agent(client, agent_id): ...
def ensure_alias(client, agent_id, config) -> str: ...
def deploy_agent(config: AgentConfig) -> AgentState: ...
```

`list_agents`, `list_agent_knowledge_bases`, `list_agent_aliases`의 paginator 또는
`nextToken`을 처리해 이름과 ID를 찾는다. Agent와 Alias가 있으면 업데이트하고
없으면 생성한다.

- [ ] **Step 9: 전체 로컬 테스트 통과**

Run: `.venv/bin/python -m unittest discover -s tests -v`

Expected: 모든 테스트 `OK`

- [ ] **Step 10: 배포 코드 커밋**

```bash
git add src/setup_agent.py tests/test_setup_agent.py
git commit -m "feat: automate Bedrock Agent deployment"
```

### Task 3: Agent 호출과 Trace 파싱

**Files:**
- Create: `tests/test_invoke_agent.py`
- Create: `src/invoke_agent.py`

- [ ] **Step 1: completion 파싱 실패 테스트 작성**

```python
def test_parse_completion_collects_chunks_and_traces():
    events = [
        {"trace": {"trace": {"orchestrationTrace": {"rationale": {"text": "search"}}}}},
        {"chunk": {"bytes": "안녕 ".encode()}},
        {"chunk": {"bytes": "CodeBuddy".encode()}},
    ]
    text, traces = parse_completion(events)
    assert text == "안녕 CodeBuddy"
    assert traces == [{"orchestrationTrace": {"rationale": {"text": "search"}}}]
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m unittest tests.test_invoke_agent -v`

Expected: 모듈 또는 함수 부재로 실패

- [ ] **Step 3: 이벤트 파싱과 호출 함수 구현**

```python
def parse_completion(events):
    chunks, traces = [], []
    for event in events:
        if "chunk" in event:
            chunks.append(event["chunk"]["bytes"].decode("utf-8"))
        if "trace" in event:
            traces.append(event["trace"].get("trace", event["trace"]))
    return "".join(chunks), traces

def invoke(prompt, session_id=None, enable_trace=False, config=None):
    state = load_state(config.state_path)
    response = boto3.client("bedrock-agent-runtime", region_name=config.region).invoke_agent(
        agentId=state.agent_id,
        agentAliasId=state.alias_id,
        sessionId=session_id or str(uuid.uuid4()),
        inputText=prompt,
        enableTrace=enable_trace,
    )
    return parse_completion(response["completion"])
```

- [ ] **Step 4: 명령행 모드 구현**

`--prompt`, `--code-review`, `--trace`, `--session-id` 옵션을 제공한다. `--code-review`
입력 없이 실행하면 SQL Injection과 0 나누기 위험을 포함한 교재 예제를 사용한다.

- [ ] **Step 5: 테스트 통과와 커밋**

Run: `.venv/bin/python -m unittest discover -s tests -v`

Expected: 모든 테스트 `OK`

```bash
git add src/invoke_agent.py tests/test_invoke_agent.py
git commit -m "feat: add Bedrock Agent invocation client"
```

### Task 4: 실제 AWS 배포와 검증

**Files:**
- Generated: `.codebuddy/agent-state.json`

- [ ] **Step 1: AWS 자격 증명과 KB 상태 확인**

Run:

```bash
aws sts get-caller-identity
aws bedrock-agent get-knowledge-base --knowledge-base-id Q1ZYRCWLIW --region ap-northeast-2
```

Expected: 계정 `158670532183`, KB 상태 `ACTIVE`

- [ ] **Step 2: 첫 배포 실행**

Run: `.venv/bin/python src/setup_agent.py`

Expected: IAM 역할, Agent, KB 연결, Prepare, `dev` Alias가 생성되고 상태 파일이 기록됨

- [ ] **Step 3: 멱등성 검증**

Run: `.venv/bin/python src/setup_agent.py`

Expected: 동일한 Agent와 Alias ID를 재사용하며 중복 리소스를 만들지 않음

- [ ] **Step 4: AWS 리소스 상태 조회**

Run:

```bash
aws bedrock-agent get-agent --agent-id "$AGENT_ID" --region ap-northeast-2
aws bedrock-agent list-agent-knowledge-bases --agent-id "$AGENT_ID" --agent-version DRAFT --region ap-northeast-2
aws bedrock-agent get-agent-alias --agent-id "$AGENT_ID" --agent-alias-id "$ALIAS_ID" --region ap-northeast-2
```

Expected: Agent `PREPARED`, KB `ENABLED`, Alias `PREPARED`

- [ ] **Step 5: 기본 호출과 코드 리뷰 호출**

Run:

```bash
.venv/bin/python src/invoke_agent.py --prompt "너의 역할을 한 문장으로 설명해줘"
.venv/bin/python src/invoke_agent.py --code-review
```

Expected: 코드 리뷰 역할 설명과 SQL Injection·0 나누기 위험 분석

- [ ] **Step 6: Trace 호출**

Run: `.venv/bin/python src/invoke_agent.py --trace --prompt "Python 함수 이름 규칙을 Knowledge Base를 참고해서 설명해줘"`

Expected: 최종 응답과 오케스트레이션/Knowledge Base 관련 Trace 출력

### Task 5: README와 최종 검증

**Files:**
- Modify: `README.md`

- [ ] **Step 1: README에 5장 추가**

다음 내용을 기록한다.

- Agent 구성과 기존 KB 연결 구조
- `setup_agent.py` 실행법
- 환경변수 목록
- `invoke_agent.py` 일반·코드 리뷰·Trace 예제
- IAM 역할과 로컬 상태 파일의 보안 주의사항
- 생성된 AWS 리소스의 이름

- [ ] **Step 2: 전체 검증 실행**

Run:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q src tests
git diff --check
git status --short
```

Expected: 테스트·구문 검사·diff 검사 모두 성공하고 `.codebuddy/`는 Git 상태에 나타나지 않음

- [ ] **Step 3: 최종 구현 커밋**

```bash
git add README.md
git commit -m "docs: document Bedrock Agent chapter 5"
```
