import boto3
import time

# Bedrock Agent 클라이언트 생성
bedrock_agent = boto3.client('bedrock-agent', region_name='ap-northeast-2')

# 확인된 고유 ID 설정
KB_ID = "Q1ZYRCWLIW"
DS_ID = "E80KSQKFP6"

def sync_knowledge_base(knowledge_base_id, data_source_id):
    """Knowledge Base 데이터 소스 동기화"""
    response = bedrock_agent.start_ingestion_job(
        knowledgeBaseId=knowledge_base_id,
        dataSourceId=data_source_id
    )
    print(f"동기화 작업 ID: {response['ingestionJob']['ingestionJobId']}")
    return response

def get_sync_status(knowledge_base_id, data_source_id, job_id):
    """동기화 상태 확인"""
    response = bedrock_agent.get_ingestion_job(
        knowledgeBaseId=knowledge_base_id,
        dataSourceId=data_source_id,
        ingestionJobId=job_id
    )
    status = response['ingestionJob']['status']
    print(f"상태: {status}")
    return status


if __name__ == "__main__":
    print(f"Knowledge Base '{KB_ID}'의 데이터 소스 '{DS_ID}' 동기화 시작...")
    try:
        # 동기화 작업 생성
        sync_response = sync_knowledge_base(KB_ID, DS_ID)
        ingestion_job_id = sync_response['ingestionJob']['ingestionJobId']

        print("\nIngestion Job 완료 대기 중...")
        while True:
            status = get_sync_status(KB_ID, DS_ID, ingestion_job_id)
            
            if status == 'COMPLETE':
                print("Ingestion Job이 성공적으로 완료되었습니다!")
                break
            elif status == 'FAILED':
                print("Ingestion Job이 실패했습니다. AWS 콘솔에서 자세한 오류를 확인하세요.")
                break
            elif status == 'ABORTED':
                print("Ingestion Job이 중단되었습니다.")
                break
            else:
                print(f"현재 상태: {status}. 10초 후 다시 확인합니다.")
                time.sleep(10)

        print("\n이제 Knowledge Base가 문서 인덱싱을 완료했습니다. 다시 질문을 시도해 보세요.")

    except Exception as e:
        print(f"오류가 발생했습니다: {e}")
