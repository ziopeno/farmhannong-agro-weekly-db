#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const repoRoot = path.resolve(__dirname, '..');
const indexPath = path.join(repoRoot, 'index.html');
const downloadsPath = '/Users/ziopeno/Downloads/Farmhannong_Agro_Dashboard_FINAL_V32.html';
const sourcePdfsPath = path.join(repoRoot, 'source-pdfs');
const downloadsSourcePdfsPath = path.join(path.dirname(downloadsPath), 'source-pdfs');
const args = new Set(process.argv.slice(2));
const REQUIRED_WEEKLY_CARD_COUNT = 20;
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
  const now = new Date();
  const day = now.getDay() || 7;
  const monday = new Date(now);
  monday.setDate(now.getDate() - day + 1);
  return monday.toISOString().slice(0, 10);
}

function fetchUrlToFile(url, label) {
  const target = path.join('/tmp', `farmhannong-${label.replace(/\s+/g, '-')}.html`);
  run('curl', ['-L', '--max-time', '30', '-sS', '-o', target, url]);
  return target;
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
    run('git', ['add', 'index.html', 'scripts/verify_weekly_deploy.js', 'scripts/generate_source_pdfs.py', 'source-pdfs']);
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
  ensure(local.cards === REQUIRED_WEEKLY_CARD_COUNT, `latest week must contain exactly ${REQUIRED_WEEKLY_CARD_COUNT} cards: latest=${local.latest}, cards=${local.cards}`);
  if (fs.existsSync(downloadsPath)) {
    const downloads = parseDashboard(downloadsPath, 'downloads copy');
    ensure(local.latest === downloads.latest, `downloads copy is not synced: local=${local.latest}, downloads=${downloads.latest}`);
    ensure(downloads.cards === REQUIRED_WEEKLY_CARD_COUNT, `downloads copy latest week must contain exactly ${REQUIRED_WEEKLY_CARD_COUNT} cards: latest=${downloads.latest}, cards=${downloads.cards}`);
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
    const raw = parseDashboard(fetchUrlToFile('https://raw.githubusercontent.com/ziopeno/farmhannong-agro-weekly-db/main/index.html', 'raw main'), 'raw main');
    ensure(raw.latest === local.latest, `raw GitHub file is stale: raw=${raw.latest}, local=${local.latest}`);
    ensure(raw.cards === REQUIRED_WEEKLY_CARD_COUNT, `raw GitHub latest week must contain exactly ${REQUIRED_WEEKLY_CARD_COUNT} cards: latest=${raw.latest}, cards=${raw.cards}`);
    const pages = parseDashboard(fetchUrlToFile('https://ziopeno.github.io/farmhannong-agro-weekly-db/', 'github pages'), 'github pages');
    ensure(pages.latest === local.latest, `GitHub Pages is stale: pages=${pages.latest}, local=${local.latest}`);
    ensure(pages.cards === REQUIRED_WEEKLY_CARD_COUNT, `GitHub Pages latest week must contain exactly ${REQUIRED_WEEKLY_CARD_COUNT} cards: latest=${pages.latest}, cards=${pages.cards}`);
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
