"""Synthetic X12 835 fixtures used by the test suite."""

import pytest


def build_edi(body: list[str], transaction_type: str = "835") -> bytes:
    element = "*"
    terminator = "~"
    isa_fields = [
        "00",
        "          ",
        "00",
        "          ",
        "ZZ",
        "SENDER         ",
        "ZZ",
        "RECEIVER       ",
        "260101",
        "1200",
        "^",
        "00501",
        "000000001",
        "0",
        "T",
        ":",
    ]
    isa = "ISA" + element + element.join(isa_fields) + terminator
    assert len(isa) == 106

    transaction = [f"ST{element}{transaction_type}{element}0001", *body]
    transaction.append(f"SE{element}{len(transaction) + 1}{element}0001")
    group = [
        "GS*HP*SENDER*RECEIVER*20260101*1200*1*X*005010X221A1",
        *transaction,
        "GE*1*1",
    ]
    return (isa + terminator.join(group) + terminator + "IEA*1*000000001" + terminator).encode()


@pytest.fixture
def valid_835() -> bytes:
    return build_edi(
        [
            "BPR*I*100.00*C*CHK************20260101",
            "TRN*1*TRACE123*PAYER01",
            "N1*PR*Example Payer",
            "N1*PE*Example Clinic",
            "CLP*CTRL001*1*150.00*100.00*10.00*12*PCLM001",
            "CAS*CO*45*40.00*1*97*10.00*1",
            "SVC*HC:99213*100.00*75.00**2",
            "CAS*PR*1*25.00",
            "LQ*HE*N123",
            "SVC*HC:93000*50.00*25.00**1",
            "LQ*HE*N456",
            "CLP*CTRL002*2*50.00*25.00*0*12*PCLM002",
            "SVC*HC:71020*50.00*25.00**1",
        ]
    )
