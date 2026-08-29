---
name: python-scripts
description: Maintenance/import Python scripts in scripts/ - what each one does and how to run it. Load before writing, editing, or running any script under scripts/, or when asked to import tournament data, dedupe players, or export the DB seed.
---

# Python scripts (`scripts/`)

Install deps once: `pip install -r scripts/requirements.txt`

| Script | Purpose | Run |
|--------|---------|-----|
| `export_seed.py` | Dumps live DB → `db/seed.sql` | `python scripts/export_seed.py` |
| `import_challonge.py` | Imports a Challonge tournament into the DB | `python scripts/import_challonge.py --api-key <key>` |
| `import_mtgtop8.py` | Imports top 8 from mtgtop8.com with fuzzy player matching | `python scripts/import_mtgtop8.py --url "https://mtgtop8.com/event?e=XXX"` |
| `players_fusion.py` | Interactive dedup of player pseudos → `scripts/fusion.sql` | `python scripts/players_fusion.py` |

`fusion.sql` is gitignored — it's an output artifact to review and execute manually, never commit it.
