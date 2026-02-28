# VAT CA3 v0.1

This repository now includes a reproducible monthly CA3 workflow with exception-stop controls.

## Command

```bash
PYTHONPATH=src python3 -m vat_ca3.run --period 2026-02
```

The command always prints:
1. A decision summary.
2. An execution plan.

Then it waits for confirmation. To execute writes:

```bash
PYTHONPATH=src python3 -m vat_ca3.run --period 2026-02 --confirm
```

## Mandatory rules implemented

- VAT on cash basis (`date de valeur`) for collected VAT.
- 1:N matching between one bank inflow and multiple invoices (`sales_1n_matches.csv`).
- Line 22 from previous month line 27, unless explicit override exists.
- Fiscal rounding to euro with exact values kept in `ca3_result.json`.
- Exception-stop: any blocking error prevents final CA3 mapping output.

## Expected monthly files

Period folder convention:

- `Bilan 2026/TVA_Codex/<YYYY-MM>/input/qonto_transactions_full_<YYYY-MM>.csv`
- `Bilan 2026/TVA_Codex/<YYYY-MM>/input/sales_1n_matches.csv`
- `Bilan 2026/TVA_Codex/<YYYY-MM>/output/tva_<YYYY-MM>_saisie_manuelle_ventes_validees.csv`
- `Bilan 2026/TVA_Codex/<YYYY-MM>/output/tva_<YYYY-MM>_saisie_manuelle_tva_validees.csv`
- `Bilan 2026/TVA_Codex/<YYYY-MM>/output/<YYYY-MM>_audit_pack/pieces_index.csv`

Optional override file (empty by default, fill only if needed):

- `data/vat_ca3/line22_overrides.csv`

## Outputs per month

Generated in `Bilan 2026/TVA_Codex/<YYYY-MM>/output/ca3_workflow/`:

- `ca3_mapping.md`
- `checklist_impots_gouv.md`
- `exceptions.csv`
- `audit_pack_index.md`
- `ca3_result.json`
- `decision_summary.md`

Ledger updated at runtime (not committed):

- `data/ca3_ledger.csv`

## Safety

- No automatic submission to impots.gouv.
- If `exceptions.csv` contains an `ERROR`, workflow stops before final mapping.
