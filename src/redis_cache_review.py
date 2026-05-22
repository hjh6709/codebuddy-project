import redis
import hashlib
import boto3
import time

kb_id = "Q1ZYRCWLIW"

# Redis 데이터베이스 연결 설정
cache = redis.Redis(host='localhost', port=6379, decode_responses=True)

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

def cached_code_review(code, kb_id, ttl_seconds=3600):
    """MD5 해시 기반 캐싱 검사 레이어 (1시간 TTL 적용)"""
    # 입력 코드 고유 해시 생성
    code_hash = hashlib.md5(code.encode()).hexdigest()
    cache_key = f"code_review:{code_hash}"

    # 메모리 내 캐시 존재 여부 확인
    cached = cache.get(cache_key)
    if cached:
        print(" 내부 캐시에서 결과 반환 (비용 0원)")
        return cached

    # 캐시 미스 발생 시 실제 RAG 엔드포인트 호출
    print(" RAG 검사 실행...")
    result = style_check(code, kb_id)

    # 결과를 Redis 캐시에 적재
    cache.setex(cache_key, ttl_seconds, result)
    return result

if __name__ == "__main__":
    test_code = "def add(a, b): return a + b"
    
    print("--- [테스트 1] 첫 번째 요청 시도 ---")
    first_run = cached_code_review(test_code, kb_id)
    print(f"결과 요약: {first_run[:60]}...")
    
    print("\n--- [테스트 2] 동일 코드 두 번째 요청 시도 ---")
    second_run = cached_code_review(test_code, kb_id)
    print(f"결과 요약: {second_run[:60]}...")
