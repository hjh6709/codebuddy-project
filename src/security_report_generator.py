import boto3

kb_id = "Q1ZYRCWLIW"

def generate_security_report(code, kb_id):
    """보안 취약점 리포트 (JSON 형식) 생성"""
    bedrock_agent_client = boto3.client('bedrock-agent-runtime', region_name='ap-northeast-2')
    
    prompt = f"""다음 코드의 보안 취약점을 분석하고 JSON 형식으로 보고서를 작성해주세요.
형식:
{{
  "vulnerabilities": [
    {{
      "line": 라인번호,
      "type": "취약점 유형",
      "severity": "CRITICAL/HIGH/MEDIUM/LOW",
      "description": "설명",
      "suggestion": "수정 제안"
    }}
  ],
  "summary": "전체 평가"
}}
코드:
{code}"""

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
    
    report = generate_security_report(vulnerable_code, kb_id)
    
    # 결과를 파일로 저장
    with open('security_report.json', 'w', encoding='utf-8') as f:
        f.write(report)
        
    print(" 리포트 저장 완료: security_report.json")
