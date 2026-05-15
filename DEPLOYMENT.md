# Deployment Notes

## Goal

Use one shared URL where viewers always see the latest weekly Farmhannong Agro Weekly DB.

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

The weekly automation should update `index.html` in this folder, commit the change, and push it to the GitHub repository. The hosting provider will then redeploy the same URL.

