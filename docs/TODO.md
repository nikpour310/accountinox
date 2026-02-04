# TODO - Phase 0 — Bootstrap & cPanel-ready Foundation

Status: In Progress

Tasks
- [x] Scaffold Next.js TS (App Router)
- [x] ESLint/Prettier + scripts (basic package.json present)
- [x] Tailwind (local) + RTL + Vazirmatn + theme tokens
- [x] Prisma init + Postgres schema (prisma/schema.prisma)
- [x] Dockerfile + docker-compose for dev (Postgres + Redis)
- [x] Layout عمومی: Header/Footer جذاب و مشترک
- [x] صفحات placeholder: / /shop /blog /auth /admin
- [x] cPanel readiness: next.config.js output standalone + productionBrowserSourceMaps=false
- [x] server.js entrypoint note (create server.js)
- [x] README base with cPanel draft

Next Steps (remaining in Phase 0)
- [ ] Add server.js entrypoint file to run standalone build under cPanel
- [ ] Add ESLint/Prettier config files
- [ ] Ensure `npm run build` produces standalone output and provide a small test to run it
- [ ] Commit convention: separate commits per logical change
- [x] Add server.js entrypoint file to run standalone build under cPanel
- [x] Add ESLint/Prettier config files
- [ ] Ensure `npm run build` produces standalone output and provide a small test to run it
- [ ] Commit convention: separate commits per logical change

Notes:
- Follow PHASE 0 acceptance criteria before moving to PHASE 1.

## TODO - Phase 1 — Auth & RBAC + Rate-limit

Status: Not Started

Tasks
- [ ] NextAuth: Google OAuth (config present)
- [ ] Credentials: email+password (present)
- [ ] Credentials: phone+password (OTP flow)
- [ ] Password hashing: Argon2 (present)
- [ ] OTP module:
	- [ ] DB model (PhoneVerification) — present
	- [x] API send/verify OTP (provider: stub)
	- [x] enable/disable via SiteSetting (checked at runtime)
- [ ] RBAC:
	- [ ] roles: ADMIN, EDITOR, SUPPORT, CUSTOMER (present)
		- [x] middleware protect /admin (ADMIN only)
	- [ ] helper checkPermission for API routes
- [ ] Rate limit on login/otp (basic rate limit for OTP send)
 - [x] Rate limit on OTP send (basic 60s check)
- [ ] AuditLog for auth events

Notes:
- Before implementing, ensure Phase 0 is accepted (standalone build verified).
- Implement minimal, safe stubs for SMS provider; no secrets in code.

### Temporary: Prisma v6 pinning (requested quick fix)

These steps are a short, targeted task-list to unblock the build by pinning Prisma to v6.x as requested.
- [ ] Pin `prisma` and `@prisma/client` to the same v6.x version (e.g. `6.0.0`) in `package.json`
- [ ] Remove `node_modules` and incompatible lockfile, reinstall dependencies
- [ ] Run `npx prisma generate` to generate the client
- [ ] Run `npm run build` (standalone) and verify output
- [ ] Report logs and mark these tasks complete
- [x] Pin `prisma` and `@prisma/client` to the same v6.x version (e.g. `6.0.0`) in `package.json`
- [x] Remove `node_modules` and incompatible lockfile, reinstall dependencies
- [x] Run `npx prisma generate` to generate the client
- [x] Run `npm run build` (standalone) and verify output
- [x] Report logs and mark these tasks complete

Note: After this temporary pin is successful we will either keep v6 for now or plan a proper migration to Prisma v7 in a later phase.

