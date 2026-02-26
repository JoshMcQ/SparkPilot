# Jira Setup and Evidence Workflow

## Goal

Create one source of truth for:

- Product delivery tasks
- GTM pipeline tasks
- Security/compliance artifacts
- POC pass/fail evidence

## Jira Project Setup

1. Create Jira project key: `SPARK`.
2. Issue types required:
   - `Epic`
   - `Story`
   - `Task`
   - `Bug`
3. Custom fields:
   - `Evidence Link` (URL)
   - `Acceptance Evidence` (multi-line text)
   - `POC Account` (short text)
4. Status workflow:
   - `To Do`
   - `In Progress`
   - `Blocked`
   - `In Review`
   - `Done`

## Import CSV Backlog

1. Open Jira settings -> `System` -> `External system import` -> `CSV`.
2. Select `planning/jira/sparkpilot_jira_import.csv`.
3. Field mapping:
   - `External ID` -> External issue ID
   - `Issue Type` -> Issue Type
   - `Summary` -> Summary
   - `Description` -> Description
   - `Priority` -> Priority
   - `Labels` -> Labels
   - `Epic Name` -> Epic Name
   - `Parent External ID` -> Parent relationship (or map to Parent)
   - `Story Points` -> Story points
4. Run import.

Alternative (API automation):

```bash
python scripts/jira_import.py \
  --base-url https://your-domain.atlassian.net \
  --email you@example.com \
  --api-token <token> \
  --project SPARK \
  --csv planning/jira/sparkpilot_jira_import.csv
```

Optional env vars for Jira custom fields:

- `JIRA_EPIC_NAME_FIELD_ID`
- `JIRA_EPIC_LINK_FIELD_ID`
- `JIRA_STORY_POINTS_FIELD_ID`

## Suggested Dashboards

1. Delivery board:
   - Filter: `project = SPARK AND labels in (product,security)`
   - Gadgets:
     - Sprint burndown
     - Created vs resolved
     - Blocked issues
2. GTM board:
   - Filter: `project = SPARK AND labels in (gtm,poc,design-partner)`
   - Gadgets:
     - Two-dimensional filter statistics (`Status x Assignee`)
     - Average age chart
3. Evidence board:
   - Filter: `project = SPARK AND "Evidence Link" is EMPTY AND status = Done`
   - Gadget:
     - Filter results

## Evidence Rules (Non-Optional)

Every issue marked `Done` must include at least one of:

1. Link to PR/commit
2. Link to test output/screenshot/recording
3. Link to customer call notes
4. Link to signed document (POC criteria, order form, security review)

## Weekly Review Rhythm

Every Friday:

1. Review KPI issues:
   - Qualified conversations
   - Demo->POC conversion
   - Days-to-POC-start
2. Mark any missed KPI as `Blocked` and create one corrective task per miss.
3. Export Jira filter results for investor/advisor proof pack.
