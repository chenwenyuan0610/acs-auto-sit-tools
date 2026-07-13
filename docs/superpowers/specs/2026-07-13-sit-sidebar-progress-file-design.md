# SIT Sidebar and Case Progress File Design

## Goal

Separate case execution and SIT settings in the left workspace, remove case-writing progress from the browser UI, persist that progress in a repository file, and enlarge the select-all checkbox.

## User Interface

The existing left `case-panel` becomes a two-column control area:

- A narrow vertical sidebar with `執行案例` and `設定` buttons.
- A content area showing exactly one corresponding panel.
- `執行案例` is active by default.
- On viewports at or below 980 px, the sidebar becomes a horizontal segmented tab row above its content.

The `執行案例` panel contains:

- Run selected and run all commands.
- The larger select-all checkbox and case count.
- Run summary.
- Case list.

The `設定` panel contains all existing SIT inputs without changing their IDs or request behavior.

Case-writing progress is removed from the page entirely, including the summary box and the per-case implementation label. The select-all checkbox is 20 by 20 px, while individual case checkboxes retain their current compact size.

## Progress File

`data/browser_case_progress.json` becomes the source of truth for case-writing progress. It contains:

```json
{
  "version": 1,
  "trackedIssuerModes": ["selection_sms_oob", "selection_sms_otp", "direct_otp", "direct_oob", "default_oob_can_switch_otp"],
  "cases": {
    "case01": {
      "completedModes": ["direct_otp", "selection_sms_otp"],
      "note": ""
    }
  }
}
```

The backend loads this file and normalizes each catalog case into the existing `caseProgress` and `caseImplementation` API structures. Missing case entries or modes default to pending. Unknown case IDs are ignored so stale records cannot affect the catalog. This preserves API compatibility while removing progress presentation from the browser.

The initial JSON content records the current computed progress so this change does not silently reset existing status.

## Error Handling

- Missing progress file: all cases are treated as pending.
- Invalid JSON or invalid top-level structure: raise a clear progress-file error during catalog loading.
- Invalid mode names: ignore them and keep only tracked issuer modes.
- Duplicate data is naturally avoided by using case IDs as object keys.

## Testing

- Unit tests verify file loading, normalization, missing-file fallback, and invalid JSON handling.
- Catalog API tests verify progress comes from the JSON file and retains the existing response shape.
- Frontend source tests verify the two sidebar panels, hidden inactive panel, removed progress text, and enlarged select-all control.
- Browser verification covers desktop and mobile panel switching, layout overflow, preserved settings, and checkbox size.
- Run the complete Python test suite and JavaScript syntax check before completion.

## Out of Scope

- Editing progress from the browser.
- Automatically marking progress from test execution results.
- Changing existing SIT request fields or execution behavior.
