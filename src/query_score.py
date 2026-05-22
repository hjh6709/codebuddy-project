import boto3

# 검색 단독 작업을 위한 런타임 클라이언트 생성
bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name='ap-northeast-2')

# 지식 기반 ID 설정
KB_ID = "Q1ZYRCWLIW"

def retrieve_documents_and_scores(kb_id, question):
    """Knowledge Base에서 관련 문서를 검색하고 점수를 반환합니다."""
    response = bedrock_agent_runtime.retrieve(
        knowledgeBaseId=kb_id,
        retrievalQuery={'text': question}
    )
    return response['retrievalResults']


if __name__ == "__main__":
    # 교안 21p 기준 검증 질의
    question = "파이썬 변수명 규칙"
    print(f"👉 '{question}'에 대한 원본 검색 결과 및 점수를 확인합니다.\n")
    
    try:
        retrieved_results = retrieve_documents_and_scores(KB_ID, question)
        
        if retrieved_results:
            print("-- Retrieved Results (Raw) --")
            for i, result in enumerate(retrieved_results):
                score = result['score']
                content = result['content']['text']
                location = result['location']['s3Location']['uri']
                
                print(f"\n[Result {i+1}]")
                print(f"🎯 관련성 점수: {score:.4f}")
                print(f"📂 출처 주소: {location}")
                print(f"📝 본문 내용: {content.strip()[:200]}...") # 가독성을 위해 앞부분만 절삭 출력
        else:
            print("❌ 검색된 결과가 없습니다.")
            
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
