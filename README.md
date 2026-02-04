# Accountinox

Accountinox — یک فروشگاه آنلاین برای فروش اکانت‌ها و یک CMS/پنل مدیریت کامل.

Stack:
- Next.js (App Router) + TypeScript
- TailwindCSS (RTL + Vazirmatn ready)
- PostgreSQL + Prisma
- NextAuth (Google + Credentials)
- Socket.io (Realtime chat)
- Payments: provider pattern (Zarinpal, Zibal)
- Tests: Vitest (unit), Playwright (e2e)

Quick start

1. Copy .env.example to .env and fill values
2. Start postgres locally (docker-compose up -d)
3. npm install
4. npx prisma generate
5. npx prisma migrate dev --name init
6. npm run seed
7. npm run dev

Notes
- AES_SECRET must be a 32-byte secret encoded in base64 and prefixed with 'base64:'.
- Disable source maps in production builds.

What's included (scaffold)
- Prisma schema with models (User, Product, Post, Order, Payment, etc.)
- Site settings model including tailwindMode toggle
- AES-GCM encrypt/decrypt helpers
- Keyword extractor utility + unit tests
- Docker + docker-compose for postgres + redis
- Seed script to create admin, sample product and post

Next steps (TODO)
- Implement full Auth flows (NextAuth + OTP)
- Admin UI and RBAC middleware
- Payment provider implementations and secure callbacks
- Chat realtime server + client integration
- SEO utilities, sitemap, robots
- Playwright e2e tests for login + checkout

Contributing
Feel free to open issues or PRs. See docs/ for more information.

## Tailwind Online/Offline

Site uses `SiteSetting.tailwindMode` to decide whether to inject Tailwind from CDN or use local built CSS. Change this from Admin Settings (or directly in DB) to switch modes.

## OTP and Auth

OTP can be enabled/disabled from site settings. A stub SMS provider is shipped by default; connect a real provider by updating `SMS_PROVIDER` and related keys.

## Tests

- Unit: `npm test` (vitest)
- E2E: `npx playwright test` (requires Playwright installation and running dev server)
