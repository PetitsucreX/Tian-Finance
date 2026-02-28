from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


DATE_PATTERNS = [
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%d/%m/%Y",
    "%d/%m/%Y %H:%M",
    "%d-%m-%Y",
    "%d-%m-%Y %H:%M:%S",
]

FINALIZED_STATUS_HINTS = {
    "executed",
    "settled",
    "completed",
    "booked",
    "processed",
    "succeeded",
    "paid",
    "validated",
    "comptabilise",
    "effectue",
    "execute",
}

NON_FINAL_STATUS_HINTS = {
    "processing",
    "pending",
    "cancelled",
    "canceled",
    "rejected",
    "declined",
    "failed",
    "initiated",
    "draft",
    "in progress",
}


@dataclass
class ExceptionItem:
    severity: str
    code: str
    message: str
    action: str


@dataclass
class SaleRow:
    value_date: date
    counterparty: str
    amount_ttc: float
    reference: str


@dataclass
class MatchRow:
    transaction_ref: str
    invoice_id: str
    invoice_ttc: float
    invoice_ht: float
    invoice_vat: float
    vat_rate_percent: float


@dataclass
class Paths:
    root: Path
    period: str
    period_dir: Path
    bank_csv: Path
    sales_csv: Path
    purchases_csv: Path
    sales_matches_csv: Path
    proofs_csv: Path
    output_dir: Path
    exceptions_csv: Path
    mapping_md: Path
    checklist_md: Path
    audit_pack_index_md: Path
    result_json: Path
    decision_summary_md: Path
    ledger_csv: Path
    line22_overrides_csv: Path


def parse_period(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Period must be YYYY-MM") from exc
    return value


def normalize_text(value: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    compact = re.sub(r"[^a-zA-Z0-9]+", " ", ascii_text.lower()).strip()
    return re.sub(r"\s+", " ", compact)


def parse_decimal(value: object) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    text = text.replace("\u00a0", " ").replace(" ", "")
    text = text.replace("EUR", "").replace("eur", "").replace("€", "")

    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")

    text = re.sub(r"[^0-9+\-.]", "", text)
    if text in {"", "+", "-", "."}:
        return None

    try:
        number = float(text)
    except ValueError:
        return None

    return -number if negative else number


def parse_date(value: object) -> Optional[date]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass

    for pattern in DATE_PATTERNS:
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def round_euro(value: float) -> int:
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def round2(value: float) -> float:
    return round(value + 1e-12, 2)


def previous_period(period: str) -> str:
    dt = datetime.strptime(period + "-01", "%Y-%m-%d")
    year = dt.year
    month = dt.month - 1
    if month == 0:
        year -= 1
        month = 12
    return f"{year:04d}-{month:02d}"


def status_is_final(status_value: str) -> bool:
    if not status_value:
        return True
    norm = normalize_text(status_value)
    for bad in NON_FINAL_STATUS_HINTS:
        if bad in norm:
            return False
    for good in FINALIZED_STATUS_HINTS:
        if good in norm:
            return True
    return True


def yes_value(value: object) -> bool:
    norm = normalize_text(str(value or ""))
    return norm in {"oui", "yes", "y", "1", "true"}


def read_csv_rows(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    text = None
    used_encoding = None
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = path.read_text(encoding=encoding)
            used_encoding = encoding
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError(f"Cannot decode CSV: {path}")

    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        delimiter = ";" if sample.count(";") >= sample.count(",") else ","
        dialect = csv.excel()
        dialect.delimiter = delimiter

    rows: List[Dict[str, str]] = []
    with path.open("r", encoding=used_encoding, newline="") as handle:
        reader = csv.DictReader(handle, dialect=dialect)
        headers = reader.fieldnames or []
        for row in reader:
            rows.append(row)
    return headers, rows


def find_column(headers: List[str], aliases: Iterable[str]) -> Optional[str]:
    norm_map = {normalize_text(h): h for h in headers}
    for alias in aliases:
        norm = normalize_text(alias)
        if norm in norm_map:
            return norm_map[norm]
    return None


def canonical_transaction_ref(value_date: date, counterparty: str, amount_ttc: float) -> str:
    cp = normalize_text(counterparty)
    return f"{value_date.isoformat()}|{cp}|{amount_ttc:.2f}"


def make_paths(root: Path, period: str, year_folder: str, output_subdir: str) -> Paths:
    period_dir = root / year_folder / "TVA_Codex" / period
    output_dir = period_dir / "output" / output_subdir
    return Paths(
        root=root,
        period=period,
        period_dir=period_dir,
        bank_csv=period_dir / "input" / f"qonto_transactions_full_{period}.csv",
        sales_csv=period_dir / "output" / f"tva_{period}_saisie_manuelle_ventes_validees.csv",
        purchases_csv=period_dir / "output" / f"tva_{period}_saisie_manuelle_tva_validees.csv",
        sales_matches_csv=period_dir / "input" / "sales_1n_matches.csv",
        proofs_csv=period_dir / "output" / f"{period}_audit_pack" / "pieces_index.csv",
        output_dir=output_dir,
        exceptions_csv=output_dir / "exceptions.csv",
        mapping_md=output_dir / "ca3_mapping.md",
        checklist_md=output_dir / "checklist_impots_gouv.md",
        audit_pack_index_md=output_dir / "audit_pack_index.md",
        result_json=output_dir / "ca3_result.json",
        decision_summary_md=output_dir / "decision_summary.md",
        ledger_csv=root / "data" / "ca3_ledger.csv",
        line22_overrides_csv=root / "data" / "vat_ca3" / "line22_overrides.csv",
    )


def add_exception(exceptions: List[ExceptionItem], severity: str, code: str, message: str, action: str) -> None:
    exceptions.append(ExceptionItem(severity=severity, code=code, message=message, action=action))


def load_bank_index(paths: Paths, exceptions: List[ExceptionItem]) -> Dict[str, List[Dict[str, object]]]:
    if not paths.bank_csv.exists():
        add_exception(
            exceptions,
            "ERROR",
            "MISSING_BANK_CSV",
            f"Fichier bancaire introuvable: {paths.bank_csv}",
            "Exporter Qonto Full Data CSV puis relancer.",
        )
        return {}

    headers, rows = read_csv_rows(paths.bank_csv)
    date_col = find_column(headers, ["Date de la valeur (UTC)", "Date de la valeur", "Settlement Date", "Value Date"])
    status_col = find_column(headers, ["Statut", "Status"])
    cp_col = find_column(headers, ["Nom de la contrepartie", "Counterparty", "Counterparty Name"])
    credit_col = find_column(headers, ["Crédit", "Credit"])
    debit_col = find_column(headers, ["Débit", "Debit"])
    amount_col = find_column(headers, ["Montant total (TTC)", "Amount", "Montant"])

    if not date_col or not cp_col:
        add_exception(
            exceptions,
            "ERROR",
            "BANK_COLUMNS_MISSING",
            "Colonnes minimales absentes dans l'export Qonto (date valeur / contrepartie).",
            "Utiliser l'export complet Qonto (Full Data).",
        )
        return {}

    index: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for row_idx, row in enumerate(rows, start=2):
        value_date = parse_date(row.get(date_col))
        if value_date is None:
            continue
        if value_date.strftime("%Y-%m") != paths.period:
            continue

        status = str(row.get(status_col) or "") if status_col else ""
        if not status_is_final(status):
            continue

        amount = None
        if credit_col or debit_col:
            credit = parse_decimal(row.get(credit_col)) if credit_col else None
            debit = parse_decimal(row.get(debit_col)) if debit_col else None
            if credit is not None or debit is not None:
                amount = (credit or 0.0) - (debit or 0.0)
        if amount is None and amount_col:
            amount = parse_decimal(row.get(amount_col))

        if amount is None:
            continue

        counterparty = str(row.get(cp_col) or "").strip()
        if not counterparty:
            continue

        ref = canonical_transaction_ref(value_date, counterparty, abs(amount))
        index[ref].append(
            {
                "row": row_idx,
                "value_date": value_date.isoformat(),
                "counterparty": counterparty,
                "amount_ttc": round2(abs(amount)),
                "status": status,
            }
        )

    return index


def load_taxable_sales(paths: Paths, exceptions: List[ExceptionItem]) -> List[SaleRow]:
    if not paths.sales_csv.exists():
        add_exception(
            exceptions,
            "ERROR",
            "MISSING_SALES_CSV",
            f"Fichier ventes validées introuvable: {paths.sales_csv}",
            "Produire/valider tva_<period>_saisie_manuelle_ventes_validees.csv.",
        )
        return []

    headers, rows = read_csv_rows(paths.sales_csv)
    date_col = find_column(headers, ["date", "value_date", "Date"])
    cp_col = find_column(headers, ["counterparty", "contrepartie", "Nom du client"])
    amount_col = find_column(headers, ["amount_ttc", "montant_ttc", "Montant TTC"])
    flag_col = find_column(headers, ["collectee_oui_non", "collectee", "taxable"])

    if not date_col or not cp_col or not amount_col or not flag_col:
        add_exception(
            exceptions,
            "ERROR",
            "SALES_COLUMNS_MISSING",
            "Colonnes requises absentes dans le fichier ventes validées.",
            "Vérifier les colonnes: date, counterparty, amount_ttc, collectee_oui_non.",
        )
        return []

    taxable_sales: List[SaleRow] = []
    for row_idx, row in enumerate(rows, start=2):
        if not yes_value(row.get(flag_col)):
            continue

        value_date = parse_date(row.get(date_col))
        counterparty = str(row.get(cp_col) or "").strip()
        amount_ttc = parse_decimal(row.get(amount_col))

        if value_date is None or not counterparty or amount_ttc is None:
            add_exception(
                exceptions,
                "ERROR",
                "INVALID_SALES_ROW",
                f"Ligne invalide dans ventes validées (row {row_idx}).",
                "Compléter date, contrepartie et montant TTC.",
            )
            continue

        if value_date.strftime("%Y-%m") != paths.period:
            add_exception(
                exceptions,
                "ERROR",
                "SALES_OUT_OF_PERIOD",
                f"Vente taxable hors période détectée (row {row_idx}, {value_date}).",
                "Corriger la date de valeur ou la période.",
            )
            continue

        taxable_sales.append(
            SaleRow(
                value_date=value_date,
                counterparty=counterparty,
                amount_ttc=abs(amount_ttc),
                reference=canonical_transaction_ref(value_date, counterparty, abs(amount_ttc)),
            )
        )

    return taxable_sales


def load_sales_matches(paths: Paths, exceptions: List[ExceptionItem]) -> Dict[str, List[MatchRow]]:
    if not paths.sales_matches_csv.exists():
        add_exception(
            exceptions,
            "ERROR",
            "MISSING_MATCHES_CSV",
            f"Fichier de matching 1:N introuvable: {paths.sales_matches_csv}",
            "Créer input/sales_1n_matches.csv (transaction_ref, invoice_id, invoice_ttc, invoice_ht, invoice_vat, vat_rate_percent).",
        )
        return {}

    headers, rows = read_csv_rows(paths.sales_matches_csv)
    ref_col = find_column(headers, ["transaction_ref"])
    id_col = find_column(headers, ["invoice_id", "facture_id"])
    ttc_col = find_column(headers, ["invoice_ttc", "ttc", "montant_ttc"])
    ht_col = find_column(headers, ["invoice_ht", "ht", "montant_ht"])
    vat_col = find_column(headers, ["invoice_vat", "vat", "montant_tva"])
    rate_col = find_column(headers, ["vat_rate_percent", "vat_rate", "taux_tva"])

    if not all([ref_col, id_col, ttc_col, ht_col, vat_col, rate_col]):
        add_exception(
            exceptions,
            "ERROR",
            "MATCH_COLUMNS_MISSING",
            "Colonnes requises absentes dans sales_1n_matches.csv.",
            "Colonnes attendues: transaction_ref, invoice_id, invoice_ttc, invoice_ht, invoice_vat, vat_rate_percent.",
        )
        return {}

    grouped: Dict[str, List[MatchRow]] = defaultdict(list)
    for row_idx, row in enumerate(rows, start=2):
        ref = str(row.get(ref_col) or "").strip()
        invoice_id = str(row.get(id_col) or "").strip()
        ttc = parse_decimal(row.get(ttc_col))
        ht = parse_decimal(row.get(ht_col))
        vat = parse_decimal(row.get(vat_col))
        rate = parse_decimal(row.get(rate_col))

        if not ref or not invoice_id or None in {ttc, ht, vat, rate}:
            add_exception(
                exceptions,
                "ERROR",
                "INVALID_MATCH_ROW",
                f"Ligne invalide dans sales_1n_matches.csv (row {row_idx}).",
                "Compléter transaction_ref, invoice_id, invoice_ttc, invoice_ht, invoice_vat, vat_rate_percent.",
            )
            continue

        grouped[ref].append(
            MatchRow(
                transaction_ref=ref,
                invoice_id=invoice_id,
                invoice_ttc=abs(ttc),
                invoice_ht=abs(ht),
                invoice_vat=abs(vat),
                vat_rate_percent=abs(rate),
            )
        )

    return grouped


def load_line20_exact(paths: Paths, exceptions: List[ExceptionItem]) -> float:
    if not paths.purchases_csv.exists():
        add_exception(
            exceptions,
            "ERROR",
            "MISSING_PURCHASES_CSV",
            f"Fichier achats validés introuvable: {paths.purchases_csv}",
            "Produire/valider tva_<period>_saisie_manuelle_tva_validees.csv.",
        )
        return 0.0

    headers, rows = read_csv_rows(paths.purchases_csv)
    date_col = find_column(headers, ["date", "value_date"])
    vat_col = find_column(headers, ["vat_amount", "montant_tva", "tva"])
    flag_col = find_column(headers, ["deductible_oui_non", "deductible", "tax_deductible"])

    if not vat_col or not flag_col:
        add_exception(
            exceptions,
            "ERROR",
            "PURCHASE_COLUMNS_MISSING",
            "Colonnes requises absentes dans le fichier achats validés.",
            "Vérifier les colonnes: vat_amount, deductible_oui_non.",
        )
        return 0.0

    total = 0.0
    for row_idx, row in enumerate(rows, start=2):
        if not yes_value(row.get(flag_col)):
            continue
        if date_col:
            value_date = parse_date(row.get(date_col))
            if value_date is not None and value_date.strftime("%Y-%m") != paths.period:
                add_exception(
                    exceptions,
                    "WARN",
                    "PURCHASE_OUT_OF_PERIOD",
                    f"Achat déductible hors période (row {row_idx}, {value_date}).",
                    "Vérifier que la date de valeur est dans la période CA3.",
                )
        vat = parse_decimal(row.get(vat_col))
        if vat is None:
            add_exception(
                exceptions,
                "ERROR",
                "PURCHASE_VAT_MISSING",
                f"Montant TVA manquant sur achat déductible (row {row_idx}).",
                "Compléter vat_amount pour les lignes déductibles.",
            )
            continue
        total += abs(vat)

    return total


def load_line22_override_from_file(paths: Paths) -> Optional[float]:
    if not paths.line22_overrides_csv.exists():
        return None
    headers, rows = read_csv_rows(paths.line22_overrides_csv)
    period_col = find_column(headers, ["period", "periode"])
    override_col = find_column(headers, ["line22_override", "ligne22_override", "line22"])
    if not period_col or not override_col:
        return None
    for row in rows:
        if str(row.get(period_col) or "").strip() == paths.period:
            return parse_decimal(row.get(override_col))
    return None


def load_previous_line27_from_ledger(paths: Paths) -> Optional[float]:
    if not paths.ledger_csv.exists():
        return None
    headers, rows = read_csv_rows(paths.ledger_csv)
    period_col = find_column(headers, ["period", "periode"])
    line27_col = find_column(headers, ["line27_to_report", "line27", "line_27"])
    if not period_col or not line27_col:
        return None

    target_prev = previous_period(paths.period)
    for row in rows:
        if str(row.get(period_col) or "").strip() == target_prev:
            return parse_decimal(row.get(line27_col))
    return None


def resolve_line22(paths: Paths, cli_override: Optional[float], exceptions: List[ExceptionItem]) -> Tuple[float, str]:
    if cli_override is not None:
        return abs(cli_override), "cli_override"

    file_override = load_line22_override_from_file(paths)
    if file_override is not None:
        return abs(file_override), "file_override"

    prev_line27 = load_previous_line27_from_ledger(paths)
    if prev_line27 is not None:
        return abs(prev_line27), "auto_prev_line27"

    add_exception(
        exceptions,
        "ERROR",
        "LINE22_UNRESOLVED",
        "Impossible de déterminer la ligne 22 (report crédit du mois précédent).",
        "Renseigner data/vat_ca3/line22_overrides.csv ou line27_to_report dans le ledger du mois précédent.",
    )
    return 0.0, "missing"


def compute_collected_from_matches(
    taxable_sales: List[SaleRow],
    grouped_matches: Dict[str, List[MatchRow]],
    bank_index: Dict[str, List[Dict[str, object]]],
    exceptions: List[ExceptionItem],
) -> Tuple[Dict[float, Dict[str, float]], float, float]:
    by_rate: Dict[float, Dict[str, float]] = defaultdict(lambda: {"base": 0.0, "tax": 0.0})
    total_base = 0.0
    total_tax = 0.0

    taxable_refs = {sale.reference for sale in taxable_sales}

    for sale in taxable_sales:
        matches = grouped_matches.get(sale.reference, [])
        if not matches:
            add_exception(
                exceptions,
                "ERROR",
                "MATCH_MISSING",
                f"Aucun matching 1:N pour la vente taxable {sale.reference}.",
                "Ajouter les factures dans input/sales_1n_matches.csv.",
            )
            continue

        ttc_sum = sum(m.invoice_ttc for m in matches)
        ht_sum = sum(m.invoice_ht for m in matches)
        vat_sum = sum(m.invoice_vat for m in matches)

        if abs(ttc_sum - sale.amount_ttc) > 0.02:
            add_exception(
                exceptions,
                "ERROR",
                "MATCH_SUM_MISMATCH",
                (
                    f"Mismatch TTC pour {sale.reference}: transaction={round2(sale.amount_ttc)} "
                    f"vs factures={round2(ttc_sum)}."
                ),
                "Corriger le matching des factures (1:N).",
            )

        if abs((ht_sum + vat_sum) - ttc_sum) > 0.03:
            add_exception(
                exceptions,
                "ERROR",
                "INVOICE_TOTAL_INCOHERENT",
                (
                    f"Incohérence HT+TVA!=TTC pour {sale.reference}: "
                    f"HT+TVA={round2(ht_sum + vat_sum)} TTC={round2(ttc_sum)}."
                ),
                "Vérifier HT/TVA/TTC des factures liées.",
            )

        bank_rows = bank_index.get(sale.reference, [])
        if not bank_rows:
            add_exception(
                exceptions,
                "ERROR",
                "BANK_MATCH_MISSING",
                f"Aucune transaction bancaire finale trouvée pour {sale.reference}.",
                "Vérifier date de valeur, contrepartie et montant côté Qonto.",
            )

        for m in matches:
            rate = m.vat_rate_percent
            by_rate[rate]["base"] += m.invoice_ht
            by_rate[rate]["tax"] += m.invoice_vat
            total_base += m.invoice_ht
            total_tax += m.invoice_vat

    # Extra rows in matching file that do not map to taxable sales.
    for ref in grouped_matches:
        if ref not in taxable_refs:
            add_exception(
                exceptions,
                "WARN",
                "UNUSED_MATCH_ROW",
                f"Matching non utilisé: {ref}",
                "Supprimer ou rattacher ce groupe à une vente taxable.",
            )

    return by_rate, total_base, total_tax


def write_exceptions(path: Path, items: List[ExceptionItem]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["severity", "code", "message", "action_recommandee"])
        for item in items:
            writer.writerow([item.severity, item.code, item.message, item.action])


def render_audit_pack_index(proofs_csv: Path, out_md: Path) -> None:
    lines = ["# Audit Pack Index", ""]
    if not proofs_csv.exists():
        lines.extend(
            [
                "Aucun index de pièces trouvé.",
                "",
                "Action: fournir `pieces_index.csv` dans l'audit pack du mois.",
            ]
        )
        out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    headers, rows = read_csv_rows(proofs_csv)
    id_col = find_column(headers, ["piece_id", "id"])
    type_col = find_column(headers, ["type"])
    status_col = find_column(headers, ["status", "statut"])
    path_col = find_column(headers, ["path", "chemin"])
    note_col = find_column(headers, ["note", "comment"])

    lines.extend([
        "| Piece | Type | Statut | Chemin | Note |",
        "|---|---|---|---|---|",
    ])

    for row in rows:
        piece_id = str(row.get(id_col) or "") if id_col else ""
        piece_type = str(row.get(type_col) or "") if type_col else ""
        status = str(row.get(status_col) or "") if status_col else ""
        piece_path = str(row.get(path_col) or "") if path_col else ""
        note = str(row.get(note_col) or "") if note_col else ""
        lines.append(f"| {piece_id} | {piece_type} | {status} | {piece_path} | {note} |")

    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_mapping(
    path: Path,
    period: str,
    line22_source: str,
    by_rate: Dict[float, Dict[str, float]],
    line20_exact: float,
    line22_exact: float,
    totals_exact: Dict[str, float],
    totals_rounded: Dict[str, int],
) -> None:
    rate_20_base = totals_exact["line08_base"]
    rate_20_tax = totals_exact["line08_tax"]

    lines = [
        f"# CA3 Mapping {period}",
        "",
        "## Regles appliquees",
        "- TVA sur encaissements: date de valeur bancaire uniquement.",
        "- Matching 1:N obligatoire entre encaissement et factures.",
        "- Arrondi fiscal a l'euro sur les lignes declaratives.",
        f"- Ligne 22 source: `{line22_source}`.",
        "",
        "## Ordre de saisie impots.gouv (arrondi euro)",
        f"1. A1 = {totals_rounded['a1']}",
        f"2. Ligne 08 (20%) base = {totals_rounded['line08_base']} ; taxe = {totals_rounded['line08_tax']}",
        f"3. Ligne 20 = {totals_rounded['line20']}",
        f"4. Ligne 22 = {totals_rounded['line22']}",
        f"5. Ligne 23 = {totals_rounded['line23']}",
        f"6. Ligne 32 = {totals_rounded['line32']}",
        "",
        "## Exact vs Arrondi",
        "| Ligne | Exact | Arrondi | Delta |",
        "|---|---:|---:|---:|",
        f"| A1 | {round2(rate_20_base)} | {totals_rounded['a1']} | {round2(totals_rounded['a1'] - rate_20_base)} |",
        f"| 08 base | {round2(rate_20_base)} | {totals_rounded['line08_base']} | {round2(totals_rounded['line08_base'] - rate_20_base)} |",
        f"| 08 taxe | {round2(rate_20_tax)} | {totals_rounded['line08_tax']} | {round2(totals_rounded['line08_tax'] - rate_20_tax)} |",
        f"| 20 | {round2(line20_exact)} | {totals_rounded['line20']} | {round2(totals_rounded['line20'] - line20_exact)} |",
        f"| 22 | {round2(line22_exact)} | {totals_rounded['line22']} | {round2(totals_rounded['line22'] - line22_exact)} |",
        f"| 16 | {round2(totals_exact['line16'])} | {totals_rounded['line16']} | {round2(totals_rounded['line16'] - totals_exact['line16'])} |",
        f"| 23 | {round2(totals_exact['line23'])} | {totals_rounded['line23']} | {round2(totals_rounded['line23'] - totals_exact['line23'])} |",
        f"| 32 | {round2(totals_exact['line32'])} | {totals_rounded['line32']} | {round2(totals_rounded['line32'] - totals_exact['line32'])} |",
        "",
        "## TVA collectee par taux (exact)",
        "| Taux | Base HT | TVA |",
        "|---:|---:|---:|",
    ]

    for rate in sorted(by_rate.keys()):
        lines.append(f"| {rate:g}% | {round2(by_rate[rate]['base'])} | {round2(by_rate[rate]['tax'])} |")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_checklist(path: Path, period: str) -> None:
    lines = [
        f"# Checklist impots.gouv - CA3 {period}",
        "",
        "1. Ouvrir `ca3_mapping.md` et reprendre les montants arrondis.",
        "2. Vérifier que la ligne 22 correspond au report crédit validé.",
        "3. Vérifier que `exceptions.csv` ne contient aucun `ERROR`.",
        "4. Contrôler les pièces de preuve dans `audit_pack_index.md`.",
        "5. Saisir manuellement dans impots.gouv (pas de soumission automatique).",
        "6. Après dépôt/paiement: archiver accusé + preuve de paiement.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_existing_ledger_row(ledger_csv: Path, period: str) -> Dict[str, str]:
    if not ledger_csv.exists():
        return {}
    headers, rows = read_csv_rows(ledger_csv)
    period_col = find_column(headers, ["period"])
    if not period_col:
        return {}
    for row in rows:
        if str(row.get(period_col) or "").strip() == period:
            return row
    return {}


def update_ledger(
    ledger_csv: Path,
    period: str,
    values: Dict[str, int],
    line27_to_report: int,
    result_json: Path,
    proofs_csv: Path,
    existing_row: Dict[str, str],
    filing_date: str,
    payment_date: str,
    payment_proof: str,
) -> None:
    required_fields = [
        "period",
        "a1",
        "line08_base",
        "line08_tax",
        "line20",
        "line22",
        "line23",
        "line32",
        "line27_to_report",
        "filing_date",
        "payment_date",
        "currency",
        "rounding",
        "source_json",
        "pieces_index",
        "certificate_depot",
        "payment_proof",
        "notes",
    ]

    rows: List[Dict[str, str]] = []
    fieldnames: List[str] = []
    if ledger_csv.exists():
        old_headers, old_rows = read_csv_rows(ledger_csv)
        fieldnames = list(old_headers)
        rows = old_rows

    for field in required_fields:
        if field not in fieldnames:
            fieldnames.append(field)

    row_data = {k: "" for k in fieldnames}
    row_data.update(existing_row)
    row_data.update(
        {
            "period": period,
            "a1": str(values["a1"]),
            "line08_base": str(values["line08_base"]),
            "line08_tax": str(values["line08_tax"]),
            "line20": str(values["line20"]),
            "line22": str(values["line22"]),
            "line23": str(values["line23"]),
            "line32": str(values["line32"]),
            "line27_to_report": str(line27_to_report),
            "filing_date": filing_date or row_data.get("filing_date", ""),
            "payment_date": payment_date or row_data.get("payment_date", ""),
            "currency": "EUR",
            "rounding": "arrondi_euro",
            "source_json": str(result_json),
            "pieces_index": str(proofs_csv),
            "payment_proof": payment_proof or row_data.get("payment_proof", ""),
            "notes": "Generated by vat_ca3.run (exception-stop enabled)",
        }
    )

    # Keep existing certificate_depot if present.
    if not row_data.get("certificate_depot") and existing_row.get("certificate_depot"):
        row_data["certificate_depot"] = existing_row["certificate_depot"]

    updated = False
    for idx, row in enumerate(rows):
        if str(row.get("period") or "").strip() == period:
            rows[idx] = row_data
            updated = True
            break
    if not updated:
        rows.append(row_data)

    rows.sort(key=lambda r: str(r.get("period") or ""))

    ledger_csv.parent.mkdir(parents=True, exist_ok=True)
    with ledger_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_decision_summary(paths: Paths, lines: List[str]) -> None:
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    paths.decision_summary_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_decision_plan(paths: Paths) -> List[str]:
    return [
        f"# Decision Summary - CA3 {paths.period}",
        "",
        "## Inputs detectes",
        f"- Banque (Qonto Full): `{paths.bank_csv}`",
        f"- Ventes validees: `{paths.sales_csv}`",
        f"- Matching 1:N: `{paths.sales_matches_csv}`",
        f"- Achats valides: `{paths.purchases_csv}`",
        f"- Index de preuves: `{paths.proofs_csv}`",
        f"- Ledger: `{paths.ledger_csv}`",
        "",
        "## Plan d'execution",
        "1. Valider la periode par date de valeur bancaire (TVA sur encaissements).",
        "2. Verifier le matching 1:N entre encaissements et factures.",
        "3. Calculer lignes CA3 exactes puis arrondies.",
        "4. Appliquer la ligne 22 via report ligne 27 precedent (ou override explicite).",
        "5. Produire livrables (mapping, checklist, exceptions, audit index).",
        "6. Mettre a jour data/ca3_ledger.csv.",
        "",
        "Regle: si un controle est en echec (ERROR), generation finale stoppee.",
    ]


def run_pipeline(
    period: str,
    root: str = ".",
    year_folder: str = "Bilan 2026",
    output_subdir: str = "ca3_workflow",
    line22_override: Optional[float] = None,
    confirm: bool = False,
    filing_date: str = "",
    payment_date: str = "",
    payment_proof: str = "",
) -> Dict[str, object]:
    root_path = Path(root).expanduser().resolve()
    paths = make_paths(root_path, period, year_folder, output_subdir)

    decision_lines = build_decision_plan(paths)
    print("\n".join(decision_lines))

    if not confirm:
        print("\nExecution not started. Re-run with --confirm to execute.")
        return {
            "success": False,
            "reason": "confirmation_required",
            "paths": paths,
        }

    exceptions: List[ExceptionItem] = []
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    write_decision_summary(paths, decision_lines)

    bank_index = load_bank_index(paths, exceptions)
    taxable_sales = load_taxable_sales(paths, exceptions)
    grouped_matches = load_sales_matches(paths, exceptions)
    line20_exact = load_line20_exact(paths, exceptions)
    line22_exact, line22_source = resolve_line22(paths, line22_override, exceptions)

    by_rate, total_base_exact, total_tax_exact = compute_collected_from_matches(
        taxable_sales=taxable_sales,
        grouped_matches=grouped_matches,
        bank_index=bank_index,
        exceptions=exceptions,
    )

    line08_base_exact = sum(v["base"] for rate, v in by_rate.items() if abs(rate - 20.0) <= 1e-6)
    line08_tax_exact = sum(v["tax"] for rate, v in by_rate.items() if abs(rate - 20.0) <= 1e-6)

    line16_exact = total_tax_exact
    line23_exact = line20_exact + line22_exact
    line32_exact = line16_exact - line23_exact

    rounded = {
        "a1": round_euro(line08_base_exact),
        "line08_base": round_euro(line08_base_exact),
        "line08_tax": round_euro(line08_tax_exact),
        "line16": round_euro(line16_exact),
        "line20": round_euro(line20_exact),
        "line22": round_euro(line22_exact),
    }
    rounded["line23"] = rounded["line20"] + rounded["line22"]
    rounded["line32"] = rounded["line16"] - rounded["line23"]
    line27_to_report = abs(rounded["line32"]) if rounded["line32"] < 0 else 0

    totals_exact = {
        "line08_base": line08_base_exact,
        "line08_tax": line08_tax_exact,
        "line16": line16_exact,
        "line20": line20_exact,
        "line22": line22_exact,
        "line23": line23_exact,
        "line32": line32_exact,
    }

    error_count = sum(1 for item in exceptions if item.severity == "ERROR")

    write_exceptions(paths.exceptions_csv, exceptions)

    if error_count > 0:
        stop_note = [
            "",
            "## Statut",
            f"STOP: {error_count} erreur(s) bloquante(s). Voir exceptions.csv.",
        ]
        write_decision_summary(paths, decision_lines + stop_note)
        return {
            "success": False,
            "reason": "exception_stop",
            "errors": [item.__dict__ for item in exceptions],
            "paths": paths,
        }

    write_mapping(
        path=paths.mapping_md,
        period=period,
        line22_source=line22_source,
        by_rate=by_rate,
        line20_exact=line20_exact,
        line22_exact=line22_exact,
        totals_exact=totals_exact,
        totals_rounded=rounded,
    )
    write_checklist(paths.checklist_md, period)
    render_audit_pack_index(paths.proofs_csv, paths.audit_pack_index_md)

    existing_ledger_row = load_existing_ledger_row(paths.ledger_csv, period)
    update_ledger(
        ledger_csv=paths.ledger_csv,
        period=period,
        values=rounded,
        line27_to_report=line27_to_report,
        result_json=paths.result_json,
        proofs_csv=paths.proofs_csv,
        existing_row=existing_ledger_row,
        filing_date=filing_date,
        payment_date=payment_date,
        payment_proof=payment_proof,
    )

    result_payload = {
        "period": period,
        "line22_source": line22_source,
        "exact": {
            "a1": round2(line08_base_exact),
            "line08_base": round2(line08_base_exact),
            "line08_tax": round2(line08_tax_exact),
            "line16": round2(line16_exact),
            "line20": round2(line20_exact),
            "line22": round2(line22_exact),
            "line23": round2(line23_exact),
            "line32": round2(line32_exact),
        },
        "rounded": rounded,
        "line27_to_report": line27_to_report,
        "sources": {
            "bank_csv": str(paths.bank_csv),
            "sales_csv": str(paths.sales_csv),
            "sales_matches_csv": str(paths.sales_matches_csv),
            "purchases_csv": str(paths.purchases_csv),
            "proofs_csv": str(paths.proofs_csv),
            "ledger_csv": str(paths.ledger_csv),
        },
    }
    paths.result_json.write_text(json.dumps(result_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return {
        "success": True,
        "paths": paths,
        "result": result_payload,
        "exceptions": [item.__dict__ for item in exceptions],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run monthly CA3 workflow with exception-stop checks.")
    parser.add_argument("--period", required=True, type=parse_period, help="Target period YYYY-MM")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--year-folder", default="Bilan 2026", help="Year folder containing TVA_Codex")
    parser.add_argument("--output-subdir", default="ca3_workflow", help="Output subdirectory under period output/")
    parser.add_argument("--line22-override", type=float, default=None, help="Explicit line 22 override")
    parser.add_argument("--filing-date", default="", help="Optional filing date YYYY-MM-DD for ledger")
    parser.add_argument("--payment-date", default="", help="Optional payment date YYYY-MM-DD for ledger")
    parser.add_argument("--payment-proof", default="", help="Optional payment proof file path for ledger")
    parser.add_argument("--confirm", action="store_true", help="Execute writes after decision plan")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_pipeline(
        period=args.period,
        root=args.root,
        year_folder=args.year_folder,
        output_subdir=args.output_subdir,
        line22_override=args.line22_override,
        confirm=args.confirm,
        filing_date=args.filing_date,
        payment_date=args.payment_date,
        payment_proof=args.payment_proof,
    )

    if result.get("reason") == "confirmation_required":
        return 0

    if not result.get("success"):
        print("Execution stopped. See exceptions.csv.")
        return 2

    paths = result["paths"]
    print("Execution completed.")
    print(f"- Mapping: {paths.mapping_md}")
    print(f"- Checklist: {paths.checklist_md}")
    print(f"- Exceptions: {paths.exceptions_csv}")
    print(f"- Audit index: {paths.audit_pack_index_md}")
    print(f"- Ledger: {paths.ledger_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
