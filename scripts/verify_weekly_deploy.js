#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const repoRoot = path.resolve(__dirname, '..');
const indexPath = path.join(repoRoot, 'index.html');
const downloadsPath = '/Users/ziopeno/Downloads/Farmhannong_Agro_Dashboard_FINAL_V32.html';
const args = new Set(process.argv.slice(2));

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

function fetchUrl(url) {
  return run('curl', ['-L', '--max-time', '30', '-sS', url]);
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
}

function maybeCommitAndPush(expectedWeek) {
  if (!args.has('--push')) return;

  const porcelain = run('git', ['status', '--porcelain']);
  if (porcelain) {
    run('git', ['add', 'index.html', 'scripts/verify_weekly_deploy.js']);
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
  const downloads = parseDashboard(downloadsPath, 'downloads copy');
  ensure(local.latest === downloads.latest, `downloads copy is not synced: local=${local.latest}, downloads=${downloads.latest}`);
  ensure(local.latestText === local.latest, `recent update label mismatch: label=${local.latestText}, latest=${local.latest}`);
  if (args.has('--expect-current-week')) {
    ensure(local.latest === expectedWeek, `latest week is not current week: latest=${local.latest}, expected=${expectedWeek}`);
  }

  const localSha = run('git', ['rev-parse', 'HEAD']);
  const remoteLine = run('git', ['ls-remote', 'origin', 'refs/heads/main']);
  const remoteSha = remoteLine.split(/\s+/)[0];
  ensure(localSha === remoteSha, `origin/main is not synced: local=${localSha}, remote=${remoteSha}`);

  if (args.has('--check-pages')) {
    const raw = parseRemoteHtml(fetchUrl('https://raw.githubusercontent.com/ziopeno/farmhannong-agro-weekly-db/main/index.html'), 'raw main');
    ensure(raw.latest === local.latest, `raw GitHub file is stale: raw=${raw.latest}, local=${local.latest}`);
    const pages = parseRemoteHtml(fetchUrl('https://ziopeno.github.io/farmhannong-agro-weekly-db/'), 'github pages');
    ensure(pages.latest === local.latest, `GitHub Pages is stale: pages=${pages.latest}, local=${local.latest}`);
  }

  console.log(JSON.stringify({
    ok: true,
    latest: local.latest,
    cards: local.cards,
    nextUpdate: local.nextText,
    localSha,
    remoteSha,
  }, null, 2));
}

function parseRemoteHtml(html, label) {
  const tempPath = path.join('/tmp', `farmhannong-${label.replace(/\s+/g, '-')}.html`);
  fs.writeFileSync(tempPath, html);
  return parseDashboard(tempPath, label);
}

main();
