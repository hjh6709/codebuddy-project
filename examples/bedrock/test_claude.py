"""Chapter 2 learning example: prompt-based code analysis with Bedrock."""

import boto3
import json

# ==========================================================
# [공통] Bedrock 클라이언트 및 모델 ID 설정
# ==========================================================
bedrock = boto3.client('bedrock-runtime', region_name='ap-northeast-2')
model_id = 'global.anthropic.claude-sonnet-4-6'


# ==========================================================
# 실습 2: 응답에서 텍스트만 추출하는 함수
# ==========================================================
def get_claude_response(user_message):
    response = bedrock.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": user_message}]}]
    )
    return response['output']['message']['content'][0]['text']


# ==========================================================
# 실습 6: 전문가용 프롬프트 템플릿 정의
# ==========================================================
CODE_ANALYSIS_PROMPT = """당신은 실무 경험 10년차 시니어 개발자입니다.
다음 코드를 철저히 분석해주세요.

## 분석 항목
1. **버그 가능성**: 논리적 오류, 예외 처리 누락
2. **보안 취약점**: SQL Injection, XSS 등
3. **코드 스타일**: PEP8, 네이밍 규칙
4. **성능 이슈**: 시간복잡도, 불필요한 연산
5. **리팩토링 제안**: 더 나은 구조 제안

## 출력 형식 (반드시 이 형식을 지켜주세요)
### 버그
- [위치] 문제 설명
### 보안
- [위치] 취약점 설명
### 스타일
- [위치] 수정 제안
### 리팩토링 제안
개선된 코드 예시

분석할 코드:
{code}"""

def analyze_code(code):
    """
    전문가용 템플릿에 타겟 코드를 매핑하고, 
    AWS 콘솔에서 생성한 가드레일 정책을 적용하여 안전하게 분석하는 함수입니다.
    """
    prompt = CODE_ANALYSIS_PROMPT.format(code=code)

    response = bedrock.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={
            'temperature': 0.2,
            'maxTokens': 2000
        },
        # 실습 5: 확인 완료된 가드레일 ID 적용
        guardrailConfig={
            'guardrailIdentifier': 'vlkw80v60yc2', 
            'guardrailVersion': 'DRAFT'
        }
    )
    return response['output']['message']['content'][0]['text']


# ==========================================================
# 메인 실행부
# ==========================================================
if __name__ == "__main__":
    
    # --- 1. 실습 1 테스트 (RAW JSON 출력) ---
    print("--- [실습 1] RAW API 전체 응답 구조 ---")
    response_raw = bedrock.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": "Hello, Claude! 안녕?"}]}]
    )
    print(json.dumps(response_raw, indent=4, ensure_ascii=False))
    
    print("\n" + "="*50 + "\n")
    
    # --- 2. 실습 2 테스트 (텍스트 추출 함수) ---
    print("⏳ [실습 2] Claude에게 'Python이 뭐야?' 질문 던지는 중...")
    answer_text = get_claude_response("Python이 뭐야?")
    print("\n[🤖 Claude Sonnet의 답변]")
    print(answer_text)
    
    print("\n" + "="*50 + "\n")

    # --- 3. 실습 6 & 7 테스트 (전문가 프롬프트 + 실제 코드 분석) ---
    print("⏳ [실습 6 & 7] Claude가 데이터베이스 연동 코드를 정밀 분석 중입니다...")
    
    # 분석 대상 실제 코드
    test_code = """
def add_numbers(a,b):
    result = a + b
    return result
"""
    
    report = analyze_code(test_code)
    print("\n[📊 CodeBuddy 전문가 포맷 분석 보고서]")
    print(report)
