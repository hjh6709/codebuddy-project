# Bedrock Agent 6장 GitHub PR Tool 구현 설계

## 목표

5장에서 배포한 `CodeBuddy-Reviewer` Agent에 공개 GitHub Pull Request를 조회하는
`get_github_pr` 도구를 추가한다. Agent는 자연어 요청에서 저장소 소유자, 저장소
이름, PR 번호를 추출하고 Lambda를 호출한 뒤 PR 정보와 변경 코드를 설명해야 한다.

## 범위

이번 구현은 6장 범위인 첫 번째 Action Group만 다룬다.

- 공개 GitHub PR 상세 정보 조회
- PR 변경 파일 목록과 patch 조회
- Lambda 함수 및 실행 역할 생성 또는 업데이트
- Lambda에 Bedrock Agent 호출 권한 추가
- OpenAPI 스키마 기반 Action Group 생성 또는 업데이트
- Agent Instructions에 도구 사용 규칙 추가
- Agent 재-Prepare 및 기존 `dev` Alias 갱신
- Lambda 직접 테스트와 Agent Tool 호출·Trace 검증

비공개 저장소, PR 댓글 작성, Slack 알림, 저장소 목록 조회는 이번 범위에서 제외한다.

## 인증과 제한

GitHub 토큰을 사용하지 않고 공개 GitHub REST API를 호출한다. 따라서 비밀정보를
코드, Lambda 환경변수, Secrets Manager에 저장하지 않는다.

인증되지 않은 GitHub REST API 요청은 공개 데이터만 조회할 수 있고 원본 IP 기준
시간당 60회로 제한된다. 시연과 수업 실습에는 충분하며, 한 번의 Tool 호출은 PR
상세와 변경 파일 조회를 위해 최소 두 번의 GitHub API 요청을 사용한다.

## 구성

### `lambda/github_pr_tool.py`

Lambda에서 실행되는 실제 도구 코드다. Python 표준 라이브러리 `urllib`만 사용하여
외부 의존성이 없는 작은 ZIP 패키지를 만든다.

Bedrock Agent 이벤트에서 다음 파라미터를 읽는다.

- `owner`: GitHub 사용자 또는 조직
- `repo`: 저장소 이름
- `pr_number`: Pull Request 번호

GitHub API의 다음 엔드포인트를 호출한다.

- `GET /repos/{owner}/{repo}/pulls/{pr_number}`
- `GET /repos/{owner}/{repo}/pulls/{pr_number}/files`

최종 응답에는 PR 제목, 설명, 상태, 작성자, 생성·수정 시각, 변경 파일 수, 추가·삭제
줄 수, 웹 URL, 변경 파일별 파일명·상태·추가·삭제 줄 수·patch를 포함한다.

patch가 너무 길어 Agent 입력이 비대해지지 않도록 파일별 patch와 전체 응답 크기에
상한을 둔다. 변경 파일 페이지는 시연에 필요한 범위까지만 조회하고 잘렸다는 표시를
응답에 포함한다.

### `src/github_tool_schema.py`

Action Group이 사용하는 OpenAPI 3.0 스키마를 순수 Python 데이터로 제공한다.
`description`에는 PR 정보 요청, 코드 변경 분석, 리뷰 요청일 때 이 도구를 사용해야
한다고 명확히 기술한다.

### `src/setup_github_tool.py`

다음 AWS 리소스를 멱등적으로 생성하거나 업데이트한다.

- Lambda 실행 IAM 역할
- `codebuddy-github-pr` Lambda 함수
- Bedrock Agent가 Lambda를 호출할 수 있는 리소스 기반 정책
- `GitHubPRTools` Action Group
- Agent Instructions
- Agent Prepare와 `dev` Alias

기존 5장의 `.codebuddy/agent-state.json`에서 Agent ID와 Alias ID를 읽는다. Lambda
함수의 ARN과 Action Group ID는 같은 상태 파일에 추가 저장한다.

### `src/invoke_agent.py`

기존 호출기를 그대로 사용한다. 6장 시연 명령과 Trace 출력 예시만 README에 추가한다.

## 데이터 흐름

1. 사용자가 `octocat/Spoon-Knife PR #40222를 가져와서 변경 내용을 설명해줘`라고 요청한다.
2. Agent가 OpenAPI 설명을 읽고 `get_github_pr` 호출을 선택한다.
3. Agent가 `owner`, `repo`, `pr_number`를 Lambda 이벤트로 전달한다.
4. Lambda가 GitHub 공개 REST API에서 PR 상세와 변경 파일을 조회한다.
5. Lambda가 Bedrock Agent 공식 응답 형식으로 결과를 반환한다.
6. Agent가 Tool 결과를 요약하고 필요하면 Knowledge Base의 코드 규칙과 함께 설명한다.

필수 파라미터가 없으면 Agent Instructions에 따라 사용자의 추가 입력을 요청한다.

## Lambda 응답 형식

성공과 실패 모두 다음 외곽 구조를 사용한다.

```json
{
  "messageVersion": "1.0",
  "response": {
    "actionGroup": "GitHubPRTools",
    "apiPath": "/github-pr",
    "httpMethod": "GET",
    "httpStatusCode": 200,
    "responseBody": {
      "application/json": {
        "body": "{\"title\":\"...\"}"
      }
    }
  }
}
```

`body`는 Bedrock Agent Lambda 계약에 맞춘 JSON 문자열로 반환한다.

## IAM 설계

Lambda 실행 역할은 CloudWatch Logs 작성 권한만 가진다. GitHub API는 공개 HTTPS
요청이므로 별도의 AWS 서비스 권한이 필요하지 않다.

Lambda 함수 리소스 정책은 다음 조건으로 제한한다.

- Principal: `bedrock.amazonaws.com`
- Action: `lambda:InvokeFunction`
- SourceArn: 현재 계정과 서울 리전의 `CodeBuddy-Reviewer` Agent ARN
- SourceAccount: 현재 AWS 계정

5장의 Agent 서비스 역할에는 Lambda 호출 권한을 추가하지 않는다. Bedrock Agent의
Lambda 호출은 함수 리소스 기반 정책으로 허용한다.

## 오류 처리

- 필수 파라미터 누락: HTTP 400
- PR 또는 저장소 없음: GitHub 404를 HTTP 404로 변환
- GitHub API 제한 초과: HTTP 429와 reset 시각 제공
- GitHub 서버 또는 네트워크 오류: HTTP 502
- Bedrock 이벤트 형식 오류: HTTP 400
- 예상하지 못한 오류: HTTP 500, 내부 토큰·헤더·환경 정보는 응답에서 제외

CloudWatch 로그에는 이벤트 경로, 저장소, PR 번호, GitHub 상태 코드와 처리 시간을
기록하되 인증 정보는 기록하지 않는다.

## 테스트

### 로컬 단위 테스트

- Bedrock 파라미터 추출
- 성공 응답과 오류 응답 형식
- GitHub PR 상세·파일 응답 정규화
- patch 및 파일 수 제한
- GitHub 404·403/429·네트워크 오류 매핑
- OpenAPI 스키마 필수 필드
- Lambda ZIP에 `github_pr_tool.py`가 올바른 핸들러 경로로 포함되는지 확인

### 실제 AWS 검증

- Lambda 직접 호출로 공개 PR 조회
- 같은 설정 스크립트 두 번 실행해 멱등성 확인
- Action Group `ENABLED`, Agent와 Alias `PREPARED` 확인
- Agent에게 공개 PR 조회 요청
- Trace에서 Action Group 호출, Lambda 결과, 최종 응답 확인

시연 대상은 구현 시점에 유효한 공개 PR을 다시 조회해 결정한다. 현재 확인된 후보는
`octocat/Spoon-Knife#40222`다.

## 제출 연계

README에 6장 아키텍처, 배포 명령, Lambda 직접 테스트, Agent Tool 호출 및 Trace
명령을 추가한다. 시연 영상에서는 자연어 요청이 Lambda와 GitHub API를 거쳐 실제
PR 정보로 반환되는 흐름을 보여준다.
