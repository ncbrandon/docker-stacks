import os
import uuid
from datetime import datetime, date
from io import BytesIO

import pandas as pd
import plotly.express as px
import pymssql
import streamlit as st
from dotenv import load_dotenv


load_dotenv()

st.set_page_config(
    page_title="Fire Flow Dashboard",
    page_icon="🚒",
    layout="wide",
)


SQL_SERVER = os.getenv("SQL_SERVER", "wwtp-sql")
SQL_PORT = int(os.getenv("SQL_PORT", "1433"))
SQL_DATABASE = os.getenv("SQL_DATABASE", "WWTP")
SQL_USER = os.getenv("SQL_USER", "sa")
SQL_PASSWORD = os.getenv("SQL_PASSWORD", "")


def get_conn(as_dict=False):
    return pymssql.connect(
        server=SQL_SERVER,
        port=SQL_PORT,
        user=SQL_USER,
        password=SQL_PASSWORD,
        database=SQL_DATABASE,
        login_timeout=10,
        timeout=30,
        as_dict=as_dict,
    )


def execute(sql, params=None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
        conn.commit()


def query_df(sql, params=None):
    with get_conn() as conn:
        return pd.read_sql(sql, conn, params=params)


def query_one(sql, params=None):
    with get_conn(as_dict=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchone()


def ensure_tables():
    statements = [
        """
        IF OBJECT_ID('dbo.FireFlowHydrants', 'U') IS NULL
        BEGIN
            CREATE TABLE dbo.FireFlowHydrants (
                Id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,
                FacilityIdentifier NVARCHAR(50) NULL,
                HydrantNumber NVARCHAR(50) NULL,
                ExistingTagNumber NVARCHAR(50) NULL,
                LocationDescription NVARCHAR(255) NULL,
                HydrantSize DECIMAL(10,2) NULL,
                Manufacturer NVARCHAR(100) NULL,
                ModelYear NVARCHAR(20) NULL,
                InstallDate DATE NULL,
                Operable BIT NULL,
                Active BIT NOT NULL DEFAULT 1,
                Latitude DECIMAL(18,10) NULL,
                Longitude DECIMAL(18,10) NULL,
                Notes NVARCHAR(MAX) NULL,
                CreatedAt DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
                UpdatedAt DATETIME2 NULL
            );
        END
        """,
        """
        IF OBJECT_ID('dbo.FireFlowTests', 'U') IS NULL
        BEGIN
            CREATE TABLE dbo.FireFlowTests (
                Id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,
                FireFlowHydrantId UNIQUEIDENTIFIER NULL,
                FacilityIdentifier NVARCHAR(50) NULL,
                HydrantNumber NVARCHAR(50) NULL,
                LocationDescription NVARCHAR(255) NULL,
                TestDate DATE NULL,
                StaticPsi DECIMAL(10,2) NULL,
                ResidualPsi DECIMAL(10,2) NULL,
                PitotPsi DECIMAL(10,2) NULL,
                OutletDiameterInches DECIMAL(10,2) NULL,
                NumberOfOutlets INT NULL,
                Coefficient DECIMAL(10,3) NULL,
                TotalGallonsFlowing DECIMAL(18,2) NULL,
                AvailableFireFlowGpm DECIMAL(18,2) NULL,
                FlowGpm DECIMAL(18,2) NULL,
                TestedBy NVARCHAR(100) NULL,
                WitnessedBy NVARCHAR(100) NULL,
                SourceFileName NVARCHAR(255) NULL,
                Notes NVARCHAR(MAX) NULL,
                ImportedAt DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
                CONSTRAINT FK_FireFlowTests_FireFlowHydrants
                    FOREIGN KEY (FireFlowHydrantId)
                    REFERENCES dbo.FireFlowHydrants(Id)
                    ON DELETE SET NULL
            );
        END
        """,
        """
        IF OBJECT_ID('dbo.FireFlowImportBatches', 'U') IS NULL
        BEGIN
            CREATE TABLE dbo.FireFlowImportBatches (
                Id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,
                SourceFileName NVARCHAR(255) NOT NULL,
                ImportType NVARCHAR(50) NOT NULL,
                RowsRead INT NOT NULL DEFAULT 0,
                RowsInserted INT NOT NULL DEFAULT 0,
                RowsUpdated INT NOT NULL DEFAULT 0,
                RowsSkipped INT NOT NULL DEFAULT 0,
                ImportedAt DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
                Notes NVARCHAR(MAX) NULL
            );
        END
        """,
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'IX_FireFlowHydrants_HydrantNumber'
            AND object_id = OBJECT_ID('dbo.FireFlowHydrants')
        )
        CREATE INDEX IX_FireFlowHydrants_HydrantNumber
        ON dbo.FireFlowHydrants(HydrantNumber);
        """,
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'IX_FireFlowTests_HydrantNumber_TestDate'
            AND object_id = OBJECT_ID('dbo.FireFlowTests')
        )
        CREATE INDEX IX_FireFlowTests_HydrantNumber_TestDate
        ON dbo.FireFlowTests(HydrantNumber, TestDate);
        """,
    ]

    for statement in statements:
        execute(statement)


def clean_text(value):
    if value is None:
        return None
    if pd.isna(value):
        return None

    # Convert numeric hydrant/location values like 46.0 to "46"
    if isinstance(value, (int, float)):
        if float(value).is_integer():
            return str(int(value))
        return str(value).strip()

    text = str(value).strip()
    if text == "" or text.lower() == "nan":
        return None

    # Also catch text values like "46.0"
    try:
        number = float(text)
        if number.is_integer():
            return str(int(number))
    except Exception:
        pass

    return text


def is_header_or_bad_row(*values):
    bad_words = {
        "id",
        "fireflowhydrantid",
        "facilityidentifier",
        "hydrantnumber",
        "locationdescription",
        "testdate",
        "flowgpm",
        "availablefireflowgpm",
        "staticpsi",
        "residualpsi",
        "pitotpsi",
        "outletdiameterinches",
        "numberofoutlets",
        "coefficient",
        "totalgallonsflowing",
        "testedby",
        "witnessedby",
        "sourcefilename",
        "notes",
    }

    cleaned = [clean_text(v) for v in values if clean_text(v) is not None]

    if not cleaned:
        return True

    matches = 0

    for value in cleaned:
        normalized = value.replace(" ", "").replace("_", "").lower()
        if normalized in bad_words:
            matches += 1

    return matches >= 2

def to_decimal(value):
    if value is None:
        return None
    if pd.isna(value):
        return None
    text = str(value).replace(",", "").strip()
    if text == "" or text.lower() == "nan":
        return None
    try:
        return float(text)
    except Exception:
        return None


def to_int(value):
    value = to_decimal(value)
    if value is None:
        return None
    return int(value)


def to_date(value):
    if value is None:
        return None
    if pd.isna(value):
        return None

    # Excel serial date numbers, for example 43606 = 05/21/2019
    if isinstance(value, (int, float)):
        try:
            if value > 20000:
                parsed = pd.to_datetime(value, unit="D", origin="1899-12-30", errors="coerce")
                if pd.notna(parsed):
                    return parsed.date()
        except Exception:
            pass

    try:
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            return None
        return parsed.date()
    except Exception:
        return None


def to_bool(value):
    text = clean_text(value)
    if text is None:
        return None

    text = text.lower()
    if text in ["true", "yes", "y", "1", "active"]:
        return 1
    if text in ["false", "no", "n", "0", "inactive"]:
        return 0
    return None


def normalize_columns(df):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def first_col(df, possible_names):
    lower_map = {str(c).strip().lower(): c for c in df.columns}

    for name in possible_names:
        key = name.strip().lower()
        if key in lower_map:
            return lower_map[key]

    for col in df.columns:
        col_lower = str(col).strip().lower()
        for name in possible_names:
            if name.strip().lower() in col_lower:
                return col

    return None


def get_value(row, df, possible_names):
    col = first_col(df, possible_names)
    if col is None:
        return None
    return row.get(col)


def find_or_create_hydrant(
    facility_identifier=None,
    hydrant_number=None,
    existing_tag=None,
    location=None,
    hydrant_size=None,
    manufacturer=None,
    model_year=None,
    install_date=None,
    operable=None,
    active=1,
    latitude=None,
    longitude=None,
    notes=None,
):
    found = None

    if hydrant_number:
        found = query_one(
            "SELECT TOP 1 * FROM dbo.FireFlowHydrants WHERE HydrantNumber = %s",
            (hydrant_number,),
        )

    if found is None and facility_identifier:
        found = query_one(
            "SELECT TOP 1 * FROM dbo.FireFlowHydrants WHERE FacilityIdentifier = %s",
            (facility_identifier,),
        )

    if found:
        hydrant_id = found["Id"]

        execute(
            """
            UPDATE dbo.FireFlowHydrants
            SET
                FacilityIdentifier = COALESCE(%s, FacilityIdentifier),
                HydrantNumber = COALESCE(%s, HydrantNumber),
                ExistingTagNumber = COALESCE(%s, ExistingTagNumber),
                LocationDescription = COALESCE(%s, LocationDescription),
                HydrantSize = COALESCE(%s, HydrantSize),
                Manufacturer = COALESCE(%s, Manufacturer),
                ModelYear = COALESCE(%s, ModelYear),
                InstallDate = COALESCE(%s, InstallDate),
                Operable = COALESCE(%s, Operable),
                Active = COALESCE(%s, Active),
                Latitude = COALESCE(%s, Latitude),
                Longitude = COALESCE(%s, Longitude),
                Notes = COALESCE(%s, Notes),
                UpdatedAt = SYSUTCDATETIME()
            WHERE Id = %s
            """,
            (
                facility_identifier,
                hydrant_number,
                existing_tag,
                location,
                hydrant_size,
                manufacturer,
                model_year,
                install_date,
                operable,
                active,
                latitude,
                longitude,
                notes,
                hydrant_id,
            ),
        )

        return hydrant_id, False

    hydrant_id = str(uuid.uuid4())

    execute(
        """
        INSERT INTO dbo.FireFlowHydrants (
            Id,
            FacilityIdentifier,
            HydrantNumber,
            ExistingTagNumber,
            LocationDescription,
            HydrantSize,
            Manufacturer,
            ModelYear,
            InstallDate,
            Operable,
            Active,
            Latitude,
            Longitude,
            Notes
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            hydrant_id,
            facility_identifier,
            hydrant_number,
            existing_tag,
            location,
            hydrant_size,
            manufacturer,
            model_year,
            install_date,
            operable,
            active if active is not None else 1,
            latitude,
            longitude,
            notes,
        ),
    )

    return hydrant_id, True


def insert_import_batch(source_file, import_type, rows_read, rows_inserted, rows_updated, rows_skipped, notes=None):
    execute(
        """
        INSERT INTO dbo.FireFlowImportBatches (
            Id, SourceFileName, ImportType, RowsRead, RowsInserted, RowsUpdated, RowsSkipped, Notes
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            str(uuid.uuid4()),
            source_file,
            import_type,
            rows_read,
            rows_inserted,
            rows_updated,
            rows_skipped,
            notes,
        ),
    )


def fire_flow_duplicate_exists(hydrant_number, test_date, static_psi, residual_psi, pitot_psi, flow_gpm):
    existing = query_one(
        """
        SELECT TOP 1 Id
        FROM dbo.FireFlowTests
        WHERE
            ISNULL(HydrantNumber, '') = ISNULL(%s, '')
            AND (
                (TestDate = %s)
                OR (TestDate IS NULL AND %s IS NULL)
            )
            AND ISNULL(StaticPsi, -999999) = ISNULL(%s, -999999)
            AND ISNULL(ResidualPsi, -999999) = ISNULL(%s, -999999)
            AND ISNULL(PitotPsi, -999999) = ISNULL(%s, -999999)
            AND ISNULL(FlowGpm, -999999) = ISNULL(%s, -999999)
        """,
        (hydrant_number, test_date, test_date, static_psi, residual_psi, pitot_psi, flow_gpm),
    )
    return existing is not None


def insert_fire_flow_test(
    hydrant_id=None,
    facility_identifier=None,
    hydrant_number=None,
    location=None,
    test_date=None,
    static_psi=None,
    residual_psi=None,
    pitot_psi=None,
    outlet_diameter=None,
    number_of_outlets=None,
    coefficient=None,
    total_gallons_flowing=None,
    available_fire_flow_gpm=None,
    flow_gpm=None,
    tested_by=None,
    witnessed_by=None,
    source_file=None,
    notes=None,
):
    execute(
        """
        INSERT INTO dbo.FireFlowTests (
            Id,
            FireFlowHydrantId,
            FacilityIdentifier,
            HydrantNumber,
            LocationDescription,
            TestDate,
            StaticPsi,
            ResidualPsi,
            PitotPsi,
            OutletDiameterInches,
            NumberOfOutlets,
            Coefficient,
            TotalGallonsFlowing,
            AvailableFireFlowGpm,
            FlowGpm,
            TestedBy,
            WitnessedBy,
            SourceFileName,
            Notes
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            str(uuid.uuid4()),
            hydrant_id,
            facility_identifier,
            hydrant_number,
            location,
            test_date,
            static_psi,
            residual_psi,
            pitot_psi,
            outlet_diameter,
            number_of_outlets,
            coefficient,
            total_gallons_flowing,
            available_fire_flow_gpm,
            flow_gpm,
            tested_by,
            witnessed_by,
            source_file,
            notes,
        ),
    )


def import_hydrant_flushing(uploaded_file):
    xls = pd.ExcelFile(uploaded_file)
    sheet_name = "Hydrants_0" if "Hydrants_0" in xls.sheet_names else xls.sheet_names[0]

    df = pd.read_excel(uploaded_file, sheet_name=sheet_name)
    df = normalize_columns(df)

    required_any = [
        "Facility Identifier",
        "Location Description",
        "Existing Tag Number",
        "Flow (PSI)",
        "Date Hydrant Flushed",
    ]

    found_required = [col for col in required_any if col in df.columns]

    if len(found_required) < 2:
        raise ValueError(
            "This does not look like the Hydrant / Flushing spreadsheet. "
            "Expected columns like Facility Identifier, Location Description, Existing Tag Number, Flow (PSI), or Date Hydrant Flushed."
        )

    rows_read = 0
    rows_inserted = 0
    rows_updated = 0
    rows_skipped = 0
    tests_inserted = 0

    for _, row in df.iterrows():
        rows_read += 1

        facility_identifier = clean_text(get_value(row, df, ["Facility Identifier", "FacilityIdentifier"]))
        location = clean_text(get_value(row, df, ["Location Description", "LocationDescription"]))
        existing_tag = clean_text(get_value(row, df, ["Existing Tag Number", "ExistingTagNumber"]))

        hydrant_number = existing_tag or facility_identifier

        if is_header_or_bad_row(facility_identifier, hydrant_number, location):
            rows_skipped += 1
            continue

        if not hydrant_number and not facility_identifier:
            rows_skipped += 1
            continue

        # Extra protection: skip accidental Fire Flow export rows.
        if hydrant_number in ["HydrantNumber", "FacilityIdentifier", "Id"]:
            rows_skipped += 1
            continue

        hydrant_size = to_decimal(get_value(row, df, ["Hydrant Size", "HydrantSize"]))
        manufacturer = clean_text(get_value(row, df, ["Manufacturer"]))
        model_year = clean_text(get_value(row, df, ["Model Year", "ModelYear"]))
        install_date = to_date(get_value(row, df, ["Install_Date", "Install Date", "InstallDate"]))
        operable = to_bool(get_value(row, df, ["Operable"]))
        active = to_bool(get_value(row, df, ["Active"]))
        notes = clean_text(get_value(row, df, ["Notes", "General Notes"]))

        longitude = to_decimal(get_value(row, df, ["x2", "X2", "X", "Longitude", "LONGITUDE"]))
        latitude = to_decimal(get_value(row, df, ["y2", "Y2", "Y", "Latitude", "LATITUDE"]))

        hydrant_id, created = find_or_create_hydrant(
            facility_identifier=facility_identifier,
            hydrant_number=hydrant_number,
            existing_tag=existing_tag,
            location=location,
            hydrant_size=hydrant_size,
            manufacturer=manufacturer,
            model_year=model_year,
            install_date=install_date,
            operable=operable,
            active=active if active is not None else 1,
            latitude=latitude,
            longitude=longitude,
            notes=notes,
        )

        if created:
            rows_inserted += 1
        else:
            rows_updated += 1

        flow_gpm = to_decimal(get_value(row, df, ["Flow (PSI)", "Flow PSI", "Flow", "Flow GPM", "FlowGpm"]))
        test_date = to_date(get_value(row, df, ["Date Hydrant Flushed", "Hydrant Flushed Date", "Test Date"]))
        tested_by = clean_text(get_value(row, df, ["Hydrant Flushed By", "Flushed By", "Tested By"]))
        fd_notes = clean_text(get_value(row, df, ["Notes from FD", "FD Notes"]))

        if flow_gpm is not None or test_date is not None:
            if not fire_flow_duplicate_exists(hydrant_number, test_date, None, None, None, flow_gpm):
                insert_fire_flow_test(
                    hydrant_id=hydrant_id,
                    facility_identifier=facility_identifier,
                    hydrant_number=hydrant_number,
                    location=location,
                    test_date=test_date,
                    flow_gpm=flow_gpm,
                    tested_by=tested_by,
                    source_file=uploaded_file.name,
                    notes=fd_notes,
                )
                tests_inserted += 1

    insert_import_batch(
        uploaded_file.name,
        "HydrantFlushing",
        rows_read,
        rows_inserted,
        rows_updated,
        rows_skipped,
        notes=f"Inserted {tests_inserted} flow test rows from flushing/GIS sheet. Flow (PSI) imported as FlowGpm.",
    )

    return rows_read, rows_inserted, rows_updated, rows_skipped, tests_inserted


def import_fire_flow_tests(uploaded_file):
    xls = pd.ExcelFile(uploaded_file)
    sheet_name = "Flowtests" if "Flowtests" in xls.sheet_names else xls.sheet_names[0]

    # Read without assuming the header row. Then find the real header row.
    raw = pd.read_excel(uploaded_file, sheet_name=sheet_name, header=None)
    raw = raw.dropna(how="all")

    header_row_index = None

    for idx, row in raw.iterrows():
        row_values = [clean_text(v) for v in row.tolist()]
        row_text = " ".join([v.lower() for v in row_values if v])

        if (
            "location" in row_text
            and "pitot" in row_text
            and "static" in row_text
            and "residual" in row_text
        ):
            header_row_index = idx
            break

    if header_row_index is None:
        raise ValueError(
            "Could not find the fire-flow header row. Expected columns like Location, Pitot, Static, and Residual."
        )

    headers = raw.loc[header_row_index].tolist()
    df = raw.loc[header_row_index + 1:].copy()
    df.columns = [clean_text(c) or f"Column{i}" for i, c in enumerate(headers)]
    df = normalize_columns(df)
    df = df.dropna(how="all")

    rows_read = 0
    rows_inserted = 0
    rows_skipped = 0

    for _, row in df.iterrows():
        rows_read += 1

        hydrant_number = clean_text(get_value(row, df, ["Location", "Hydrant", "Hydrant Number", "HydrantNumber"]))

        test_date = to_date(get_value(row, df, ["Test Date", "Date"]))

        total_gallons_flowing = to_decimal(get_value(row, df, ["Q", "Total Gallons Flowing", "Gallons Flowing"]))
        flow_gpm = total_gallons_flowing

        coefficient = to_decimal(get_value(row, df, ["Coefficient", "Coefficient C = .9", "C = .9"]))
        outlet_diameter = to_decimal(get_value(row, df, ["Diameter of outlet", "Outlet Diameter", "Diameter"]))
        number_of_outlets = to_int(get_value(row, df, ["Number of outlets flowing", "Number of Outlets", "Outlets"]))
        pitot_psi = to_decimal(get_value(row, df, ["Pitot", "Pitot PSI"]))
        available_fire_flow_gpm = to_decimal(get_value(row, df, ["Available Fire Flow", "AFF", "Available Fire Flow GPM"]))
        static_psi = to_decimal(get_value(row, df, ["Static", "Static PSI"]))
        residual_psi = to_decimal(get_value(row, df, ["Residual", "Residual PSI"]))
        witnessed_by = clean_text(get_value(row, df, ["Witnessed By", "Witnessed"]))

        # Skip repeated header rows or accidental exports.
        if is_header_or_bad_row(
            hydrant_number,
            test_date,
            flow_gpm,
            available_fire_flow_gpm,
            static_psi,
            residual_psi,
            pitot_psi,
        ):
            rows_skipped += 1
            continue

        if not hydrant_number:
            rows_skipped += 1
            continue

        # Skip rows that do not contain any useful fire-flow numbers.
        if (
            flow_gpm is None
            and available_fire_flow_gpm is None
            and static_psi is None
            and residual_psi is None
            and pitot_psi is None
        ):
            rows_skipped += 1
            continue

        hydrant_id, _ = find_or_create_hydrant(hydrant_number=hydrant_number)

        if fire_flow_duplicate_exists(
            hydrant_number,
            test_date,
            static_psi,
            residual_psi,
            pitot_psi,
            flow_gpm,
        ):
            rows_skipped += 1
            continue

        insert_fire_flow_test(
            hydrant_id=hydrant_id,
            hydrant_number=hydrant_number,
            test_date=test_date,
            static_psi=static_psi,
            residual_psi=residual_psi,
            pitot_psi=pitot_psi,
            outlet_diameter=outlet_diameter,
            number_of_outlets=number_of_outlets,
            coefficient=coefficient,
            total_gallons_flowing=total_gallons_flowing,
            available_fire_flow_gpm=available_fire_flow_gpm,
            flow_gpm=flow_gpm,
            witnessed_by=witnessed_by,
            source_file=uploaded_file.name,
        )

        rows_inserted += 1

    insert_import_batch(
        uploaded_file.name,
        "FireFlow",
        rows_read,
        rows_inserted,
        0,
        rows_skipped,
        notes="Imported fire-flow test spreadsheet.",
    )

    return rows_read, rows_inserted, rows_skipped

@st.cache_data(ttl=30)
def load_hydrants():
    return query_df(
        """
        SELECT
            h.Id,
            h.FacilityIdentifier,
            h.HydrantNumber,
            h.ExistingTagNumber,
            h.LocationDescription,
            h.HydrantSize,
            h.Manufacturer,
            h.ModelYear,
            h.InstallDate,
            h.Operable,
            h.Active,
            h.Latitude,
            h.Longitude,
            latest.TestDate AS LatestTestDate,
            latest.FlowGpm AS LatestFlowGpm,
            latest.AvailableFireFlowGpm AS LatestAvailableFireFlowGpm,
            latest.StaticPsi AS LatestStaticPsi,
            latest.ResidualPsi AS LatestResidualPsi
        FROM dbo.FireFlowHydrants h
        OUTER APPLY (
            SELECT TOP 1 *
            FROM dbo.FireFlowTests t
            WHERE t.FireFlowHydrantId = h.Id
            ORDER BY t.TestDate DESC, t.ImportedAt DESC
        ) latest
        ORDER BY TRY_CONVERT(INT, h.HydrantNumber), h.HydrantNumber, h.FacilityIdentifier
        """
    )


@st.cache_data(ttl=30)
def load_tests():
    return query_df(
        """
        SELECT
            t.Id,
            t.FireFlowHydrantId,
            t.FacilityIdentifier,
            t.HydrantNumber,
            t.LocationDescription,
            t.TestDate,
            t.FlowGpm,
            t.AvailableFireFlowGpm,
            t.StaticPsi,
            t.ResidualPsi,
            t.PitotPsi,
            t.OutletDiameterInches,
            t.NumberOfOutlets,
            t.Coefficient,
            t.TotalGallonsFlowing,
            t.TestedBy,
            t.WitnessedBy,
            t.SourceFileName,
            t.Notes,
            t.ImportedAt
        FROM dbo.FireFlowTests t
        ORDER BY t.TestDate DESC, TRY_CONVERT(INT, t.HydrantNumber), t.HydrantNumber
        """
    )


@st.cache_data(ttl=30)
def load_import_batches():
    return query_df(
        """
        SELECT *
        FROM dbo.FireFlowImportBatches
        ORDER BY ImportedAt DESC
        """
    )


def export_excel(hydrants, tests):
    output = BytesIO()

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        hydrants.to_excel(writer, sheet_name="Hydrants", index=False)
        tests.to_excel(writer, sheet_name="Fire Flow Tests", index=False)

    return output.getvalue()


def dashboard_page():
    st.title("🚒 Fire Flow Dashboard")

    hydrants = load_hydrants()
    tests = load_tests()

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Hydrants", len(hydrants))
    col2.metric("Fire-flow tests", len(tests))

    latest_date = ""
    if not tests.empty and "TestDate" in tests:
        latest = pd.to_datetime(tests["TestDate"], errors="coerce").max()
        latest_date = latest.strftime("%m/%d/%Y") if pd.notna(latest) else ""

    col3.metric("Latest test date", latest_date)

    lowest = ""
    if not tests.empty:
        aff = pd.to_numeric(tests["AvailableFireFlowGpm"], errors="coerce").dropna()
        flow = pd.to_numeric(tests["FlowGpm"], errors="coerce").dropna()
        combined = aff if not aff.empty else flow
        if not combined.empty:
            lowest = f"{combined.min():,.0f}"

    col4.metric("Lowest flow/AFF GPM", lowest)

    st.divider()

    if tests.empty:
        st.info("No fire-flow tests imported yet.")
        return

    tests_chart = tests.copy()
    tests_chart["TestDate"] = pd.to_datetime(tests_chart["TestDate"], errors="coerce")

    top_aff = tests_chart.dropna(subset=["AvailableFireFlowGpm"]).copy()
    if not top_aff.empty:
        top_aff["AvailableFireFlowGpm"] = pd.to_numeric(top_aff["AvailableFireFlowGpm"], errors="coerce")
        top_aff = top_aff.sort_values("AvailableFireFlowGpm", ascending=False).head(20)

        fig = px.bar(
            top_aff.sort_values("AvailableFireFlowGpm"),
            x="AvailableFireFlowGpm",
            y="HydrantNumber",
            orientation="h",
            title="Top 20 Available Fire Flow Values",
            labels={"AvailableFireFlowGpm": "Available Fire Flow (GPM)", "HydrantNumber": "Hydrant"},
        )
        st.plotly_chart(fig, use_container_width=True)

    low_flow = tests_chart.copy()
    low_flow["BestFlow"] = pd.to_numeric(low_flow["AvailableFireFlowGpm"], errors="coerce")
    low_flow["BestFlow"] = low_flow["BestFlow"].fillna(pd.to_numeric(low_flow["FlowGpm"], errors="coerce"))
    low_flow = low_flow.dropna(subset=["BestFlow"]).sort_values("BestFlow").head(20)

    if not low_flow.empty:
        fig = px.bar(
            low_flow.sort_values("BestFlow", ascending=False),
            x="BestFlow",
            y="HydrantNumber",
            orientation="h",
            title="Lowest 20 Flow / Available Fire Flow Values",
            labels={"BestFlow": "Flow / AFF (GPM)", "HydrantNumber": "Hydrant"},
        )
        st.plotly_chart(fig, use_container_width=True)

    pressure_df = tests_chart.dropna(subset=["StaticPsi", "ResidualPsi"])
    if not pressure_df.empty:
        fig = px.scatter(
            pressure_df,
            x="StaticPsi",
            y="ResidualPsi",
            hover_data=["HydrantNumber", "TestDate", "FlowGpm", "AvailableFireFlowGpm"],
            title="Static PSI vs Residual PSI",
            labels={"StaticPsi": "Static PSI", "ResidualPsi": "Residual PSI"},
        )
        st.plotly_chart(fig, use_container_width=True)


def import_page():
    st.title("Import Fire Flow Data")

    st.subheader("Import Hydrant / Flushing Spreadsheet")
    st.write("Use this for the GIS/flushing workbook. `Flow (PSI)` will be imported as `FlowGpm`.")

    flushing_file = st.file_uploader(
        "Hydrant / Flushing Excel file",
        type=["xlsx"],
        key="flushing_file",
    )

    if flushing_file is not None:
        if st.button("Import Hydrant / Flushing File"):
            try:
                with st.spinner("Importing hydrant/flushing data..."):
                    result = import_hydrant_flushing(flushing_file)
                    st.cache_data.clear()

                rows_read, rows_inserted, rows_updated, rows_skipped, tests_inserted = result

                st.success(
                    f"Import complete. Rows read: {rows_read}, hydrants inserted: {rows_inserted}, "
                    f"hydrants updated: {rows_updated}, skipped: {rows_skipped}, "
                    f"test rows inserted: {tests_inserted}."
                )
            except Exception as exc:
                st.error(str(exc))

    st.divider()

    st.subheader("Import Fire Flow Test Spreadsheet")
    st.write("Use this for the 2021 fire-flow workbook with static, residual, pitot, and available fire flow.")

    fire_flow_file = st.file_uploader(
        "Fire Flow Excel file",
        type=["xlsx"],
        key="fire_flow_file",
    )

    if fire_flow_file is not None:
        if st.button("Import Fire Flow Test File"):
            try:
                with st.spinner("Importing fire-flow tests..."):
                    result = import_fire_flow_tests(fire_flow_file)
                    st.cache_data.clear()

                rows_read, rows_inserted, rows_skipped = result

                st.success(
                    f"Import complete. Rows read: {rows_read}, tests inserted: {rows_inserted}, "
                    f"skipped: {rows_skipped}."
                )
            except Exception as exc:
                st.error(str(exc))

    st.divider()

    st.subheader("Import History")
    batches = load_import_batches()
    st.dataframe(batches, use_container_width=True)


def hydrants_page():
    st.title("Hydrants")

    hydrants = load_hydrants()

    if hydrants.empty:
        st.info("No hydrants imported yet.")
        return

    search = st.text_input("Search hydrant number, HYD number, or location")

    filtered = hydrants.copy()

    if search:
        s = search.lower()
        filtered = filtered[
            filtered.astype(str).apply(
                lambda row: row.str.lower().str.contains(s, na=False).any(),
                axis=1,
            )
        ]

    st.dataframe(filtered, use_container_width=True, hide_index=True)

    selected = st.selectbox(
        "Select a hydrant to view history",
        options=filtered["Id"].tolist(),
        format_func=lambda x: (
            filtered.loc[filtered["Id"] == x, "HydrantNumber"].iloc[0]
            if not filtered.loc[filtered["Id"] == x].empty
            else str(x)
        ),
    )

    if selected:
        tests = load_tests()
        history = tests[tests["FireFlowHydrantId"].astype(str) == str(selected)].copy()

        if history.empty:
            st.info("No history for this hydrant yet.")
            return

        st.subheader("Hydrant History")
        st.dataframe(history, use_container_width=True, hide_index=True)

        history["TestDate"] = pd.to_datetime(history["TestDate"], errors="coerce")
        history = history.sort_values("TestDate")

        flow_cols = []
        if history["FlowGpm"].notna().any():
            flow_cols.append("FlowGpm")
        if history["AvailableFireFlowGpm"].notna().any():
            flow_cols.append("AvailableFireFlowGpm")

        if flow_cols:
            fig = px.line(
                history,
                x="TestDate",
                y=flow_cols,
                markers=True,
                title="Flow History",
                labels={"value": "GPM", "TestDate": "Test Date", "variable": "Metric"},
            )
            st.plotly_chart(fig, use_container_width=True)

        pressure_cols = []
        if history["StaticPsi"].notna().any():
            pressure_cols.append("StaticPsi")
        if history["ResidualPsi"].notna().any():
            pressure_cols.append("ResidualPsi")
        if history["PitotPsi"].notna().any():
            pressure_cols.append("PitotPsi")

        if pressure_cols:
            fig = px.line(
                history,
                x="TestDate",
                y=pressure_cols,
                markers=True,
                title="Pressure History",
                labels={"value": "PSI", "TestDate": "Test Date", "variable": "Metric"},
            )
            st.plotly_chart(fig, use_container_width=True)


def tests_page():
    st.title("Fire Flow Tests")

    tests = load_tests()

    if tests.empty:
        st.info("No fire-flow tests imported yet.")
        return

    tests["TestDate"] = pd.to_datetime(tests["TestDate"], errors="coerce")

    col1, col2, col3 = st.columns(3)

    search = col1.text_input("Search")
    start_date = col2.date_input("Start date", value=None)
    end_date = col3.date_input("End date", value=None)

    filtered = tests.copy()

    if search:
        s = search.lower()
        filtered = filtered[
            filtered.astype(str).apply(
                lambda row: row.str.lower().str.contains(s, na=False).any(),
                axis=1,
            )
        ]

    if start_date:
        filtered = filtered[filtered["TestDate"] >= pd.to_datetime(start_date)]

    if end_date:
        filtered = filtered[filtered["TestDate"] <= pd.to_datetime(end_date)]

    st.dataframe(filtered, use_container_width=True, hide_index=True)


def export_page():
    st.title("Export Data")

    hydrants = load_hydrants()
    tests = load_tests()

    st.write("Download all Fire Flow data as Excel.")

    export_bytes = export_excel(hydrants, tests)

    st.download_button(
        label="Download Fire Flow Excel Export",
        data=export_bytes,
        file_name=f"FireFlowExport_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def setup_page():
    st.title("Database Setup / Check")

    if st.button("Create / Verify Fire Flow Tables"):
        ensure_tables()
        st.cache_data.clear()
        st.success("Fire Flow tables verified.")

    st.subheader("Table Counts")

    counts = query_df(
        """
        SELECT 'FireFlowHydrants' AS TableName, COUNT(*) AS TotalRows FROM dbo.FireFlowHydrants
        UNION ALL
        SELECT 'FireFlowTests' AS TableName, COUNT(*) AS TotalRows FROM dbo.FireFlowTests
        UNION ALL
        SELECT 'FireFlowImportBatches' AS TableName, COUNT(*) AS TotalRows FROM dbo.FireFlowImportBatches
        """
     )

    st.dataframe(counts, use_container_width=True, hide_index=True)


try:
    ensure_tables()
except Exception as exc:
    st.error("Could not connect to SQL Server or create Fire Flow tables.")
    st.exception(exc)
    st.stop()


st.sidebar.title("Fire Flow")
page = st.sidebar.radio(
    "Page",
    [
        "Dashboard",
        "Import",
        "Hydrants",
        "Fire Flow Tests",
        "Export",
        "Database Setup",
    ],
)

if page == "Dashboard":
    dashboard_page()
elif page == "Import":
    import_page()
elif page == "Hydrants":
    hydrants_page()
elif page == "Fire Flow Tests":
    tests_page()
elif page == "Export":
    export_page()
elif page == "Database Setup":
    setup_page()
