# Farmhannong Agro Weekly

Static dashboard for Farmhannong Agro Weekly card news.

Weekly updates must add exactly 20 article cards for the new Monday date key. Use `node scripts/verify_weekly_deploy.js --sync-downloads --expect-current-week` to catch incomplete updates before deployment.

## Server-side Weekly Automation

This repository includes a GitHub Actions workflow at `.github/workflows/weekly-update.yml`.

- Schedule: every Monday 09:00 Korea Standard Time.
- Runner: GitHub-hosted Ubuntu runner, so the local Mac does not need to be on.
- Flow: collect agrochemical/agriculture market news, generate exactly 20 Korean card-news items with OpenAI, update `index.html`, generate source evidence PDFs, verify the dashboard, then commit and push to `main`.
- Email flow: send the latest weekly briefing to configured recipients with a card-news PDF attachment and an inline JPG summary in the email body.

Required repository secret:

- `OPENAI_API_KEY`: OpenAI API key used by the weekly generation script.

Optional repository variable:

- `OPENAI_MODEL`: model name. If empty, the script uses `gpt-4.1-mini`.
- `SUMMARY_EMAIL_RECIPIENTS`: optional admin-only comma-separated email recipient list for weekly summary emails.
- `SITE_URL`: optional public site URL used in summary emails.

Optional repository secrets for weekly summary email:

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM`

If email recipients or SMTP settings are empty, the weekly update still runs and email sending is skipped.

The public `구독하기` button can send a subscription request to an approval endpoint. The approval endpoint emails the administrator, and the administrator approval link adds the address to `SUMMARY_EMAIL_RECIPIENTS`. For privacy and security, the public static page must not contain a GitHub token or SMTP password.

## Subscription Approval Setup

The approval endpoint is implemented as a Google Apps Script template at `scripts/subscription_approval_apps_script.js`.

1. Create a fine-grained GitHub token that can read and write repository Actions variables for `ziopeno/farmhannong-agro-weekly-db`.
2. Create a Google Apps Script project and paste the contents of `scripts/subscription_approval_apps_script.js`.
3. In Apps Script, open `Project Settings` -> `Script properties` and add `GITHUB_TOKEN` with the GitHub token value.
4. Deploy the Apps Script project as a web app with access set to `Anyone`.
5. Copy the web app URL and put it in `index.html` as `subscriptionApprovalEndpoint`.

After this setup, visitors enter only their email address. The administrator receives an approval email at `ziopeno@gmail.com`; clicking `구독 승인하기` automatically updates the repository variable `SUMMARY_EMAIL_RECIPIENTS`.

If `subscriptionApprovalEndpoint` is empty, the site keeps the older fallback behavior and opens a prefilled email request to the administrator.

Manual run:

1. Open the GitHub repository.
2. Go to `Actions`.
3. Select `Weekly Agro News Update`.
4. Click `Run workflow`.
5. Leave `target_date` blank for the current Monday, or enter a Monday date such as `2026-06-01`.

## Deployment

This folder is prepared for static hosting.

- Entry file: `index.html`
- Build command: none
- Output directory: project root

Recommended deployment flow:

1. Create a GitHub repository named `farmhannong-agro-weekly-db`.
2. Upload `index.html`, `.nojekyll`, and this `README.md`.
3. Connect the repository to Cloudflare Pages or Netlify.
4. Set the production branch to `main`.
5. Share the deployed site URL with viewers.

Viewers should use the deployed URL, not an emailed HTML attachment. The URL will keep showing the latest deployed version after weekly updates.

## Permissions

Only repository collaborators with write access can edit or delete the dashboard source.
People who receive only the deployed site URL can view the dashboard but cannot modify the source file.
