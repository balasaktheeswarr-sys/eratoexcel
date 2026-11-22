# ERA to Excel

A learning project that reads one X12 835 Electronic Remittance Advice (ERA)
transaction and creates a formatted Excel workbook with payment, claim, service
line, adjustment, and validation information.

Uploads are parsed in memory and are not written to disk. The sample file and
automated tests use synthetic names and identifiers only. Claim identifiers are
masked in the Streamlit preview.

```markdown
## Tools and Tech Stack

- **Python** — core application and parsing logic.
- **Streamlit** — web interface for uploading ERA files, previewing results, and downloading the workbook.
- **Pandas** — organizes parsed data into tables.
- **OpenPyXL** — formats and generates the Excel workbook.
- **Pytest** — tests the parser and workbook generation.
- **X12 835** — the remittance advice format processed by the application.

## Backend Logic

The application validates uploaded X12 835 files, detects their delimiters, and checks transaction envelope information. It extracts payment, claim, service-line, adjustment, and remark data, while reporting validation issues. The Streamlit interface displays data previews and masks claim identifiers. Pandas and OpenPyXL then create a formatted Excel workbook in memory, ready to download.
```

## Project layout

```text
era-to-excel/
├── app.py
├── parser.py
├── excel_writer.py
├── requirements.txt
├── README.md
├── samples/
│   └── sample_835.edi
└── tests/
    ├── conftest.py
    ├── test_parser.py
    └── test_excel_writer.py
```

## Setup on Windows

Open PowerShell in this project folder and create a virtual environment:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell prevents script activation, use Command Prompt:

```cmd
.venv\Scripts\activate.bat
```

## Run the application

From the project folder, with the virtual environment active:

```powershell
streamlit run app.py
```

Open the local address printed by Streamlit, then upload
`samples\sample_835.edi`. The application shows validation results and a masked
preview; use **Download Excel workbook** to create the five-sheet `.xlsx` file.

## Run the tests

```powershell
python -m pytest -q
```

The test fixtures are synthetic and cover file validation, transaction
structure, payment/claim/service extraction, adjustment and remark association,
invalid monetary values, and workbook sheets and formatting.

## How the code is organized

- `parser.py` checks the ISA header and envelope, detects the element,
  component, and segment delimiters, and groups extracted values by claim and
  service line. Monetary values use `Decimal`. A bad amount becomes `None` and
  is recorded in the Errors sheet rather than being changed to zero.
- `excel_writer.py` turns the parsed records into five Pandas tables and uses
  openpyxl to format headers, widths, filters, frozen panes, and currency cells.
- `app.py` provides the Streamlit uploader, validation status, metrics,
  identifier-masked claim preview, and in-memory workbook download.

## Current scope

The first version accepts one transaction set per uploaded file and requires
the basic ISA/IEA, GS/GE, and ST/SE envelope. It extracts the payment, claim,
service line, CAS adjustment, and LQ remark details listed in the project
requirements. Other segments are reported as not extracted in the Errors
sheet, so review those messages when interpreting a workbook. This is a
learning converter, not a complete X12 implementation.
