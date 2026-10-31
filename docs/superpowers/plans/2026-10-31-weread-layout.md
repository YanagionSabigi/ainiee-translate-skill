# WeRead feedback layout and display repair

> **For agentic workers:** Use superpowers:executing-plans. User supplied the concrete layout and authorized release 2.1.3 and installed-skill update.

**Goal:** Separate excerpt/thought headings and panels, show them side by side on desktop, repair phone wraps without changing frozen evidence, and distribute 2.1.3 without a PR.

**Architecture:** A small frontend projection module maps displayed text back to source codepoint ranges. Existing evidence IDs and legacy labels identify groups; existing Python adapters, schema and writeback remain unchanged. Plain JS/CSS and current design tokens continue.

**Spec:** Latest user screenshots and follow-ups; docs/weread-layout-validation.md captures the final agreed behavior. The explanatory UI hint was explicitly removed per follow-up.

## Tasks and evidence

- [x] RED: new Node tests fail because display projection module is absent.
- [x] GREEN: group projections, Chinese/English single wraps, preserved blank paragraphs and thought newlines, exact Unicode quote mapping; 3 new tests pass.
- [x] Integrate h2 sections into app.js, responsive two-column CSS and original source quote mapping. Remove UI hint per steering; keep skill guidance.
- [x] Verify real Oxygen Smith item at 1280/390, separate equal columns / stacked mobile, no overflow or hint. Keep private screenshot/package outside public history.
- [x] Final complete regression: 283 pass; frontend 10 pass; archive/wheel neutral export + display module pass; independent review no findings.
- Release operation after reviewed commit: publish owner main/release and v2.1.3, update installed skill with backup and SHA verification, sync workspace development branch. No PR or upstream writes.

## Review focus

Preserve original material and business CAS; source-offset mapping across removed labels/CRLF/emoji; intentional thought newlines; generic evidence not misclassified; new JS in skill/wheel and slim reviewer export; multiple and unlinked thoughts remain distinct.
