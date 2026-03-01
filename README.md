# Pediatric Fever Clinical Decision Support

Production-ready v1 includes:
- CHOP-first rules-spec router with transparent activation reasons
- YAML pathway scaffolds for all configured pathways
- Deterministic UTICalc pretest lookup (2-24 months)
- Consistency validator for sources, pathway graphs, and router references
- Streamlit Router + Pathway Navigator
- Pure-Python smoke tests for key clinical scenarios

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run Streamlit App

```bash
streamlit run app.py
```

## Scaffold Pathway Stubs

```bash
python tools/scaffold_pathways.py
```

This creates any missing `pathways/<id>.yaml` stubs from `source/sources.yaml`.

## Validate

```bash
python tools/validate_all.py
```

Checks:
- every source pathway id has `pathways/<id>.yaml`
- each graph has `start` and `end`
- every node has `source_urls`
- link nodes target existing pathway ids
- `pathways/master_router.yaml` references only known pathway ids

## Smoke Test Router

```bash
python tools/smoke_test_router.py
```

Scenarios covered:
- Kawasaki activation with fever >=5 days and KD features >=4
- UTICalc >=2% pathway activation (2-24 months)
- Seizure parallel activation (febrile seizure + meningitis)
- Orbital/preseptal activation and critical escalation with pain on EOM
- Sepsis activation and critical escalation with hypoxia

## Fill in CHOP Algorithm Steps Safely

1. Open the pathway YAML (for example: `pathways/fever_infant.yaml`).
2. Replace `algorithm_stub` and `definitions_stub` with structured nodes and edges curated manually from the source pathway page.
3. Keep `id`, `source_urls`, and edge connectivity valid.
4. Preserve at least one `source_urls` entry on every node.
5. Re-run `python tools/validate_all.py` after edits.

Important constraints enforced in this repo:
- Do not scrape CHOP pages for algorithm steps.
- Do not invent medical logic inside pathway graph content.
- Keep router behavior transparent via explicit activation reasons.
