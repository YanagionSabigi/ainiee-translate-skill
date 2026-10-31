from pathlib import Path
import shutil
import subprocess

import pytest


def test_reading_note_layout_and_source_quote_mapping():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required for frontend behavior checks')
    script = Path(__file__).resolve().parents[1] / '前端/reading-notes.test.mjs'
    result = subprocess.run([node, '--test', str(script)], capture_output=True, timeout=30)
    assert result.returncode == 0, (result.stdout + result.stderr).decode('utf8', errors='replace')
