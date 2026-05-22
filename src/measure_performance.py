import boto3
import time

kb_id = "Q1ZYRCWLIW"

def style_check(code, kb_id):
    """지식 기반을 활용한 기본 코드 스타일 검사 수행"""
    bedrock_agent_client_for_rag = boto3.client('bedrock-agent-runtime', region_name='ap-northeast-2')
    
    prompt = f"""당신은 코드 스타일 검사기입니다. 다음 코드에서 PEP8 또는 일반적인 스타일 규칙을 위반한 부분을 찾아주세요.
형식:
[라인번호] 위반 유형: 설명

코드:
{code}"""

    response = bedrock_agent_client_for_rag.retrieve_and_generate(
        input={'text': prompt},
        retrieveAndGenerateConfiguration={
            'type': 'KNOWLEDGE_BASE',
            'knowledgeBaseConfiguration': {
                'knowledgeBaseId': kb_id,
                'modelArn': 'global.anthropic.claude-sonnet-4-6'
            }
        }
    )
    return response['output']['text']

def measure_performance(kb_id, code):
    """RAG 검사 소요 시간 및 예상 비용 측정"""
    start = time.time()
    result = style_check(code, kb_id)
    elapsed = time.time() - start
    
    print(f"⏱️ 소요 시간: {elapsed:.2f}초")
    print(f"📝 결과 길이: {len(result)}자")
    
    # 토큰 수 예측 (공백 기준 샘플 계산)
    tokens = len(code.split()) + len(result.split())
    print(f"💰 예상 비용: 약 ${tokens * 0.00001:.4f}")
    return result

if __name__ == "__main__":
    test_code = "def add(a, b): return a + b"
    
    print("=== [실습 10] RAG 성능 및 비용 분석 측정 ===")
    measure_performance(kb_id, test_code)
