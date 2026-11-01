# Review presets validation · 2026-11-01

Local branch: `feat/workbench-030-review-presets`, based on AiNiee `05c1fb3`. Upstream Workbench 0.3.0: `3ada76923a62b28cd7a3c5e47dcd423b5f5cf82d`. No push, PR, release or installed-skill modification.

## Automated evidence

- Before implementation: 15 glossary/reading/portable baseline tests passed.
- New preset tests initially failed for missing review-data, profile and 0.3.0 resources; helper tests initially failed for missing glossary module.
- Full Python regression: **295 passed**, `pytest --basetemp ../../测试/p9 --tb=short`, 93.57 s, after the keyboard fix. The run required local-socket permission for the existing progress service test.
- Historical full-field glossary binding regression is included in the final full suite (also passed independently). Old frozen packages can still edit their original category/note fields and preserve unknown fields; new term packages restrict edits to dst.
- Actual local-runtime Node tests: **17 passed**, `node --test 测试/前端/*.test.mjs`. Includes upstream navigation/diff/draft cases, WeRead source quote offsets, term previews, cross-page eligibility and in-memory DOM tests of actual app components/actions.
- `build.py --check`: source and bundled scripts identical. Local skill ZIP and wheel built and inspected for glossary metadata, glossary.js and navigation.js. Portable synthetic demo exports both modules and frozen metadata.
- Portable formal submit → return JSON → import → compare → apply tested with independent derived terms, preserved private fields and no blanket adoption of alternative translations.
- `git diff --check`: no whitespace errors.

Full logs remain local under `local/presets-*-tests.txt`; public test fixtures contain synthetic data only.

## Verified behavior

- Ordinary terms have no top queue; derived terms show only their family and a class approval button. Active search/status/facet filters disable whole-family approval until cleared.
- Shared previews show source above current translation, choosing before until explicit accept/edit. A proposed alternative cannot replace the displayed name by default.
- Family approval keeps provisional translations across pages and excludes roots, other families, required items, existing edits/comments/quotes and submitted entries.
- Term details default open and show four metadata labels. Comparison contains dst only; redundant rationale and source-context disclosure are absent.
- Metadata rejects unknown/duplicate associations, cyclic relationships, invalid context/page types and ambiguous family identities. Legacy homographs without source-keyed metadata remain independently reviewable through index/hash bindings.

## Limitations and manual review

**No desktop/mobile browser visual verification is claimed.** In-app browser timed out on the local service. Native browser tooling then stopped because it could not determine the current Windows browser URL confidently enough to enforce its policy; no alternate browser automation was attempted. The in-memory DOM checks verify component structure and actions, not actual typography, wrapping or responsive layout. Inspect the synthetic package on desktop and a narrow screen before accepting the visual layout.

Synthetic artifacts (ignored local files):

- `local/presets-dist/术语校对-合成演示-最终.zip`: 35 synthetic terms, two derived families, account family across two preview pages, one proposed alternative and missing-evidence case. Extract and run `开始校对.cmd`.
- `local/presets-dist/ainiee-translate-review-presets-local.zip`: local skill build, not a published release.
- `local/presets-dist/ainiee_translate-2.1.3-py3-none-any.whl`: local feature build; existing AiNiee release number unchanged.

Independent code review completed with one P2 finding: Space on a focused button was intercepted by the upstream navigation shortcut. The regression failed before the fix, then all 17 frontend tests passed. Native buttons and button-role controls are now excluded; the reviewer verified the narrow fix and source/bundle parity. No other consequential findings. The first reviewer was unavailable due service usage limits; the fallback review completed normally.

## Release acceptance

On 2026-11-01 the user explicitly accepted the implementation and authorized merging into their main, pushing to their remote and publishing 2.2.0. This supersedes the development-phase local-only restriction above. The accepted changes are applied onto origin/main; local-only historical drafts are not included. Automated browser screenshots were not re-claimed.
