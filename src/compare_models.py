import boto3
import json

# Bedrock 런타임 클라이언트 생성
bedrock = boto3.client('bedrock-runtime', region_name='ap-northeast-2')

def get_claude_response(user_message):
    """
    invoke_model 방식을 사용하여 Claude 3 하이쿠/소넷 모델을 호출하고 응답을 파싱합니다.
    """
    # 강의 자료의 구조에 맞춰 하이쿠 또는 소넷 지정 (여기서는 3 Haiku/Sonnet 계열 기준)
    model_id = 'anthropic.claude-3-haiku-20240307-v1:0' 
    
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 500,
        "messages": [
            {
                "role": "user",
                "content": user_message
            }
        ]
    })
    
    try:
        response = bedrock.invoke_model(
            modelId=model_id,
            body=body
        )
        
        # 핵심 경로: response -> body -> read() -> JSON 파싱 -> content[0]['text']
        result = json.loads(response['body'].read())
        return result['content'][0]['text']
        
    except Exception as e:
        return f"Claude 에러: {e}"

def call_titan(prompt):
    """
    invoke_model 방식을 사용하여 Amazon Titan Text 최신 모델을 호출하고 응답을 파싱합니다.
    """
    # 에러가 난 구버전(v1) 대신 v2 또는 현재 리전 지원 아이디로 변경합니다.
    # 만약 v2:0도 에러가 난다면 Bedrock 콘솔의 Model Catalog에서 정확한 ID를 확인해야 합니다.
    model_id = 'amazon.titan-text-express-v2:0'
    
    body = json.dumps({
        "inputText": prompt,
        "textGenerationConfig": {
            "maxTokenCount": 500,
            "temperature": 0.7
        }
    })
    
    try:
        response = bedrock.invoke_model(
            modelId=model_id,
            body=body
        )
        
        result = json.loads(response['body'].read())
        # Titan 모델에 따라 출력 키가 'outputText'인 경우와 구조가 살짝 다를 수 있습니다.
        return result['results'][0]['outputText']
        
    except Exception as e:
        return f"Titan 에러: {e}"
# ==========================================
# 메인 실행부: 두 모델 비교 테스트
# ==========================================
if __name__ == "__main__":
    query = "Python이 뭐야?"
    print(f"❓ 질문: {query}\n")
    
    print("⏳ Claude 응답 요청 중...")
    claude_res = get_claude_response(query)
    print(f"\n[🤖 Claude Sonnet/Haiku]")
    print(claude_res)
    
    print("\n" + "="*50 + "\n")
    
    print("⏳ Titan 응답 요청 중...")
    titan_res = call_titan(query)
    print(f"\n[🐯 Amazon Titan]")
    print(titan_res)
