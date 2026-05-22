import boto3

kb_id = "Q1ZYRCWLIW"

def search_with_topk(kb_id, question, top_k):
    """numberOfResults(TopK) 파라미터를 동적으로 변경하여 조치"""
    bedrock_agent_client = boto3.client('bedrock-agent-runtime', region_name='ap-northeast-2')
    
    response = bedrock_agent_client.retrieve_and_generate(
        input={'text': question},
        retrieveAndGenerateConfiguration={
            'type': 'KNOWLEDGE_BASE',
            'knowledgeBaseConfiguration': {
                'knowledgeBaseId': kb_id,
                'modelArn': 'global.anthropic.claude-sonnet-4-6',
                'retrievalConfiguration': {
                    'vectorSearchConfiguration': {
                        'numberOfResults': top_k  # 튜닝 대상 파라미터 (1~100)
                    }
                }
            }
        }
    )
    return response['output']['text']

if __name__ == "__main__":
    question = "SQL 인젝션을 방지하기 위한 가이드라인과 코딩 규칙을 자세히 설명해줘."
    
    # 1. 최소 지식만 참조 (TopK = 1)
    print("=== [테스트 1] TopK = 1 설정 ===")
    print(search_with_topk(kb_id, question, top_k=1))
    
    print("\n" + "="*50 + "\n")
    
    # 2. 풍부한 지식 참조 (TopK = 5)
    print("=== [테스트 2] TopK = 5 설정 ===")
    print(search_with_topk(kb_id, question, top_k=5))
