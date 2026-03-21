# SparkPilot Design System v1 (Working Baseline)

Date: 2026-03-18

## Purpose
Establish a consistent visual and interaction system for Phase 4 UI work so new screens feel unified, trustworthy, and production-grade.

## 1) Color Palette (token-driven)
Source of truth: `ui/app/styles/tokens.css`

### Core surfaces
- `--bg-canvas-top: #eef4f4`
- `--bg-canvas-bottom: #d9e2e1`
- `--surface-0: #f4f8f8`
- `--surface-1: #fcfefe`
- `--surface-2: #f3f8f7`

### Text hierarchy
- `--text-strong: #112029` (headers/primary emphasis)
- `--text: #1a2d38` (default body)
- `--text-soft: #355061` (secondary)
- `--text-muted: #5f7382` (tertiary/help)

### State colors
- Success/brand: `--accent: #0d7f5e`, `--accent-strong: #0b654c`
- Info: `--info: #2869be`
- Warning: `--warning: #8b5600`
- Danger: `--danger: #a63a3a`

### Rule
All new components must consume design tokens (no ad-hoc hex colors unless tokenized first).

## 2) Typography

- Headings use compact tracking and strong color (`h1/h2/h3` in `globals.css`).
- Body text defaults to `--text`; helper copy uses `--text-muted`.
- Monospace text reserved for IDs/code-like values (`ShortId`, technical fields).

### Rule
- Keep copy concise and operator-first.
- Avoid decorative heading variants; use semantic heading levels and tokenized sizes.

## 3) Spacing & Layout

Token scale:
- `--space-1`..`--space-8` (4px to 40px)

Primary layout primitives:
- `.stack` for vertical rhythm
- `.card-grid` for responsive card collections
- `.table-wrap` for data tables
- `.detail-grid` / `.kv-grid` for metadata breakdown

### Rule
Use spacing tokens only; no one-off pixel spacing in new components unless promoted into tokens.

## 4) Component Library (Current + Required)

### Current reusable building blocks
- Card surfaces (`.card`)
- Badges/chips (`badgeClass(...)` patterns)
- Table wrappers + pagination
- Inline links + button variants
- Preflight status list/panel patterns

### Needed next components (priority)
1. Stat/KPI card (title, value, delta, trend)
2. Empty-state component (icon/title/body/CTA)
3. Alert/banner component with severity + remediation slot
4. Standard filter row (search, selects, date range)
5. Timeline/activity list component for run/provisioning events

## 5) Accessibility & Interaction Baseline

- Keep focus-visible states tokenized (`--shadow-focus`)
- Minimum contrast: meet WCAG AA for text and interactive controls
- Preserve keyboard accessibility for expandable rows and action controls

## 6) Implementation Checklist for New Screens

Before merging any new UI screen:
1. Uses tokenized colors/spacing/radii/shadows
2. Includes polished loading/empty/error states
3. Uses consistent card/table/alert patterns
4. Handles narrow/mobile layouts without overflow regressions
5. Includes basic interaction/a11y sanity checks

## 7) Immediate Follow-up

- Extract repeated status/alert/empty-state markup into shared components under `ui/components/`.
- Add visual regression baseline script to avoid ad-hoc screenshot capture.
