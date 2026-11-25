# 무료 뉴스 AI 설정: Groq

뉴스속보는 이제 **Groq의 무료 API**를 사용합니다. 기존 Gemini API는 호출하지 않습니다.

## 최초 설정

1. https://console.groq.com/keys 에 로그인해 무료 Groq API 키를 발급합니다.
2. GitHub 저장소의 **Settings → Secrets and variables → Actions → New repository secret**으로 이동합니다.
3. Name: `GROQ_API_KEY`, Secret: 발급한 실제 API 키 (`gsk_...`) 전체를 넣습니다.
4. 저장 후 다음 자동 수집 시 운영 환경에서 모델 심사를 실행합니다. 키를 파일·OBS URL·방송 채팅에 붙여넣지 마세요.
5. Actions 로그의 `AI screening: reviewed=... approved=...`를 확인합니다.

## 동작 방식

- **1분마다** KBS/MBC/JTBC/연합뉴스 RSS를 수집합니다.
- Groq의 `openai/gpt-oss-20b` 모델로 기사 8개씩 **15분 이상 간격**으로 일괄 심사합니다.
- Gemini API나 유료 모델로 자동 전환하지 않습니다.
- Groq 키가 없거나 API 오류·쿼터 소진이 발생해도, 최근 45분 이내의 근거가 명백한 주요 국가기관 결정/인사 기사만 보수적인 무료 로컬 필터로 방송합니다.
- AI가 명시적으로 **거절한 기사는 로컬 필터가 재승인하지 않습니다.**
- 명시적 차단: USGS 지진, [단독], 선관위·부정선거, 북한 미사일, 가벼운 지방 인사, 과거 재탕 등.
- 보수적 로컬 필터는 인공지능이 아닙니다. 뉴스 중요도 판단이 AI보다 제한적이며 놓치는 기사가 있을 수 있습니다.

## 무료 한도

Groq에는 무료 플랜이 있지만 모델별 일일 요청/토큰 한도가 있습니다. 실제 한도는 https://console.groq.com/settings/limits 에서 확인하십시오. 추가 과금이 발생하지 않도록 무료 플랜을 유지하고 결제 정보를 등록하지 않는 것이 좋습니다.

## 문제 해결

- `Groq API key missing`: GitHub Actions secret이 없거나 환경에 접근할 수 없습니다.
- `HTTP 401`: 키 오류 또는 만료. 실제 발급한 키만 사용하십시오.
- `HTTP 429`: 무료 사용량 제한. 60분 재시도 중단, 그동안 무료 로컬 필터는 계속 작동합니다.
- `AI screening: reviewed=8 approved=0`: AI 심사는 작동했지만 이번 묶음은 조건을 통과하지 못했습니다.
- 주요 국회 표결/장관 확정 뉴스가 실제 자막에서 누락되면 보수적 로컬 필터의 기준을 점검하십시오.

GitHub Actions 로그에 나오는 `AI screening: ...`은 AI 심사이며 실제 OBS 화면 표시의 증명이 아닙니다. 화면 표시 기록은 별도 기록창에서 확인하십시오.
