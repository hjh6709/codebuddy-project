import boto3

kb_id = "Q1ZYRCWLIW"

def style_check(code, kb_id):
    """코드 스타일 검사 후 위반 사항 리스트 반환"""
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

if __name__ == "__main__":
    samples = [
        "def add(a,b): return a+b",
        "def GetUserData(): pass",
        "import os, sys",
        "x = 1\ny = 2\nz=x+y",
        "def long_function_name_very_long_parameter_list(param1, param2, param3, param4, param5): pass"
    ]
    
    for i, code in enumerate(samples, 1):
        print(f"\n=== 샘플 {i} ===")
        print(f"코드: {code}")
        result = style_check(code, kb_id)
        print(f"결과: {result[:200]}...")
