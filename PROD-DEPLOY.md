# Production Deploy

Use these scripts from the repo root to avoid repeating the same deploy steps every session.

## Rules

- Push the commit first: `git push origin main`
- Frontend deploys go through Vercel.
- Backend deploys do not use `git pull` on the server.
- Backend deploys use `git checkout <commit> -- <paths>` on the server to avoid dragging unrelated worktree changes into production.

## Frontend

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy-frontend-prod.ps1
```

What it does:

1. Runs `npm run build` in `miniapp`
2. Runs `npx vercel deploy --prod --yes`
3. Runs `npx vercel inspect <deployment-url>`

Optional flags:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy-frontend-prod.ps1 -SkipBuild
powershell -ExecutionPolicy Bypass -File .\deploy-frontend-prod.ps1 -SkipInspect
```

## Backend

Safe mode with explicit paths:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy-backend-prod.ps1 `
  -Commit 220390c `
  -Paths auth.py,database.py,handlers/commands.py,miniapp_server.py
```

Fast mode for a backend-only commit:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy-backend-prod.ps1 -Commit (git rev-parse HEAD)
```

What it does:

1. Connects to `getsuga@213.171.26.232`
2. Works inside `/home/getsuga/x-poizon-miniapp`
3. Creates a backup in `/home/getsuga/x-poizon-miniapp-backups/...`
4. Fetches `origin main`
5. Checks out only the requested backend paths from the requested commit
6. Restarts:
   `x-poizon-miniapp.service`
   `x-poizon-bot.service`
7. Calls:
   `http://127.0.0.1:8081/api/health`

If `-Paths` is omitted, the script derives deployable backend paths from the commit and keeps only:

- `auth.py`
- `config.py`
- `database.py`
- `handlers/*`
- `main.py`
- `miniapp_server.py`
- `models.py`
- `requirements.txt`
- `services/*`
- `utils/*`

## Common flows

Frontend-only change:

```powershell
git push origin main
powershell -ExecutionPolicy Bypass -File .\deploy-frontend-prod.ps1
```

Backend-only change:

```powershell
git push origin main
powershell -ExecutionPolicy Bypass -File .\deploy-backend-prod.ps1 -Commit (git rev-parse HEAD)
```

Mixed frontend + backend change:

```powershell
git push origin main
powershell -ExecutionPolicy Bypass -File .\deploy-frontend-prod.ps1
powershell -ExecutionPolicy Bypass -File .\deploy-backend-prod.ps1 -Commit (git rev-parse HEAD) -Paths auth.py,database.py,miniapp_server.py
```

## Current production targets

- Frontend project: `x-poizon-miniapp`
- Main public aliases:
  - `https://app.x-poizon.ru`
  - `https://x-poizon-miniapp.vercel.app`
- Backend server: `getsuga@213.171.26.232`
- Backend path: `/home/getsuga/x-poizon-miniapp`
- Backend services:
  - `x-poizon-miniapp.service`
  - `x-poizon-bot.service`
