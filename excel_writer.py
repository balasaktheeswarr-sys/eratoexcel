"""Create a formatted Excel workbook from parsed 835 data."""

from __future__ import annotations

from io import BytesIO
from typing import Any

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill

from parser import ERAData


SHEET_COLUMNS: dict[str, list[str]] = {
    "Payment Summary": [
        "payer_name",
        "payee_name",
        "payment_amount",
        "payment_date",
        "payment_method",
        "trace_number",
    ],
    "Claim Payments": [
        "patient_control_number",
        "payer_claim_control_number",
        "claim_status",
        "total_billed_amount",
        "claim_payment_amount",
        "patient_responsibility_amount",
        "remark_codes",
    ],
    "Service Lines": [
        "patient_control_number",
        "payer_claim_control_number",
        "service_line_number",
        "procedure_service_code",
        "service_charge_amount",
        "paid_amount",
        "units",
        "remark_codes",
    ],
    "Adjustments": [
        "association_type",
        "patient_control_number",
        "payer_claim_control_number",
        "service_line_number",
        "group_code",
        "reason_code",
        "adjustment_amount",
    ],
    "Errors": ["severity", "segment", "message"],
}

CURRENCY_COLUMNS = {
    "payment_amount",
    "total_billed_amount",
    "claim_payment_amount",
    "patient_responsibility_amount",
    "service_charge_amount",
    "paid_amount",
    "adjustment_amount",
}


def _records_frame(
    columns: list[str], records: list[dict[str, Any]]
) -> pd.DataFrame:
    """Keep sheet columns stable, including when a result has no rows."""
    return pd.DataFrame.from_records(records, columns=columns)


def create_workbook(data: ERAData) -> bytes:
    """Return the formatted five-sheet workbook as in-memory XLSX bytes."""
    payment_rows = [data.payment] if data.payment else []
    sheet_records = {
        "Payment Summary": payment_rows,
        "Claim Payments": data.claims,
        "Service Lines": data.service_lines,
        "Adjustments": data.adjustments,
        "Errors": data.errors,
    }

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, columns in SHEET_COLUMNS.items():
            frame = _records_frame(columns, sheet_records[sheet_name])
            frame.to_excel(writer, sheet_name=sheet_name, index=False)
            worksheet = writer.sheets[sheet_name]
            worksheet.freeze_panes = "A2"
            worksheet.auto_filter.ref = worksheet.dimensions

            for cell in worksheet[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="244062")
                cell.alignment = Alignment(vertical="center", wrap_text=True)
            worksheet.row_dimensions[1].height = 30

            for column_index, column_name in enumerate(columns, start=1):
                values = [
                    str(worksheet.cell(row=row, column=column_index).value or "")
                    for row in range(1, worksheet.max_row + 1)
                ]
                width = min(max(max(map(len, values), default=0) + 2, 12), 42)
                worksheet.column_dimensions[
                    worksheet.cell(row=1, column=column_index).column_letter
                ].width = width
                if column_name in CURRENCY_COLUMNS:
                    for row in range(2, worksheet.max_row + 1):
                        worksheet.cell(row=row, column=column_index).number_format = (
                            '$#,##0.00;[Red]($#,##0.00)'
                        )

    return output.getvalue()
