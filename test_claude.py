import boto3
import json

bedrock = boto3.client('bedrock-runtime', region_name='ap-northeast-2')

model_id = 'global.anthropic.claude-sonnet-4-6'

response = bedrock.converse(
    modelId=model_id,
    messages=[
        {
            "role": "user",
            "content": [{"text": "Hello, Claude! 안녕?"}]
        }
    ]
)

print(json.dumps(response, indent=4, ensure_ascii=False))

def get_claude_response(user_message):
    """
    사용자의 질문을 받아 Converse API를 호출하고,
    정확히 답변 텍스트만 추출하여 반환하는 함수입니다.
    """
    model_id = 'global.anthropic.claude-sonnet-4-6'
    
    response = bedrock.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": user_message}]}]
    )
    
    # 교안 4p 경로: response -> output -> message -> content[0] -> text
    return response['output']['message']['content'][0]['text']


if __name__ == "__main__":
    print("⏳ Claude에게 질문을 던지는 중입니다...")
    
    # 교안 4p 실습 예시 문항
    query = "Python이 뭐야?"
    answer = get_claude_response(query)
    
    print("\n[🤖 Claude Sonnet의 답변]")
    print(answer)
