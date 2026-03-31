# Deploy Incident 2026-03-31

## Summary
Oracle Cloud VPS production deploys failed in two separate ways on 2026-03-31. Both issues are now addressed in the GitHub Actions workflow.

## What Failed
1. The VPS working tree had a locally modified `.env`, so `git pull origin main` failed with:
   `error: Your local changes to the following files would be overwritten by merge: .env`
2. After switching away from `git pull`, the VPS still failed during container recreation because the host uses `docker-compose 1.29.2`, which crashed with:
   `KeyError: 'ContainerConfig'`

## Fixes Applied
1. The deploy workflow now uses:
   - `git fetch origin main`
   - `git reset --hard origin/main`
   This makes the VPS checkout match `origin/main` exactly and avoids local file drift blocking deploys.
2. The workflow rewrites `.env` after the git reset so production secrets remain managed by GitHub Actions.
3. The workflow now uses:
   - `docker-compose down --remove-orphans || true`
   - `docker-compose up -d --build`
   This avoids the `docker-compose` recreate path that was crashing on the VPS.
4. A failure trap now prints diagnostics:
   - `docker ps -a`
   - `docker-compose ... ps`
   - `docker-compose ... logs --tail=200`
   - `curl -v http://127.0.0.1:8000/health`

## Relevant Runs
- `23780934643`: failed because tracked `.env` blocked `git pull`
- `23782901349`: failed with `docker-compose` `ContainerConfig`
- `23782937571`: deploy succeeded after compose workflow fix

## Current State
- Production health check: `https://www.dealcat.co.kr/health`
- Expected success response: `{"status":"ok",...}`
- `.env` is no longer tracked in git

## Follow-up
- Consider upgrading the VPS from legacy `docker-compose` v1 to Docker Compose v2.
- Keep production secrets only in GitHub Actions secrets, not in tracked files.

## Traffic Analytics Recommendation
- Start with **Cloudflare Web Analytics** if the goal is simple traffic visibility with minimal ops. This project already sits behind Cloudflare, so setup is the lowest-friction option.
- Use **Umami** if you want a self-hosted product with more product analytics features such as goals, funnels, journeys, retention, UTM, and attribution.
- Use **Plausible** if you want a simple privacy-friendly dashboard but prefer a managed product over operating another service yourself.

### Recommended Order
1. Enable Cloudflare Web Analytics first.
2. Add Umami later only if Cloudflare metrics are not deep enough.
3. Choose Plausible instead of Umami if you want hosted analytics with less server maintenance.

### Cloudflare Web Analytics Checklist
1. Open Cloudflare Dashboard and select the `dealcat.co.kr` zone.
2. Go to `Analytics & Logs` -> `Web Analytics`.
3. Enable Web Analytics for the site.
4. If Cloudflare asks for a script snippet, add it to `templates/index.html` before `</head>`.
5. Deploy once after the snippet change if manual injection is required.
6. Confirm pageviews appear in Cloudflare after a few minutes.
7. Keep this as the default traffic dashboard unless product-level funnel analysis becomes necessary.
