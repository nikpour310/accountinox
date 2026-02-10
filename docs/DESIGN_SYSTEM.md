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

Animations
 - `animate-fade-in`: subtle opacity entrance (use for hero sections and main content wrappers).
 - `animate-fade-up`: small upward entrance with fade (use for cards, product items, and list entries).
 - `animate-scale-in`: very small scale + fade for overlays, dropdowns, and modals.
 - `animate-subtle-pop`: quick pop animation for toasts or one-off attention-grabbers.
 - `smooth-hover` / `smooth-transition`: utility class applying `transition-all duration-150 ease-out` for buttons and CTAs.

How to use
- Add `animate-fade-in` to large hero containers: they will gently fade in on load.
- Add `animate-fade-up` to cards and list items to create a cohesive staggered entrance when combined with small JS delays.
- Use `animate-scale-in` on dropdowns and modals to avoid abrupt pop-in behaviour (also works together with Alpine `x-transition`).
- Prefer `smooth-hover` on interactive CTAs to standardize hover timing.

Conservative application
- We apply animations sparingly to avoid motion overload. Current conservative mappings used in the project:
	- `animate-fade-in`: hero sections and footer wrappers.
	- `animate-fade-up`: feature cards, product cards, blog cards.
	- `animate-scale-in`: dropdowns and small overlays (user menu, modals).
	- `smooth-hover`: primary CTAs and major buttons (hero CTAs, product CTAs, signup/login in navbar).
	- `subtle-pop`: small navbar items to draw attention on first load/hover.

If you want the animations removed or changed to be even more subtle (shorter duration or reduced translate), tell me which pattern to tweak and I'll apply it across the project.

After editing animations or utilities, rebuild Tailwind:
```
npx tailwindcss -i static/css/main.css -o static/css/output.css --minify
```
