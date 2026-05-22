import boto3

kb_id = "Q1ZYRCWLIW"

# Bedrock 런타임 클라이언트 생성 (서울 리전)
bedrock_runtime_client = boto3.client('bedrock-runtime', region_name='ap-northeast-2')

def get_claude_response(user_message):
    """지정된 메시지로 Claude 모델을 호출하여 답변을 반환"""
    response = bedrock_runtime_client.converse(
        modelId='global.anthropic.claude-sonnet-4-6',
        messages=[{"role": "user", "content": [{"text": user_message}]}]
    )
    return response['output']['message']['content'][0]['text']

def filter_by_relevance(kb_id, question, threshold=0.7):
    """관련성 점수가 threshold 미만인 문서는 제외하고 LLM 호출"""
    # Bedrock Agent Runtime 클라이언트를 명시적으로 생성
    bedrock_agent_client = boto3.client('bedrock-agent-runtime', region_name='ap-northeast-2')
    
    # 먼저 검색 결과 가져오기 (생성 없이)
    response = bedrock_agent_client.retrieve(
        knowledgeBaseId=kb_id,
        retrievalQuery={'text': question},
        retrievalConfiguration={
            'vectorSearchConfiguration': {
                'numberOfResults': 10
            }
        }
    )
    
    # 점수 높은 문서만 필터링
    filtered_docs = []
    for r in response['retrievalResults']:
        if r['score'] >= threshold:
            filtered_docs.append(r['content']['text'])
            
    # 필터링된 문서로 컨텍스트 구성 후 LLM 호출
    context = "\n\n".join(filtered_docs)
    final_prompt = f"참고 문서:\n{context}\n\n질문: {question}"
    
    return get_claude_response(final_prompt)

if __name__ == "__main__":
    # 테스트 실행
    print(filter_by_relevance(kb_id, "SQL Injection 방지", threshold=0.7))
