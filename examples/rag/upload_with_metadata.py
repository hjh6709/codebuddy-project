"""Chapter 3 learning example: upload Knowledge Base documents."""

import boto3

# S3 클라이언트 생성 (서울 리전 설정)
s3 = boto3.client('s3', region_name='ap-northeast-2')

# 사용 중인 고유 S3 버킷 이름
BUCKET_NAME = "codebuddy-kb-docs-jeonghyun"

def upload_with_metadata(file_path, bucket, key, metadata):
    """메타데이터와 함께 파일 업로드"""
    with open(file_path, 'rb') as f:
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=f.read(),
            Metadata=metadata  # 별도 파일 없이 S3 자체 헤더에 메타데이터 주입
        )
    print(f"업로드 완료: {key} with {metadata}")


if __name__ == "__main__":
    print("🚀 [실습 8] 교안 규격에 맞춘 S3 메타데이터 업로드 시작...")
    
    # 1. Python 문서 업로드 (지정된 하위 경로 및 태그 적용)
    upload_with_metadata(
        'pep8.txt',
        BUCKET_NAME,
        'style-guides/python/pep8.txt',
        {'language': 'python', 'rule_type': 'style'}
    )
    
    # 2. JavaScript 문서 업로드 (지정된 하위 경로 및 태그 적용)
    upload_with_metadata(
        'airbnb-style.txt',
        BUCKET_NAME,
        'style-guides/javascript/airbnb.txt',
        {'language': 'javascript', 'rule_type': 'style'}
    )
