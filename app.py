"""Streamlit interface for converting an X12 835 file to Excel."""

from pathlib import Path

import pandas as pd
import streamlit as st

from excel_writer import create_workbook
from parser import ERAParseError, parse_835


def _mask_identifier(value: object) -> str:
    """Keep only the last four characters of an identifier in the preview."""
    identifier = str(value or "")
    if not identifier:
        return ""
    if len(identifier) <= 4:
        return "****"
    return f"{'*' * (len(identifier) - 4)}{identifier[-4:]}"


st.set_page_config(page_title="ERA to Excel", page_icon="📄", layout="wide")
st.title("ERA to Excel")
st.write(
    "Convert an X12 835 Electronic Remittance Advice file into an organized "
    "Excel workbook."
)
st.caption(
    "Files are processed in memory. Patient identifiers are masked in previews. "
    "Use synthetic data while learning; this tool does not claim HIPAA compliance."
)

uploaded_file = st.file_uploader(
    "Choose an ERA file",
    type=["edi", "txt", "x12"],
    help="Supported formats: .edi, .txt, and .x12",
)

if uploaded_file is not None:
    try:
        era_data = parse_835(uploaded_file.getvalue(), uploaded_file.name)
    except ERAParseError as exc:
        st.error(f"File validation failed: {exc}")
    else:
        st.success("File validated and parsed as an X12 835 transaction.")
        payment = era_data.payment
        metric_columns = st.columns(4)
        amount = payment.get("payment_amount")
        metric_columns[0].metric(
            "Payment amount", f"${amount:,.2f}" if amount is not None else "Unavailable"
        )
        metric_columns[1].metric("Claims", len(era_data.claims))
        metric_columns[2].metric("Service lines", len(era_data.service_lines))
        metric_columns[3].metric("Validation messages", len(era_data.errors))

        st.subheader("Payment preview")
        payment_preview = {
            "Payer": payment.get("payer_name", ""),
            "Payee": payment.get("payee_name", ""),
            "Payment amount": amount,
            "Payment date": payment.get("payment_date", ""),
            "Payment method": payment.get("payment_method", ""),
            "Trace number": payment.get("trace_number", ""),
        }
        st.dataframe(pd.DataFrame([payment_preview]), hide_index=True, use_container_width=True)

        st.subheader("Claim preview")
        claim_preview = []
        for claim in era_data.claims:
            claim_preview.append(
                {
                    "Patient control number": _mask_identifier(
                        claim.get("patient_control_number")
                    ),
                    "Payer claim control number": _mask_identifier(
                        claim.get("payer_claim_control_number")
                    ),
                    "Claim status": claim.get("claim_status"),
                    "Billed amount": claim.get("total_billed_amount"),
                    "Paid amount": claim.get("claim_payment_amount"),
                    "Patient responsibility": claim.get("patient_responsibility_amount"),
                }
            )
        st.dataframe(
            pd.DataFrame(claim_preview),
            hide_index=True,
            use_container_width=True,
        )

        if era_data.errors:
            with st.expander("Validation warnings and errors"):
                st.dataframe(
                    pd.DataFrame(era_data.errors),
                    hide_index=True,
                    use_container_width=True,
                )

        workbook = create_workbook(era_data)
        output_name = f"{Path(uploaded_file.name).stem or 'remittance'}_converted.xlsx"
        st.download_button(
            "Download Excel workbook",
            data=workbook,
            file_name=output_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
