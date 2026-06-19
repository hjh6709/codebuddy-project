# Bedrock Agent Chapter 6 GitHub PR Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 공개 GitHub Pull Request의 상세 정보와 변경 patch를 조회하는 Lambda Tool을 기존 CodeBuddy Bedrock Agent의 Action Group으로 배포한다.

**Architecture:** Lambda 코드는 Python 표준 라이브러리만 사용해 GitHub REST API를 호출하며, 순수 함수와 네트워크 경계를 분리해 로컬 단위 테스트가 가능하게 한다. `setup_github_tool.py`가 Lambda IAM 역할·함수·리소스 정책·OpenAPI Action Group·Agent Instructions·Prepare/Alias를 멱등적으로 관리한다.

**Tech Stack:** Python 3.12, boto3, botocore, unittest, AWS Lambda, Amazon Bedrock Agents, GitHub REST API

---

## 파일 구조

- Create: `lambda/github_pr_tool.py` - Bedrock 이벤트 처리와 GitHub 공개 PR 조회
- Create: `src/github_tool_schema.py` - OpenAPI 3.0 Action Group 스키마
- Create: `src/setup_github_tool.py` - Lambda와 Action Group 배포 자동화
- Create: `tests/test_github_pr_tool.py` - Lambda 로직과 오류 매핑 테스트
- Create: `tests/test_github_tool_schema.py` - OpenAPI 스키마 테스트
- Create: `tests/test_setup_github_tool.py` - ZIP·정책·리소스 선택 테스트
- Modify: `src/agent_config.py` - 선택적 Lambda/Action Group 상태 저장
- Modify: `tests/test_agent_config.py` - 상태 하위 호환 테스트
- Modify: `README.md` - 6장 실행과 시연 방법

### Task 1: Agent 상태 확장

**Files:**
- Modify: `src/agent_config.py`
- Modify: `tests/test_agent_config.py`

- [ ] **Step 1: 기존 상태 파일 하위 호환 실패 테스트 작성**

```python
def test_load_state_accepts_chapter5_state_without_tool_fields(self):
    path.write_text(
        '{"agent_id":"A","alias_id":"B","role_arn":"arn:test"}',
        encoding="utf-8",
    )
    state = load_state(path)
    self.assertIsNone(state.lambda_arn)
    self.assertIsNone(state.action_group_id)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m unittest tests.test_agent_config -v`

Expected: `AgentState`에 `lambda_arn` 속성이 없어 실패

- [ ] **Step 3: 선택 필드와 상태 갱신 함수 구현**

```python
@dataclass(frozen=True)
class AgentState:
    agent_id: str
    alias_id: str
    role_arn: str
    lambda_arn: str | None = None
    action_group_id: str | None = None

def update_tool_state(state, lambda_arn, action_group_id):
    return replace(
        state,
        lambda_arn=lambda_arn,
        action_group_id=action_group_id,
    )
```

`load_state()`는 누락된 선택 필드에 `None`을 사용한다.

- [ ] **Step 4: 상태 테스트 통과**

Run: `.venv/bin/python -m unittest tests.test_agent_config -v`

Expected: 설정과 Chapter 5/6 상태 round-trip 테스트 모두 `OK`

- [ ] **Step 5: 상태 확장 커밋**

```bash
git add src/agent_config.py tests/test_agent_config.py
git commit -m "feat: extend Agent state for GitHub tool"
```

### Task 2: GitHub PR Lambda 로직

**Files:**
- Create: `lambda/github_pr_tool.py`
- Create: `tests/test_github_pr_tool.py`

- [ ] **Step 1: 파라미터 추출과 응답 형식 실패 테스트 작성**

```python
def test_extract_parameters_validates_required_values():
    event = {
        "parameters": [
            {"name": "owner", "value": "octocat"},
            {"name": "repo", "value": "Spoon-Knife"},
            {"name": "pr_number", "value": "40222"},
        ]
    }
    self.assertEqual(
        extract_parameters(event),
        ("octocat", "Spoon-Knife", 40222),
    )

def test_build_response_serializes_body_as_json_string():
    response = build_response(EVENT, 200, {"title": "PR"})
    body = response["response"]["responseBody"]["application/json"]["body"]
    self.assertEqual(json.loads(body), {"title": "PR"})
```

- [ ] **Step 2: 모듈 부재 실패 확인**

Run: `.venv/bin/python -m unittest tests.test_github_pr_tool -v`

Expected: Lambda 모듈을 찾을 수 없어 실패

- [ ] **Step 3: 이벤트 파싱과 Bedrock 응답 함수 구현**

```python
def extract_parameters(event):
    values = {item["name"]: item["value"] for item in event.get("parameters", [])}
    missing = [name for name in ("owner", "repo", "pr_number") if not values.get(name)]
    if missing:
        raise RequestError(400, f"Missing required parameters: {', '.join(missing)}")
    try:
        pr_number = int(values["pr_number"])
    except (TypeError, ValueError):
        raise RequestError(400, "pr_number must be an integer")
    if pr_number <= 0:
        raise RequestError(400, "pr_number must be positive")
    return values["owner"], values["repo"], pr_number
```

`build_response()`는 `messageVersion`, `actionGroup`, `apiPath`, `httpMethod`,
`httpStatusCode`, JSON 문자열 `body`를 항상 포함한다.

- [ ] **Step 4: GitHub 응답 정규화 실패 테스트 작성**

```python
def test_normalize_pr_limits_files_and_patch_length():
    result = normalize_pr(PR_PAYLOAD, FILES_PAYLOAD, max_files=1, max_patch_chars=10)
    self.assertEqual(len(result["files"]), 1)
    self.assertTrue(result["files_truncated"])
    self.assertEqual(result["files"][0]["patch"], "@@ patch\n")
```

- [ ] **Step 5: PR 정규화 구현**

반환 필드는 `title`, `body`, `state`, `author`, `created_at`, `updated_at`,
`changed_files`, `additions`, `deletions`, `html_url`, `files`,
`files_truncated`, `patches_truncated`로 고정한다. 기본 제한은 파일 20개,
파일별 patch 4,000자, 전체 patch 30,000자다.

- [ ] **Step 6: GitHub 오류 매핑 실패 테스트 작성**

```python
def test_github_404_maps_to_request_error():
    error = HTTPError(url, 404, "Not Found", {}, None)
    with self.assertRaisesRegex(RequestError, "찾을 수 없습니다"):
        map_github_error(error)

def test_rate_limit_maps_to_429_with_reset():
    headers = {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1234"}
    error = HTTPError(url, 403, "Forbidden", headers, None)
    mapped = map_github_error(error)
    self.assertEqual(mapped.status_code, 429)
    self.assertIn("1234", mapped.message)
```

- [ ] **Step 7: GitHub HTTP 클라이언트와 handler 구현**

`github_get()`는 `Accept: application/vnd.github+json`,
`X-GitHub-Api-Version: 2022-11-28`, 식별 가능한 `User-Agent`를 전송한다.
`handler()`는 상세·파일 엔드포인트를 호출하고 `RequestError`, `HTTPError`,
`URLError`, 예상하지 못한 오류를 각각 안전한 Bedrock 응답으로 변환한다.

- [ ] **Step 8: Lambda 테스트 통과**

Run: `.venv/bin/python -m unittest tests.test_github_pr_tool -v`

Expected: 파라미터, 정규화, 제한, 오류 매핑, handler 테스트 모두 `OK`

- [ ] **Step 9: Lambda 로직 커밋**

```bash
git add lambda/github_pr_tool.py tests/test_github_pr_tool.py
git commit -m "feat: add public GitHub PR Lambda tool"
```

### Task 3: OpenAPI 스키마

**Files:**
- Create: `src/github_tool_schema.py`
- Create: `tests/test_github_tool_schema.py`

- [ ] **Step 1: OpenAPI 실패 테스트 작성**

```python
def test_schema_defines_get_github_pr_operation():
    operation = GITHUB_PR_OPENAPI_SCHEMA["paths"]["/github-pr"]["get"]
    self.assertEqual(operation["operationId"], "get_github_pr")
    parameters = {item["name"]: item for item in operation["parameters"]}
    self.assertEqual(set(parameters), {"owner", "repo", "pr_number"})
    self.assertTrue(all(item["required"] for item in parameters.values()))
```

- [ ] **Step 2: 실패 확인 후 스키마 구현**

Run: `.venv/bin/python -m unittest tests.test_github_tool_schema -v`

Expected: 모듈 부재로 실패한 뒤 구현 후 `OK`

스키마는 OpenAPI `3.0.0`, `/github-pr` GET, `get_github_pr` operationId와 세
필수 query 파라미터를 정의한다. description에 PR 조회·변경 분석·코드 리뷰 요청에서
사용한다는 문장을 포함한다.

- [ ] **Step 3: 스키마 커밋**

```bash
git add src/github_tool_schema.py tests/test_github_tool_schema.py
git commit -m "feat: define GitHub PR Action Group schema"
```

### Task 4: Lambda와 Action Group 배포

**Files:**
- Create: `src/setup_github_tool.py`
- Create: `tests/test_setup_github_tool.py`
- Modify: `src/setup_agent.py`
- Modify: `tests/test_setup_agent.py`

- [ ] **Step 1: Lambda ZIP 실패 테스트 작성**

```python
def test_build_lambda_zip_contains_expected_handler(tmp_path):
    archive = build_lambda_zip(ROOT / "lambda" / "github_pr_tool.py")
    with ZipFile(BytesIO(archive)) as zip_file:
        self.assertEqual(zip_file.namelist(), ["github_pr_tool.py"])
```

- [ ] **Step 2: IAM 정책과 Action Group 선택 실패 테스트 작성**

```python
def test_build_lambda_trust_policy_uses_lambda_service():
    policy = build_lambda_trust_policy()
    self.assertEqual(
        policy["Statement"][0]["Principal"]["Service"],
        "lambda.amazonaws.com",
    )

def test_find_action_group_returns_matching_id():
    groups = [{"actionGroupName": "GitHubPRTools", "actionGroupId": "AG1"}]
    self.assertEqual(find_action_group(groups, "GitHubPRTools"), "AG1")
```

- [ ] **Step 3: 실패 확인**

Run: `.venv/bin/python -m unittest tests.test_setup_github_tool -v`

Expected: 배포 모듈 부재로 실패

- [ ] **Step 4: Lambda IAM 역할과 함수 멱등 배포 구현**

다음 함수를 구현한다.

```python
def ensure_lambda_role(iam_client, config) -> str: ...
def build_lambda_zip(source_path: Path) -> bytes: ...
def ensure_lambda_function(lambda_client, role_arn, zip_bytes, config) -> str: ...
def ensure_lambda_permission(lambda_client, function_name, agent_arn, account_id): ...
```

역할에는 AWS 관리 정책 `AWSLambdaBasicExecutionRole`을 연결한다. 함수가 있으면
코드와 설정을 업데이트하고 `function_updated_v2` waiter로 완료를 기다린다.
함수 설정은 Python 3.12, handler `github_pr_tool.handler`, timeout 30초,
memory 256MB다.

- [ ] **Step 5: Agent Instructions 확장 테스트와 구현**

`src/setup_agent.py`의 기본 Instructions에 동일 문자열을 반복 추가하지 않도록
`build_agent_instruction(include_github_tool: bool)` 순수 함수를 도입한다.
도구 지침은 필수 파라미터 누락 시 질문하고 PR 정보·변경 분석 요청에 Tool을
호출하도록 명시한다.

- [ ] **Step 6: Action Group 멱등 배포 구현**

```python
def ensure_action_group(agent_client, agent_id, lambda_arn) -> str: ...
def update_agent_for_github_tool(agent_client, agent_id, config, role_arn): ...
def deploy_github_tool(config=None) -> AgentState: ...
```

기존 Action Group은 `update_agent_action_group`, 없으면
`create_agent_action_group`을 사용한다. DRAFT에 `ENABLED` 상태로 연결하고 OpenAPI
payload는 `json.dumps(GITHUB_PR_OPENAPI_SCHEMA)`로 전달한다.

- [ ] **Step 7: Prepare, Alias, 상태 저장 연결**

5장의 `prepare_agent()`와 `ensure_alias()`를 재사용한다. 배포 완료 후
`.codebuddy/agent-state.json`에 Lambda ARN과 Action Group ID를 저장한다.

- [ ] **Step 8: 전체 로컬 테스트 통과**

Run:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q src lambda tests
git diff --check
```

Expected: 기존 17개와 6장 신규 테스트 모두 `OK`

- [ ] **Step 9: 배포 코드 커밋**

```bash
git add src/setup_github_tool.py src/setup_agent.py \
  tests/test_setup_github_tool.py tests/test_setup_agent.py
git commit -m "feat: automate GitHub PR Action Group deployment"
```

### Task 5: 실제 AWS 배포와 Tool 검증

**Files:**
- Generated: `.codebuddy/agent-state.json`

- [ ] **Step 1: Chapter 5 상태 파일 재생성**

새 worktree에는 ignored 상태 파일이 없으므로 먼저 실행한다.

Run: `.venv/bin/python src/setup_agent.py`

Expected: 기존 Agent `CYGYQHXX1Y`와 Alias `IZKSK9EH2L`를 재사용하고 상태 파일 생성

- [ ] **Step 2: GitHub Tool 첫 배포**

Run: `.venv/bin/python src/setup_github_tool.py`

Expected: Lambda 역할·함수·호출 권한·Action Group 생성, Agent 재-Prepare 완료

- [ ] **Step 3: 두 번째 실행으로 멱등성 확인**

Run: `.venv/bin/python src/setup_github_tool.py`

Expected: 같은 Lambda ARN과 Action Group ID를 재사용

- [ ] **Step 4: Lambda 직접 호출**

Bedrock 이벤트 형식을 JSON으로 구성해 `aws lambda invoke`로 현재 유효한 공개 PR을
조회한다.

Expected: HTTP 200, PR 제목·상태·파일 목록과 patch 포함

- [ ] **Step 5: AWS 리소스 상태 확인**

Run:

```bash
aws lambda get-function --function-name codebuddy-github-pr
aws bedrock-agent list-agent-action-groups \
  --agent-id CYGYQHXX1Y --agent-version DRAFT
aws bedrock-agent get-agent --agent-id CYGYQHXX1Y
aws bedrock-agent get-agent-alias \
  --agent-id CYGYQHXX1Y --agent-alias-id IZKSK9EH2L
```

Expected: Lambda Active, Action Group ENABLED, Agent/Alias PREPARED

- [ ] **Step 6: Agent Tool 호출과 Trace**

Run:

```bash
.venv/bin/python src/invoke_agent.py --trace \
  --prompt "octocat/Spoon-Knife PR #<현재번호>를 가져와 변경 내용을 설명해줘"
```

Expected: Trace에 Action Group/Lambda invocation과 observation이 나타나고 실제 PR 요약 반환

### Task 6: README와 최종 검증

**Files:**
- Modify: `README.md`

- [ ] **Step 1: README에 6장 추가**

Lambda → GitHub API → Agent 흐름, 공개 API 시간당 60회 제한, 배포 명령, Lambda
직접 테스트, Agent Tool/Trace 시연 명령, 생성 리소스 이름을 기록한다.

- [ ] **Step 2: 최종 검증**

Run:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q src lambda tests
git diff --check
git status --short
```

Expected: 모든 검증 성공, `.codebuddy/`는 Git 상태에 나타나지 않음

- [ ] **Step 3: 문서 커밋**

```bash
git add README.md
git commit -m "docs: document GitHub PR Tool chapter 6"
```
