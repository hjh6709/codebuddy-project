# CodeBuddy Agent

AWS Bedrock Agent가 GitHub Pull Request를 자동 분석하고, 리뷰 댓글과 Slack 알림을 전달하는 서버리스 코드 리뷰 시스템입니다.

GitHub Webhook이 PR 생성 또는 코드 변경을 감지하면 API Gateway와 Lambda를 거쳐 Bedrock Agent를 비동기로 호출합니다. Agent는 GitHub 변경사항, Knowledge Base의 스타일·보안 문서, 코드 분석 Tool을 활용해 리뷰를 작성합니다.

## 주요 기능

- GitHub PR 생성·재오픈·코드 변경 시 자동 리뷰
- 버그, 보안, 스타일, 복잡도, 테스트 누락 분석
- GitHub PR에 Markdown 리뷰 댓글 작성
- Slack 채널에 리뷰 완료 알림 전송
- API Gateway `/review`를 통한 수동 리뷰 요청
- HMAC-SHA256 기반 GitHub Webhook 검증
- CloudFormation 기반 서버리스 배포

## 아키텍처

```text
GitHub Pull Request
        │ webhook
        ▼
API Gateway /webhook/github
        │ HMAC 검증
        ▼
Orchestrator Lambda
        │ 비동기 호출
        ▼
Review Worker Lambda
        │ InvokeAgent
        ▼
Amazon Bedrock Agent
   ├── Knowledge Base
   └── CodeBuddy Tools Lambda
          ├── GitHub PR 조회·댓글
          ├── 복잡도 분석
          ├── 테스트 생성
          ├── 리팩터링 제안
          └── Slack 알림
```

## 저장소 구조

```text
.
├── README.md
├── cloudformation/
│   └── codebuddy-serverless.yaml
├── docs/
│   └── api-spec.yaml
├── lambda/
│   ├── codebuddy_orchestrator.py
│   ├── codebuddy_review_worker.py
│   └── codebuddy_tools.py
├── src/
│   ├── agent_config.py
│   ├── codebuddy_tool_schema.py
│   ├── invoke_agent.py
│   ├── setup_agent.py
│   ├── setup_codebuddy_tools.py
│   └── setup_serverless.py
├── knowledge-base/
│   ├── pep8.txt
│   ├── owasp-top10.txt
│   ├── airbnb-style.txt
│   ├── javascript_airbnb.txt
│   ├── java_google.txt
│   └── golang_effective.txt
├── tests/
└── examples/
```

`examples/`는 1~6장 대표 실습을 보존한 학습용 코드이며 배포 대상이 아닙니다.

## 사전 준비

- Python 3.12 이상
- AWS CLI 로그인 및 Bedrock 사용 권한
- GitHub Personal Access Token
- Slack Incoming Webhook URL
- 기존에 생성한 Amazon Bedrock Knowledge Base ID

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
aws sts get-caller-identity
gh auth status
```

민감정보는 Git에 커밋하지 않습니다.

```bash
export AWS_REGION=ap-northeast-2
export CODEBUDDY_KB_ID="<knowledge-base-id>"
export GITHUB_TOKEN="<github-token>"
export SLACK_WEBHOOK_URL="<slack-incoming-webhook>"
export CODEBUDDY_GITHUB_REPOSITORY="owner/repository"
```

## 배포

### 1. Bedrock Agent 생성

```bash
python -m src.setup_agent
```

Agent ID, Alias ID 등은 Git에서 제외된 `.codebuddy/agent-state.json`에 저장됩니다.

### 2. 통합 Tool 배포

```bash
python -m src.setup_codebuddy_tools
```

GitHub PR 조회·댓글, Slack 알림, 코드 분석 기능을 하나의 Lambda 및 Agent Action Group으로 구성합니다.

### 3. 서버리스 API와 GitHub Webhook 배포

```bash
python -m src.setup_serverless
```

이 명령은 다음 리소스를 생성하거나 업데이트합니다.

- API Gateway REST API
- Orchestrator Lambda
- Review Worker Lambda
- IAM 역할과 최소 권한 정책
- API Key와 Usage Plan
- Secrets Manager Webhook Secret
- GitHub Repository Webhook

## API

전체 요청·응답 및 오류 코드는
[OpenAPI 3.0 명세](docs/api-spec.yaml)에서 확인할 수 있습니다.

### 수동 PR 리뷰

```http
POST /prod/review
Content-Type: application/json
x-api-key: <api-key>
```

```json
{
  "pr_url": "https://github.com/owner/repository/pull/1",
  "notify_slack": true
}
```

성공 응답:

```json
{
  "message": "CodeBuddy review started",
  "status": "processing",
  "repository": "owner/repository",
  "pr_number": 1
}
```

### GitHub Webhook

```http
POST /prod/webhook/github
X-GitHub-Event: pull_request
X-Hub-Signature-256: sha256=<hmac-signature>
```

지원 이벤트:

- `opened`
- `reopened`
- `synchronize`

Webhook Secret은 Secrets Manager에서 생성되며 저장소나 상태 파일에 평문으로 저장되지 않습니다.

## 테스트

```bash
python -m unittest discover -s tests -v
```

테스트 범위:

- Agent 및 Action Group 설정
- GitHub·Slack Tool
- PR URL과 입력 검증
- HMAC Webhook 검증
- 비동기 Lambda 호출
- CloudFormation 보안·스로틀링·배포 구조

CloudFormation 검증:

```bash
aws cloudformation validate-template \
  --template-body file://cloudformation/codebuddy-serverless.yaml
```

## 시연 순서

1. 기능 브랜치에서 Pull Request를 생성합니다.
2. GitHub Webhook delivery가 `202`를 반환합니다.
3. CodeBuddy가 PR에 자동 리뷰 댓글을 작성합니다.
4. Slack `codebuddy-alert` 채널에 완료 알림이 도착합니다.
5. 리뷰 지적사항을 수정하고 push합니다.
6. `synchronize` 이벤트로 CodeBuddy가 자동 재리뷰합니다.

실제 검증에는 PR #9의 생성·수정·재리뷰 흐름을 사용했습니다.

## 보안

- GitHub Webhook HMAC-SHA256 검증
- `hmac.compare_digest`를 이용한 타이밍 공격 방지
- API Key 및 계층별 throttling 적용
- IAM 리소스 범위 최소화
- S3 배포 산출물 서버 측 암호화
- Webhook Secret의 Secrets Manager 저장
- `.env`, `.codebuddy/`, worktree 및 캐시 파일 Git 제외

## 제출물

- GitHub Repository: 전체 소스 코드와 CloudFormation
- README: 설치, 배포, API, 테스트, 시연 가이드
- 데모 영상: PR 생성 → 자동 리뷰 → Slack → 수정 → 재리뷰
- 발표 자료: 5장 이내 PPT
