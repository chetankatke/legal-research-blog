# Legal Research System — Setup Notes

## API Status
- **Provider:** MiniMax
- **Base URL:** `https://api.minimax.io/v1`
- **Model:** `MiniMax-M3` (confirmed working)
- **Key:** in `~/.hermes/.env` as `MINIMAX_API_KEY`
- **Marathi translation:** ✅ produces Devanagari
- **Summarization:** ✅ accurate
- **JSON output mode:** ✅ valid JSON, parseable
- **Caveat:** Model emits a `<think>...</think>` reasoning block before the answer. Scripts must strip this block to get clean output. (See `<think>` followed by `</think>` then a blank line, then the actual response.)

## Vault path
- `OBSIDIAN_VAULT_PATH=~/Obsidian/legal-research` (set in `~/.hermes/.env`)

## Folders
- `00-Inbox/` — raw drops (currently empty; reserved for future auto-ingestion)
- `Cases/` — one folder per case (English master)
- `Translations/mr/` — Marathi translations
- `Templates/` — Obsidian templates
- `Indexes/` — auto-populated list of all cases + translations
- `.obsidian/` — Obsidian app config (created on first open)

## Scripts (planned)
- `ingest_to_obsidian.py` — single-case ingester (PDF → case note)
- `translate_to_marathi.py` — Marathi translator
- `post_download.py` — orchestrator ("add to obsidian" / "blog this" trigger)

## v2 (deferred)
- Hindi + 8 other Indian languages
- Deep-research via dzhng/deep-research
- Astro blog site
- Public hosting
