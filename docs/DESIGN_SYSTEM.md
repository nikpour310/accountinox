# Design system — Accountinox

Summary of core design-system classes created in `static/css/main.css` and used across templates.

Core components
- `.btn` : base button reset (inline-flex, center, rounded).
- `.btn-primary` : primary CTA (primary color bg, white text, hover/active states).
- `.btn-secondary` : secondary CTA (border or muted bg).
- `.btn-ghost` : transparent button style.
- `.btn-icon` : small square icon button used in header controls.
- `.card` : card container with padding, rounded corners, shadow.
- `.section-title` : consistent section heading sizing & spacing.
- `.form-input` : input/textarea/select primitives (borders, padding, focus ring).
- `.badge` : small status pill (rounded, bg variants).

Usage notes
- Place `output.css` (generated from `static/css/main.css`) in base template: it is already referenced by `templates/base.html`.
- Prefer semantic composition: use `btn btn-primary` for primary buttons, `card` for content panels, and `form-input` for all form controls.
- Avoid `@apply` of plugin shorthand utilities (e.g., `form-input` uses explicit primitives to prevent circular @apply with plugins).

Files
- Tailwind source: `static/css/main.css`
- Production CSS: `static/css/output.css`
- Tailwind config: `tailwind.config.js`

When adding new components, add them to `static/css/main.css` under `@layer components` and rebuild `npx tailwindcss -i static/css/main.css -o static/css/output.css --minify`.

If you want, I can expand this into a living style guide with examples and screenshots.
