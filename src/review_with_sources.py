import boto3

# 전역 변수를 소문자로 선언하여 교안 코드와 매칭
kb_id = "Q1ZYRCWLIW"

def check_with_sources (code, kb_id):
    """코드 검사 + 어떤 문서가 사용됐는지 출력 """
    bedrock_agent_client = boto3.client('bedrock-agent-runtime', region_name='ap-northeast-2')
    
    response = bedrock_agent_client.retrieve_and_generate(
        input={'text': f"다음 코드의 PEP8 위반사항을 찾아줘: \n{code}"},
        retrieveAndGenerateConfiguration={
            'type': 'KNOWLEDGE_BASE',
            'knowledgeBaseConfiguration': {
                'knowledgeBaseId': kb_id,
                'modelArn': 'global.anthropic.claude-sonnet-4-6'
            }
        }
    )
    
    print(" 참고한 문서:")
    for result in response.get('retrievedResults', []):
        score = result['score']
        content = result['content']['text'][:150]
        print(f" 관련성 {score:.2f}: {content}...")
        
    print("\n최종 답변:")
    return response['output']['text']

if __name__ == "__main__":
    code = "def calculate(x,y): return x+y"
    print(check_with_sources (code, kb_id))
