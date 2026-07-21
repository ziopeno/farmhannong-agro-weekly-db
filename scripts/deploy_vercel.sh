#!/usr/bin/env bash
# Farmhannong Agro Weekly — Vercel 배포 (GitHub Actions 미경유)
#
# 목적: GitHub Actions/Pages 장애와 무관하게 사이트를 게시한다.
#       Codex 주간 루틴이 재암호화·검증을 마친 뒤 이 스크립트로 바로 배포한다.
#
# 안전 원칙(누출 차단): 배포 대상은 "화이트리스트"로만 구성한다.
#   허용 = payload.enc(암호문) + 정적 로더 index.html + 비민감 자산(아이콘/manifest/robots/이미지).
#   금지 = 평문 app.html, 복호 코드 .site-access.json, .github/, scripts/, 내부 문서/시크릿.
#   화이트리스트라 "새 민감 파일이 실수로 섞여도" 배포되지 않는다(블랙리스트보다 안전).
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="$REPO/.deploy/farmhannong-agro-weekly"   # 배포 스테이징(=Vercel 프로젝트명/URL 근거)
LINK="$REPO/.deploy/.vercel-link"               # 프로젝트 링크 영속 저장(동일 프로젝트 재배포)

cd "$REPO"

# 1) payload.enc 존재 + 암호문 무결성(평문 유출 방지)
test -f payload.enc || { echo "ERROR: payload.enc 없음 — 먼저 node scripts/encrypt_site.js"; exit 1; }
if grep -q "const newsDatabase" payload.enc; then
  echo "ERROR: payload.enc에 평문 카드 데이터가 섞였습니다. 배포 중단."; exit 1
fi

# 2) 클린 스테이징 재구성 — 화이트리스트만 복사
rm -rf "$STAGE"
mkdir -p "$STAGE/assets"
ALLOW=( index.html payload.enc manifest.json icon.svg icon-192.png icon-512.png apple-touch-icon.png robots.txt )
for f in "${ALLOW[@]}"; do
  [ -f "$f" ] && cp "$f" "$STAGE/$f"
done
[ -f assets/header-people-illustration.png ] && cp assets/header-people-illustration.png "$STAGE/assets/"

# 3) 방어 검증 — 민감 파일이 스테이징에 절대 없어야 함
for bad in app.html .site-access.json .weekly-email.env; do
  [ -e "$STAGE/$bad" ] && { echo "ERROR: 민감 파일 $bad 이 배포 대상에 포함됨. 중단."; exit 1; }
done
if grep -rql "const newsDatabase" "$STAGE" 2>/dev/null; then
  echo "ERROR: 스테이징에 평문 카드 데이터 감지. 중단."; exit 1
fi

# 4) 정적 헤더 — 검색 비색인 + payload는 매번 재검증(주간 갱신 즉시 반영)
cat > "$STAGE/vercel.json" <<'JSON'
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "headers": [
    { "source": "/payload.enc", "headers": [ { "key": "Cache-Control", "value": "public, max-age=0, must-revalidate" } ] },
    { "source": "/(.*)", "headers": [ { "key": "X-Robots-Tag", "value": "noindex, nofollow" } ] }
  ]
}
JSON

# 5) 기존 프로젝트 링크 복원(있으면) → 같은 프로젝트/URL로 재배포
if [ -f "$LINK/project.json" ]; then
  mkdir -p "$STAGE/.vercel"
  cp "$LINK/project.json" "$STAGE/.vercel/project.json"
fi

# 6) 배포(프로덕션)
cd "$STAGE"
echo "→ vercel deploy --prod  (staging: $STAGE)"
set +e
OUT="$(npx --yes vercel deploy --prod --yes 2>&1)"; RC=$?
set -e
echo "$OUT"
[ "$RC" -ne 0 ] && { echo "ERROR: vercel deploy 실패 (rc=$RC)"; exit "$RC"; }

# 7) 첫 배포면 프로젝트 링크 저장(다음부터 동일 프로젝트)
if [ -f "$STAGE/.vercel/project.json" ]; then
  mkdir -p "$LINK"
  cp "$STAGE/.vercel/project.json" "$LINK/project.json"
fi

URL="$(printf '%s\n' "$OUT" | grep -Eo 'https://[a-zA-Z0-9._-]+\.vercel\.app' | tail -1)"
echo ""
echo "DEPLOYED: ${URL:-'(URL 파싱 실패 — 위 출력에서 Production URL 확인)'}"
