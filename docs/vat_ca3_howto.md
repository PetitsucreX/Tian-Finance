# How To Run CA3 Monthly Workflow

## 1. Prepare inputs

1. Export Qonto full CSV for the period (date de valeur based).
2. Validate sales/purchases CSVs in monthly output.
3. Create `input/sales_1n_matches.csv` for taxable inflows.

### `sales_1n_matches.csv` format

```csv
transaction_ref,invoice_id,invoice_ttc,invoice_ht,invoice_vat,vat_rate_percent
2026-01-09|client alpha|25080.00,INV001,8360.00,6966.67,1393.33,20
2026-01-09|client alpha|25080.00,INV002,8360.00,6966.67,1393.33,20
2026-01-09|client alpha|25080.00,INV003,8360.00,6966.66,1393.34,20
```

`transaction_ref` must be:

`<value_date>|<normalized_counterparty>|<amount_ttc_2_decimals>`

## 2. Dry run decision summary

```bash
PYTHONPATH=src python3 -m vat_ca3.run --period 2026-02
```

## 3. Confirm execution

```bash
PYTHONPATH=src python3 -m vat_ca3.run --period 2026-02 --confirm
```

## 4. Review outputs

- `ca3_mapping.md`: values to enter in CA3.
- `checklist_impots_gouv.md`: pre-signature checks.
- `exceptions.csv`: anomalies and actions.
- `audit_pack_index.md`: evidence inventory.
- `ca3_result.json`: exact and rounded values.

## 5. After filing

Update filing/payment proofs in the audit pack and rerun if needed to sync ledger metadata.
