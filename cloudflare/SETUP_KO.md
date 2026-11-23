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
4. **지금 사용 중인 Cloudflare Worker에는 이미 /caption-log 기능이 있으므로 코드 전체를 다시 붙여넣을 필요가 없습니다.**
   위 KV 바인딩과 Secret 설정만 완료하고 Deploy하세요.
5. OBS 자막 화면과 기록창의 Worker 연결은 기본값으로 아래 주소를 사용하므로,
   긴 `?logApi=` 주소를 별도로 추가하지 않아도 됩니다.
   - `https://shindong73.github.io/-/view.html#key=기존비밀키`
   - `https://shindong73.github.io/-/history.html#key=기존비밀키`
   기존 `#key=` 값은 유지하고 채팅이나 공개 웹페이지에 절대 올리지 마세요.
6. 실제 자막 화면에 새 헤드라인이 표시된 후 기록창에서 **중앙 저장 기록**이
   증가하는지 확인하세요. 예전 OBS 브라우저 소스에서만 생성된 로컬 기록은
   중앙 저장 설정 이전에는 복원되지 않을 수 있습니다.
7. Cloudflare KV 무료 플랜의 하루 쓰기 1,000건·리스트 조회 1,000회·저장 1GB
   한도 내에서 사용하세요. 기록창은 화면을 보고 있을 때 3분마다 자동 조회하며,
   새로고침 버튼으로 즉시 조회할 수 있습니다.

기록에는 자막 제목, 언론사, 실제 표시 시작 시각, 예정 표시 시간만 담습니다.
클라이언트에서 AES-GCM 암호화한 데이터를 KV에 보관하고, 기록창에서만 복호화합니다.
중앙 로그는 최근 최대 500건, 최대 35일 보관하며 브라우저는 실패 시 로컬 기록을 유지하고 재시도합니다.
기록창의 **CSV 저장**에는 실제 표시 시작 기록만 포함하며, 후보 뉴스는 포함하지 않습니다.

Worker URL은 코드에 HTTPS로 고정되어 있습니다. `?logApi=off`를 붙이면 디버깅용으로 중앙 저장 연동을 임시 비활성화합니다.
이 기능이 정상 작동하는지 검증하기 전까지 기존 속보 자막 전송 동작은 변경되지 않습니다.

## Cron 1분 연동 점검 및 예비 수집

GitHub 저장소의 기본 예약 실행은 **5분 간격**으로 설정되어 있습니다.
Cloudflare Worker가 정상 작동하면 별도의 `workflow_dispatch` 실행이 매분 생성되며,
기본 예약 실행은 Cloudflare 장애 시의 예비 수집 경로로 유지합니다.
GitHub Actions 스케줄은 지연될 수 있어 정확한 실행 분을 보장하지 않습니다.

기존 Cloudflare Worker에 등록된 비밀 변수 `GITHUB_DISPATCH_TOKEN`은 유지하세요.
Cloudflare 편집기의 코드를 최신 `cloudflare/minute-dispatch.mjs`와 일치시키고
다시 Deploy해야 GitHub의 코드 수정 내용이 실제 Worker에도 반영됩니다.

배포된 Worker 주소 뒤에 `/health`를 붙여 접속하세요.
응답에 `"version":"2026-11-23-diagnostics-v1"`가 있으면 수정된 코드가 배포된 것입니다.
`"github_token_configured":true`면 비밀 변수 이름에 값이 있음을 뜻하지만,
GitHub 토큰 자체가 유효하다거나 Cron이 호출된다는 보증은 아닙니다.
`false`면 **Production** 환경의 `GITHUB_DISPATCH_TOKEN` 등록을 확인하세요.

Cloudflare > Workers & Pages > 해당 Worker > Settings > Triggers:
`Minute(s)=1` 또는 `* * * * *`.
Cron 변경은 전체 네트워크 적용까지 최대 15분 소요될 수 있습니다.

Cloudflare > Observability > Logs의 실행 유형에서 **Scheduled**를 확인하세요.
- `OBS minute cron fired`: 예약 호출 자체는 실행됨
- `Dispatched GitHub news collection: HTTP 204`: GitHub 실행 요청 접수
- `GITHUB_DISPATCH_TOKEN secret is missing`: Worker에 비밀 변수가 없음
- `GitHub workflow dispatch failed: HTTP 401`: 토큰 인증 실패 가능성
- `GitHub workflow dispatch failed: HTTP 403`: Actions 권한 부족 가능성
- `GitHub workflow dispatch failed: HTTP 404`: 저장소/워크플로 접근 오류 가능성

실제 GitHub Actions에 `workflow_dispatch`가 연달아 생성되는지도 확인하세요.
`/health`는 읽기 전용이며 GitHub 실행을 강제하지 않습니다.
토큰 또는 원본 로그의 인증 헤더는 공개하지 마세요.
