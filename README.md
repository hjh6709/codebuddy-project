# 📊 Amazon Bedrock 기반 AI 코드 리뷰 에이전트 실습 정리

> AWS Amazon Bedrock과 Claude Sonnet 4.6 모델을 활용하여 RAG(Retrieval-Augmented Generation) 파이프라인을 구축하고,  
> 코드 스타일 검사 및 보안 취약점 진단을 자동화하는 실습 프로젝트입니다.

---

## 🛠️ 기술 스택

| 구분 | 내용 |
|---|---|
| AI 모델 | Claude Sonnet 4.6 (`global.anthropic.claude-sonnet-4-6`) |
| AWS 서비스 | Amazon Bedrock, Bedrock Agent Runtime, S3, Knowledge Base |
| 리전 | 서울 (`ap-northeast-2`) |
| 캐싱 | Redis (인메모리 중복 요청 차단) |
| 언어 | Python 3.x |

---

## 📂 프로젝트 구조

```
codebuddy-project/
├── requirements.txt          # 패키지 의존성 명세
├── test_bedrock.py           # Bedrock 최초 연결 테스트
├── test_claude.py            # Claude 호출 및 가드레일 적용 실습
├── src/
│   ├── compare_models.py
│   ├── upload_with_metadata.py
│   ├── start_sync.py / check_status.py / check_kb.py
│   ├── query_kb.py / query_score.py
│   ├── style_check.py / review_style.py / review_with_sources.py
│   ├── multi_sample_check.py
│   ├── security_check.py / security_report_generator.py / security_report.json
│   ├── semantic_search.py / topk_tuning.py / relevance_filter.py
│   ├── review_multilang.py / redis_cache_review.py / measure_performance.py
│   ├── test_rag.py
│   ├── full_project_review.py
│   ├── project_review_report.md
│   ├── pep8.txt / owasp-top10.txt / airbnb-style.txt
│   └── javascript_airbnb.txt / java_google.txt / golang_effective.txt
```

---

## 📂 [1장] Amazon Bedrock 개요 및 환경 구축

### `requirements.txt`
프로젝트 실행에 필요한 파이썬 패키지 의존성을 명세한 파일입니다.  
`boto3`, `redis` 등 핵심 라이브러리가 포함되어 있습니다.

### `test_bedrock.py`
서울 리전(`ap-northeast-2`)에 Bedrock Runtime 클라이언트를 생성하고,  
`Converse API`를 통해 Claude Sonnet 4.6 모델을 최초로 호출하는 연결 확인용 스크립트입니다.

### `src/compare_models.py`
같은 질문을 **Amazon Titan Text Express v2**와 **Claude 3 Haiku** 두 모델에 동시에 던져,  
응답 스타일과 출력 품질을 나란히 비교하는 모델 비교 실습 스크립트입니다.  
각 모델의 응답 구조 파싱 방식(`invoke_model` → `body.read()`)도 함께 확인합니다.

---

## 📂 [2장] Boto3로 LLM 호출 및 코드 분석 기초

### `test_claude.py`
Bedrock `Converse API`의 응답 객체 구조를 JSON으로 출력하여 분석하고,  
텍스트만 깔끔하게 추출하는 헬퍼 함수(`get_claude_response`)를 구현합니다.  
`temperature`, `maxTokens` 등 추론 파라미터 제어와 **AWS 가드레일(Guardrail)** 정책 적용도 함께 실습합니다.  
전문가용 코드 분석 프롬프트 템플릿을 통해 버그, 보안, 스타일, 성능을 구조화된 포맷으로 진단합니다.

---

## 📂 [3장] RAG 이해 및 Knowledge Base 구축

### `pep8.txt` / `owasp-top10.txt` / `airbnb-style.txt`
RAG 시스템의 지식 원천이 되는 가이드라인 문서입니다.  
각각 Python PEP8 코딩 스타일, OWASP Top 10 보안 위협, Airbnb JavaScript 스타일 규칙을 담고 있습니다.

### `src/upload_with_metadata.py`
로컬 가이드라인 문서를 S3 버킷에 업로드할 때, 언어(`language`) 및 규칙 유형(`rule_type`) 메타데이터 태그를 자동으로 주입하는 스크립트입니다.  
Knowledge Base가 적절한 문서를 검색할 수 있도록 필터 기반 검색을 지원합니다.

### `src/start_sync.py`
Boto3로 Bedrock Knowledge Base의 데이터 소스 동기화(Ingestion Job)를 시작하고,  
동기화 완료까지 상태를 **폴링(polling)** 방식으로 모니터링하는 제어 스크립트입니다.

### `src/check_status.py` / `src/check_kb.py`
Knowledge Base ID와 데이터 소스 ID를 기반으로 AWS 자원 상태 및 과거 동기화 이력을 조회·모니터링하는 보조 스크립트입니다.

### `src/query_kb.py`
`retrieve_and_generate` API를 활용한 기본 지식 기반 질의응답(Q&A) 테스트 스크립트입니다.  
질문을 던지면 Knowledge Base에서 관련 청크를 검색한 뒤 Claude가 답변을 생성합니다.

### `src/query_score.py`
`retrieve` API를 단독으로 호출하여 검색된 청크의 원본 텍스트와 **유사도 점수(Relevance Score)** 를 파싱·출력합니다.  
각 청크가 질문과 얼마나 관련 있는지 점수를 통해 직접 확인할 수 있습니다.

---

## 📂 [4장] RAG로 코드 스타일/보안 검사 구현

### `src/style_check.py` / `src/review_style.py`
Knowledge Base에 저장된 코딩 스타일 가이드를 참조하여, 입력 코드의 규칙 위반 사항을 `[라인번호] 위반 유형: 설명` 형식으로 리포팅하는 스타일 검사 엔진입니다.

### `src/review_with_sources.py`
답변 생성 시 참조한 S3 문서의 **출처 URI**와 **매칭 스코어**를 함께 역추적하여 출력합니다.  
어떤 가이드 문서가 근거가 되었는지 투명하게 확인할 수 있습니다.

### `src/multi_sample_check.py`
의도적으로 규칙을 위반한 코드 샘플 5종을 배열로 구성하고, 반복문으로 각각 스타일 검사를 수행합니다.  
검사 엔진의 정확도와 일관성을 검증하는 용도입니다.

### `src/security_check.py`
OWASP Top 10 기반으로 **SQL Injection, XSS, 하드코딩된 인증 키** 등을 탐지하는 보안 진단 모듈입니다.  
`retrieve_and_generate` API를 통해 Knowledge Base의 OWASP 가이드를 참조하여 취약점을 진단합니다.

### `src/security_report_generator.py`
보안 진단 결과를 위치(`line`), 유형(`type`), 심각도(`severity`), 수정 제안(`suggestion`)이 포함된  
**규격화된 JSON 포맷**으로 저장하는 리포트 생성 스크립트입니다.

### `src/security_report.json`
`security_report_generator.py`가 생성한 취약점 분석 결과 JSON 파일 본체입니다.  
SQL Injection(CRITICAL), 과도한 데이터 노출(MEDIUM), 입력값 검증 누락(HIGH) 등 항목이 정형화되어 저장됩니다.

### `src/semantic_search.py`
`retrievalConfiguration`의 `overrideSearchType`을 `SEMANTIC`으로 고정하여,  
단순 키워드 매칭이 아닌 **의미 기반 벡터 검색** 레이어를 적용하는 실습 스크립트입니다.

### `src/topk_tuning.py`
`numberOfResults` 파라미터를 3, 5, 10으로 변경하며 검색 결과 분량과 노이즈 수준을 비교 튜닝합니다.  
최적의 검색 결과 수를 실험적으로 찾는 데 사용됩니다.

### `src/relevance_filter.py`
`retrieve` API로 먼저 청크를 가져온 뒤, **관련성 점수가 0.7 미만인 문서를 제외**하고  
고품질 청크만 컨텍스트로 조합하여 Claude를 호출하는 필터링 파이프라인입니다.  
노이즈를 줄여 답변 정확도를 높이는 것이 목적입니다.

### `javascript_airbnb.txt` / `java_google.txt` / `golang_effective.txt`
다국어 지원을 위한 언어별 로컬 스타일 가이드 문서입니다.  
각각 JavaScript(Airbnb 스타일), Java(Google 스타일), Go(Effective Go) 컨벤션을 담고 있습니다.

### `src/review_multilang.py`
입력 코드의 언어(JavaScript, Java, Go)를 파라미터로 받아, 해당 언어에 맞는 스타일 가이드를  
Knowledge Base에서 동적으로 매칭하여 검사하는 **다중 언어 공통 검사 모듈**입니다.

### `src/redis_cache_review.py`
동일한 코드에 대한 중복 요청을 차단하기 위해 **MD5 해시 키** 기반 Redis 캐싱 레이어를 구현합니다.  
캐시 히트 시 RAG 호출 없이 저장된 결과를 즉시 반환하여 **API 비용을 0으로** 절감합니다.  
기본 TTL은 1시간(`3600초`)이며, 첫 번째와 두 번째 동일 요청의 동작 차이를 확인할 수 있습니다.

### `src/measure_performance.py`
`time` 모듈을 활용하여 RAG 파이프라인의 **응답 지연시간(Latency)** 을 계측하고,  
사용된 토큰 수를 기반으로 소수점 달러 단위의 예상 비용을 시뮬레이션합니다.

### `src/test_rag.py`
RAG 전체 파이프라인(검색 → 컨텍스트 구성 → 생성)을 통합하여 샌드박스 환경에서 테스트하는 스크립트입니다.

### `src/full_project_review.py`
4장 실습의 종합 자동화 스크립트입니다.  
실제 서비스 프로젝트(**Cledyu 프로젝트**)의 지정된 TypeScript/Go 파일들을 순회하며  
스타일 검사와 보안 취약점 진단을 일괄 수행하고, 결과를 마크다운 리포트로 저장합니다.

```
대상 파일 (Cledyu 프로젝트):
- apps/web/app/(platform)/labs/page.tsx
- apps/web/app/(platform)/layout.tsx
- apps/web/components/lab/LabCard.tsx
- apps/web/components/ui/Navbar.tsx
- apps/api/internal/api/handlers/lab.go
```

### `src/project_review_report.md`
`full_project_review.py` 실행 결과로 생성된 **종합 코드 리뷰 최종 보고서**입니다.  
파일별 스타일 위반 사항과 보안 취약점이 마크다운 형태로 구조화되어 있습니다.  
예: `labs/page.tsx`에서 배열 인덱스를 React key로 사용하는 문제, `<Suspense>` fallback 누락 등이 탐지되었습니다.

---

## 🔄 전체 아키텍처 흐름

### [사전 작업] Knowledge Base 구축

```
가이드 문서 (pep8.txt, owasp-top10.txt, airbnb-style.txt ...)
        ↓ upload_with_metadata.py
  S3 버킷 (언어/규칙 유형 메타데이터 태그 포함)
        ↓ start_sync.py
  Amazon Bedrock Knowledge Base (벡터 임베딩 인덱싱)
```

### [런타임] 코드 검사 파이프라인

```
                     입력 코드 + 프롬프트
                            ↓
              ┌─────────────────────────────┐
              │  Amazon Bedrock             │
              │  Knowledge Base (벡터 검색) │
              └─────────────────────────────┘
                 ↙                       ↘
  [경로 A] retrieve API             [경로 B] retrieve_and_generate API
  관련 청크 + 유사도 점수 반환        검색 + Claude 생성 통합 처리
  → relevance_filter.py              → style_check.py
    (0.7 미만 청크 제거)              → security_check.py
  → Claude 직접 호출                 → review_multilang.py
       ↓                                      ↓
       └──────────────┬───────────────────────┘
                      ↓
            스타일 위반 / 보안 취약점 진단 결과
                      ↓
        ┌─────────────────────────────────┐
        │ security_report.json            │
        │ project_review_report.md        │
        └─────────────────────────────────┘
```

---

## 📋 실습 강의 자료

본 프로젝트는 아래 4개 강의 PDF 실습 내용을 기반으로 작성되었습니다.

| 챕터 | 강의명 |
|---|---|
| 1장 | Amazon Bedrock 개요 및 환경 구축 |
| 2장 | Boto3로 LLM 호출 및 코드 분석 기초 |
| 3장 | RAG 이해 및 Knowledge Base 구축 |
| 4장 | RAG로 코드 스타일/보안 검사 구현 |
