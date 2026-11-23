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


## 실제 화면 표시된 자막 기록 (선택 설정)

기존 '서버 선별 뉴스' 기록은 실제 자막 송출을 입증하지 못합니다. 새 기록창은
자막 브라우저 화면에 **표시가 시작된 이벤트만** 기록하며, 테스트 항목은 제외합니다.
단, 브라우저 화면이 열렸다고 해서 OBS가 생방송으로 송출 중이었다는 뜻은 아닙니다.

중앙 저장 없이 쓰면 자막 페이지 `localStorage`에만 남습니다.
OBS 브라우저 소스와 모바일 브라우저는 저장소가 분리되므로,
휴대전화에서 같은 기록을 확인하려면 다음 Cloudflare KV 연동을 완료하세요.

1. Cloudflare > Storage & databases > KV에서 네임스페이스 `obs-caption-logs` 생성.
2. 기존 뉴스 Cron Worker > **Settings > Bindings > Add binding > KV namespace**:
   - Variable name: `CAPTION_LOGS`
   - Namespace: `obs-caption-logs`
3. 기존 Worker > **Settings > Variables and Secrets > Add variable**:
   - Key: `CAPTION_LOG_SECRET`
   - Value: 현재 OBS 뷰어 주소의 `#key=`에 설정한 길고 랜덤한 비밀키와 **동일한 값**
   - Secret 체크하고 저장/배포. 비밀키를 채팅이나 공개 저장소에 게시하지 마세요.
4. Worker 편집기 전체 코드를 이 저장소의 최신 `cloudflare/minute-dispatch.mjs`
   파일로 교체해 배포. 기존 `GITHUB_DISPATCH_TOKEN`과 매분 Cron은 유지됩니다.
5. Worker 공개 주소가 예를 들어 `https://example.workers.dev`라면
   OBS 브라우저 소스 URL을 다음처럼 바꾸세요 (비밀키는 기존 값을 사용).
   ```text
   https://shindong73.github.io/-/view.html?logApi=https://example.workers.dev#key=기존비밀키
   ```
   기록창도 다음 주소로 접속합니다.
   ```text
   https://shindong73.github.io/-/history.html?logApi=https://example.workers.dev#key=기존비밀키
   ```
6. 실시간 헤드라인을 하나 표시한 후 기록창을 열어 **중앙 저장 기록** 수치가
   늘었는지 확인하세요. 위 주소의 `example.workers.dev`는 실제 Worker 주소로 교체하세요.

기록에는 자막 제목, 언론사, 실제 표시 시작 시각, 예정 표시 시간만 담습니다.
클라이언트에서 AES-GCM 암호화한 데이터를 KV에 보관하고, 기록창에서만 복호화합니다.
중앙 로그는 최근 최대 500건, 최대 35일 보관하며 브라우저는 실패 시 로컬 기록을 유지하고 재시도합니다.
기록창의 **CSV 저장**에는 실제 표시 시작 기록만 포함하며, 후보 뉴스는 포함하지 않습니다.

GitHub Pages와 OBS 브라우저 소스에서의 `logApi` 쿼리 값은 모두 HTTPS를 사용하세요.
이 기능이 정상 작동하는지 검증하기 전까지 기존 속보 자막 전송 동작은 변경되지 않습니다.
