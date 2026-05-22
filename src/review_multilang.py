import boto3

kb_id = "Q1ZYRCWLIW"

def ask_knowledge_base(kb_id, prompt):
    """Knowledge Base에 질문하여 답변을 반환하는 헬퍼 함수"""
    bedrock_agent_client = boto3.client('bedrock-agent-runtime', region_name='ap-northeast-2')
    
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

def check_multilang(code, language):
    """언어별 스타일 가이드 검사"""
    prompt = f"""{language} 코드 스타일 가이드에 따라 다음 코드를 검사해주세요.
언어: {language}
코드:
{code}"""
    return ask_knowledge_base(kb_id, prompt)

if __name__ == "__main__":
    # 1. JavaScript 코드 검사
    js_code = """function helloWorld() {
}
console.log('Hello, World!');"""
    
    print("--- JavaScript 코드 검사 ---")
    print(check_multilang(js_code, "JavaScript"))

    # 2. Java 코드 검사
    java_code = """public class HelloWorld {
    public static void main(String[] args) {
        System.out.println("Hello, World!");
    }
}"""
    
    print("\n--- Java 코드 검사 ---")
    print(check_multilang(java_code, "Java"))

    # 3. Go 코드 검사
    go_code = """package main
import "fmt"
func main() {
    fmt.Println("Hello, World!")
}"""
    
    print("\n--- Go 코드 검사 ---")
    print(check_multilang(go_code, "Go"))
