from io import BytesIO

from openpyxl import load_workbook

from excel_writer import create_workbook
from parser import parse_835
from conftest import build_edi


def test_creates_formatted_five_sheet_workbook(valid_835):
    result = parse_835(valid_835, "synthetic.edi")
    workbook_bytes = create_workbook(result)
    workbook = load_workbook(BytesIO(workbook_bytes), data_only=True)

    assert workbook.sheetnames == [
        "Payment Summary",
        "Claim Payments",
        "Service Lines",
        "Adjustments",
        "Errors",
    ]
    payment_sheet = workbook["Payment Summary"]
    assert payment_sheet["A2"].value == "Example Payer"
    assert payment_sheet["C2"].value == 100
    assert payment_sheet.freeze_panes == "A2"
    assert payment_sheet.auto_filter.ref is not None
    assert payment_sheet["A1"].font.bold
    assert payment_sheet["C2"].number_format.startswith("$")

    claims_sheet = workbook["Claim Payments"]
    assert claims_sheet.max_row == 3
    assert claims_sheet["A2"].value == "CTRL001"
    service_sheet = workbook["Service Lines"]
    assert service_sheet.max_row == 4
    adjustments_sheet = workbook["Adjustments"]
    assert adjustments_sheet.max_row == 4


def test_places_invalid_amount_validation_in_errors_sheet():
    content = build_edi(
        [
            "BPR*I*invalid*C*CHK************20260101",
            "TRN*1*TRACE001",
            "N1*PR*Example Payer",
            "N1*PE*Example Clinic",
            "CLP*CTRL001*1*10.00*10.00*0*12*PCLM001",
        ]
    )
    workbook = load_workbook(
        BytesIO(create_workbook(parse_835(content, "synthetic.edi"))),
        data_only=True,
    )

    errors_sheet = workbook["Errors"]
    assert errors_sheet.max_row == 2
    assert errors_sheet["A2"].value == "Error"
    assert errors_sheet["B2"].value == "BPR"
    assert "Invalid payment amount" in errors_sheet["C2"].value
