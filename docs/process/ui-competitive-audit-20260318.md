# UI Competitive Audit — 2026-03-18

## Scope
Benchmarked SparkPilot UX expectations against:
- Data Mechanics / Spot Wave
- Unravel Data
- Kubecost
- Pepperdata

## Competitive Baseline (what users expect)

1. **Strong first-run guidance**
   - Guided setup, clear success/fail states, actionable remediation.
2. **Real-time operational visibility**
   - Pipeline/run health + bottlenecks + queue/cluster pressure surfaced quickly.
3. **Cost transparency and controls**
   - Team/project-level chargeback views, budgets, anomaly detection, optimization cues.
4. **Prescriptive recommendations**
   - “What failed, why, what exact command/action fixes it.”

## SparkPilot Current Position (from shipped work this sprint)

### Strengths
- Preflight diagnostics are now first-class (API + CLI + UI), with fail/warn/pass checks and remediation text.
- BYOC-Lite IAM/IRSA/OIDC checks are concrete, with deterministic gate ordering and audit events.
- Environment views now expose provisioning mode and BYOC metadata clearly.
- Access flow includes guided workflow + validation/error mapping.

### Gaps vs competition
- No polished competitive dashboard for cost + health overview yet (cross-page synthesis still limited).
- Visual system still inconsistent in places (design-system maturity lower than best-in-class tools).
- “Executive/FinOps narrative” views (top spend drivers, optimization opportunities, trend forecasting) remain basic.
- Marketing/landing narrative and onboarding polish not yet at competitor level.

## Prioritized UI Actions (next)

1. **Dashboard home revamp**
   - single-pane cards: run health, preflight pass-rate, queue pressure, budget headroom.
2. **FinOps views**
   - add top cost centers, drift/anomaly callouts, and recommended savings actions.
3. **Consistent design system pass**
   - typography, spacing, status colors, empty states, table ergonomics.
4. **Guided customer onboarding wizard**
   - cross-account role/OIDC/trust setup with checkpointed validation and recovery.

## References
- Data Mechanics / Spot acquisition context + Spark optimization framing: https://www.netapp.com/newsroom/press-releases/news-rel-20210622-428076/
- Unravel platform + Spark/FinOps positioning: https://www.unraveldata.com/platform/platform-overview/
- Kubecost cost allocation/optimization positioning: https://www.apptio.com/products/kubecost/
- Pepperdata observability/optimization positioning: https://www.pepperdata.com/solutions/big-data-optimization
