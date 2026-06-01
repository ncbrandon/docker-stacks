import os
import re
import math
from io import BytesIO
from datetime import date, datetime

import pandas as pd
import pymssql
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from dotenv import load_dotenv

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


# ------------------------------------------------------------
# Basic setup
# ------------------------------------------------------------

load_dotenv()

st.set_page_config(
    page_title=os.getenv("APP_TITLE", "Rainfall & Wastewater Flow Dashboard"),
    page_icon="🌧️",
    layout="wide",
)

APP_TITLE = os.getenv("APP_TITLE", "Rainfall & Wastewater Flow Dashboard")

SQL_HOST = os.getenv("SQL_HOST", "wwtp-sql")
SQL_PORT = int(os.getenv("SQL_PORT", "1433"))
SQL_DATABASE = os.getenv("SQL_DATABASE", "WWTP")
SQL_USER = os.getenv("SQL_USER", "sa")
SQL_PASSWORD = os.getenv("SQL_PASSWORD", "")

RAIN_FLOW_TABLE = "RainFlowDaily"


# ------------------------------------------------------------
# Styling
# ------------------------------------------------------------

st.markdown(
    """
    <style>
    .main {
        background: linear-gradient(180deg, #f5fbff 0%, #eef7f4 100%);
    }

    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }

    .hero-card {
        background: linear-gradient(135deg, #0f4c81 0%, #2f8f83 100%);
        padding: 1.25rem 1.5rem;
        border-radius: 22px;
        color: white;
        box-shadow: 0 12px 30px rgba(0,0,0,0.18);
        margin-bottom: 1rem;
    }

    .hero-card h1 {
        margin: 0;
        font-size: 2rem;
        line-height: 1.15;
    }

    .hero-card p {
        margin-top: 0.5rem;
        font-size: 1rem;
        opacity: 0.95;
    }

    .metric-card {
        background: white;
        border-radius: 18px;
        padding: 1rem;
        box-shadow: 0 6px 18px rgba(15, 76, 129, 0.10);
        border: 1px solid rgba(15, 76, 129, 0.08);
    }

    .small-note {
        color: #53656f;
        font-size: 0.9rem;
    }

    div[data-testid="stMetricValue"] {
        font-size: 1.7rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ------------------------------------------------------------
# SQL helpers
# ------------------------------------------------------------

def get_connection():
    if not SQL_PASSWORD:
        raise RuntimeError("SQL_PASSWORD is missing. Add it to .env or Portainer environment variables.")

    return pymssql.connect(
        server=SQL_HOST,
        port=SQL_PORT,
        user=SQL_USER,
        password=SQL_PASSWORD,
        database=SQL_DATABASE,
        login_timeout=10,
        timeout=60,
        as_dict=True,
    )


def execute_sql(sql, params=None):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
        conn.commit()


def query_df(sql, params=None):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            rows = cur.fetchall()
    return pd.DataFrame(rows)


def init_database():
    sql = f"""
    IF OBJECT_ID('dbo.{RAIN_FLOW_TABLE}', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.{RAIN_FLOW_TABLE} (
            Id UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID() PRIMARY KEY,
            EntryDate DATE NOT NULL UNIQUE,
            RainfallInches DECIMAL(10,3) NULL,
            WastewaterFlowMgd DECIMAL(10,3) NULL,
            Notes NVARCHAR(500) NULL,
            SourceFileName NVARCHAR(255) NULL,
            ImportedAt DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
            UpdatedAt DATETIME2 NULL
        );
    END;
    """
    execute_sql(sql)


def upsert_rain_flow_rows(df: pd.DataFrame, source_file_name: str = None):
    if df.empty:
        return {"inserted_or_updated": 0, "skipped": 0}

    cleaned = df.copy()

    required_cols = ["EntryDate", "RainfallInches", "WastewaterFlowMgd"]
    for col in required_cols:
        if col not in cleaned.columns:
            cleaned[col] = None

    if "Notes" not in cleaned.columns:
        cleaned["Notes"] = None

    cleaned["EntryDate"] = pd.to_datetime(cleaned["EntryDate"], errors="coerce").dt.date
    cleaned["RainfallInches"] = pd.to_numeric(cleaned["RainfallInches"], errors="coerce")
    cleaned["WastewaterFlowMgd"] = pd.to_numeric(cleaned["WastewaterFlowMgd"], errors="coerce")

    cleaned = cleaned.dropna(subset=["EntryDate"])
    cleaned = cleaned.drop_duplicates(subset=["EntryDate"], keep="last")

    rows = []
    skipped = 0

    for _, r in cleaned.iterrows():
        entry_date = r["EntryDate"]

        rainfall = r["RainfallInches"]
        flow = r["WastewaterFlowMgd"]
        notes = r.get("Notes", None)

        rainfall_value = None if pd.isna(rainfall) else float(rainfall)
        flow_value = None if pd.isna(flow) else float(flow)

        if rainfall_value is None and flow_value is None:
            skipped += 1
            continue

        rows.append(
            (
                entry_date,
                rainfall_value,
                flow_value,
                None if pd.isna(notes) else str(notes)[:500],
                source_file_name,
            )
        )

    if not rows:
        return {"inserted_or_updated": 0, "skipped": skipped}

    sql = f"""
    MERGE dbo.{RAIN_FLOW_TABLE} AS target
    USING (
        SELECT
            CAST(%s AS DATE) AS EntryDate,
            CAST(%s AS DECIMAL(10,3)) AS RainfallInches,
            CAST(%s AS DECIMAL(10,3)) AS WastewaterFlowMgd,
            CAST(%s AS NVARCHAR(500)) AS Notes,
            CAST(%s AS NVARCHAR(255)) AS SourceFileName
    ) AS source
    ON target.EntryDate = source.EntryDate
    WHEN MATCHED THEN
        UPDATE SET
            RainfallInches = COALESCE(source.RainfallInches, target.RainfallInches),
            WastewaterFlowMgd = COALESCE(source.WastewaterFlowMgd, target.WastewaterFlowMgd),
            Notes = COALESCE(source.Notes, target.Notes),
            SourceFileName = COALESCE(source.SourceFileName, target.SourceFileName),
            UpdatedAt = SYSUTCDATETIME()
    WHEN NOT MATCHED THEN
        INSERT (
            EntryDate,
            RainfallInches,
            WastewaterFlowMgd,
            Notes,
            SourceFileName
        )
        VALUES (
            source.EntryDate,
            source.RainfallInches,
            source.WastewaterFlowMgd,
            source.Notes,
            source.SourceFileName
        );
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            for row in rows:
                cur.execute(sql, row)
        conn.commit()

    return {"inserted_or_updated": len(rows), "skipped": skipped}


def load_rain_flow_data(start_date=None, end_date=None):
    where = []
    params = []

    if start_date:
        where.append("EntryDate >= %s")
        params.append(start_date)

    if end_date:
        where.append("EntryDate <= %s")
        params.append(end_date)

    where_sql = ""
    if where:
        where_sql = "WHERE " + " AND ".join(where)

    sql = f"""
    SELECT
        EntryDate,
        CAST(RainfallInches AS FLOAT) AS RainfallInches,
        CAST(WastewaterFlowMgd AS FLOAT) AS WastewaterFlowMgd,
        Notes,
        SourceFileName,
        ImportedAt,
        UpdatedAt
    FROM dbo.{RAIN_FLOW_TABLE}
    {where_sql}
    ORDER BY EntryDate;
    """

    df = query_df(sql, tuple(params))
    if not df.empty:
        df["EntryDate"] = pd.to_datetime(df["EntryDate"])
        df["Month"] = df["EntryDate"].dt.to_period("M").dt.to_timestamp()
        df["Year"] = df["EntryDate"].dt.year
        df["MonthNumber"] = df["EntryDate"].dt.month
        df["MonthName"] = df["EntryDate"].dt.strftime("%b")
    return df


# ------------------------------------------------------------
# Workbook parsing
# ------------------------------------------------------------

MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

STRUCTURED_DATE_NAMES = [
    "date",
    "entrydate",
    "entry_date",
    "day",
]

STRUCTURED_RAIN_NAMES = [
    "rainfall",
    "rainfallinches",
    "rainfall_inches",
    "rain",
    "rain_inches",
    "raininches",
    "precip",
    "precipitation",
]

STRUCTURED_FLOW_NAMES = [
    "wastewaterflow",
    "wastewaterflowmgd",
    "wastewater_flow_mgd",
    "flow",
    "flowmgd",
    "mgd",
    "wwflow",
    "ww_flow",
    "plantflow",
    "plant_flow",
]

STRUCTURED_NOTES_NAMES = [
    "notes",
    "note",
    "comments",
    "comment",
]


def clean_col_name(value):
    value = str(value).strip().lower()
    value = re.sub(r"[^a-z0-9]+", "", value)
    return value


def to_float_or_none(value):
    if value is None:
        return None

    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned == "":
            return None
        cleaned = cleaned.replace(",", "")
        cleaned = cleaned.replace("<", "")
        cleaned = cleaned.replace(">", "")
        try:
            return float(cleaned)
        except Exception:
            return None

    try:
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def parse_structured_upload(uploaded_file):
    name = uploaded_file.name.lower()

    if name.endswith(".csv"):
        raw = pd.read_csv(uploaded_file)
    else:
        raw = pd.read_excel(uploaded_file)

    if raw.empty:
        return pd.DataFrame()

    col_map = {}
    for col in raw.columns:
        cleaned = clean_col_name(col)

        if cleaned in [clean_col_name(x) for x in STRUCTURED_DATE_NAMES]:
            col_map[col] = "EntryDate"
        elif cleaned in [clean_col_name(x) for x in STRUCTURED_RAIN_NAMES]:
            col_map[col] = "RainfallInches"
        elif cleaned in [clean_col_name(x) for x in STRUCTURED_FLOW_NAMES]:
            col_map[col] = "WastewaterFlowMgd"
        elif cleaned in [clean_col_name(x) for x in STRUCTURED_NOTES_NAMES]:
            col_map[col] = "Notes"

    parsed = raw.rename(columns=col_map)

    needed = ["EntryDate", "RainfallInches", "WastewaterFlowMgd"]
    found_needed = [c for c in needed if c in parsed.columns]

    if "EntryDate" not in found_needed:
        raise ValueError(
            "Could not find a Date column. Use a structured file with columns like Date, RainfallInches, and WastewaterFlowMgd."
        )

    if "RainfallInches" not in parsed.columns:
        parsed["RainfallInches"] = None

    if "WastewaterFlowMgd" not in parsed.columns:
        parsed["WastewaterFlowMgd"] = None

    if "Notes" not in parsed.columns:
        parsed["Notes"] = None

    parsed = parsed[["EntryDate", "RainfallInches", "WastewaterFlowMgd", "Notes"]]
    parsed["EntryDate"] = pd.to_datetime(parsed["EntryDate"], errors="coerce")
    parsed = parsed.dropna(subset=["EntryDate"])

    return parsed


def find_year_from_sheet_name(sheet_name):
    match = re.search(r"(20\d{2}|19\d{2})", str(sheet_name))
    if match:
        return int(match.group(1))
    return None


def is_rain_sheet(sheet_name):
    return "rain" in str(sheet_name).lower()


def detect_day_column(raw: pd.DataFrame, start_row: int):
    best_col = None
    best_hits = 0

    cols_to_check = min(8, raw.shape[1])

    for c in range(cols_to_check):
        hits = 0

        for r in range(start_row, min(start_row + 40, raw.shape[0])):
            value = raw.iat[r, c]
            num = to_float_or_none(value)

            if num is not None and float(num).is_integer() and 1 <= int(num) <= 31:
                hits += 1

        if hits > best_hits:
            best_hits = hits
            best_col = c

    if best_hits >= 10:
        return best_col

    return None


def detect_month_header_row(raw: pd.DataFrame):
    """
    Finds the header row for both types of sheets:

    1. Rain sheets:
       Day | January | February | March | ...

    2. Flow sheets:
       Day | 43846 | 43877 | 43906 | ...
       These are Excel date serial numbers formatted as months in Excel.
    """

    rows_to_check = min(20, len(raw))

    # First, try normal month names.
    best_row_idx = None
    best_hits = 0

    for i in range(rows_to_check):
        row = raw.iloc[i].tolist()
        hits = 0

        for cell in row:
            if pd.isna(cell):
                continue

            text = str(cell).strip().lower()
            text = re.sub(r"[^a-z]", "", text)

            if text in MONTHS:
                hits += 1

        if hits > best_hits:
            best_hits = hits
            best_row_idx = i

    if best_hits >= 3:
        return best_row_idx

    # Second, try Excel date serial headers.
    # Your flow sheets have month headers stored as numbers like 43846, 43877, etc.
    for i in range(rows_to_check):
        date_serial_hits = 0

        for c in range(1, raw.shape[1]):
            cell = raw.iat[i, c]

            if pd.isna(cell):
                continue

            if isinstance(cell, (pd.Timestamp, datetime, date)):
                date_serial_hits += 1
                continue

            num = to_float_or_none(cell)

            if num is not None and num > 1000:
                date_serial_hits += 1

        if date_serial_hits >= 10:
            return i

    return None


def infer_month_columns(raw: pd.DataFrame, header_row: int):
    """
    Returns a dictionary:
        column_index -> month_number

    Handles either:
        January, February, March...
    or:
        Excel date serial numbers across the top of the flow sheets.
    """

    month_columns = {}

    # Normal month-name headers.
    for c in range(raw.shape[1]):
        cell = raw.iat[header_row, c]

        if pd.isna(cell):
            continue

        text = str(cell).strip().lower()
        text = re.sub(r"[^a-z]", "", text)

        if text in MONTHS:
            month_columns[c] = MONTHS[text]

    if len(month_columns) >= 3:
        return month_columns

    # Excel date serial / date headers.
    date_like_cols = []

    for c in range(1, raw.shape[1]):
        cell = raw.iat[header_row, c]

        if pd.isna(cell):
            continue

        if isinstance(cell, (pd.Timestamp, datetime, date)):
            month_num = int(cell.month)
            date_like_cols.append((c, month_num))
            continue

        num = to_float_or_none(cell)

        if num is not None and num > 1000:
            date_like_cols.append((c, None))

    if len(date_like_cols) >= 10:
        # For your yearly flow sheets, the 12 columns are Jan-Dec in order.
        # Some headers are just Excel serials, so assigning by position is safer.
        for idx, item in enumerate(sorted(date_like_cols, key=lambda x: x[0])[:12]):
            col_idx, detected_month = item

            if detected_month is not None and 1 <= detected_month <= 12:
                month_columns[col_idx] = detected_month
            else:
                month_columns[col_idx] = idx + 1

    return month_columns


def parse_wide_year_sheet(raw: pd.DataFrame, year: int, value_type: str):
    """
    Converts wide sheets like:

        Day | Jan | Feb | Mar | ...
         1  | ... | ... | ...
         2  | ... | ... | ...

    Also handles your wastewater-flow sheets where the headers are stored as
    Excel date serial numbers instead of month names.

    value_type should be either "rain" or "flow".
    """

    if raw.empty or year is None:
        return pd.DataFrame()

    header_row = detect_month_header_row(raw)

    if header_row is None:
        return pd.DataFrame()

    month_columns = infer_month_columns(raw, header_row)

    if not month_columns:
        return pd.DataFrame()

    day_col = detect_day_column(raw, header_row + 1)

    if day_col is None:
        return pd.DataFrame()

    rows = []

    for r in range(header_row + 1, raw.shape[0]):
        day_value = raw.iat[r, day_col]
        day_num = to_float_or_none(day_value)

        if day_num is None:
            continue

        if not float(day_num).is_integer():
            continue

        day_num = int(day_num)

        if not 1 <= day_num <= 31:
            continue

        for col_idx, month_num in month_columns.items():
            value = to_float_or_none(raw.iat[r, col_idx])

            try:
                entry_date = date(year, month_num, day_num)
            except ValueError:
                continue

            if value_type == "rain":
                rows.append(
                    {
                        "EntryDate": entry_date,
                        "RainfallInches": 0.0 if value is None else value,
                        "WastewaterFlowMgd": None,
                        "Notes": None,
                    }
                )
            else:
                rows.append(
                    {
                        "EntryDate": entry_date,
                        "RainfallInches": None,
                        "WastewaterFlowMgd": value,
                        "Notes": None,
                    }
                )

    return pd.DataFrame(rows)


def parse_historical_workbook(uploaded_file):
    xls = pd.ExcelFile(uploaded_file)
    parsed_frames = []

    for sheet_name in xls.sheet_names:
        year = find_year_from_sheet_name(sheet_name)
        if year is None:
            continue

        try:
            raw = pd.read_excel(xls, sheet_name=sheet_name, header=None)
        except Exception:
            continue

        value_type = "rain" if is_rain_sheet(sheet_name) else "flow"
        parsed = parse_wide_year_sheet(raw, year, value_type)

        if not parsed.empty:
            parsed["ParsedFromSheet"] = sheet_name
            parsed_frames.append(parsed)

    if not parsed_frames:
        return pd.DataFrame()

    combined = pd.concat(parsed_frames, ignore_index=True)
    combined["EntryDate"] = pd.to_datetime(combined["EntryDate"]).dt.date

    grouped = (
        combined.groupby("EntryDate", as_index=False)
        .agg(
            RainfallInches=("RainfallInches", "max"),
            WastewaterFlowMgd=("WastewaterFlowMgd", "max"),
            Notes=("Notes", "first"),
        )
    )

    return grouped


def parse_any_upload(uploaded_file):
    """
    First try structured Date/Rainfall/Flow format.
    If that fails or finds no rows, try the older historical wide workbook format.
    """
    filename = uploaded_file.name.lower()

    if filename.endswith(".csv"):
        return parse_structured_upload(uploaded_file)

    file_bytes = uploaded_file.getvalue()

    structured_error = None

    try:
        structured = parse_structured_upload(BytesIO(file_bytes))
        if not structured.empty:
            return structured
    except Exception as ex:
        structured_error = str(ex)

    try:
        historical = parse_historical_workbook(BytesIO(file_bytes))
        if not historical.empty:
            return historical
    except Exception as ex:
        raise ValueError(
            f"Could not parse this workbook as a structured upload or historical workbook. "
            f"Structured error: {structured_error}. Historical error: {ex}"
        )

    raise ValueError(
        "No usable rows found. Use columns Date, RainfallInches, WastewaterFlowMgd, "
        "or upload the older workbook with sheets like 2016 and 2016 Rain."
    )


# ------------------------------------------------------------
# Consumption report discovery
# ------------------------------------------------------------

def get_candidate_consumption_tables():
    sql = """
    SELECT
        TABLE_SCHEMA,
        TABLE_NAME,
        COLUMN_NAME
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE
        COLUMN_NAME LIKE '%Consumed%'
        OR COLUMN_NAME LIKE '%Consumption%'
        OR COLUMN_NAME LIKE '%Water%'
        OR COLUMN_NAME LIKE '%ReadDate%'
        OR COLUMN_NAME LIKE '%Billing%'
        OR COLUMN_NAME LIKE '%Pumped%'
    ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION;
    """

    df = query_df(sql)

    if df.empty:
        return []

    candidates = []

    for (schema, table), group in df.groupby(["TABLE_SCHEMA", "TABLE_NAME"]):
        cols = set(str(c).lower() for c in group["COLUMN_NAME"].tolist())

        has_consumed = any("consumed" in c or "consumption" in c for c in cols)
        has_date = any("date" in c or "period" in c or "billing" in c for c in cols)

        if has_consumed and has_date:
            candidates.append(
                {
                    "schema": schema,
                    "table": table,
                    "columns": group["COLUMN_NAME"].tolist(),
                }
            )

    return candidates


def pick_column(columns, preferred):
    normalized = {clean_col_name(c): c for c in columns}

    for p in preferred:
        key = clean_col_name(p)
        if key in normalized:
            return normalized[key]

    for c in columns:
        c_low = str(c).lower()
        for p in preferred:
            if str(p).lower() in c_low:
                return c

    return None


def load_consumption_data():
    """
    Tries to automatically find your existing monthly water-consumption report table.
    If it cannot find it, the dashboard still works without this section.
    """

    try:
        candidates = get_candidate_consumption_tables()
    except Exception:
        return pd.DataFrame(), None

    if not candidates:
        return pd.DataFrame(), None

    best = None

    for c in candidates:
        cols_lower = [str(x).lower() for x in c["columns"]]
        score = 0

        for word in ["waterconsumed", "consumed", "currentreaddate", "lastreaddate", "billingdays", "periodlabel"]:
            if any(word in clean_col_name(x) for x in cols_lower):
                score += 1

        if best is None or score > best["score"]:
            best = {**c, "score": score}

    if best is None:
        return pd.DataFrame(), None

    schema = best["schema"]
    table = best["table"]
    columns = best["columns"]

    consumed_col = pick_column(
        columns,
        [
            "WaterConsumed",
            "Consumed",
            "WaterConsumption",
            "Consumption",
            "TotalConsumed",
        ],
    )

    date_col = pick_column(
        columns,
        [
            "CurrentReadDate",
            "ReadDate",
            "LastReadDate",
            "ReportDate",
            "PeriodEnd",
            "PeriodEndDate",
            "Month",
            "CreatedAt",
        ],
    )

    pumped_col = pick_column(
        columns,
        [
            "WaterPumped",
            "Pumped",
            "TotalPumped",
            "PumpedAveragePerDay",
        ],
    )

    label_col = pick_column(
        columns,
        [
            "PeriodLabel",
            "ReportMonth",
            "MonthLabel",
            "Name",
        ],
    )

    if consumed_col is None or date_col is None:
        return pd.DataFrame(), None

    select_cols = [date_col, consumed_col]

    if pumped_col and pumped_col not in select_cols:
        select_cols.append(pumped_col)

    if label_col and label_col not in select_cols:
        select_cols.append(label_col)

    quoted_cols = ", ".join(f"[{c}]" for c in select_cols)

    sql = f"""
    SELECT TOP 5000 {quoted_cols}
    FROM [{schema}].[{table}]
    ORDER BY [{date_col}];
    """

    try:
        raw = query_df(sql)
    except Exception:
        return pd.DataFrame(), None

    if raw.empty:
        return pd.DataFrame(), None

    out = pd.DataFrame()
    out["Date"] = pd.to_datetime(raw[date_col], errors="coerce")
    out["WaterConsumedRaw"] = pd.to_numeric(raw[consumed_col], errors="coerce")

    if pumped_col and pumped_col in raw.columns:
        out["WaterPumpedRaw"] = pd.to_numeric(raw[pumped_col], errors="coerce")
    else:
        out["WaterPumpedRaw"] = None

    if label_col and label_col in raw.columns:
        out["PeriodLabel"] = raw[label_col].astype(str)
    else:
        out["PeriodLabel"] = out["Date"].dt.strftime("%Y-%m")

    out = out.dropna(subset=["Date", "WaterConsumedRaw"])
    if out.empty:
        return pd.DataFrame(), None

    # Convert gallons to million gallons when numbers look like gallons.
    # If values are already small, assume they are already MG.
    max_consumed = out["WaterConsumedRaw"].max()

    if pd.notna(max_consumed) and max_consumed > 10000:
        out["WaterConsumedMG"] = out["WaterConsumedRaw"] / 1_000_000
    else:
        out["WaterConsumedMG"] = out["WaterConsumedRaw"]

    max_pumped = pd.to_numeric(out["WaterPumpedRaw"], errors="coerce").max()

    if pd.notna(max_pumped) and max_pumped > 10000:
        out["WaterPumpedMG"] = out["WaterPumpedRaw"] / 1_000_000
    else:
        out["WaterPumpedMG"] = out["WaterPumpedRaw"]

    out["Month"] = out["Date"].dt.to_period("M").dt.to_timestamp()

    source = f"{schema}.{table}"
    return out, source


# ------------------------------------------------------------
# Download helpers
# ------------------------------------------------------------

def make_template_xlsx():
    template = pd.DataFrame(
        {
            "Date": [
                "2026-01-01",
                "2026-01-02",
                "2026-01-03",
            ],
            "RainfallInches": [
                0.00,
                0.25,
                1.10,
            ],
            "WastewaterFlowMgd": [
                0.350,
                0.410,
                0.620,
            ],
            "Notes": [
                "",
                "",
                "Heavy rain",
            ],
        }
    )

    output = BytesIO()

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        template.to_excel(writer, index=False, sheet_name="RainFlowUpload")

        workbook = writer.book
        worksheet = writer.sheets["RainFlowUpload"]

        header_format = workbook.add_format(
            {
                "bold": True,
                "bg_color": "#0F4C81",
                "font_color": "white",
                "border": 1,
            }
        )

        date_format = workbook.add_format({"num_format": "yyyy-mm-dd"})
        number_format = workbook.add_format({"num_format": "0.000"})

        for col_num, value in enumerate(template.columns.values):
            worksheet.write(0, col_num, value, header_format)

        worksheet.set_column("A:A", 14, date_format)
        worksheet.set_column("B:C", 18, number_format)
        worksheet.set_column("D:D", 35)

    output.seek(0)
    return output.getvalue()


def make_pdf_report(df, monthly, start_date, end_date):
    output = BytesIO()

    doc = SimpleDocTemplate(
        output,
        pagesize=landscape(letter),
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    story = []

    title = Paragraph("Rainfall & Wastewater Flow Report", styles["Title"])
    story.append(title)
    story.append(Spacer(1, 12))

    subtitle = Paragraph(f"Date range: {start_date} through {end_date}", styles["Normal"])
    story.append(subtitle)
    story.append(Spacer(1, 12))

    if df.empty:
        story.append(Paragraph("No data available for this date range.", styles["Normal"]))
    else:
        total_rain = df["RainfallInches"].sum(skipna=True)
        avg_flow = df["WastewaterFlowMgd"].mean(skipna=True)
        max_flow_row = df.loc[df["WastewaterFlowMgd"].idxmax()] if df["WastewaterFlowMgd"].notna().any() else None
        max_rain_row = df.loc[df["RainfallInches"].idxmax()] if df["RainfallInches"].notna().any() else None

        summary_data = [
            ["Metric", "Value"],
            ["Total Rainfall", f"{total_rain:,.2f} inches"],
            ["Average WW Flow", f"{avg_flow:,.3f} MGD" if pd.notna(avg_flow) else "N/A"],
            [
                "Max Daily WW Flow",
                f"{max_flow_row['WastewaterFlowMgd']:,.3f} MGD on {max_flow_row['EntryDate'].date()}"
                if max_flow_row is not None
                else "N/A",
            ],
            [
                "Max Daily Rainfall",
                f"{max_rain_row['RainfallInches']:,.2f} inches on {max_rain_row['EntryDate'].date()}"
                if max_rain_row is not None
                else "N/A",
            ],
        ]

        summary_table = Table(summary_data, colWidths=[220, 360])
        summary_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F4C81")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F3F8FA")),
                    ("PADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(summary_table)
        story.append(Spacer(1, 18))

        if not monthly.empty:
            story.append(Paragraph("Monthly Summary", styles["Heading2"]))
            story.append(Spacer(1, 8))

            month_table_data = [["Month", "Rainfall Inches", "Avg WW Flow MGD", "Total WW Treated MG"]]

            for _, r in monthly.tail(18).iterrows():
                month_table_data.append(
                    [
                        r["Month"].strftime("%Y-%m"),
                        f"{r['RainfallInches']:,.2f}",
                        f"{r['AvgWastewaterFlowMgd']:,.3f}",
                        f"{r['WastewaterTreatedMG']:,.2f}",
                    ]
                )

            month_table = Table(month_table_data, colWidths=[120, 150, 170, 180])
            month_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2F8F83")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("PADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            story.append(month_table)

    doc.build(story)
    output.seek(0)
    return output.getvalue()


# ------------------------------------------------------------
# Chart helpers
# ------------------------------------------------------------

def build_daily_chart(df, rainfall_lag_days=0):
    chart_df = df.copy()

    if rainfall_lag_days > 0:
        chart_df["RainfallForComparison"] = chart_df["RainfallInches"].shift(rainfall_lag_days)
        rain_name = f"Rainfall shifted {rainfall_lag_days} day(s)"
    else:
        chart_df["RainfallForComparison"] = chart_df["RainfallInches"]
        rain_name = "Rainfall"

    chart_df["Flow7DayAvg"] = chart_df["WastewaterFlowMgd"].rolling(window=7, min_periods=1).mean()

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Bar(
            x=chart_df["EntryDate"],
            y=chart_df["RainfallForComparison"],
            name=rain_name,
            opacity=0.65,
        ),
        secondary_y=False,
    )

    fig.add_trace(
        go.Scatter(
            x=chart_df["EntryDate"],
            y=chart_df["WastewaterFlowMgd"],
            name="Wastewater Flow MGD",
            mode="lines+markers",
            line=dict(width=3),
        ),
        secondary_y=True,
    )

    fig.add_trace(
        go.Scatter(
            x=chart_df["EntryDate"],
            y=chart_df["Flow7DayAvg"],
            name="7-Day Avg WW Flow",
            mode="lines",
            line=dict(width=2, dash="dash"),
        ),
        secondary_y=True,
    )

    fig.update_layout(
        title="Daily Rainfall vs Wastewater Flow",
        height=560,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=30, r=30, t=80, b=30),
    )

    fig.update_yaxes(title_text="Rainfall Inches", secondary_y=False)
    fig.update_yaxes(title_text="Wastewater Flow MGD", secondary_y=True)

    return fig


def build_monthly_df(df):
    if df.empty:
        return pd.DataFrame()

    monthly = (
        df.groupby("Month", as_index=False)
        .agg(
            RainfallInches=("RainfallInches", "sum"),
            AvgWastewaterFlowMgd=("WastewaterFlowMgd", "mean"),
            MaxWastewaterFlowMgd=("WastewaterFlowMgd", "max"),
            WastewaterTreatedMG=("WastewaterFlowMgd", "sum"),
            DaysWithData=("WastewaterFlowMgd", "count"),
        )
    )

    monthly["Year"] = monthly["Month"].dt.year
    monthly["MonthNumber"] = monthly["Month"].dt.month
    monthly["MonthName"] = monthly["Month"].dt.strftime("%b")

    return monthly


def build_monthly_chart(monthly):
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Bar(
            x=monthly["Month"],
            y=monthly["RainfallInches"],
            name="Monthly Rainfall",
            opacity=0.7,
        ),
        secondary_y=False,
    )

    fig.add_trace(
        go.Scatter(
            x=monthly["Month"],
            y=monthly["AvgWastewaterFlowMgd"],
            name="Average WW Flow MGD",
            mode="lines+markers",
            line=dict(width=3),
        ),
        secondary_y=True,
    )

    fig.update_layout(
        title="Monthly Rainfall vs Average Wastewater Flow",
        height=520,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=30, r=30, t=80, b=30),
    )

    fig.update_yaxes(title_text="Rainfall Inches", secondary_y=False)
    fig.update_yaxes(title_text="Average WW Flow MGD", secondary_y=True)

    return fig


def build_scatter_chart(df):
    scatter_df = df.dropna(subset=["RainfallInches", "WastewaterFlowMgd"]).copy()

    if scatter_df.empty:
        return None

    fig = px.scatter(
        scatter_df,
        x="RainfallInches",
        y="WastewaterFlowMgd",
        trendline="ols",
        hover_data=["EntryDate"],
        title="Rainfall vs Wastewater Flow Correlation",
        labels={
            "RainfallInches": "Rainfall Inches",
            "WastewaterFlowMgd": "Wastewater Flow MGD",
        },
    )

    fig.update_layout(
        height=520,
        margin=dict(l=30, r=30, t=80, b=30),
    )

    return fig


def build_year_over_year_chart(monthly, metric):
    if monthly.empty:
        return None

    y_col = metric

    fig = px.line(
        monthly,
        x="MonthNumber",
        y=y_col,
        color="Year",
        markers=True,
        title=f"Year-over-Year {metric}",
        labels={
            "MonthNumber": "Month",
            y_col: metric,
        },
    )

    fig.update_xaxes(
        tickmode="array",
        tickvals=list(range(1, 13)),
        ticktext=["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    )

    fig.update_layout(
        height=520,
        margin=dict(l=30, r=30, t=80, b=30),
    )

    return fig


def build_consumption_comparison_chart(monthly, consumption_df):
    if monthly.empty or consumption_df.empty:
        return None

    comp = monthly[["Month", "WastewaterTreatedMG", "RainfallInches"]].copy()

    monthly_consumption = (
        consumption_df.groupby("Month", as_index=False)
        .agg(
            WaterConsumedMG=("WaterConsumedMG", "sum"),
            WaterPumpedMG=("WaterPumpedMG", "sum"),
        )
    )

    comp = comp.merge(monthly_consumption, on="Month", how="inner")

    if comp.empty:
        return None

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=comp["Month"],
            y=comp["WastewaterTreatedMG"],
            name="Wastewater Treated MG",
        )
    )

    fig.add_trace(
        go.Bar(
            x=comp["Month"],
            y=comp["WaterConsumedMG"],
            name="Water Consumed MG",
        )
    )

    if comp["WaterPumpedMG"].notna().any():
        fig.add_trace(
            go.Scatter(
                x=comp["Month"],
                y=comp["WaterPumpedMG"],
                name="Water Pumped MG",
                mode="lines+markers",
                line=dict(width=3),
            )
        )

    fig.update_layout(
        title="Wastewater Treated vs Water Consumed",
        height=540,
        barmode="group",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=30, r=30, t=80, b=30),
        yaxis_title="Million Gallons",
    )

    return fig


# ------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------

with st.sidebar:
    st.header("Controls")

    try:
        init_database()
        db_status = "Connected"
        st.success("SQL connected")
    except Exception as ex:
        db_status = "Error"
        st.error("SQL connection failed")
        st.caption(str(ex))

    st.divider()

    all_data_for_dates = pd.DataFrame()

    if db_status == "Connected":
        try:
            all_data_for_dates = load_rain_flow_data()
        except Exception:
            all_data_for_dates = pd.DataFrame()

    if not all_data_for_dates.empty:
        min_date = all_data_for_dates["EntryDate"].min().date()
        max_date = all_data_for_dates["EntryDate"].max().date()
    else:
        min_date = date(date.today().year, 1, 1)
        max_date = date.today()

    selected_range = st.date_input(
        "Date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )

    if isinstance(selected_range, tuple) and len(selected_range) == 2:
        start_date, end_date = selected_range
    else:
        start_date = min_date
        end_date = max_date

    group_view = st.selectbox(
        "Main view",
        ["Daily", "Monthly", "Year-over-Year"],
        index=0,
    )

    rainfall_lag_days = st.selectbox(
        "Rainfall comparison lag",
        [0, 1, 2, 3, 4, 5, 7],
        index=0,
        help="Use this to compare rain to wastewater flow on later days.",
    )

    st.divider()

    st.download_button(
        "Download blank upload template",
        data=make_template_xlsx(),
        file_name="rainfall_flow_upload_template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ------------------------------------------------------------
# Header
# ------------------------------------------------------------

st.markdown(
    f"""
    <div class="hero-card">
        <h1>🌧️ {APP_TITLE}</h1>
        <p>
            Track rainfall, wastewater plant flow, and water-consumption comparisons.
            Use this to spot wet-weather flow increases, infiltration/inflow patterns,
            and month-over-month or year-over-year trends.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)


# ------------------------------------------------------------
# Stop early if DB is unavailable
# ------------------------------------------------------------

if db_status != "Connected":
    st.stop()


# ------------------------------------------------------------
# Upload section
# ------------------------------------------------------------

with st.expander("Upload rainfall / wastewater flow data", expanded=False):
    st.markdown(
        """
        Upload either:

        1. A structured Excel/CSV file with columns like  
           `Date`, `RainfallInches`, `WastewaterFlowMgd`, `Notes`

        2. Your older historical workbook with sheets like  
           `2016`, `2016 Rain`, `2017`, `2017 Rain`, etc.
        """
    )

    uploaded_file = st.file_uploader(
        "Upload Excel or CSV",
        type=["xlsx", "xls", "csv"],
    )

    if uploaded_file is not None:
        try:
            parsed_upload = parse_any_upload(uploaded_file)

            st.success(f"Parsed {len(parsed_upload):,} rows from {uploaded_file.name}")

            preview = parsed_upload.copy()
            preview["EntryDate"] = pd.to_datetime(preview["EntryDate"], errors="coerce").dt.date
            st.dataframe(preview.head(100), use_container_width=True)

            col1, col2 = st.columns([1, 3])

            with col1:
                if st.button("Import / update SQL", type="primary"):
                    result = upsert_rain_flow_rows(parsed_upload, uploaded_file.name)
                    st.success(
                        f"Imported or updated {result['inserted_or_updated']:,} rows. "
                        f"Skipped {result['skipped']:,} blank rows."
                    )
                    st.rerun()

            with col2:
                csv_data = parsed_upload.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "Download cleaned parsed CSV",
                    data=csv_data,
                    file_name="cleaned_rainfall_flow_data.csv",
                    mime="text/csv",
                )

        except Exception as ex:
            st.error("Upload could not be parsed.")
            st.exception(ex)


# ------------------------------------------------------------
# Load selected data
# ------------------------------------------------------------

df = load_rain_flow_data(start_date, end_date)

if df.empty:
    st.info(
        "No rainfall / wastewater flow records are in SQL for this date range yet. "
        "Upload your historical workbook or the structured template to begin."
    )
    st.stop()

monthly = build_monthly_df(df)


# ------------------------------------------------------------
# KPI cards
# ------------------------------------------------------------

total_rain = df["RainfallInches"].sum(skipna=True)
avg_flow = df["WastewaterFlowMgd"].mean(skipna=True)
max_flow = df["WastewaterFlowMgd"].max(skipna=True)
max_rain = df["RainfallInches"].max(skipna=True)
total_ww_treated = df["WastewaterFlowMgd"].sum(skipna=True)

rain_days = int((df["RainfallInches"].fillna(0) > 0).sum())
flow_days = int(df["WastewaterFlowMgd"].notna().sum())

col1, col2, col3, col4, col5, col6 = st.columns(6)

with col1:
    st.metric("Total Rainfall", f"{total_rain:,.2f} in")

with col2:
    st.metric("Rain Days", f"{rain_days:,}")

with col3:
    st.metric("Avg WW Flow", f"{avg_flow:,.3f} MGD" if pd.notna(avg_flow) else "N/A")

with col4:
    st.metric("Max WW Flow", f"{max_flow:,.3f} MGD" if pd.notna(max_flow) else "N/A")

with col5:
    st.metric("Max Rain Day", f"{max_rain:,.2f} in" if pd.notna(max_rain) else "N/A")

with col6:
    st.metric("WW Treated", f"{total_ww_treated:,.2f} MG")


# ------------------------------------------------------------
# Main chart tabs
# ------------------------------------------------------------

tab_daily, tab_monthly, tab_yoy, tab_consumption, tab_data = st.tabs(
    [
        "Daily",
        "Monthly",
        "Year-over-Year",
        "Water Consumed Comparison",
        "Data / Downloads",
    ]
)

with tab_daily:
    st.subheader("Daily Rainfall vs Wastewater Flow")

    st.plotly_chart(
        build_daily_chart(df, rainfall_lag_days=rainfall_lag_days),
        use_container_width=True,
    )

    scatter = build_scatter_chart(df)
    if scatter is not None:
        st.plotly_chart(scatter, use_container_width=True)

    st.markdown("### Highest rainfall days")
    top_rain = (
        df.sort_values("RainfallInches", ascending=False)
        .loc[:, ["EntryDate", "RainfallInches", "WastewaterFlowMgd", "Notes"]]
        .head(10)
    )
    st.dataframe(top_rain, use_container_width=True, hide_index=True)

    st.markdown("### Highest wastewater flow days")
    top_flow = (
        df.sort_values("WastewaterFlowMgd", ascending=False)
        .loc[:, ["EntryDate", "RainfallInches", "WastewaterFlowMgd", "Notes"]]
        .head(10)
    )
    st.dataframe(top_flow, use_container_width=True, hide_index=True)


with tab_monthly:
    st.subheader("Monthly Trends")

    if monthly.empty:
        st.info("No monthly summary available.")
    else:
        st.plotly_chart(build_monthly_chart(monthly), use_container_width=True)

        monthly_display = monthly.copy()
        monthly_display["Month"] = monthly_display["Month"].dt.strftime("%Y-%m")
        st.dataframe(monthly_display, use_container_width=True, hide_index=True)


with tab_yoy:
    st.subheader("Year-over-Year Comparison")

    metric_choice = st.selectbox(
        "Metric",
        [
            "RainfallInches",
            "AvgWastewaterFlowMgd",
            "MaxWastewaterFlowMgd",
            "WastewaterTreatedMG",
        ],
    )

    yoy_chart = build_year_over_year_chart(monthly, metric_choice)

    if yoy_chart is not None:
        st.plotly_chart(yoy_chart, use_container_width=True)
    else:
        st.info("Not enough data for a year-over-year chart.")


with tab_consumption:
    st.subheader("Wastewater Treated vs Water Consumed")

    consumption_df, consumption_source = load_consumption_data()

    if consumption_df.empty:
        st.warning(
            "I could not automatically find a monthly water-consumption table in the database yet. "
            "The rainfall and wastewater graphs will still work. Once we know the exact table/columns "
            "from your monthly report data, this section can be locked directly to that table."
        )

        with st.expander("What the app looked for"):
            st.markdown(
                """
                The app searched SQL Server for tables with columns similar to:

                - `WaterConsumed`
                - `CurrentReadDate`
                - `LastReadDate`
                - `PeriodLabel`
                - `WaterPumped`
                - `BillingDays`
                """
            )
    else:
        st.caption(f"Using consumption source table: `{consumption_source}`")

        comp_chart = build_consumption_comparison_chart(monthly, consumption_df)

        if comp_chart is not None:
            st.plotly_chart(comp_chart, use_container_width=True)
        else:
            st.info(
                "Consumption data was found, but it does not overlap the selected rainfall/flow date range."
            )

        st.markdown("### Consumption data found")
        display_consumption = consumption_df.copy()
        display_consumption["Date"] = display_consumption["Date"].dt.date
        display_consumption["Month"] = display_consumption["Month"].dt.strftime("%Y-%m")
        st.dataframe(display_consumption, use_container_width=True, hide_index=True)


with tab_data:
    st.subheader("Data and Downloads")

    export_df = df.copy()
    export_df["EntryDate"] = export_df["EntryDate"].dt.date

    st.dataframe(export_df, use_container_width=True, hide_index=True)

    csv_bytes = export_df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "Download selected data as CSV",
        data=csv_bytes,
        file_name=f"rainfall_flow_{start_date}_to_{end_date}.csv",
        mime="text/csv",
    )

    pdf_bytes = make_pdf_report(df, monthly, start_date, end_date)

    st.download_button(
        "Download PDF summary report",
        data=pdf_bytes,
        file_name=f"rainfall_flow_report_{start_date}_to_{end_date}.pdf",
        mime="application/pdf",
    )

    with st.expander("Database info"):
        count_df = query_df(f"SELECT COUNT(*) AS TotalRows FROM dbo.{RAIN_FLOW_TABLE};")
        st.dataframe(count_df, use_container_width=True, hide_index=True)

        st.markdown(
            f"""
            **SQL Server:** `{SQL_HOST}`  
            **Database:** `{SQL_DATABASE}`  
            **Table:** `dbo.{RAIN_FLOW_TABLE}`
            """
        )
