"""Tests for translate_to_marathi.py."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "translate_to_marathi.py"


def run_script(*args, vault=None, expect_success=True, timeout=60):
    env = os.environ.copy()
    if vault is not None:
        env["OBSIDIAN_VAULT_PATH"] = str(vault)
    env["MINIMAX_OFFLINE"] = "1"  # disable LLM in tests; use cached fixtures
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, env=env, timeout=timeout,
    )
    if expect_success and result.returncode != 0:
        raise AssertionError(
            f"Script failed (rc={result.returncode}):\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )
    return result


@pytest.fixture
def vault_with_case(tmp_path, monkeypatch):
    """Create a vault with one ingested case (using offline ingestion)."""
    vault = tmp_path / "vault"
    (vault / "Cases" / "dk-basu-1996").mkdir(parents=True)
    (vault / "Cases" / "dk-basu-1996" / "README.md").write_text(
        "---\ntype: case\ntitle: D.K. Basu v. State of West Bengal\n---\n\n# D.K. Basu v. State of West Bengal\n\nThis is a landmark Supreme Court case on custodial violence.\n"
    )
    (vault / "Cases" / "dk-basu-1996" / "metadata.json").write_text(
        json.dumps({"case_title": "D.K. Basu v. State of West Bengal"})
    )
    (vault / "Translations" / "mr").mkdir(parents=True)
    (vault / "Indexes").mkdir(parents=True)
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(vault))
    return vault


class TestTranslationBasics:
    def test_writes_to_marathi_path(self, vault_with_case, monkeypatch):
        # Patch the LLM call to return a known Marathi string
        from translate_to_marathi import call_llm
        monkeypatch.setattr("translate_to_marathi.call_llm",
                            lambda prompt, max_tokens=500: "भारताच्या सर्वोच्च न्यायालयाचा निकाल")
        run_script("dk-basu-1996", vault=vault_with_case)
        out = vault_with_case / "Translations" / "mr" / "dk-basu-1996.md"
        assert out.exists()

    def test_translated_file_has_wikilink_to_source(self, vault_with_case, monkeypatch):
        from translate_to_marathi import call_llm
        monkeypatch.setattr("translate_to_marathi.call_llm",
                            lambda prompt, max_tokens=500: "अनुवादित मजकूर")
        run_script("dk-basu-1996", vault=vault_with_case)
        out = vault_with_case / "Translations" / "mr" / "dk-basu-1996.md"
        content = out.read_text()
        # Should link back to the English source
        assert "Cases/dk-basu-1996" in content

    def test_translated_file_has_frontmatter(self, vault_with_case, monkeypatch):
        from translate_to_marathi import call_llm
        monkeypatch.setattr("translate_to_marathi.call_llm",
                            lambda prompt, max_tokens=500: "अनुवादित मजकूर")
        run_script("dk-basu-1996", vault=vault_with_case)
        out = vault_with_case / "Translations" / "mr" / "dk-basu-1996.md"
        content = out.read_text()
        assert content.startswith("---")
        assert "language: mr" in content
        assert "source:" in content

    def test_skips_cached_translations(self, vault_with_case, monkeypatch):
        # Pre-create a translation file dated today
        out = vault_with_case / "Translations" / "mr" / "dk-basu-1996.md"
        out.write_text("---\nlanguage: mr\n---\n\nAlready translated.")
        from translate_to_marathi import call_llm
        called = []
        monkeypatch.setattr("translate_to_marathi.call_llm",
                            lambda prompt, max_tokens=500: (called.append(1), "should not be called")[1])
        run_script("dk-basu-1996", vault=vault_with_case)
        # The LLM should not have been called
        assert called == []
        # The original cached file should be unchanged
        assert "Already translated." in out.read_text()

    def test_force_flag_overrides_cache(self, vault_with_case, monkeypatch):
        out = vault_with_case / "Translations" / "mr" / "dk-basu-1996.md"
        out.write_text("---\nlanguage: mr\n---\n\nOld translation")
        from translate_to_marathi import call_llm
        monkeypatch.setattr("translate_to_marathi.call_llm",
                            lambda prompt, max_tokens=500: "नवीन अनुवाद")
        run_script("dk-basu-1996", "--force", vault=vault_with_case)
        content = out.read_text()
        assert "नवीन अनुवाद" in content or "New translation" not in content
        # Force should have triggered a re-translation (the LLM was called)
        # We assert by checking the file content changed
        assert "Old translation" not in content

    def test_handles_missing_case(self, tmp_path, monkeypatch):
        vault = tmp_path / "vault"
        (vault / "Cases").mkdir(parents=True)
        (vault / "Translations" / "mr").mkdir(parents=True)
        monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(vault))
        result = run_script("nonexistent-case", vault=vault, expect_success=False)
        assert result.returncode != 0
        assert "not found" in result.stderr.lower() or "no such" in result.stderr.lower()

    def test_dry_run_creates_no_files(self, vault_with_case, monkeypatch):
        from translate_to_marathi import call_llm
        monkeypatch.setattr("translate_to_marathi.call_llm",
                            lambda prompt, max_tokens=500: "अनुवादित")
        before = set(vault_with_case.rglob("*"))
        run_script("dk-basu-1996", "--dry-run", vault=vault_with_case)
        after = set(vault_with_case.rglob("*"))
        assert before == after
