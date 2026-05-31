/**
 * Farmhannong Agro Weekly subscription approval endpoint.
 *
 * Deploy this file as a Google Apps Script web app. The public site posts
 * subscription requests here, this script emails the administrator, and the
 * administrator approval link updates the GitHub Actions repository variable
 * SUMMARY_EMAIL_RECIPIENTS.
 */

const CONFIG = {
  ADMIN_EMAIL: 'ziopeno@gmail.com',
  GITHUB_OWNER: 'ziopeno',
  GITHUB_REPO: 'farmhannong-agro-weekly-db',
  RECIPIENT_VARIABLE: 'SUMMARY_EMAIL_RECIPIENTS',
  REQUEST_TTL_MS: 7 * 24 * 60 * 60 * 1000,
};

function doPost(e) {
  try {
    const request = parseSubscriptionRequest_(e);
    const id = Utilities.getUuid();
    const token = Utilities.getUuid().replace(/-/g, '');
    const createdAt = Date.now();

    PropertiesService.getScriptProperties().setProperty(
      requestKey_(id),
      JSON.stringify({ ...request, token, createdAt })
    );

    sendApprovalMail_(id, token, request);

    return jsonResponse_({ ok: true });
  } catch (error) {
    console.error(error);
    return jsonResponse_({ ok: false, error: String(error.message || error) });
  }
}

function doGet(e) {
  try {
    const action = String(e.parameter.action || '');
    if (action !== 'approve') {
      return htmlResponse_('잘못된 요청', '<p>지원하지 않는 승인 요청입니다.</p>');
    }

    const id = String(e.parameter.id || '');
    const token = String(e.parameter.token || '');
    const key = requestKey_(id);
    const store = PropertiesService.getScriptProperties();
    const raw = store.getProperty(key);

    if (!raw) {
      return htmlResponse_('승인 실패', '<p>이미 처리되었거나 만료된 구독 요청입니다.</p>');
    }

    const request = JSON.parse(raw);
    if (request.token !== token) {
      return htmlResponse_('승인 실패', '<p>승인 링크가 올바르지 않습니다.</p>');
    }

    if (Date.now() - Number(request.createdAt || 0) > CONFIG.REQUEST_TTL_MS) {
      store.deleteProperty(key);
      return htmlResponse_('승인 만료', '<p>승인 링크가 만료되었습니다. 다시 구독 요청을 받아주세요.</p>');
    }

    const result = approveRecipient_(request.email);
    store.deleteProperty(key);

    const message = result.added
      ? `${escapeHtml_(request.email)} 주소를 자동발송 수신자에 추가했습니다.`
      : `${escapeHtml_(request.email)} 주소는 이미 자동발송 수신자에 있습니다.`;

    return htmlResponse_('구독 승인 완료', `<p>${message}</p>`);
  } catch (error) {
    console.error(error);
    return htmlResponse_('승인 오류', `<p>${escapeHtml_(String(error.message || error))}</p>`);
  }
}

function parseSubscriptionRequest_(e) {
  const raw = e && e.postData && e.postData.contents ? e.postData.contents : '{}';
  const data = JSON.parse(raw);
  const email = normalizeEmail_(data.email);

  if (!email) {
    throw new Error('메일 주소를 확인할 수 없습니다.');
  }

  return {
    email,
    latestDate: String(data.latestDate || ''),
    sourceUrl: String(data.sourceUrl || ''),
    requestedAt: String(data.requestedAt || new Date().toISOString()),
  };
}

function sendApprovalMail_(id, token, request) {
  const approveUrl = `${ScriptApp.getService().getUrl()}?action=approve&id=${encodeURIComponent(id)}&token=${encodeURIComponent(token)}`;
  const subject = `[Agro Weekly] 구독 승인 요청: ${request.email}`;
  const htmlBody = `
    <div style="font-family:Arial,'Noto Sans KR',sans-serif;line-height:1.6;color:#1a202c">
      <h2>Agro Weekly 구독 승인 요청</h2>
      <p>아래 메일 주소를 자동발송 수신자로 승인하려면 버튼을 눌러주세요.</p>
      <table style="border-collapse:collapse;margin:16px 0">
        <tr><th style="text-align:left;padding:6px 10px;background:#edf2f7">메일 주소</th><td style="padding:6px 10px">${escapeHtml_(request.email)}</td></tr>
        <tr><th style="text-align:left;padding:6px 10px;background:#edf2f7">신청 기준 주차</th><td style="padding:6px 10px">${escapeHtml_(request.latestDate || '-')}</td></tr>
        <tr><th style="text-align:left;padding:6px 10px;background:#edf2f7">신청 시각</th><td style="padding:6px 10px">${escapeHtml_(request.requestedAt || '-')}</td></tr>
      </table>
      <p>
        <a href="${approveUrl}" style="display:inline-block;background:#005a2b;color:#fff;text-decoration:none;padding:12px 18px;border-radius:6px;font-weight:bold">
          구독 승인하기
        </a>
      </p>
      <p style="font-size:13px;color:#4a5568">버튼이 열리지 않으면 아래 주소를 브라우저에 붙여넣으세요.</p>
      <p style="font-size:12px;word-break:break-all;color:#4a5568">${approveUrl}</p>
    </div>
  `;

  MailApp.sendEmail({
    to: CONFIG.ADMIN_EMAIL,
    subject,
    htmlBody,
  });
}

function approveRecipient_(email) {
  const token = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!token) {
    throw new Error('Apps Script Script properties에 GITHUB_TOKEN을 설정해주세요.');
  }

  const currentVariable = getRepositoryVariable_(token, CONFIG.RECIPIENT_VARIABLE);
  const recipients = currentVariable.value
    .split(',')
    .map((item) => normalizeEmail_(item))
    .filter(Boolean);

  if (recipients.includes(email)) {
    return { added: false, value: currentVariable.value };
  }

  recipients.push(email);
  const nextValue = recipients.join(',');
  upsertRepositoryVariable_(token, CONFIG.RECIPIENT_VARIABLE, nextValue, currentVariable.exists);
  return { added: true, value: nextValue };
}

function getRepositoryVariable_(token, name) {
  const url = githubVariableUrl_(name);
  const response = UrlFetchApp.fetch(url, {
    method: 'get',
    headers: githubHeaders_(token),
    muteHttpExceptions: true,
  });

  if (response.getResponseCode() === 404) {
    return { exists: false, value: '' };
  }

  assertGitHubResponse_(response);
  return { exists: true, value: JSON.parse(response.getContentText()).value || '' };
}

function upsertRepositoryVariable_(token, name, value, exists) {
  const url = exists ? githubVariableUrl_(name) : githubVariablesUrl_();
  const payload = exists ? { value } : { name, value };
  const response = UrlFetchApp.fetch(url, {
    method: exists ? 'patch' : 'post',
    contentType: 'application/json',
    payload: JSON.stringify(payload),
    headers: githubHeaders_(token),
    muteHttpExceptions: true,
  });

  assertGitHubResponse_(response);
}

function githubVariableUrl_(name) {
  return `${githubVariablesUrl_()}/${encodeURIComponent(name)}`;
}

function githubVariablesUrl_() {
  return `https://api.github.com/repos/${CONFIG.GITHUB_OWNER}/${CONFIG.GITHUB_REPO}/actions/variables`;
}

function githubHeaders_(token) {
  return {
    Authorization: `Bearer ${token}`,
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
  };
}

function assertGitHubResponse_(response) {
  const code = response.getResponseCode();
  if (code >= 200 && code < 300) {
    return;
  }

  throw new Error(`GitHub API 오류 (${code}): ${response.getContentText()}`);
}

function normalizeEmail_(value) {
  const email = String(value || '').trim().toLowerCase();
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) ? email : '';
}

function requestKey_(id) {
  return `SUBSCRIPTION_REQUEST_${id}`;
}

function jsonResponse_(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}

function htmlResponse_(title, body) {
  return HtmlService.createHtmlOutput(`
    <!doctype html>
    <html lang="ko">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>${escapeHtml_(title)}</title>
      </head>
      <body style="font-family:Arial,'Noto Sans KR',sans-serif;line-height:1.6;padding:32px;color:#1a202c">
        <h1>${escapeHtml_(title)}</h1>
        ${body}
      </body>
    </html>
  `);
}

function escapeHtml_(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
