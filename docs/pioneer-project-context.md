# Pioneer / Project Accounting — project context

**Use in future chats:** type `@docs/pioneer-project-context.md` so the agent loads this file.

**Production:** https://projectaccounting-production.up.railway.app  
**Repo:** C:\project_accounting (GitHub → Railway auto-deploy on main)

---

## Android + Railway — one codebase, one deploy

**Goal:** Change UI/logic once, push to GitHub → Railway redeploys → web browsers and Android show the same app.

**Do NOT** build a separate native Android UI duplicating BOM/Ops/Misc screens.

| Phase | What | Result |
|-------|------|--------|
| Now | Django on Railway + shared cockpit HTML/CSS | Single source of truth |
| Phase 2 | PWA — manifest, icons, meta in base_app.html | Android Install app → same Railway URL |
| Phase 3 | TWA — Play Store shell + assetlinks.json | Play Store app loading Railway HTML |
| Optional | Capacitor WebView → production URL | Native plugins without UI rewrite |

**Workflow:** Edit templates/CSS → push main → Railway → refresh web + reopen Android app.

**Layout:** Extend layouts/cockpit.html; shared static/css/pioneer/; mobile sidebar via cockpit-shell.js.

**Planned not built yet:** manifest.webmanifest, PWA icons, optional service worker, TWA android/ folder.

---

## BOM vs Misc — hard boundaries

- Major vs ad-hoc lane: manual only; no auto detection.
- One task = one lane; BOM unrelated to Misc PO/MRO.
- misc_purchase.html frozen unless explicitly asked.
- BOM: Start BOM POST only; bom_print.html + browser print.

---

## Ops dashboard

- Cross-task activity feed; column Project Status/stage.
- Sidebar accordion: default I. FIELD DEFINITION open; one open at a time (localStorage ops-dashboard-nav-open).
- No main-content task switcher.

---

## Git / deploy

- Commit/push only when user asks.
- Push main → Railway (railway.toml + scripts/railway_start.sh).

---

## How to refer in a new chat

1. @docs/pioneer-project-context.md
2. Say: Follow pioneer-project-context and Cursor rules.
3. Open this chat from Chat history.
