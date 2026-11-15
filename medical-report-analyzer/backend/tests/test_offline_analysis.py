"""Unit tests for the deterministic offline analysis path (no LLM)."""

from __future__ import annotations

from app.services.offline_analysis_service import analyse_report_text_offline


def test_offline_classifies_below_within_above() -> None:
    text = (
        "Hemoglobin: 10.2 g/dL 12.0-15.5\n"
        "Creatinine: 0.9 mg/dL 0.6-1.2\n"
        "Glucose: 110 mg/dL 70-100\n"
    )
    result = analyse_report_text_offline(text)
    by_name = {p["name"].lower(): p for p in result["parameters"]}
    assert by_name["hemoglobin"]["status"] == "Low"
    assert by_name["creatinine"]["status"] == "Normal"
    assert by_name["glucose"]["status"] == "High"


def test_offline_supports_one_sided_bounds() -> None:
    text = "Total Cholesterol: 215 mg/dL < 200 mg/dL\nHDL Cholesterol: 42 mg/dL > 40 mg/dL\n"
    result = analyse_report_text_offline(text)
    by_name = {p["name"].lower(): p for p in result["parameters"]}
    chol = next(p for k, p in by_name.items() if "total" in k)
    hdl = next(p for k, p in by_name.items() if "hdl" in k)
    assert chol["status"] == "High"
    assert hdl["status"] == "Normal"


def test_offline_supports_units_inside_range_and_parens() -> None:
    text = (
        "Hemoglobin: 15.2 g/dL 13.8 - 17.2 g/dL\n"
        "WBC: 7.8 10^3/uL (4.5 - 11.0 10^3/uL)\n"
    )
    result = analyse_report_text_offline(text)
    assert len(result["parameters"]) == 2
    assert all(p["status"] == "Normal" for p in result["parameters"])


def test_offline_ignores_printed_flag_word() -> None:
    text = "Hemoglobin: 10.2 g/dL 12.0-15.5 Normal\n"
    result = analyse_report_text_offline(text)
    assert result["parameters"][0]["status"] == "Low"


def test_offline_strips_parenthesized_flag_from_range() -> None:
    text = "Fasting Blood Glucose: 108 mg/dL 70 - 99 (HIGH) mg/dL\n"
    result = analyse_report_text_offline(text)
    param = result["parameters"][0]
    assert param["status"] == "High"
    assert param["reference_range"] == "70 - 99 mg/dL"
    assert param["report_flag"] == "High"
    assert param["flag_mismatch"] is False


def test_offline_derives_risks_from_validated_statuses() -> None:
    text = "Hemoglobin: 10.2 g/dL 12.0-15.5\nGlucose: 95 mg/dL 70-100\n"
    result = analyse_report_text_offline(text)
    anemia = result["disease_risks"]["anemia"]
    assert anemia["state"] == "requires_review"
    assert anemia["level"] is None
    assert any("10.2" in e for e in anemia["evidence"])
    diabetes = result["disease_risks"]["diabetes"]
    assert diabetes["state"] == "insufficient_data"
    assert result["disease_risks"]["ckd"]["state"] == "insufficient_data"


def test_offline_skips_junk_lines_without_units_or_ranges() -> None:
    text = "Report Date 2024-01-01\nHemoglobin: 10.2 g/dL 12.0-15.5\n"
    result = analyse_report_text_offline(text)
    assert len(result["parameters"]) == 1
    assert result["parameters"][0]["name"] == "Hemoglobin"


def test_offline_empty_text_reports_no_rows() -> None:
    result = analyse_report_text_offline("No measurable content here at all.")
    assert result["parameters"] == []
    assert "no measurable laboratory rows" in result["summary"].lower()


COLUMN_TABLE_TEXT = """MEDREPORT DIAGNOSTICS LABS
TEST DESCRIPTION
RESULT
UNITS
REFERENCE RANGE
Hemoglobin (Hb)
15.2
g/dL
13.8 - 17.2
Fasting Blood Glucose
108
mg/dL
70 - 99 (HIGH)
Total Cholesterol
215
mg/dL
< 200 (HIGH)
HDL (Good) Cholesterol
42
mg/dL
> 40
Serum Creatinine
0.9
mg/dL
0.7 - 1.3
CLINICAL OBSERVATIONS & NOTES:
fasting blood glucose at 108 mg/dL indicates a pre-diabetic state and warrants dietary intervention.
Page 1
"""


def test_offline_parses_column_style_table() -> None:
    """Multi-column lab tables (one field per line) parse into validated rows."""
    result = analyse_report_text_offline(COLUMN_TABLE_TEXT)
    by_name = {p["name"].lower(): p for p in result["parameters"]}
    assert len(result["parameters"]) == 5
    assert by_name["hemoglobin (hb)"]["status"] == "Normal"
    assert by_name["fasting blood glucose"]["status"] == "High"
    assert by_name["total cholesterol"]["status"] == "High"
    assert by_name["hdl (good) cholesterol"]["status"] == "Normal"
    assert by_name["serum creatinine"]["status"] == "Normal"
    # Narrative prose must not leak in as parameters or reference ranges.
    assert not any("warrants" in (p["reference_range"] or "") for p in result["parameters"])
    diabetes = result["disease_risks"]["diabetes"]
    assert diabetes["state"] == "requires_review"
    assert diabetes["level"] is None
    assert any("108" in e for e in diabetes["evidence"])
    assert result["disease_risks"]["ckd"]["state"] == "insufficient_data"
