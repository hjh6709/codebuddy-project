import boto3
import json
import numpy as np

# Bedrock 런타임 클라이언트 생성 (서울 리전 설정)
bedrock = boto3.client('bedrock-runtime', region_name='ap-northeast-2')

def get_embedding(text):
    """
    텍스트를 받아 Amazon Titan Embeddings v2 모델을 호출하고
    1024차원의 벡터(숫자 배열)로 변환하여 반환합니다.
    """
    response = bedrock.invoke_model(
        modelId='amazon.titan-embed-text-v2:0',
        contentType='application/json',
        body=json.dumps({
            "inputText": text,
            "dimensions": 1024,
            "normalize": True
        })
    )
    result = json.loads(response['body'].read())
    return result['embedding']


def cosine_similarity(vec1, vec2):
    """
    두 벡터 간의 코사인 유사도를 계산하여 -1에서 1 사이의 값을 반환합니다.
    """
    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    return dot_product / (norm1 * norm2)


if __name__ == "__main__":
    print("--- [실습 1 검증] ---")
    sample_text = "Python 변수명은 snake_case를 사용합니다"
    embedding = get_embedding(sample_text)
    print(f"✅ 벡터 길이: {len(embedding)}")
    
    print("\n" + "="*50 + "\n")
    
    print("--- [실습 2] 코사인 유사도 분석 시작 ---")
    
    # 교안 6p 실습 타겟 코드 스니펫 3개
    code1 = "def calculate_total(items): return sum(items)"
    code2 = "def get_sum(prices): return sum(prices)"
    code3 = "def make_coffee(): return '☕'"
    
    print("⏳ 세 가지 코드 스니펫의 임베딩 벡터 생성 중...")
    emb1 = get_embedding(code1)
    emb2 = get_embedding(code2)
    emb3 = get_embedding(code3)
    
    print("\n⏳ 벡터 공간 내 거리(유사도) 계산 중...")
    # 기능이 비슷한 code1과 code2 비교
    sim_1_2 = cosine_similarity(emb1, emb2)
    # 기능이 아예 다른 code1과 code3 비교
    sim_1_3 = cosine_similarity(emb1, emb3)
    
    print("\n[📊 코드 유사도 분석 결과]")
    print(f"✅ code1 vs code2 (비슷한 기능): {sim_1_2:.4f}")
    print(f"✅ code1 vs code3 (무관한 기능): {sim_1_3:.4f}")
