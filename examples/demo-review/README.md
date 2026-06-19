# Automatic Review Demo

PR #9에서 GitHub Webhook 자동 리뷰를 검증할 때 사용한 기능 예제입니다.

1. 최초 PR에서 `total=0` 입력 검증 누락을 CodeBuddy가 발견했습니다.
2. 수정 push 후 `synchronize` 이벤트가 자동 재리뷰를 실행했습니다.
3. 입력 타입과 경계값 검증까지 보완했습니다.

이 코드는 시연 기록용이며 최종 서버리스 런타임에는 포함되지 않습니다.
