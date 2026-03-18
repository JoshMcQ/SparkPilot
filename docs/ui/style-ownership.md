# UI Style Ownership Boundaries

Global styling is layered under `ui/app/styles/` and imported by `ui/app/globals.css`.

## Layers

1. `tokens.css`
   - Design tokens, spacing, colors, and semantic aliases.
   - Owner: UI foundations.

2. `base.css`
   - Element-level resets and page-level background/text defaults.
   - Owner: UI foundations.

3. `components.css`
   - Cross-page component classes (preflight lists, diagnostics toolbar, reconciliation badges).
   - Owner: feature teams adding shared primitives.

4. `globals.css`
   - Legacy layout and page-level classes still in migration.
   - Owner: page implementers; new shared styles should prefer `styles/components.css`.

## Rules

- Put new tokens only in `tokens.css`.
- Put raw element resets only in `base.css`.
- Put reusable class-level UI patterns in `components.css`.
- Avoid adding new token/base styles directly into `globals.css`.
