# VAT CA3 v0.1

This repository now includes a reproducible monthly CA3 workflow with exception-stop controls.

> **语音/视频逐字稿工具**：把 iPhone「语音备忘录」（经 iCloud 同步到 Mac）、文件夹或
> 「照片」库里的录音/视频，用本地 faster-whisper **一字不漏**转成逐字稿，可**从手机一键
> 触发 Mac 转写**。详见 [`docs/voice_transcriber_howto.md`](docs/voice_transcriber_howto.md)。
> 快速开始：`pip install -e ".[transcriber]"` 然后
> `voice-transcriber transcribe --source voicememos --output-dir ~/Desktop/逐字稿`。

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
