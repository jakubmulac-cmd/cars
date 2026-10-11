import copy
import json
import os
import secrets
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from fleet.db import collection, connect, migrate
from fleet.importer import commit, stage, validate
from fleet.main import app

SNAPSHOT = os.environ.get("FLEET_TEST_SNAPSHOT")


class IsolatedDatabase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"FLEET_DATA_DIR": self.temp.name})
        self.env.start()
        migrate()
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()
        self.password = secrets.token_urlsafe(24)

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        self.env.stop()
        self.temp.cleanup()

    def login(self):
        self.assertEqual(self.client.post("/api/auth/setup", json={"password": self.password}).status_code, 200)


class AuthenticationTests(IsolatedDatabase):
    def test_private_endpoints_require_authentication(self):
        for endpoint in ("/api/dashboard", "/api/export", "/api/vehicles/V001", "/api/connectors"):
            self.assertEqual(self.client.get(endpoint).status_code, 401)

    def test_setup_login_logout_and_password_hash(self):
        self.assertEqual(self.client.post("/api/auth/setup", json={"password": "short"}).status_code, 422)
        self.login()
        self.assertEqual(self.client.get("/api/dashboard").status_code, 200)
        cookie = self.client.cookies.get("fleet_session")
        self.assertTrue(cookie)
        with connect() as con:
            self.assertNotIn(self.password, con.execute("SELECT password_hash FROM users").fetchone()[0])
            self.assertNotEqual(cookie, con.execute("SELECT token_hash FROM sessions").fetchone()[0])
        self.assertEqual(self.client.post("/api/auth/setup", json={"password": self.password}).status_code, 409)
        self.client.post("/api/auth/logout", json={})
        self.assertEqual(self.client.get("/api/export").status_code, 401)
        self.assertEqual(self.client.post("/api/auth/login", json={"password": self.password}).status_code, 200)

    def test_cross_site_request_rejected(self):
        response = self.client.post("/api/auth/setup", json={"password": self.password}, headers={"Origin": "https://unrelated.example"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.client.get("/api/auth/status").json()["configured"])

    def test_login_rate_limit(self):
        self.login()
        self.client.post("/api/auth/logout", json={})
        for _ in range(5):
            self.assertEqual(self.client.post("/api/auth/login", json={"password": "incorrect"}).status_code, 401)
        self.assertEqual(self.client.post("/api/auth/login", json={"password": "incorrect"}).status_code, 429)

    def test_page_security_headers_and_no_embedded_data(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])
        self.assertNotIn('"vehicles":', response.text)

    def test_unknown_host_rejected(self):
        self.assertEqual(self.client.get("/", headers={"Host": "unrelated.example"}).status_code, 400)


@unittest.skipUnless(SNAPSHOT, "Pro kontrolu skutečného snímku nastavte FLEET_TEST_SNAPSHOT; soukromá data nejsou v Gitu")
class SnapshotTests(IsolatedDatabase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = json.loads(Path(SNAPSHOT).read_text())

    def import_snapshot(self):
        return commit(stage(self.snapshot)["id"])

    def test_schema_references_and_financial_totals(self):
        report = validate(self.snapshot)
        self.assertEqual(report["counts"]["vehicles"], 31)
        self.assertEqual({key: Decimal(value) for key, value in report["totals"].items()},
                         {key: Decimal(value) for key, value in {"q4":"53847", "retro":"9475", "new":"63322", "historical":"106230", "triumph":"19818"}.items()})

    def test_idempotence_and_full_source_preservation(self):
        first = self.import_snapshot()
        second = self.import_snapshot()
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        with connect() as con:
            self.assertEqual(len(collection(con, "vehicles")), 31)
            self.assertEqual(len(collection(con, "premium_lines")), 14)
            self.assertEqual(len(collection(con, "odometer_readings")), 105)
            self.assertEqual(len(collection(con, "rides")), 63)
            self.assertEqual(len(collection(con, "source_observations")), 2885)
            self.assertEqual({x['observation_id']:x for x in collection(con, "source_observations")}, {x['observation_id']:x for x in self.snapshot['source_observations']})

    def test_invalid_reference_and_duplicate_rejected(self):
        broken = copy.deepcopy(self.snapshot)
        broken["premium_lines"][0]["asset_id"] = "V999"
        with self.assertRaises(ValueError):
            stage(broken)
        broken = copy.deepcopy(self.snapshot)
        broken["vehicles"][1]["uuid"] = broken["vehicles"][0]["uuid"]
        with self.assertRaises(ValueError):
            stage(broken)
        with connect() as con:
            self.assertEqual(len(collection(con,"vehicles")), 0)

    def test_interrupted_import_rolls_back(self):
        staged = stage(self.snapshot)
        import fleet.importer as importer
        original = importer.encode
        calls = 0
        def fail(value):
            nonlocal calls
            calls += 1
            if calls == 10:
                raise RuntimeError("Simulated interruption")
            return original(value)
        with patch.object(importer,"encode",side_effect=fail):
            with self.assertRaises(RuntimeError):
                commit(staged['id'])
        with connect() as con:
            self.assertEqual(len(collection(con,"vehicles")), 0)
        commit(staged['id'])
        with connect() as con:
            self.assertEqual(len(collection(con,"vehicles")), 31)

    def test_critical_unknowns_and_distinct_identities(self):
        self.import_snapshot()
        self.login()
        data = self.client.get('/api/dashboard').json()
        vehicles = {x['asset_id']:x for x in data['vehicles']}
        self.assertNotEqual(vehicles['V001']['vin'],vehicles['V029']['vin'])
        self.assertNotEqual(vehicles['V007']['vin'],vehicles['V007']['source_vin'])
        self.assertIsNone(vehicles['V019']['rz'])
        self.assertEqual(vehicles['V027']['asset_state'],'Plánovaný nákup')
        self.assertEqual(vehicles['V001']['last_reading']['km'],90200)
        self.assertEqual(vehicles['V001']['last_reading']['date'],'2026-01-05')
        self.assertEqual(data['counts']['candidates'],12)
        self.assertIsNone(data['metadata']['billing_reconciliation']['insurer_settlement_confirmed'])
        golf = self.client.get('/api/vehicles/V007').json()
        self.assertIsNone(golf['operations'][0]['engine_ccm'])
        for policy in data['vehicles']:
            insurance = policy.get('insurance')
            if insurance and insurance.get('period_semantics') == 'billing_period':
                self.assertIsNone(insurance['contract_end_confirmed'])

    def test_manual_reading_and_task_assignment_survive_import(self):
        self.import_snapshot()
        self.login()
        issue = self.snapshot['issues'][0]
        self.assertEqual(self.client.patch(f"/api/issues/{issue['issue_id']}",json={"assigned_to":"Správce"}).status_code,200)
        self.assertEqual(self.client.post('/api/vehicles/V001/readings',json={"km":"93000.5","date":"2026-10-10","evidence":"Doložená fotografie tachometru"}).status_code,200)
        self.import_snapshot()
        vehicle = self.client.get('/api/vehicles/V001').json()
        self.assertEqual(vehicle['vehicle']['last_reading']['km'],93000.5)
        self.assertEqual(len(vehicle['manual_readings']),1)
        dashboard = self.client.get('/api/dashboard').json()
        current = next(i for i in dashboard['issues'] if i['issue_id'] == issue['issue_id'])
        self.assertEqual(current['assigned_to'],'Správce')

    def test_critical_closure_requires_insurer_evidence(self):
        self.import_snapshot()
        self.login()
        p0 = next(i for i in self.snapshot['issues'] if i['priority'] == 'P0')
        endpoint = f"/api/issues/{p0['issue_id']}"
        self.assertEqual(self.client.patch(endpoint,json={"close":True}).status_code,422)
        wrong = {"close":True,"evidence_type":"supporting_document","evidence_title":"Oznámení","evidence_url":"https://example.com/document","evidence_date":"2026-10-11","closure_note":"Pouze zpráva o odeslání platby"}
        self.assertEqual(self.client.patch(endpoint,json=wrong).status_code,422)
        wrong['evidence_type'] = 'insurer_confirmation'
        self.assertEqual(self.client.patch(endpoint,json=wrong).status_code,200)
        with connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM audit_log WHERE action='issue_closed_with_manual_evidence'").fetchone()[0],1)

    def test_invalid_reading_rejected(self):
        self.import_snapshot()
        self.login()
        for km in ('NaN','-1','Infinity'):
            self.assertEqual(self.client.post('/api/vehicles/V001/readings',json={"km":km,"date":"2026-10-10","evidence":"Doložený údaj"}).status_code,422)

    def test_full_private_export_and_disabled_connectors(self):
        self.import_snapshot()
        self.login()
        exported = self.client.get('/api/export').json()
        self.assertEqual(len(exported['sources']),21)
        self.assertEqual(len(exported['source_observations']),2885)
        self.assertTrue(all(c['state'] == 'disabled' for c in self.client.get('/api/connectors').json()))


if __name__ == '__main__':
    unittest.main()
