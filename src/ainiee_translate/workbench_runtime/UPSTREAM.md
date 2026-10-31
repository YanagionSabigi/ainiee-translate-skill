Review Workbench

Source: https://github.com/YanagionSabigi/review-workbench
Commit: 208e5a9bd15b75ca21a201cd97cfdfd85270c101
License: MIT (LICENSE); KaTeX license in web/vendor/katex/LICENSE.
Local patches: AiNiee UI labels and evidence hierarchy; business integration lives outside this runtime.

AiNiee protocol extension: frozen item.allow_empty_blocks lists optional glossary text fields; generic prose remains non-empty. Adapter validates all local submissions against the same protocol as imports and holds the Store lock during consumption.

AiNiee comparison supplies a private project directory for transient diff text, keeping book content in the workspace and avoiding restricted Windows OS temp directories. The upstream compare/git_diff default API behavior remains available.

Portable review export follows upstream slim packaging: no AI skill, examples, Git repository or math assets for plain text.

Upstream version: 0.2.0. Directory toggle uses a contextual sidebar icon. Recipient launchers are copied from templates; old recipient ZIPs must be re-exported.
