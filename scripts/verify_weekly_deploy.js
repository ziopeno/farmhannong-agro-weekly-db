#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const repoRoot = path.resolve(__dirname, '..');
// 평문 앱은 app.html(git 미추적). 배포물은 index.html(입장 로더, 정적) + payload.enc(암호문).
const indexPath = path.join(repoRoot, 'app.html');
const payloadPath = path.join(repoRoot, 'payload.enc');
const accessPath = path.join(repoRoot, '.site-access.json');
const downloadsPath = '/Users/ziopeno/Downloads/Farmhannong_Agro_Dashboard_FINAL_V32.html';
const sourcePdfsPath = path.join(repoRoot, 'source-pdfs');
const downloadsSourcePdfsPath = path.join(path.dirname(downloadsPath), 'source-pdfs');
const args = new Set(process.argv.slice(2));
// 자체검색 20건은 항상 포함. 업로드 리포트가 있으면 최대 20건(origin:"pdf") 추가 → 총 20~40건.
const MIN_WEEKLY_CARD_COUNT = 20;
const MAX_WEEKLY_CARD_COUNT = 40;
const REQUIRED_WEEKLY_CARD_COUNT = `${MIN_WEEKLY_CARD_COUNT}~${MAX_WEEKLY_CARD_COUNT}`;
const okCount = (n) => n >= MIN_WEEKLY_CARD_COUNT && n <= MAX_WEEKLY_CARD_COUNT;
const isGitHubActions = process.env.GITHUB_ACTIONS === 'true';

function run(command, commandArgs, options = {}) {
  const result = execFileSync(command, commandArgs, {
    cwd: repoRoot,
    encoding: 'utf8',
    stdio: options.stdio || ['ignore', 'pipe', 'pipe'],
  });
  return typeof result === 'string' ? result.trim() : '';
}

function parseDashboard(filePath, label) {
  const html = fs.readFileSync(filePath, 'utf8');
  const marker = 'const newsDatabase = ';
  const start = html.indexOf(marker);
  if (start < 0) throw new Error(`${label}: newsDatabase marker missing`);
  const dataStart = start + marker.length;
  const end = html.indexOf(';\n        let allDates', dataStart);
  if (end < 0) throw new Error(`${label}: newsDatabase end marker missing`);
  const db = JSON.parse(html.slice(dataStart, end));
  const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
  if (!scriptMatch) throw new Error(`${label}: script tag missing`);
  new Function(scriptMatch[1]);
  const latest = Object.keys(db).sort().reverse()[0];
  return {
    label,
    html,
    latest,
    cards: db[latest]?.length || 0,
    latestText: html.match(/최근 업데이트: ([^<]+)/)?.[1]?.trim(),
    nextText: html.match(/다음 업데이트 예정: ([^<]+)/)?.[1]?.trim(),
  };
}

function mondayOfCurrentWeek() {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('en-US', {
      timeZone: 'Asia/Seoul',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).formatToParts(new Date()).map(part => [part.type, part.value])
  );
  const todayKst = new Date(Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day)));
  const day = todayKst.getUTCDay() || 7;
  const monday = new Date(todayKst);
  monday.setUTCDate(todayKst.getUTCDate() - day + 1);
  const year = monday.getUTCFullYear();
  const month = String(monday.getUTCMonth() + 1).padStart(2, '0');
  const date = String(monday.getUTCDate()).padStart(2, '0');
  return `${year}-${month}-${date}`;
}

function fetchUrlToFile(url, label) {
  const target = path.join('/tmp', `farmhannong-${label.replace(/\s+/g, '-')}.html`);
  run('curl', ['-L', '--max-time', '30', '-sS', '-o', target, url]);
  return target;
}

// payload.enc(JSON 문자열)를 .site-access.json의 첫 코드로 복호해 평문 HTML을 돌려준다.
const crypto = require('crypto');
function decryptPayloadText(payloadText, label) {
  const payload = JSON.parse(payloadText);
  const access = JSON.parse(fs.readFileSync(accessPath, 'utf8'));
  const code = access.users?.[0]?.code;
  if (!code) throw new Error('.site-access.json에 코드가 없어 복호 검증 불가');
  const salt = Buffer.from(payload.salt, 'base64');
  const key = crypto.pbkdf2Sync(code.normalize('NFKC'), salt, payload.kdf.iters, 32, 'sha256');
  const dec = (k, obj) => {
    const iv = Buffer.from(obj.iv, 'base64');
    const data = Buffer.from(obj.ct, 'base64');
    const tag = data.subarray(data.length - 16);
    const ct = data.subarray(0, data.length - 16);
    const d = crypto.createDecipheriv('aes-256-gcm', k, iv);
    d.setAuthTag(tag);
    return Buffer.concat([d.update(ct), d.final()]);
  };
  let raw = null;
  for (const w of payload.wraps) { try { raw = dec(key, w); break; } catch (e) {} }
  if (!raw) throw new Error(`${label}: 첫 코드로 wrap 해제 실패(코드/암호문 불일치)`);
  return dec(raw, payload.content).toString('utf8');
}

function parseEncryptedDashboard(payloadText, label) {
  const html = decryptPayloadText(payloadText, label);
  const target = path.join('/tmp', `farmhannong-${label.replace(/\s+/g, '-')}-dec.html`);
  fs.writeFileSync(target, html);
  return parseDashboard(target, label);
}

function ensure(condition, message) {
  if (!condition) throw new Error(message);
}

function maybeSyncDownloads() {
  if (!args.has('--sync-downloads')) return;
  const local = fs.readFileSync(indexPath);
  const current = fs.existsSync(downloadsPath) ? fs.readFileSync(downloadsPath) : null;
  if (!current || !local.equals(current)) {
    fs.copyFileSync(indexPath, downloadsPath);
    console.log(`synced downloads copy: ${downloadsPath}`);
  }
  if (fs.existsSync(sourcePdfsPath)) {
    fs.rmSync(downloadsSourcePdfsPath, { recursive: true, force: true });
    fs.cpSync(sourcePdfsPath, downloadsSourcePdfsPath, { recursive: true });
    console.log(`synced source PDFs: ${downloadsSourcePdfsPath}`);
  }
}

function maybeCommitAndPush(expectedWeek) {
  if (!args.has('--push')) return;

  const porcelain = run('git', ['status', '--porcelain']);
  if (porcelain) {
    run('git', ['add', 'index.html', 'payload.enc', 'scripts/verify_weekly_deploy.js', 'scripts/generate_source_pdfs.py', 'source-pdfs']);
    run('git', ['commit', '-m', `Ensure weekly deployment for ${expectedWeek}`], { stdio: ['ignore', 'pipe', 'pipe'] });
  }

  const branchStatus = run('git', ['status', '--short', '--branch']);
  if (branchStatus.includes('behind')) {
    throw new Error(`local branch is behind origin/main; refusing to push without review\n${branchStatus}`);
  }

  const localSha = run('git', ['rev-parse', 'HEAD']);
  const remoteLine = run('git', ['ls-remote', 'origin', 'refs/heads/main']);
  const remoteSha = remoteLine.split(/\s+/)[0];
  if (localSha !== remoteSha) {
    run('git', ['push', 'origin', 'main'], { stdio: 'inherit' });
  }
}

function main() {
  maybeSyncDownloads();

  const expectedWeek = mondayOfCurrentWeek();
  maybeCommitAndPush(expectedWeek);

  const local = parseDashboard(indexPath, 'local index');
  ensure(okCount(local.cards), `latest week must contain ${REQUIRED_WEEKLY_CARD_COUNT} cards: latest=${local.latest}, cards=${local.cards}`);

  // payload.enc가 app.html과 같은 내용인지(암호화 누락 방지)
  ensure(fs.existsSync(payloadPath), 'payload.enc가 없습니다. node scripts/encrypt_site.js 를 실행하세요.');
  const localPayload = parseEncryptedDashboard(fs.readFileSync(payloadPath, 'utf8'), 'local payload');
  ensure(localPayload.latest === local.latest && localPayload.cards === local.cards,
    `payload.enc가 app.html과 다릅니다(encrypt_site.js 재실행 필요): payload=${localPayload.latest}/${localPayload.cards}, app=${local.latest}/${local.cards}`);
  if (fs.existsSync(downloadsPath)) {
    const downloads = parseDashboard(downloadsPath, 'downloads copy');
    ensure(local.latest === downloads.latest, `downloads copy is not synced: local=${local.latest}, downloads=${downloads.latest}`);
    ensure(okCount(downloads.cards), `downloads copy latest week must contain ${REQUIRED_WEEKLY_CARD_COUNT} cards: latest=${downloads.latest}, cards=${downloads.cards}`);
  } else if (!isGitHubActions) {
    console.warn(`downloads copy not found; skipped local Downloads check: ${downloadsPath}`);
  }
  ensure(local.latestText === local.latest, `recent update label mismatch: label=${local.latestText}, latest=${local.latest}`);
  if (args.has('--expect-current-week')) {
    ensure(local.latest === expectedWeek, `latest week is not current week: latest=${local.latest}, expected=${expectedWeek}`);
  }

  const localSha = run('git', ['rev-parse', 'HEAD']);
  const remoteLine = run('git', ['ls-remote', 'origin', 'refs/heads/main']);
  const remoteSha = remoteLine.split(/\s+/)[0];
  ensure(localSha === remoteSha, `origin/main is not synced: local=${localSha}, remote=${remoteSha}`);

  if (args.has('--check-pages')) {
    // 원격은 암호문(payload.enc)을 받아 복호한 뒤 검사한다. 평문이 원격에 노출되면 안 된다.
    const rawText = fs.readFileSync(fetchUrlToFile('https://raw.githubusercontent.com/ziopeno/farmhannong-agro-weekly-db/main/payload.enc', 'raw payload'), 'utf8');
    const raw = parseEncryptedDashboard(rawText, 'raw payload');
    ensure(raw.latest === local.latest, `raw GitHub payload is stale: raw=${raw.latest}, local=${local.latest}`);
    ensure(okCount(raw.cards), `raw GitHub latest week must contain ${REQUIRED_WEEKLY_CARD_COUNT} cards: latest=${raw.latest}, cards=${raw.cards}`);
    const pagesText = fs.readFileSync(fetchUrlToFile('https://ziopeno.github.io/farmhannong-agro-weekly-db/payload.enc', 'pages payload'), 'utf8');
    const pages = parseEncryptedDashboard(pagesText, 'pages payload');
    ensure(pages.latest === local.latest, `GitHub Pages is stale: pages=${pages.latest}, local=${local.latest}`);
    ensure(okCount(pages.cards), `GitHub Pages latest week must contain ${REQUIRED_WEEKLY_CARD_COUNT} cards: latest=${pages.latest}, cards=${pages.cards}`);
    // 공개 로더에 평문 카드 데이터가 섞여 있지 않은지 확인
    const loader = fs.readFileSync(fetchUrlToFile('https://ziopeno.github.io/farmhannong-agro-weekly-db/', 'pages loader'), 'utf8');
    ensure(loader.indexOf('newsDatabase') === -1, 'public loader page leaks plaintext data');
  }

  console.log(JSON.stringify({
    ok: true,
    latest: local.latest,
    cards: local.cards,
    requiredCards: REQUIRED_WEEKLY_CARD_COUNT,
    nextUpdate: local.nextText,
    localSha,
    remoteSha,
  }, null, 2));
}

main();
