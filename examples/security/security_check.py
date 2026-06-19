"""Chapter 4 learning example: check source code against OWASP guidance."""

import boto3

kb_id = "Q1ZYRCWLIW"

def check_security(code, kb_id):
    """보안 취약점 검사"""
    bedrock_agent_client = boto3.client('bedrock-agent-runtime', region_name='ap-northeast-2')
    
    prompt = f"""다음 코드에서 보안 취약점을 찾아주세요. 특히 SQL Injection, XSS, 하드코딩된 비밀번호를 중점적으로 검사해주세요.
코드:
{code}
취약점이 있으면 위치, 유형, 심각도, 수정 제안을 포함해 주세요."""

    response = bedrock_agent_client.retrieve_and_generate(
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

if __name__ == "__main__":
    vulnerable_code = """def get_user_by_name(username):
    query = "SELECT * FROM users WHERE name = '" + username + "'"
    cursor.execute(query)"""
    
    print(check_security(vulnerable_code, kb_id))
