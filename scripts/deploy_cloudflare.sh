#!/usr/bin/env bash
# Farmhannong Agro Weekly — Cloudflare Pages 배포 (GitHub Actions 미경유, 무료·상업사용 허용)
#
# 목적: GitHub Actions/Pages 장애와 무관하게 사이트를 게시한다. 주 배포 경로.
#       Vercel 대체(상업적 사용 약관 리스크 제거). Cloudflare Pages 무료 플랜은 상업사용 허용.
#
# 안전 원칙(누출 차단): 배포 대상은 "화이트리스트"로만 구성한다.
#   허용 = payload.enc(암호문) + 정적 로더 index.html + 비민감 자산(아이콘/manifest/robots/이미지).
#   금지 = 평문 app.html, 복호 코드 .site-access.json, .github/, scripts/, 내부 문서/시크릿.
#
# 인증: `npx wrangler login`(OAuth, 1회) 또는 환경변수 CLOUDFLARE_API_TOKEN(무기한 토큰 권장).
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="$REPO/.deploy/cf-farmhannong-agro-weekly"
PROJECT="farmhannong-agro-weekly"

cd "$REPO"

# 0) 인증 로드 — gitignore된 .cloudflare.env(CLOUDFLARE_API_TOKEN[, CLOUDFLARE_ACCOUNT_ID])가 있으면 사용.
#    없으면 `npx wrangler login` OAuth 자격증명으로 동작.
[ -f "$REPO/.cloudflare.env" ] && { set -a; . "$REPO/.cloudflare.env"; set +a; }

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

# 4) Cloudflare Pages 헤더 파일(_headers) — 검색 비색인 + payload 재검증
cat > "$STAGE/_headers" <<'HDR'
/payload.enc
  Cache-Control: public, max-age=0, must-revalidate

/*
  X-Robots-Tag: noindex, nofollow
HDR

# 5) 프로젝트 보장(없으면 생성). 이미 있으면 무시.
npx --yes wrangler pages project create "$PROJECT" --production-branch=main >/dev/null 2>&1 || true

# 6) 배포(프로덕션 = main 브랜치)
echo "→ wrangler pages deploy (staging: $STAGE, project: $PROJECT)"
set +e
OUT="$(npx --yes wrangler pages deploy "$STAGE" --project-name="$PROJECT" --branch=main --commit-dirty=true 2>&1)"; RC=$?
set -e
echo "$OUT"
[ "$RC" -ne 0 ] && { echo "ERROR: wrangler pages deploy 실패 (rc=$RC)"; exit "$RC"; }

# 7) URL 추출(프로덕션 별칭 <project>.pages.dev 우선)
URL="$(printf '%s\n' "$OUT" | grep -Eo 'https://[a-zA-Z0-9._-]+\.pages\.dev' | tail -1)"
echo ""
echo "DEPLOYED: ${URL:-https://${PROJECT}.pages.dev}"
