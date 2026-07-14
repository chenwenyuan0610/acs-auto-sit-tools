# Excel Field HTML Validation Design

## Goal

Validate challenge HTML by treating every non-empty wording field imported from `challenge_ui_info.xlsx` as required text, while sending each generated case locale through AReq `browserLanguage`.

## Scope

- Apply strict Excel-field validation only to cases generated from an imported wording workbook.
- Keep the compatibility rules for fixed legacy cases unchanged.
- Use the existing `expected.prompts`, `expected.uiFields`, result comparison, and red missing-text display.
- Do not add a keyword column or another configuration file.

## Validation Rules

Each non-empty Excel wording field is one required text assertion. Before comparison, both expected and actual text are converted to comparable visible text:

- decode HTML entities;
- remove HTML tags while preserving text boundaries;
- collapse repeated whitespace;
- treat `<br>`, block boundaries, and line breaks as whitespace;
- treat `{0}`, `{1}`, and other numbered placeholders as non-empty dynamic values.

A generated case fails when any Excel field is absent. The result contains the original expected field values, captured visible text, and the missing field values so the existing UI can highlight differences in red.

## Result Presentation

The main comparison area shows only information needed to review the test:

- overall status, issuer mode, locale, and `acsTransID`;
- each Excel field name and expected wording;
- whether the wording was found;
- missing wording in red.

The full challenge HTML and raw execution response remain available in a collapsed `技術細節` section. They are not rendered in the main expected or actual result columns.

## Language Mapping

Generated cases continue to map workbook locales to AReq values:

- `zh_TW` -> `zh-TW`
- `en_US` -> `en-US`
- `zh_CN` -> `zh-CN`

The generated case stores the mapped value in `browserLanguage`, and `_transaction_for_case` places it in the outgoing AReq payload.

## Compatibility

Legacy cases may contain descriptive labels or dynamic transaction values and retain their existing normalization and ignore rules. Workbook-generated cases carry an explicit validation mode so their Merchant, Help, amount, card, and other fields are not silently skipped.

## Verification

- Unit-test generated case metadata and all three locale mappings.
- Unit-test HTML tags, entities, whitespace, and numbered placeholders.
- Unit-test that fields ignored by legacy rules remain required for Excel validation.
- Unit-test missing field reporting.
- Unit-test that the main result summary omits full HTML and the collapsed technical details retain it.
- Run the complete test suite before committing and pushing.
