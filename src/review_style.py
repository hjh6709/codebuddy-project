import boto3

bedrock = boto3.client('bedrock-agent-runtime', region_name='ap-northeast-2')

KB_ID = "Q1ZYRCWLIW"

def check_code_style(code, kb_id):
    prompt = f"""
다음 코드가 PEP8 스타일 가이드를 위반하는 부분이 있다면 알려주세요.
위반 사항이 없으면 "통과"라고 답변해주세요.

코드:
{code}
"""
    response = bedrock.retrieve_and_generate(
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
    target_code = """
def add(a,b):
    return a+b
"""
    try:
        result = check_code_style(target_code, KB_ID)
        print(result)
    except Exception as e:
        print(f"오류 발생: {e}")
