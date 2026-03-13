---
description: "Use when building, styling, or reviewing any Next.js frontend file. Covers component conventions, Tailwind design tokens, RBAC route gating, API wiring, and accessibility standards for the Outdoor Sports Club project."
applyTo: "src/**/*.ts, src/**/*.tsx"
---

# Designer & Frontend Standards — Outdoor Sports Club

## Surfaces & Routing

| Route prefix | Surface | Auth mechanism | Entry point |
| :--- | :--- | :--- | :--- |
| `/` | **Home Page** | None — fully public | Direct URL / any visitor |
| `/portal/*` | **Member Portal** | Cognito Social Login (Google / Facebook) | Login button on Home Page |
| `/admin/*` | **Admin Portal** | Cognito Social Login; Level 4+ required | Login button on Home Page |
| `/kiosk/*` | **Kiosk View** | Device Token (header `x-device-token`) | Auto-loaded on paired tablets |

* The **Home Page** (`/`) is the primary public interface — public content only; no auth required
* After a successful Cognito login from the Home Page, redirect users to `/portal/dashboard` (Level 0–3) or `/admin/dashboard` (Level 4–6) based on `training_level`
* Protect every `/admin/*` route with a server-side level check against `training_level`; redirect Level 3 and below to `/portal/dashboard`
* Protect every `/kiosk/*` route with Device Token middleware; never present a personal login prompt on a kiosk tablet — the kiosk login flow uses the Device Token only and is completely separate from the website
* Guest (Level 0) users may only access `/portal/waiver` and `/portal/guest-payment` until a waiver is signed and fee paid

## Component Conventions

* Components are named functions exported from their own file — never anonymous arrow function module exports
* One component per file; filename matches the component name in PascalCase (e.g., `MemberBadge.tsx`)
* Props interfaces are defined inline above the component and named `<ComponentName>Props`
* Use the Next.js App Router — Server Components by default; add `"use client"` only when the component requires browser APIs, event handlers, or React state

## Tailwind & Design Tokens

Use these tokens consistently across all surfaces:

| Token purpose | Tailwind class(es) |
| :--- | :--- |
| Primary action | `bg-green-700 hover:bg-green-800 text-white` |
| Destructive action | `bg-red-600 hover:bg-red-700 text-white` |
| Neutral / secondary | `bg-gray-100 hover:bg-gray-200 text-gray-900` |
| Card / panel | `bg-white rounded-2xl shadow-md p-6` |
| Page background | `bg-gray-50 min-h-screen` |
| Body text | `text-gray-800 text-base` |
| Label / caption | `text-gray-500 text-sm` |
| Error text | `text-red-600 text-sm` |
| Focus ring | `focus:outline-none focus:ring-2 focus:ring-green-600` |

* No inline styles (`style={{...}}`) anywhere — Tailwind only
* No hardcoded color hex values — use Tailwind's palette

## Kiosk View — Tablet UX Rules

* All interactive elements must have a minimum touch target of **48×48 px** (`min-h-12 min-w-12`)
* Layout must be usable in **portrait orientation** on a standard 10–11" tablet
* Font size for primary kiosk labels: `text-2xl` or larger
* QR scan viewfinder (`html5-qrcode`) must fill at least 60% of viewport width
* The check-in success / failure result must be displayed in a full-screen overlay for immediate visibility:
    * Success: green background, member name, training level confirmed
    * Denied: red background, reason code (e.g., "Level 3 Required", "Waiver Expired")
* Consumable purchase flow: item selection → quantity → NFC payment prompt → confirmation; never skip a step

## API Wiring

* All API base URLs come from `process.env.NEXT_PUBLIC_API_BASE_URL` — never hardcoded
* Device Token for kiosk requests comes from `process.env.NEXT_PUBLIC_DEVICE_TOKEN` — never embedded in source
* Every `fetch` / API call must handle three states: **loading**, **success**, and **error**
* Display a user-visible error message (not just a console log) on every failure path
* Use the endpoint contracts defined in `docs/design.md` Section 7 exactly — do not invent new routes

## RBAC — Level-Gated UI

* Derive the current user's `training_level` from the **AWS Cognito** session token on every protected render
* Hide, disable, or redirect UI elements that exceed the user's level — do not just hide buttons while leaving routes accessible
* Admin Portal section visibility by minimum level:

| Section | Minimum Level |
| :--- | :--- |
| Range Open / Close | Level 4 (RSO / Instructor) |
| Member Management | Level 5 (Administrator) |
| Finance & Ledger | Level 5 (Administrator) |
| Device Pairing | Level 6 (Webmaster) |
| Auth Recovery | Level 6 (Webmaster) |

## Accessibility

* All images and icons must have descriptive `alt` text or `aria-label`
* Form inputs must have associated `<label>` elements (use `htmlFor` / `id` pairing)
* Color is never the sole means of conveying state — pair color with an icon or text label
* Interactive elements must be keyboard-navigable and have visible focus rings (see design tokens above)

## TypeScript

* Strict mode — no implicit `any`
* All component props, API response shapes, and event handler parameters must be explicitly typed
* Define API response types in `src/types/api.ts`; import from there rather than redeclaring inline
* Imports ordered: React → Next.js → third-party → local (`@/`)
* Keep components lean — no speculative abstractions, no unused props, no dead branches. See the Code Complexity & Bloat rules in `.github/instructions/linter.instructions.md`.
