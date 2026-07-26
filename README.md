# AI Morning Brief

매일 아침 7시(KST), AI 업계 뉴스를 수집 → 중복 제거 → 중요도 판단 → 한국어 요약해서
Telegram으로 보내주는 개인용 자동화 시스템. **운영 비용 0원**을 목표로 설계되었습니다.

## 아키텍처 요약

```
GitHub Actions (매일 22:00 UTC = 07:00 KST, cron)
   └─ main.py
        ├─ src/fetch.py      RSS 피드 수집 (config/feeds.yaml)
        ├─ src/dedupe.py     제목 유사도로 중복 기사 클러스터링
        ├─ src/score.py      출처 가중치 + 키워드 + 유사보도 수 + 최신성으로 중요도 스코어링
        ├─ src/summarize.py  Gemini → Groq → 규칙기반+번역, 3단계 무료 폴백
        └─ src/notify.py     Telegram으로 전송
```

모든 설정(피드 목록, 키워드, 임계값)은 `config/feeds.yaml`, `config/settings.yaml`에 있고,
코드를 건드리지 않고 수정할 수 있습니다.

## 비용 구조 (왜 0원인가)

| 구성요소 | 무료인 이유 |
|---|---|
| RSS 수집 | API 키 없이 공개 피드를 읽기만 함 |
| GitHub Actions | **Public 저장소는 완전 무제한 무료** |
| 중복 제거 / 중요도 판단 | 로컬 연산 (rapidfuzz), 외부 호출 없음 |
| Gemini API (1순위 요약) | Google AI Studio 무료 티어 (신용카드 불필요). 하루 1회 호출로 한도의 극히 일부만 사용 |
| Groq API (2순위 백업) | 무료 티어. Gemini 장애/한도 초과 시에만 호출 |
| 규칙기반 폴백 (3순위) | 완전 무료, API 키 없이도 항상 동작 보장 |
| Telegram | Bot API 자체가 무료 |

**유료 API(OpenAI/Anthropic 등)는 기본 설정에 전혀 포함되어 있지 않습니다.** 위 3단계 폴백만으로
하루 1회 실행에는 충분합니다. 언젠가 요약 품질을 더 높이고 싶다면 `src/summarize.py`의 폴백 체인
끝에 유료 API 호출을 하나 더 추가하면 되지만, 지금은 만들지 않았습니다.

## 사전 준비물 (모두 무료)

1. **GitHub 계정** — 이미 있다고 가정
2. **Google AI Studio API 키** (Gemini, 무료)
   - https://aistudio.google.com/apikey 에서 로그인 후 "Create API key" 클릭
   - 신용카드 등록 불필요
3. **Groq API 키** (무료, Gemini 백업용)
   - https://console.groq.com/keys 에서 로그인 후 키 발급
4. **Telegram Bot** (아래 안내 참고)

### Telegram Bot 만들기

1. Telegram에서 `@BotFather` 검색 후 대화 시작
2. `/newbot` 입력 → 봇 이름과 username(반드시 `bot`으로 끝나야 함) 입력
3. 발급된 **API 토큰**을 메모 (예: `123456789:ABCdefGhIJKlmNoPQRstuVWXyz`) → 이게 `TELEGRAM_BOT_TOKEN`
4. 만든 봇에게 아무 메시지나 보낸 뒤, 브라우저로
   `https://api.telegram.org/bot<토큰>/getUpdates` 접속
5. 응답 JSON에서 `"chat":{"id": ...}` 값을 확인 → 이게 `TELEGRAM_CHAT_ID`

## GitHub 저장소 설정

1. GitHub에서 새 **Public** 저장소 생성 (Actions 완전 무료 사용을 위해)
2. 이 폴더를 push:
   ```bash
   git remote add origin <저장소 URL>
   git branch -M main
   git push -u origin main
   ```
3. 저장소의 **Settings → Secrets and variables → Actions → New repository secret**에서 아래 4개 등록:
   - `GEMINI_API_KEY`
   - `GROQ_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
4. **Actions** 탭 → `AI Morning Brief` 워크플로우 → **Run workflow**로 수동 실행해 테스트
   (스케줄까지 기다리지 않아도 됩니다)

이후에는 매일 07:00 KST에 자동으로 실행됩니다.

## 로컬에서 테스트하기

Telegram으로 실제 전송하지 않고 콘솔에 브리핑만 출력해볼 수 있습니다:

```bash
python -m venv .venv
.venv/Scripts/activate   # Windows
pip install -r requirements.txt

# Gemini/Groq 키 없이 규칙기반 폴백까지만 테스트
DRY_RUN=1 python main.py

# 키를 넣고 LLM 요약까지 테스트하려면 (PowerShell)
$env:GEMINI_API_KEY="..."; $env:DRY_RUN="1"; python main.py
```

## 커스터마이징

- **피드 추가/제거**: `config/feeds.yaml`만 수정 (코드 변경 불필요)
- **중요 키워드 조정**: `config/settings.yaml`의 `keywords.high` / `keywords.medium`
- **브리핑에 담을 기사 수, 조회 시간 범위**: `config/settings.yaml`의 `pipeline` 섹션
- **사용량 소프트 캡**: `config/settings.yaml`의 `usage_limits` (무료 한도 근접 시 자동으로 다음 폴백 단계로 전환)

## 사용량/비용 가드레일

- LLM 호출은 실행당 정확히 1회, 재시도 최대 2회로 제한
- LLM에 넘기는 기사는 중요도 상위 15개로 사전 필터링 (입력 토큰 캡)
- `state/usage.json`에 일별 호출 수를 기록하고, 소프트 캡 초과 시 다음 폴백 단계로 자동 전환
- 모든 외부 호출에 타임아웃 설정, 워크플로우 자체에 `timeout-minutes: 10` 설정으로 무료 Actions 분(minute) 소진 방지
- 유료 API 키는 애초에 시크릿으로 등록하지 않는 한 절대 호출되지 않음
