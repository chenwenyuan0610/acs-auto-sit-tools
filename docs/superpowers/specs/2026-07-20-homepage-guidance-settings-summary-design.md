# Homepage Guidance and Current Settings Summary Design

## Goal

Make the ACS Auto SIT landing experience understandable to a first-time user. The page should explain the intended test workflow, show the effective non-sensitive test context before execution, and preserve the existing execution, settings, advanced-tools, and results behavior.

## Branding

- Browser title and top-left product name: `HiTRUST ACS Cloud Auto SIT Tools`
- Product description: `模擬 ACS 自動化測試交易工具`

## User Guidance

Add a compact guidance panel at the top of the **執行案例** view, before the execution buttons and case list.

The panel uses the heading `開始測試前，請依序完成以下設定` and describes this four-step flow:

1. 前往「設定」，確認本次測試使用的 AReq URL、發卡行模式、語系、OTP 與其他測試參數。
2. 回到「執行案例」，勾選要執行的案例，或選擇全部執行。
3. 執行選取案例並等待測試完成。
4. 前往「測試結果」，查看通過、失敗、略過、錯誤明細，並視需要儲存紀錄或下載 HTML 報告。

The guidance remains visible and compact. It is not a modal, wizard, or dismissible notification, so users can refer to it whenever they return to the execution view.

## Current Settings Summary

Add a responsive `目前測試設定` summary row beneath the product branding in the global header. It remains visible when switching between execution, settings, advanced tools, and results.

The summary displays:

- 發卡行設定
- 發卡行模式
- Challenge 偏好
- 語系
- 可執行案例數
- 已選取案例數

The summary must not display AReq URLs, card numbers, OTP values, lookup URLs, or other long or sensitive settings.

The summary updates when:

- issuer profile changes;
- issuer mode changes;
- preferred challenge changes;
- wording locale changes;
- the available case catalog is reloaded;
- case selection changes, including select-all.

Include a `前往設定` action beside the summary. Activating it switches the existing tabbed interface to the settings panel and preserves current form values.

## Layout and Accessibility

- Reuse the current visual language: compact cards, pills, spacing, borders, and responsive breakpoints.
- Keep the product branding visually primary and the settings summary secondary.
- On narrow screens, allow summary items and guidance steps to wrap into a vertical layout without horizontal overflow.
- Use semantic headings and lists for guidance.
- Give the settings summary an accessible label and use a real button for `前往設定`.
- Existing keyboard tab navigation and ARIA relationships must remain intact.

## Implementation Boundaries

Expected source changes:

- `static/index.html`: branding, guidance markup, summary markup, and cache-busting query updates if needed.
- `static/styles.css`: responsive presentation for the guidance and summary.
- `static/app.js`: derive and refresh current-setting labels, selected-case counts, and settings navigation.
- Frontend tests: assert the new product copy, guidance content, summary fields, sensitive-data exclusion, and update wiring.

No backend API or persisted-settings schema changes are required. The summary reads from the existing form controls and loaded case catalog.

## Verification

- Run focused frontend tests covering static markup and JavaScript wiring.
- Run the full automated test suite.
- Start the local app and verify the page at desktop and mobile widths.
- Confirm the header summary changes after modifying issuer mode, challenge preference, locale, and case selection.
- Confirm `前往設定` opens the settings panel.
- Confirm no sensitive values appear in the header summary and no horizontal overflow is introduced.

