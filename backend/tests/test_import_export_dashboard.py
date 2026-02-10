from __future__ import annotations

from fastapi.testclient import TestClient


def test_dashboard_quality_and_pending(client: TestClient, auth_headers):
    headers = auth_headers("qa")

    quality = client.get("/api/v1/dashboard/quality", params={"version_key": "v1.0.0"}, headers=headers)
    assert quality.status_code == 200
    assert "execution_rate" in quality.json()["data"]

    pending = client.get("/api/v1/dashboard/issues/pending", params={"version_key": "v1.0.0"}, headers=headers)
    assert pending.status_code == 200
    assert isinstance(pending.json()["data"], list)


def test_cases_import_validate_and_export(client: TestClient, auth_headers):
    headers = auth_headers("qa")

    csv_body = "case_key,title,module,steps,expected,tags\nTC-900,导入用例,导入模块,步骤,预期,导入\n"
    validate_resp = client.post(
        "/api/v1/cases:import",
        params={"validate_only": "true"},
        files={"file": ("cases.csv", csv_body, "text/csv")},
        headers=headers,
    )
    assert validate_resp.status_code == 200
    assert validate_resp.json()["data"]["valid_rows"] == 1

    import_resp = client.post(
        "/api/v1/cases:import",
        params={"mode": "upsert", "validate_only": "false"},
        files={"file": ("cases.csv", csv_body, "text/csv")},
        headers=headers,
    )
    assert import_resp.status_code == 200

    export_resp = client.get(
        "/api/v1/cases:export",
        params={"version_key": "v1.0.0", "format": "xlsx"},
        headers=headers,
    )
    assert export_resp.status_code == 200
    assert export_resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
