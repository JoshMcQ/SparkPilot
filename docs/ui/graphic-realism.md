# SparkPilot UI Graphic Realism Language

This document captures the visual system implemented in `ui/app/globals.css`.

## Design Tokens

- Color system:
  - Neutral canvas and layered material surfaces.
  - Semantic accents for success, info, warning, and danger states.
- Depth:
  - Inset highlights plus soft, medium, and elevated shadows.
- Shape and spacing:
  - Shared radius scale (`xs` to `xl`) and spacing scale (`space-1` to `space-8`).
- Motion:
  - Standardized timing/easing tokens and reduced-motion fallback.

## Realism Principles Applied

- Surfaces use subtle gradients and highlights instead of flat fills.
- Cards, tables, and controls share a consistent border and depth model.
- Header and auth panels use translucent layered materials for continuity.
- Background adds ambient gradients and grain texture for visual atmosphere.

## Interaction and Accessibility

- Buttons, nav links, form controls, and summary toggles all have:
  - hover and active depth changes,
  - clear focus-visible rings,
  - disabled-state affordances.
- Expandable environment rows now support keyboard interaction:
  - `Tab` focus,
  - `Enter` and `Space` toggle.
- Motion honors `prefers-reduced-motion: reduce`.

## Screen Consistency Coverage

- Overview/dashboard
- Environments list/detail
- Runs and diagnostics
- Costs and usage
- Access and governance
- Shared nav/header/auth panel
