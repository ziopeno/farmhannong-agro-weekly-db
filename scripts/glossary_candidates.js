#!/usr/bin/env node
/*
 * 용어집 성장 보조 도구.
 * 지정 주차(기본: 최신)의 카드 본문에서 "전문용어집(GLOSS_GROUPS)에 아직 없는 영문 용어 후보"를 뽑아준다.
 * 매주 카드 생성 후 실행 → 출력된 후보 중 실제 잡초·해충·병해·농약 용어만 app.html의 GLOSS_GROUPS에 한국어로 추가.
 *
 * 사용:  node scripts/glossary_candidates.js [YYYY-MM-DD]
 *   인자 없으면 가장 최근 주차를 검사.
 */
const fs = require('fs');
const path = require('path');

const appPath = path.resolve(__dirname, '..', 'app.html');
const html = fs.readFileSync(appPath, 'utf8');

// 1) 기존 용어집 키
const gm = 'const GLOSS_GROUPS = ';
const gs = html.indexOf(gm);
if (gs < 0) { console.error('GLOSS_GROUPS를 찾지 못했습니다.'); process.exit(1); }
const groups = JSON.parse(html.slice(gs + gm.length, html.indexOf('};', gs) + 1));
const glossKeys = new Set();
for (const cat in groups) for (const k in groups[cat]) glossKeys.add(k.toLowerCase());

// 2) newsDatabase
const nm = 'const newsDatabase = ';
const ns = html.indexOf(nm) + nm.length;
const db = JSON.parse(html.slice(ns, html.indexOf(';\n        let allDates', ns)));

// 3) 대상 주차
const arg = process.argv.slice(2).find(a => /^\d{4}-\d{2}-\d{2}$/.test(a));
const weeks = Object.keys(db).sort();
const week = arg || weeks[weeks.length - 1];
const cards = db[week] || [];

// 4) 생물·병해를 가리키는 접미사(이게 끝에 오면 진짜 용어일 확률↑)
const BIO_SUFFIX = new Set(('worm worms weed weeds grass blight rot mold mould mildew rust smut scab canker wilt '
  + 'spot bug bugs midge moth beetle mite mites aphid aphids hopper borer weevil thrips fly flies '
  + 'nematode nematodes virus viroid fungus mosaic').split(/\s+/));
const hasBioSuffix = lo => { const w = lo.split(' ').pop(); return BIO_SUFFIX.has(w) || [...BIO_SUFFIX].some(s => w.endsWith(s) && w.length > s.length + 1); };

// 5) 회사·기관·일반어 제외(노이즈 감소)
const DENY = new Set((`
bayer syngenta basf corteva adama nufarm fmc upl sumitomo mitsui nissan nihon nohyaku sipcam nichino
valent monsanto rainbow ginkgo xarvio lavie enlist roundup agriscience croplife dupont kumiai isagro bioworks yamaha
crop science group chemical chemicals agriculture agricultural agro protection plant health bill house
international research seeds farm fork pest management authority medicines veterinary pesticide pesticides
rodenticide act news daily report reuters bloomberg market company corporation holdings global commission
guide package modern alliance reduced tillage stewardship native shatter tolerance prevention programs
california statewide outreach infrastructure technology western producer producers expo lifecycle obsolete
species production systems based future farming spraying spectrum cereal grain european county zavala
the and for with that this from have has was are its inc ltd new use used per via also more most
such been being said says can could would should may might not but all any one two three billion million
`).trim().split(/\s+/).filter(Boolean));

const isAcronym = orig => /^[A-Z][A-Z0-9]{1,5}$/.test(orig);       // 전부 대문자 짧은 약어(기관·매체)
function ok(lo, isPhrase) {
  if (lo.length < 4 || /^\d/.test(lo)) return false;
  if (glossKeys.has(lo)) return false;
  for (const g of glossKeys) { if (g.indexOf(lo) !== -1 || lo.indexOf(g) !== -1) return false; }
  const parts = lo.split(' ');
  if (parts.some(p => DENY.has(p))) return false;
  return true;
}

const strong = {}, uni = {};   // strong = 접미사 매칭(생물·병해 의심), uni = 그 외 단어
for (const c of cards) {
  const orig = String(c.body || '').match(/[A-Za-z][A-Za-z\-]{2,}/g) || [];
  for (let i = 0; i < orig.length; i++) {
    const t = orig[i], lo = t.toLowerCase();
    if (isAcronym(t)) continue;
    // 2단어 구: 끝 단어가 생물·병해 접미사일 때만(예: tar spot, lygus bug)
    if (i + 1 < orig.length && !isAcronym(orig[i + 1])) {
      const pair = (t + ' ' + orig[i + 1]).toLowerCase();
      if (hasBioSuffix(pair) && ok(pair, true)) strong[pair] = (strong[pair] || 0) + 1;
    }
    if (!ok(lo, false)) continue;
    if (hasBioSuffix(lo)) strong[lo] = (strong[lo] || 0) + 1;
    else uni[lo] = (uni[lo] || 0) + 1;
  }
}
const fmt = o => Object.entries(o).sort((a, b) => b[1] - a[1]).map(([k, v]) => `  ${k}  (${v})`).join('\n');

console.log(`\n=== 주차 ${week} · 용어집 미등록 영문 후보 (현재 사전 ${glossKeys.size}개) ===`);
console.log('\n[★ 생물·병해 의심 — 우선 검토]\n' + (Object.keys(strong).length ? fmt(strong) : '  (없음)'));
console.log('\n[그 외 단어 — 농약성분 등 살펴볼 것]\n' + (Object.keys(uni).length ? fmt(uni) : '  (없음)'));
console.log('\n→ 이 중 실제 잡초·해충·병해·농약 용어만 app.html의 GLOSS_GROUPS 해당 카테고리에 "영문(소문자)":"한국어" 로 추가.');
console.log('   (회사·기관·제품 브랜드명은 추가하지 않음)\n');
