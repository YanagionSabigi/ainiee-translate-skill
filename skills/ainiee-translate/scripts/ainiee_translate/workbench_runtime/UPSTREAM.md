Review Workbench

Source: https://github.com/YanagionSabigi/review-workbench
Commit: 3ada76923a62b28cd7a3c5e47dcd423b5f5cf82d
License: MIT (LICENSE); KaTeX license in web/vendor/katex/LICENSE.
Local patches: AiNiee UI labels and evidence hierarchy; business integration lives outside this runtime.

AiNiee protocol extension: frozen item.allow_empty_blocks lists optional glossary text fields; generic prose remains non-empty. Adapter validates all local submissions against the same protocol as imports and holds the Store lock during consumption.

AiNiee comparison supplies a private project directory for transient diff text, keeping book content in the workspace and avoiding restricted Windows OS temp directories. The upstream compare/git_diff default API behavior remains available.

Portable review export follows upstream slim packaging: no AI skill, examples, Git repository or math assets for plain text.

Upstream version: 0.3.0. Navigation shortcuts, status cards, stateful sidebar icons and accept-or-keep page approval are synchronized. Recipient launchers are copied from templates; old recipient ZIPs must be re-exported.

AiNiee 2.1.3 display patch: separate WeRead excerpt/thought h2 sections, unwrap phone-highlight line wraps with source-mapped quotes; frozen material is unchanged.

Local review presets: optional review_profile (glossary/reading) and term_info are AiNiee protocol extensions, not upstream fields. Explicit semantic families, translation-only term decisions, open evidence and two-line previews. Family approval keeps current translations and skips existing drafts/required/submitted items. Current-block comparison excludes frozen display metadata from its single-item validation probe; complete packages retain family-reference validation.
