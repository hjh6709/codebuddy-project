import boto3

# Bedrock Agent 클라이언트 생성
bedrock_agent = boto3.client('bedrock-agent', region_name='ap-northeast-2')

# 사용자 Knowledge Base ID 설정
kb_id = "Q1ZYRCWLIW"

print(f"Knowledge Base ID: {kb_id} 상태 확인 중...")
try:
    # 1. Knowledge Base 상세 정보 가져오기 (교안 18p)
    kb_response = bedrock_agent.get_knowledge_base(knowledgeBaseId=kb_id)
    kb_status = kb_response['knowledgeBase']['status']
    kb_name = kb_response['knowledgeBase']['name']
    print(f"\nKnowledge Base '{kb_name}' (ID: {kb_id}) 상태: {kb_status}")

    if kb_status == 'ACTIVE':
        # 2. Knowledge Base에 연결된 데이터 소스 목록 가져오기 (교안 18p)
        ds_response = bedrock_agent.list_data_sources(knowledgeBaseId=kb_id)
        data_sources = ds_response['dataSourceSummaries']
        
        if data_sources:
            print("\n- 연결된 데이터 소스")
            for ds_summary in data_sources:
                data_source_id = ds_summary['dataSourceId']
                data_source_name = ds_summary['name']
                data_source_status = ds_summary['status']
                print(f"  이름: {data_source_name}, ID: {data_source_id}, 상태: {data_source_status}")
                
                # 3. 각 데이터 소스의 마지막 ingestion job 상태 확인 (교안 18p)
                ingestion_jobs_response = bedrock_agent.list_ingestion_jobs(
                    knowledgeBaseId=kb_id,
                    dataSourceId=data_source_id
                )
                ingestion_jobs = ingestion_jobs_response['ingestionJobSummaries']
                
                if ingestion_jobs:
                    latest_job = ingestion_jobs[0]  # 최신 작업 가져오기
                    job_status = latest_job['status']
                    job_start_time = latest_job['startedAt']
                    job_end_time = latest_job.get('endedAt', 'N/A')
                    print(f"  최신 Ingestion Job: 상태={job_status}, 시작={job_start_time}, 종료={job_end_time}")
                    
                    if latest_job.get('failureReasons'):
                        print(f"  실패 이유: {latest_job['failureReasons']}")
                else:
                    print("  - 이 데이터 소스에 대한 Ingestion Job이 없다.")
        else:
            print("\n Knowledge Base에 연결된 데이터 소스가 없다.")
            
    elif kb_status == 'CREATING':
        print("Knowledge Base가 아직 생성 중입니다. 잠시 후 다시 시도해주세요.")
    elif kb_status == 'DELETING':
        print("Knowledge Base가 삭제 중입니다.")
    elif kb_status == 'FAILED':
        print("Knowledge Base 생성에 실패했습니다. AWS 콘솔에서 자세한 오류를 확인해주세요.")

except bedrock_agent.exceptions.ResourceNotFoundException:
    print(f"오류: Knowledge Base ID '{kb_id}'를 찾을 수 없다. 올바른 ID인지 확인하거나 먼저 KB를 생성해야 한다.")
except Exception as e:
    print(f"오류가 발생했다: {e}")
