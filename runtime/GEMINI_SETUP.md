# Gemini 무료 API 선별 설정

Google AI Studio https://aistudio.google.com/apikey 에서 API 키를 생성하세요.
GitHub 저장소 https://github.com/shindong73/- 로 이동하여 상단 Settings 메뉴를 클릭합니다.
왼쪽 메뉴 Secrets and variables > Actions > New repository secret에서
이름 GEMINI_API_KEY, 값에 발급받은 키를 넣고 저장합니다.
Actions > Resource refresh > Run workflow 로 수동 실행하여 동작을 확인할 수 있습니다.

무료 한도/프로젝트 조건은 https://ai.google.dev/gemini-api/docs/pricing 에서 확인하세요.
키가 없으면 기존 규칙 필터만 사용합니다. 키가 있는데 오류가 나면 새로운 정치뉴스는
그 실행에서 보류하고 다음 실행에서 재시도합니다. 지진 알림은 영향을 받지 않습니다.
기사 원문 전체가 아닌 RSS 기사 제목과 언론사 정보를 AI로 전달합니다.
키는 코드/채팅/이슈에 공개하면 안 됩니다.
