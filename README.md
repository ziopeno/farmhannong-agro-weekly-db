# Farmhannong Agro Weekly

Static dashboard for Farmhannong Agro Weekly card news.

Weekly updates must add exactly 20 article cards for the new Monday date key. Use `node scripts/verify_weekly_deploy.js --sync-downloads --expect-current-week` to catch incomplete updates before deployment.

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
