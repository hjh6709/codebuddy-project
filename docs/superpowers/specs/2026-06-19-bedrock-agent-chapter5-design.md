# Bedrock Agent 5장 구현 설계

## 목표

3·4장에서 구축한 `code-style-kb` Knowledge Base를 사용하는 코드 리뷰용
Amazon Bedrock Agent를 Boto3로 생성하고 실제 AWS에 배포한다. 동일한 명령을
다시 실행해도 불필요한 Agent, IAM 역할, Alias가 중복 생성되지 않아야 한다.

## 범위

이번 구현은 5장 범위만 다룬다.

- Bedrock Agent 서비스 역할 생성 또는 재사용
- `CodeBuddy-Reviewer` Agent 생성 또는 업데이트
- Knowledge Base `Q1ZYRCWLIW` 연결
- Agent Prepare 완료 대기
- `dev` Alias 생성 또는 업데이트
- Agent 기본 호출, 코드 리뷰 호출, Trace 출력
- 생성된 리소스 식별자를 로컬 상태 파일에 저장

GitHub API Lambda와 Action Group은 6장에서 별도로 구현한다.

## 구성

### `src/setup_agent.py`

AWS 계정 ID를 STS에서 조회하고, Agent 서비스 역할과 최소 권한 인라인 정책을
생성하거나 갱신한다. 이후 이름을 기준으로 기존 Agent를 찾아 업데이트하거나
새로 생성한다. Knowledge Base 연결 여부도 확인한 뒤 필요한 경우에만 연결한다.
Prepare 상태를 폴링하고, 준비가 끝나면 `dev` Alias를 생성하거나 업데이트한다.

생성 결과는 `.codebuddy/agent-state.json`에 기록한다. 이 파일은 계정별 리소스
ID를 포함하므로 Git 추적 대상에서 제외한다.

### `src/invoke_agent.py`

상태 파일에서 Agent ID와 Alias ID를 읽어 `invoke_agent`를 호출한다. 기본 호출,
코드 리뷰 예제, Trace 활성화 호출을 명령행 옵션으로 제공한다. 스트리밍
`completion` 이벤트에서 `chunk`와 `trace`를 구분하여 처리한다.

### 설정

고정 기본값은 다음과 같다.

- 리전: `ap-northeast-2`
- 모델: `global.anthropic.claude-sonnet-4-6`
- Knowledge Base: `Q1ZYRCWLIW`
- Agent 이름: `CodeBuddy-Reviewer`
- Alias 이름: `dev`

환경변수로 기본값을 덮어쓸 수 있게 하여 다른 계정과 환경에서도 재사용한다.

## IAM 설계

Agent 역할의 신뢰 정책은 `bedrock.amazonaws.com`만 역할을 맡을 수 있게 하고,
현재 AWS 계정과 서울 리전의 Agent ARN 조건을 적용한다.

인라인 권한은 다음으로 제한한다.

- Agent 오케스트레이션에 필요한 Bedrock 모델 호출
- 지정된 Knowledge Base 조회

6장의 Lambda 호출 권한은 이번 범위에 포함하지 않는다.

## 실행 흐름

1. 현재 AWS 자격 증명과 Knowledge Base 상태를 검증한다.
2. IAM 역할을 생성하거나 정책을 최신 상태로 갱신한다.
3. IAM 전파를 기다린 뒤 Agent를 생성하거나 업데이트한다.
4. DRAFT Agent에 Knowledge Base를 연결한다.
5. Prepare를 실행하고 `PREPARED` 상태까지 기다린다.
6. `dev` Alias를 생성하거나 업데이트하고 준비 상태를 확인한다.
7. 리소스 ID를 상태 파일에 저장한다.
8. 기본 질문과 취약한 코드 예제로 호출 테스트를 수행한다.
9. Trace에서 Knowledge Base 사용 과정을 확인한다.

## 오류 처리

- AWS 자격 증명, Knowledge Base, 모델 또는 IAM 권한 문제를 구분해 출력한다.
- Agent와 Alias 상태 폴링에는 제한 시간을 둔다.
- `FAILED` 상태에서는 AWS가 제공한 실패 사유와 권장 조치를 출력한다.
- 부분 생성 후 재실행하면 기존 리소스를 찾아 이어서 진행한다.
- 상태 파일이 없거나 손상된 경우 명확한 복구 안내를 제공한다.

## 검증

- Python 구문 검사 및 단위 테스트
- 두 번 연속 설정 스크립트를 실행해 멱등성 확인
- AWS에서 Agent, KB 연결, Alias 상태 조회
- Agent에게 역할을 묻는 기본 호출
- SQL Injection 예제 코드 리뷰 호출
- Trace에서 Knowledge Base 검색 또는 오케스트레이션 이벤트 확인

## 제출 연계

README에 5장 구조, 설정 명령, 호출 예제와 생성 리소스를 추가한다. 시연 영상에서는
설정 스크립트 실행 결과, Agent 호출, 코드 리뷰 답변 및 Trace를 보여줄 수 있다.
