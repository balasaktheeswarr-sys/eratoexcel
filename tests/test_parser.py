from decimal import Decimal

import pytest

from conftest import build_edi
from parser import ERAParseError, parse_835


def test_parses_payment_and_multiple_claims_and_services(valid_835):
    result = parse_835(valid_835, "synthetic.edi")

    assert result.payment["payment_amount"] == Decimal("100.00")
    assert result.payment["payment_method"] == "CHK"
    assert result.payment["trace_number"] == "TRACE123"
    assert str(result.payment["payment_date"]) == "2026-01-01"
    assert result.payment["payer_name"] == "Example Payer"
    assert result.payment["payee_name"] == "Example Clinic"
    assert result.errors == []
    assert len(result.claims) == 2
    assert len(result.service_lines) == 3
    assert result.claims[0]["patient_control_number"] == "CTRL001"
    assert result.claims[0]["claim_payment_amount"] == Decimal("100.00")
    assert result.service_lines[0]["procedure_service_code"] == "99213"
    assert result.service_lines[0]["units"] == "2"


def test_rejects_unsupported_file_extension(valid_835):
    with pytest.raises(ERAParseError, match="Unsupported file extension"):
        parse_835(valid_835, "synthetic.csv")


def test_rejects_non_835_transaction():
    content = build_edi(["BPR*I*100.00*C*CHK************20260101"], "837")
    with pytest.raises(ERAParseError, match="expected 835"):
        parse_835(content, "synthetic.edi")


def test_rejects_missing_or_malformed_envelope(valid_835):
    with pytest.raises(ERAParseError, match="ISA"):
        parse_835(b"not an X12 file", "synthetic.edi")
    with pytest.raises(ERAParseError, match="closing IEA"):
        parse_835(valid_835.rsplit(b"IEA", 1)[0], "synthetic.edi")


def test_records_multiple_adjustments_and_associates_them(valid_835):
    result = parse_835(valid_835, "synthetic.edi")

    assert len(result.adjustments) == 3
    assert result.adjustments[0]["association_type"] == "claim"
    assert result.adjustments[0]["reason_code"] == "45"
    assert result.adjustments[1]["reason_code"] == "97"
    assert result.adjustments[1]["adjustment_amount"] == Decimal("10.00")
    assert result.adjustments[2]["association_type"] == "service_line"
    assert result.adjustments[2]["service_line_number"] == 1
    assert result.adjustments[2]["adjustment_amount"] == Decimal("25.00")


def test_associates_remarks_with_current_service_or_claim(valid_835):
    result = parse_835(valid_835, "synthetic.edi")

    assert result.service_lines[0]["remark_codes"] == "N123"
    assert result.service_lines[1]["remark_codes"] == "N456"
    assert result.claims[0]["remark_codes"] == ""


def test_invalid_money_is_reported_not_replaced_with_zero():
    content = build_edi(
        [
            "BPR*I*bad-money*C*CHK************20260101",
            "CLP*CTRL001*1*not-a-number*25.00*0*12*PCLM001",
        ]
    )
    result = parse_835(content, "synthetic.x12")

    assert result.payment["payment_amount"] is None
    assert result.claims[0]["total_billed_amount"] is None
    assert sum(error["severity"] == "Error" for error in result.errors) == 2


def test_reports_malformed_transaction_segment_count():
    content = build_edi(
        ["BPR*I*100.00*C*CHK************20260101", "CLP*CTRL001*1*20.00*10.00*0*12*PCLM001"]
    ).replace(b"SE*4*0001", b"SE*99*0001")
    result = parse_835(content, "synthetic.edi")

    assert any("SE01" in error["message"] for error in result.errors)


def test_rejects_transaction_missing_se(valid_835):
    content = valid_835.replace(b"~SE*15*0001", b"")
    with pytest.raises(ERAParseError, match="missing its SE"):
        parse_835(content, "synthetic.edi")


def test_claim_level_remark_stays_on_claim():
    content = build_edi(
        [
            "BPR*I*10.00*C*CHK************20260101",
            "TRN*1*TRACE001",
            "CLP*CTRL001*1*10.00*10.00*0*12*PCLM001",
            "LQ*HE*N765",
            "SVC*HC:99213*10.00*10.00**1",
        ]
    )
    result = parse_835(content, "synthetic.txt")

    assert result.claims[0]["remark_codes"] == "N765"
    assert result.service_lines[0]["remark_codes"] == ""
