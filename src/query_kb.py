import boto3

# Bedrock Agent Runtime 클라이언트 생성
bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name='ap-northeast-2')

# 지식 기반 ID
KB_ID = "Q1ZYRCWLIW"

def ask_knowledge_base(kb_id, question):
    """Knowledge Base에 질문하고 답변 받기"""
    response = bedrock_agent_runtime.retrieve_and_generate(
        input={'text': question},
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
    # 검증용 질문 리스트
    questions = [
        "파이썬 변수명 규칙은 무엇인가요?",
        "SQL Injection을 방지하는 방법은?",
        "React에서 컴포넌트 이름은 어떻게 짓나요?"
    ]
    
    print("--- [실습 9] Knowledge Base 질문 테스트 ---")
    for q in questions:
        print(f"\n❓ 질문: {q}")
        try:
            answer = ask_knowledge_base(KB_ID, q)
            print(f"🤖 답변:\n{answer}")
        except Exception as e:
            print(f"❌ 오류 발생: {e}")
