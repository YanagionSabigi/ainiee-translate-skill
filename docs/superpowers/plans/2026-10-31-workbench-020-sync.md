# Workbench 0.2.0 synchronization

> **For agentic workers:** Use superpowers:executing-plans. This is an upstream synchronization within the previously approved integration design.

**Goal:** Synchronize directory navigation and portable launchers from workbench 0.2.0, install locally and publish AiNiee 2.1.2 on the owner's branches without a PR.

**Architecture:** Retain plain HTML/CSS/JS, existing paper/green CSS tokens, Python service and all AiNiee business adapters. Three-way merge changed upstream files from 9a3b0d6 to 208e5a9; include launcher templates as wheel data as well as skill files.

**Spec:** Existing 2026-10-30 integration design, latest user request, and upstream docs/releases/0.2.0.md. No redesign alternatives are needed for this explicit upstream synchronization.

## Global constraints

- Recipient Python 3.11+, jsonschema >=4.23,<5; no automatic install/download; Node.js 18+ only for formula decisions.
- No skill, examples, Git repository or duplicate templates inside recipient ZIPs. No private book data in public artifacts.
- Existing ZIPs require re-export. Full AI skill installer retains SKILL and templates.
- macOS executable permissions can be checked here; do not claim macOS runtime verification.

## Task 1: Synchronize runtime and packaging

- [x] Extend portable integration test to require Windows/macOS launchers, permissions and dependency guidance; run RED against old export.
- [x] Merge upstream transfer.py, index.html, app.js, app.css and runtime version; add launcher templates and wheel package-data.
- [x] Rebuild bundle; run portable test GREEN and workbench compatibility tests.

## Task 2: Validate and distribute

- [x] Document sidebar behavior and distinguish released skill vs recipient demo package; bump metadata to 2.1.2.
- [x] Re-export private Oxygen test package; inspect desktop/mobile sidebar and real Windows startup from a Chinese/spaced path.
- [x] Run full regression, upstream Python/Node tests, build and inspect ZIP/wheel from neutral directories.
- [x] Independent code review; fix important findings. Commit and push only owner's main/release, publish new release, synchronize installed skill and canonical checkout.

## Review focus

- Wheel must contain non-Python launcher templates, including the Chinese CMD filename.
- CMD fallback and errors must preserve helpful output without hidden installation.
- Collapsed directory must remain keyboard accessible and show correct tooltip/ARIA state.
- Private Oxygen package is local only; upstream public demo links must be identified as workbench examples.
- Recipient package must not carry its own duplicate template directory.

## Execution record

Task 1 complete: launcher regression RED (CMD missing) → GREEN. Task 2 validation complete: 282 AiNiee, 36 upstream Python and 7 Node tests pass; ZIP/wheel neutral exports pass. Independent review: no findings. Browser visual checks unavailable because Windows URL policy could not determine current URL; documented in acceptance report. Publication and installed-skill synchronization are completed in the following release operation.
