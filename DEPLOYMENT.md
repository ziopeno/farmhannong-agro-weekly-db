# Deployment Notes

## Goal

Use one shared URL where viewers always see the latest weekly Farmhannong Agro Weekly.

## Recommended Setup

Use GitHub as the source of truth and Cloudflare Pages or Netlify as the public website.

### GitHub Repository

- Repository name: `farmhannong-agro-weekly-db`
- Visibility:
  - Public if using GitHub Pages on a free GitHub account.
  - Private is possible with Cloudflare Pages/Netlify, but Cloudflare/Netlify must be granted access to the private repository.
- Write access: only the administrator account.

### Cloudflare Pages

Settings:

- Framework preset: None
- Build command: empty
- Build output directory: `/`
- Production branch: `main`

Cloudflare Pages deploys automatically when `index.html` is updated and pushed to `main`.

### Sharing

Share only the deployed website URL. Do not share the raw HTML file as an email attachment if weekly updates should continue.

People with the URL can keep using the same URL every week. They do not need a new file after each update.

## Weekly Automation

The weekly automation should update `index.html` in this folder with exactly 20 article cards for the new Monday date key, commit the change, and push it to the GitHub repository. The hosting provider will then redeploy the same URL.

Run `node scripts/verify_weekly_deploy.js --sync-downloads --expect-current-week` before deployment. The check fails if the latest week has anything other than 20 cards.

## GitHub Actions Automation

The repository now contains `.github/workflows/weekly-update.yml` for server-side weekly updates.

Schedule:

- Monday 09:00 Korea Standard Time
- GitHub cron: `0 0 * * 1`

Required setup in GitHub:

1. Open `Settings` -> `Secrets and variables` -> `Actions`.
2. Add repository secret `OPENAI_API_KEY`.
3. Optional: add repository variable `OPENAI_MODEL`; leave it empty to use the script default.
4. Optional email recipients: add repository variable `SUMMARY_EMAIL_RECIPIENTS` with comma-separated addresses. This is the admin-only place to edit recipients.
5. Optional email SMTP secrets: add `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, and `SMTP_FROM`.

After this is set, GitHub runs the weekly updater on its own server. The local Mac and GitHub Desktop do not need to be open.

The workflow can also be run manually from `Actions` -> `Weekly Agro News Update` -> `Run workflow`.

For Gmail SMTP, use `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, and an app password as `SMTP_PASSWORD`. Do not put email passwords inside `index.html`.

The site subscription popup is a safe request flow: visitors enter an email address, then the site sends the request to the configured approval endpoint. The endpoint emails the administrator an approval link. When the administrator clicks the link, the endpoint updates `SUMMARY_EMAIL_RECIPIENTS` in GitHub. The public static page must not contain a GitHub token or SMTP password.

Subscription approval setup:

1. Copy `scripts/subscription_approval_apps_script.js` into a Google Apps Script project.
2. Add Script property `GITHUB_TOKEN` with a fine-grained GitHub token that can read and write repository Actions variables.
3. Deploy the script as a web app with access set to `Anyone`.
4. Paste the deployed web app URL into `index.html` as `subscriptionApprovalEndpoint`.

If `subscriptionApprovalEndpoint` is left empty, the popup falls back to opening a prefilled request email to the administrator.

Weekly emails use the subject `Ageo weekly 공유 ('YYYY-MM-DD')`, start with `금주의 Agro weekly를 공유드리오니 업무에 참고 부탁드립니다.`, include a JPG summary in the email body, and attach the full card-news PDF.
