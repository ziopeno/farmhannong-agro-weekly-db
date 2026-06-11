# Farmhannong Agro Weekly

팜한농 해외사업팀용 주간 농약·작물보호 카드뉴스 대시보드.
**사내 전용** — 사이트는 개인별 입장 코드로 잠겨 있으며, 콘텐츠는 AES-256-GCM으로 암호화되어 배포됩니다.

## 저장소 구조 (공개 저장소에는 암호문만 존재)

| 파일 | 설명 |
|---|---|
| `index.html` | 입장 코드 로더(정적). 코드 확인 후 `payload.enc`를 복호해 앱을 띄움 |
| `payload.enc` | 앱 전체의 암호문 (AES-256-GCM, 코드별 키 래핑) |
| `app.html` | **평문 앱 — git 미추적(로컬 전용).** 모든 편집은 이 파일에 |
| `.site-access.json` | **개인별 입장 코드 — git 미추적(로컬 전용)** |
| `scripts/encrypt_site.js` | `app.html` + 코드 목록 → `payload.enc` 생성 |
| `source-pdfs/` | 출처 증빙 PDF (외신 기사 사본) |
| `inbox/` | 주간 참고 리포트(PDF) 추출 JSON 투입 폴더 |

## 주간 업데이트 흐름 (로컬 자동화)

1. `app.html`의 `newsDatabase`에 새 주차(월요일 키) 추가 — 자체검색 20건 + (inbox에 리포트 있으면) 리포트 카드 최대 20건(`origin:"pdf"`)
2. `python3 scripts/generate_source_pdfs.py` — 출처 PDF 생성
3. `node scripts/encrypt_site.js` — **payload.enc 재생성 (필수)**
4. `node scripts/verify_weekly_deploy.js --sync-downloads --expect-current-week` — 검증
5. 커밋 → (관리자 승인 후) `git push` → GitHub Pages 자동 배포
6. (관리자 승인 후) `python3 scripts/run_local_weekly_email_dispatch.py` — 주간 메일

## 접근 관리

- 코드 추가/회수: `.site-access.json`의 `users` 배열 수정 → `node scripts/encrypt_site.js` 재실행 → 커밋·푸시.
  재암호화 시 콘텐츠 키가 교체되므로 **회수된 코드(및 그 브라우저의 저장 키)는 즉시 무효**가 됩니다.
- 입장한 브라우저는 복호 키를 localStorage에 저장해 재방문 시 자동 입장합니다.

## 주간 메일 설정 (로컬 Mac)

- 미추적 파일 `.weekly-email.env`를 `.weekly-email.env.example`에서 만들거나,
- macOS 키체인 서비스 `farmhannong-weekly-email`에 `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SUMMARY_EMAIL_RECIPIENTS`, `SITE_URL`을 저장합니다.

수신자·SMTP 자격증명은 추적되는 파일에 절대 넣지 않습니다.

## 주의

- `app.html` / `.site-access.json`은 절대 커밋하지 않습니다 (.gitignore에 등록됨).
- 카드 데이터·코드 등 평문이 공개 저장소에 올라가면 안 됩니다. `verify_weekly_deploy.js --check-pages`가 공개 로더의 평문 누출도 함께 검사합니다.
