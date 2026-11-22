"""Parse one X12 835 remittance advice transaction."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import PurePath
import re
from typing import Any


ALLOWED_EXTENSIONS = {".edi", ".txt", ".x12"}
KNOWN_SEGMENTS = {
    "ISA", "IEA", "GS", "GE", "ST", "SE", "BPR", "TRN", "CUR",
    "REF", "DTM", "N1", "N2", "N3", "N4", "PER", "RDM", "ENT",
    "NM1", "LX", "TS3", "TS2", "CLP", "CAS", "MIA", "MOA", "REF",
    "SVC", "LQ", "AMT", "QTY", "PLB", "SE", "GE", "IEA",
}
INTERPRETED_SEGMENTS = {
    "ST", "SE", "BPR", "TRN", "N1", "NM1", "CLP", "SVC", "CAS", "LQ",
}


class ERAParseError(ValueError):
    """Raised when an upload cannot be safely interpreted as an 835."""


@dataclass
class ERAData:
    """Payment-level information and related worksheet rows."""

    payment: dict[str, Any] = field(default_factory=dict)
    claims: list[dict[str, Any]] = field(default_factory=list)
    service_lines: list[dict[str, Any]] = field(default_factory=list)
    adjustments: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)


def _error(
    result: ERAData,
    message: str,
    severity: str = "Warning",
    segment: str = "",
) -> None:
    result.errors.append(
        {"severity": severity, "segment": segment, "message": message}
    )


def _money(
    value: str,
    result: ERAData,
    segment: str,
    field_name: str,
) -> Decimal | None:
    if not value:
        _error(result, f"Missing {field_name}; amount was not set.", "Error", segment)
        return None
    try:
        amount = Decimal(value)
    except InvalidOperation:
        amount = None
    if amount is None or not amount.is_finite() or not re.fullmatch(
        r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", value
    ):
        _error(
            result,
            f"Invalid {field_name} value {value!r}; amount was not set.",
            "Error",
            segment,
        )
        return None
    return amount


def _validate_envelope(
    segments: list[list[str]], result: ERAData
) -> list[list[str]]:
    if not segments or segments[0][0] != "ISA":
        raise ERAParseError("The interchange must start with an ISA segment.")
    if segments[-1][0] != "IEA":
        raise ERAParseError("The interchange is missing its closing IEA segment.")

    isa, iea = segments[0], segments[-1]
    if len(isa) < 17:
        raise ERAParseError("The ISA segment is missing required control fields.")
    if len(iea) < 3 or isa[13] != iea[2]:
        raise ERAParseError("ISA13 and IEA02 interchange control numbers do not match.")

    groups: list[list[list[str]]] = []
    current_group: list[list[str]] | None = None
    transactions: list[list[str]] = []
    current_transaction: list[str] | None = None

    for segment in segments[1:-1]:
        tag = segment[0]
        if tag == "GS":
            if current_group is not None or len(segment) < 7:
                raise ERAParseError("Malformed or nested GS functional group.")
            current_group = [segment]
            groups.append(current_group)
        elif tag == "GE":
            if current_group is None or len(segment) < 3:
                raise ERAParseError("GE segment has no matching GS segment.")
            if current_group[0][6] != segment[2]:
                raise ERAParseError("GS06 and GE02 functional control numbers do not match.")
            transaction_count = sum(1 for item in current_group if item[0] == "ST")
            if not segment[1].isdigit():
                _error(result, "GE01 transaction count is missing or invalid.", "Warning", "GE")
            elif int(segment[1]) != transaction_count:
                _error(result, "GE01 transaction count does not match the group.", "Warning", "GE")
            current_group = None
            continue
        elif tag == "ST":
            if current_group is None or current_transaction is not None or len(segment) < 3:
                raise ERAParseError("Malformed ST transaction start or missing GS.")
            current_transaction = []
            transactions.append(current_transaction)
        elif tag == "SE":
            if current_transaction is None or len(segment) < 3:
                raise ERAParseError("SE segment has no matching ST segment.")
            start = next(
                item for item in reversed(current_group or []) if item[0] == "ST"
            )
            if start[2] != segment[2]:
                raise ERAParseError("ST02 and SE02 transaction control numbers do not match.")
            if not segment[1].isdigit():
                _error(result, "SE01 segment count is missing or invalid.", "Warning", "SE")
            else:
                actual_count = len(current_transaction) + 1
                if int(segment[1]) != actual_count:
                    _error(result, "SE01 segment count does not match the transaction.", "Warning", "SE")
            current_group.append(segment)
            current_transaction.append(segment)
            current_transaction = None
            continue

        if current_group is not None:
            current_group.append(segment)
        if current_transaction is not None:
            current_transaction.append(segment)

    if current_group is not None:
        raise ERAParseError("Functional group is missing its GE segment.")
    if current_transaction is not None:
        raise ERAParseError("Transaction set is missing its SE segment.")
    if not iea[1].isdigit():
        _error(result, "IEA01 group count is missing or invalid.", "Warning", "IEA")
    elif int(iea[1]) != len(groups):
        _error(result, "IEA01 functional group count does not match the interchange.", "Warning", "IEA")

    if len(transactions) != 1:
        raise ERAParseError(
            f"Expected exactly one transaction set; found {len(transactions)}."
        )
    transaction = transactions[0]
    if len(transaction) < 2 or len(transaction[0]) < 2 or transaction[0][1] != "835":
        transaction_type = (
            transaction[0][1] if transaction and len(transaction[0]) > 1 else "unknown"
        )
        raise ERAParseError(
            f"Unsupported transaction set {transaction_type!r}; expected 835."
        )
    return [segments[0], *transaction, segments[-1]]


def parse_835(content: bytes | str, filename: str) -> ERAData:
    """Validate an uploaded file and extract its single 835 transaction.

    Monetary fields that cannot be parsed are represented as ``None`` and
    reported in ``errors``. The original upload is never written to disk.
    """
    extension = PurePath(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ERAParseError(
            "Unsupported file extension. Upload an .edi, .txt, or .x12 file."
        )
    try:
        text = content.decode("utf-8-sig") if isinstance(content, bytes) else content
    except UnicodeDecodeError as exc:
        raise ERAParseError("The file is not valid UTF-8 encoded text.") from exc
    if not isinstance(text, str) or not text:
        raise ERAParseError("The uploaded file is empty.")
    if len(text) < 106 or not text.startswith("ISA"):
        raise ERAParseError("The file does not start with a complete X12 ISA header.")

    element_separator = text[3]
    component_separator = text[104]
    segment_terminator = text[105]
    delimiters = {element_separator, component_separator, segment_terminator}
    isa_version = text[84:89]
    if isa_version >= "00402":
        repetition_separator = text[82]
        delimiters.add(repetition_separator)
    if (
        len(delimiters) != (4 if isa_version >= "00402" else 3)
        or any(char.isalnum() or char.isspace() for char in delimiters)
        or text[105] in text[0:105]
    ):
        raise ERAParseError("Could not detect valid X12 delimiters from the ISA header.")
    isa_fields = text[:105].split(element_separator)
    if len(isa_fields) != 17 or isa_fields[0] != "ISA":
        raise ERAParseError("The ISA header is malformed or has invalid delimiters.")

    raw_segments = text.split(segment_terminator)
    segments = [
        part.strip().split(element_separator)
        for part in raw_segments
        if part.strip()
    ]
    result = ERAData()
    scoped_segments = _validate_envelope(segments, result)

    active_claim: dict[str, Any] | None = None
    active_service: dict[str, Any] | None = None
    service_number = 0
    saw_bpr = False
    transaction_segments = scoped_segments[1:-1]

    for segment in transaction_segments:
        tag = segment[0]
        if tag not in INTERPRETED_SEGMENTS:
            description = (
                "recognized but not extracted"
                if tag in KNOWN_SEGMENTS
                else "unsupported"
            )
            _error(
                result,
                f"Segment {tag!r} is {description} by this version.",
                "Warning",
                tag,
            )

        if tag == "BPR":
            saw_bpr = True
            if len(segment) < 17:
                _error(result, "BPR is missing payment fields.", "Error", "BPR")
                continue
            result.payment.update(
                {
                    "payment_amount": _money(segment[2], result, "BPR", "payment amount"),
                    "payment_method": segment[4],
                    "payment_date": segment[16] or None,
                }
            )
            if segment[16]:
                try:
                    result.payment["payment_date"] = datetime.strptime(
                        segment[16], "%Y%m%d"
                    ).date()
                except ValueError:
                    _error(result, f"Invalid payment date {segment[16]!r}.", "Error", "BPR")
                    result.payment["payment_date"] = None
        elif tag == "TRN":
            if len(segment) > 2:
                result.payment["trace_number"] = segment[2]
            else:
                _error(result, "TRN is missing its trace number.", "Error", "TRN")
        elif tag == "N1" and len(segment) > 2:
            if segment[1] == "PR":
                result.payment["payer_name"] = segment[2]
            elif segment[1] == "PE":
                result.payment["payee_name"] = segment[2]
        elif tag == "NM1" and len(segment) > 3:
            if segment[1] == "PR":
                result.payment.setdefault("payer_name", segment[3])
            elif segment[1] == "PE":
                result.payment.setdefault("payee_name", segment[3])
        elif tag == "CLP":
            if len(segment) < 8:
                _error(result, "CLP is missing required claim fields.", "Error", "CLP")
            active_claim = {
                "patient_control_number": segment[1] if len(segment) > 1 else "",
                "claim_status": segment[2] if len(segment) > 2 else "",
                "total_billed_amount": _money(
                    segment[3] if len(segment) > 3 else "",
                    result,
                    "CLP",
                    "total billed amount",
                ),
                "claim_payment_amount": _money(
                    segment[4] if len(segment) > 4 else "",
                    result,
                    "CLP",
                    "claim payment amount",
                ),
                "patient_responsibility_amount": _money(
                    segment[5] if len(segment) > 5 else "",
                    result,
                    "CLP",
                    "patient responsibility amount",
                ),
                "payer_claim_control_number": segment[7] if len(segment) > 7 else "",
                "remark_codes": [],
            }
            result.claims.append(active_claim)
            active_service = None
            service_number = 0
        elif tag == "SVC":
            if active_claim is None:
                _error(result, "SVC appears before a CLP claim.", "Error", "SVC")
                active_service = None
                continue
            service_number += 1
            procedure_parts = (
                segment[1].split(component_separator) if len(segment) > 1 else []
            )
            procedure = (
                procedure_parts[1]
                if len(procedure_parts) > 1
                else (procedure_parts[0] if procedure_parts else "")
            )
            active_service = {
                "patient_control_number": active_claim["patient_control_number"],
                "payer_claim_control_number": active_claim["payer_claim_control_number"],
                "service_line_number": service_number,
                "procedure_service_code": procedure,
                "service_charge_amount": _money(
                    segment[2] if len(segment) > 2 else "",
                    result,
                    "SVC",
                    "service charge amount",
                ),
                "paid_amount": _money(
                    segment[3] if len(segment) > 3 else "",
                    result,
                    "SVC",
                    "service paid amount",
                ),
                "units": segment[5] if len(segment) > 5 and segment[5] else None,
                "remark_codes": [],
            }
            result.service_lines.append(active_service)
        elif tag == "CAS":
            if active_claim is None:
                _error(result, "CAS appears outside a claim.", "Error", "CAS")
                continue
            associated_type = "service_line" if active_service is not None else "claim"
            for index in range(2, len(segment), 3):
                reason = segment[index]
                amount_text = segment[index + 1] if index + 1 < len(segment) else ""
                amount = _money(amount_text, result, "CAS", "adjustment amount")
                result.adjustments.append(
                    {
                        "association_type": associated_type,
                        "patient_control_number": active_claim["patient_control_number"],
                        "payer_claim_control_number": active_claim["payer_claim_control_number"],
                        "service_line_number": (
                            active_service["service_line_number"]
                            if active_service is not None
                            else None
                        ),
                        "group_code": segment[1] if len(segment) > 1 else "",
                        "reason_code": reason,
                        "adjustment_amount": amount,
                    }
                )
        elif tag == "LQ":
            if len(segment) < 3:
                _error(result, "LQ is missing its remark code.", "Error", "LQ")
                continue
            if segment[1] != "HE":
                _error(
                    result,
                    f"LQ code-list qualifier {segment[1]!r} is not supported.",
                    "Warning",
                    "LQ",
                )
                continue
            remark = segment[2]
            if active_service is not None:
                active_service["remark_codes"].append(remark)
            elif active_claim is not None:
                active_claim["remark_codes"].append(remark)
            else:
                _error(result, "LQ appears outside a claim or service line.", "Warning", "LQ")

    if not saw_bpr:
        raise ERAParseError("The 835 transaction is missing its required BPR payment segment.")
    if not result.claims:
        raise ERAParseError("The 835 transaction does not contain any CLP claim segments.")
    for field_name, label in (
        ("trace_number", "trace number"),
        ("payer_name", "payer name"),
        ("payee_name", "payee name"),
    ):
        if not result.payment.get(field_name):
            _error(result, f"Payment {label} was not provided.", "Warning")
    if "payment_date" not in result.payment:
        _error(result, "Payment date was not provided.", "Warning", "BPR")
    for claim in result.claims:
        claim["remark_codes"] = ", ".join(claim["remark_codes"])
    for service in result.service_lines:
        service["remark_codes"] = ", ".join(service["remark_codes"])
    return result
