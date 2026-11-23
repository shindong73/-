# 무료 1분 수집 스케줄러 설정

이 파일들은 설정 가능한 Cloudflare Worker 코드입니다.
Cloudflare 계정과 GitHub 토큰 연결은 별도 사용자 작업이 필요합니다.

1) https://github.com/settings/personal-access-tokens/new
   GitHub fine-grained token 생성
   - Owner: shindong73
   - Repository: shindong73/- 만 선택
   - Actions: Read and write
   - 다른 권한은 기본 최소로 유지
2) https://dash.cloudflare.com/ 접속 > Workers & Pages > Create Worker
3) https://github.com/shindong73/-/blob/main/cloudflare/minute-dispatch.mjs
   소스를 Worker 편집기에 붙이고 배포 (또는 Wrangler로 이 폴더 배포)
4) Cloudflare Worker Settings > Variables and Secrets 에서 Secret 추가:
   이름 GITHUB_DISPATCH_TOKEN / 값은 1단계 GitHub PAT
5) Cloudflare Worker Settings > Triggers > Cron Triggers 설정:
   * * * * *
   시간대는 UTC이며 모든 분에 동작합니다.
   Wrangler 사용 시 wrangler.toml에 이미 지정돼 있습니다.
6) GitHub 실행 보기:
   https://github.com/shindong73/-/actions/workflows/refresh.yml
   Event가 workflow_dispatch 이며 테스트/배포가 성공하는지 확인하세요.

주의: GitHub 토큰을 채팅/코드/공개 이슈에 붙이지 마세요.
매분 수집 실행 요청을 보낼 수 있지만, GitHub 작업 대기 및 Pages 배포 시간은 남습니다.
기존 GitHub schedule은 비상시 백업으로 유지합니다.
GitHub/Cloudflare의 사용 제한과 Gemini API 무료 한도를 확인하세요.

Cloudflare 공식 문서:
https://developers.cloudflare.com/workers/configuration/cron-triggers/
GitHub 공식 문서:
https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event
