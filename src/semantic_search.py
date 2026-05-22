import boto3

kb_id = "Q1ZYRCWLIW"

def semantic_search_query(kb_id, question):
    """시맨틱 검색 사용"""
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
                        'numberOfResults': 5,
                        'overrideSearchType': 'SEMANTIC'
                    }
                }
            }
        }
    )
    return response['output']['text']

if __name__ == "__main__":
    question = "사용자 입력을 SQL 쿼리에 직접 넣으면 위험해?"
    print("시맨틱 결과:\n", semantic_search_query(kb_id, question))
