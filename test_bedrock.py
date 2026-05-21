import boto3

bedrock = boto3.client('bedrock-runtime',\
                        region_name='ap-northeast-2')
model_id='global.anthropic.claude-sonnet-4-6'
try:
  response=bedrock.converse(
    modelId=model_id,
    messages=[
      {
        "role": "user",
        "content":[{"text":"Hello, Claude! 안녕?"}]
      }
    ]
  )
  print("---Claude의 응답---")
  print(response['output']['message']['content'][0]['text'])

except Exception as e:
  print(f"에러 발생: {e}")
