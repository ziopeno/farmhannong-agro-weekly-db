#!/usr/bin/env node
// app.html(평문, git 미추적)을 AES-256-GCM으로 암호화해 payload.enc를 만든다.
// 콘텐츠 키 K는 실행마다 새로 뽑고, .site-access.json의 사용자별 입장 코드로
// 각각 K를 감싼다(wrap). 코드 하나를 지우고 재실행하면 그 사람만 접근 불가가 된다.
//
// 사용법:  node scripts/encrypt_site.js
// 입력:    app.html, .site-access.json   →   출력: payload.enc
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const repoRoot = path.resolve(__dirname, '..');
const appPath = path.join(repoRoot, 'app.html');
const accessPath = path.join(repoRoot, '.site-access.json');
const outPath = path.join(repoRoot, 'payload.enc');

const PBKDF2_ITERS = 150000;

function deriveKey(code, salt) {
  return crypto.pbkdf2Sync(code.normalize('NFKC'), salt, PBKDF2_ITERS, 32, 'sha256');
}

function encryptGcm(key, plaintextBuf) {
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
  const ct = Buffer.concat([cipher.update(plaintextBuf), cipher.final(), cipher.getAuthTag()]);
  return { iv: iv.toString('base64'), ct: ct.toString('base64') };
}

function main() {
  const html = fs.readFileSync(appPath);
  const access = JSON.parse(fs.readFileSync(accessPath, 'utf8'));
  const users = (access.users || []).filter(u => u && u.code);
  if (!users.length) throw new Error('.site-access.json에 사용자 코드가 없습니다');

  const salt = crypto.randomBytes(16);
  const contentKey = crypto.randomBytes(32);

  const wraps = users.map(u => encryptGcm(deriveKey(u.code, salt), contentKey));
  const content = encryptGcm(contentKey, html);

  const payload = {
    v: 1,
    kdf: { name: 'PBKDF2-SHA256', iters: PBKDF2_ITERS },
    salt: salt.toString('base64'),
    wraps,
    content,
  };
  fs.writeFileSync(outPath, JSON.stringify(payload));
  console.log(JSON.stringify({
    ok: true,
    users: users.length,
    appBytes: html.length,
    payloadBytes: fs.statSync(outPath).size,
    out: path.relative(repoRoot, outPath),
  }, null, 2));
}

main();
