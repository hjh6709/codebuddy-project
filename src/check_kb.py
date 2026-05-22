import boto3

# 지식 기반 및 에이전트 관리를 위한 bedrock-agent 클라이언트 생성
bedrock_agent = boto3.client('bedrock-agent', region_name='ap-northeast-2')

print("⏳ 현재 AWS 서울 리전에 생성된 지식 기반(Knowledge Base) 목록을 불러오는 중...")

try:
    # 생성된 KB 목록 가져오기
    response = bedrock_agent.list_knowledge_bases()
    
    print("\n[📊 연결된 지식 기반 목록]")
    for kb in response['knowledgeBaseSummaries']:
        print(f"✅ ID: {kb['knowledgeBaseId']} | 이름: {kb['name']} | 상태: {kb['status']}")
except Exception as e:
    print(f"❌ 목록을 가져오는 중 오류가 발생했습니다: {e}")
