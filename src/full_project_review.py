import boto3
from pathlib import Path

kb_id = "Q1ZYRCWLIW"

SKIP_DIRS = {'node_modules', '.next', '.git', 'dist', '__pycache__'}
TARGET_EXTENSIONS = {'.ts', '.tsx', '.go'}
TARGET_FILES = [
    'apps/web/app/(platform)/labs/page.tsx',
    'apps/web/app/(platform)/layout.tsx',
    'apps/web/components/lab/LabCard.tsx',
    'apps/web/components/ui/Navbar.tsx',
    'apps/api/internal/api/handlers/lab.go',
]

def style_check(code, kb_id):
    """지식 기반을 활용한 코드 스타일 검사"""
    bedrock_agent_client = boto3.client('bedrock-agent-runtime', region_name='ap-northeast-2')
    prompt = f"""당신은 코드 스타일 검사기입니다. 다음 코드에서 일반적인 스타일 규칙을 위반한 부분을 찾아주세요.
TypeScript/Go 코드라면 해당 언어의 컨벤션 기준으로 검사해주세요.
형식:
[라인번호] 위반 유형: 설명

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

def check_security(code, kb_id):
    """지식 기반을 활용한 보안 취약점 검사"""
    bedrock_agent_client = boto3.client('bedrock-agent-runtime', region_name='ap-northeast-2')
    prompt = f"""다음 코드에서 보안 취약점을 찾아주세요. 특히 SQL Injection, XSS, 하드코딩된 비밀번호를 중점적으로 검사해주세요.
코드:
{code}
취약점이 있으면 위치, 유형, 심각도, 수정 제안을 포함해 주세요."""
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

def full_project_review(project_path, kb_id):
    """지정된 파일들을 순회하며 스타일 및 보안 검사 수행"""
    results = {}
    base = Path(project_path)

    for rel_path in TARGET_FILES:
        target = base / rel_path
        if not target.exists():
            print(f"⚠️  파일 없음: {rel_path}")
            continue

        with open(target, 'r', encoding='utf-8') as f:
            code = f.read()

        if len(code) < 50:
            continue

        print(f"🔍 검사 중: {rel_path}")
        style_result = style_check(code, kb_id)
        security_result = check_security(code, kb_id)

        results[rel_path] = {
            'style': style_result,
            'security': security_result,
            'lines': len(code.splitlines())
        }

    with open('project_review_report.md', 'w', encoding='utf-8') as f:
        f.write("# 📊 프로젝트 통합 코드 리뷰 리포트\n\n")
        for filepath, data in results.items():
            f.write(f"## 📄 {filepath} ({data['lines']}줄)\n\n")
            f.write("### 🔹 스타일 검사 결과\n")
            f.write(data['style'] + "\n\n")
            f.write("### 🔹 보안 취약점 검사 결과\n")
            f.write(data['security'] + "\n\n")
            f.write("---\n\n")

    print("🎉 종합 리포트 생성 완료: project_review_report.md")
    return results

if __name__ == "__main__":
    full_project_review('./', kb_id)
