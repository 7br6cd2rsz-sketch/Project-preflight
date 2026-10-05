"""Regression cases for service triage, preserved answers and guarded writes."""
import ast
import copy
import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import urlparse

import analysis_engine as engine


class TriageTests(unittest.TestCase):
    def test_runtime_scenarios(self):
        result = engine.self_check()
        self.assertEqual(result["passed"], 16)
        self.assertTrue(result["healthy"])
        self.assertFalse(result["external_model"])

    def test_hazard_has_priority_for_every_supported_brand_and_type(self):
        for t, brand in (("Laadpaal", "Easee"), ("Zonnepanelen", "SolarEdge"), ("Thuisbatterij", "GoodWe"), ("Elektro", "Onbekend")):
            for text in ("Rook en brandlucht uit het apparaat", "Geen productie, rook komt uit de kast", "Geen rook, maar wel vonken uit het apparaat"):
                with self.subTest(type=t, brand=brand, text=text):
                    result = engine.assess(t, text, {"manufacturer": brand, "app_online": "offline", "error_code": "Utility Loss"})
                    self.assertEqual(result["triage_level"], "veiligheidsreview")
                    self.assertEqual(result["service_route"], "site-required")
                    self.assertIn("veiligheidsreview", result["dispatch"])

    def test_negated_symptoms_do_not_create_incident(self):
        for text in ("Geen rook of brandlucht. App is offline.", "Geen rook, geen brandlucht. Laden werkt niet.", "Without smoke or sparks. Charger is offline.", "De lader rookt niet. App offline."):
            with self.subTest(text=text):
                result = engine.assess("Laadpaal", text, {"manufacturer": "Easee", "app_online": "offline"})
                self.assertEqual(result["fault_category"], "Offline / connectiviteit")

    def test_error_cannot_be_dismissed_by_offline_status(self):
        result = engine.assess("Laadpaal", "De lader is offline", {"manufacturer": "Easee", "app_online": "offline", "error_code": "RCD error", "led": "rood"})
        self.assertEqual(result["fault_category"], "Laderfout / foutstatus")
        self.assertEqual(result["triage_level"], "technische review")

    def test_safety_code_survives_unrelated_negation_and_monitoring(self):
        for code in ("18x86", "8x58", "2x19"):
            result = engine.assess("Zonnepanelen", "Geen productie en monitoring offline", {"manufacturer": "SolarEdge", "error_code": code, "monitoring_status": "offline"})
            self.assertEqual(result["fault_category"], "Isolatiefout")
            self.assertEqual(result["fault_confidence"], "hoog")

    def test_multiple_oem_faults_prioritize_safety_and_explain_conflict(self):
        result = engine.assess("Zonnepanelen", "Utility Loss en Isolation Failure", {"manufacturer": "GoodWe"})
        self.assertEqual(result["triage_level"], "veiligheidsreview")
        self.assertTrue(any("Meerdere foutfamilies" in w for w in result["warnings"]))
        self.assertNotEqual(result["fault_confidence"], "hoog")

    def test_unknown_code_is_not_a_confident_diagnosis(self):
        for brand in ("SolarEdge", "GoodWe"):
            result = engine.assess("Zonnepanelen", "Display toont een code", {"manufacturer": brand, "error_code": "XYZ-987"})
            self.assertEqual(result["fault_confidence"], "laag")
            self.assertEqual(result["triage_level"], "technische review")
            self.assertTrue(any("niet inhoudelijk herkend" in w for w in result["warnings"]))

    def test_explicit_no_error_does_not_create_alarm(self):
        for code in ("geen", "Geen foutcode", "none", "no error", 0):
            result = engine.assess("Zonnepanelen", "Opbrengst beoordelen", {"manufacturer": "GoodWe", "error_code": code})
            self.assertEqual(result["fault_category"], "Prestatie-/monitoringafwijking")
            self.assertNotIn("Foutmelding", result["missing"])

    def test_unknown_answers_and_keywords_are_not_complete_information(self):
        result = engine.assess("Zonnepanelen", "Productie en foutcode zijn onbekend", {"manufacturer": "GoodWe", "model": "none", "serial": "onbekend", "production": "onbekend", "error_code": "weet niet", "monitoring_status": "unknown"})
        for missing in ("Model", "Serienummer", "Productie", "Foutmelding", "Monitoringstatus"):
            self.assertIn(missing, result["missing"])
        self.assertLess(result["score"], 50)

    def test_numeric_zero_is_a_real_observation(self):
        result = engine.assess("Thuisbatterij", "Batterij laadt niet", {"manufacturer": "GoodWe", "soc": 0, "error_code": "geen"})
        self.assertNotIn("Laadpercentage batterij", result["missing"])
        self.assertEqual(result["fault_category"], "Batterijstoring — oorzaak nog open")
        result = engine.assess("Zonnepanelen", "Geen productie", {"manufacturer": "GoodWe", "production": 0})
        self.assertNotIn("Productie", result["missing"])

    def test_optional_firmware_and_photo_do_not_reduce_readiness(self):
        extra = {"manufacturer": "GoodWe", "model": "Testmodel", "serial": "TEST-000", "soc": 0, "error_code": "geen", "monitoring_status": "online"}
        result = engine.assess("Thuisbatterij", "Batterij laadt niet", extra)
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["missing"], [])
        result_with_photo = engine.assess("Thuisbatterij", "Batterij laadt niet", {**extra, "photo_present": False, "firmware": "onbekend"})
        self.assertEqual(result_with_photo["score"], result["score"])

    def test_out_of_range_percentage_is_rejected(self):
        for value in (-1, "101%", "120 procent"):
            with self.assertRaisesRegex(ValueError, "tussen 0 en 100"):
                engine.assess("Thuisbatterij", "Batterijstatus", {"soc": value})

    def test_non_numeric_battery_status_is_not_a_percentage(self):
        for value in ("laag", "ja", True):
            result = engine.assess("Thuisbatterij", "Batterij laadt niet", {"soc": value})
            self.assertIn("Laadpercentage batterij", result["missing"])

    def test_invalid_online_choice_is_not_a_known_connection(self):
        result = engine.assess("Laadpaal", "Laden lukt niet", {"manufacturer": "Easee", "app_online": "ja"})
        self.assertIn("App/cloudstatus", result["missing"])

    def test_conflicting_status_is_not_hidden(self):
        result = engine.assess("Laadpaal", "App is offline", {"manufacturer": "Easee", "app_online": "online"})
        self.assertTrue(any("spreken elkaar tegen" in w for w in result["warnings"]))
        self.assertNotEqual(result["fault_confidence"], "hoog")

    def test_zero_production_keeps_daylight_question(self):
        result = engine.assess("Zonnepanelen", "Omvormer toont 0 W in de nacht", {"manufacturer": "GoodWe", "production": "0 W"})
        self.assertTrue(any("overdag" in q for q in result["followup_questions"]))
        self.assertEqual(result["service_route"], "remote-first")

    def test_all_observations_survive_json_round_trip(self):
        extra = {"manufacturer": "Easee", "model": "Test", "serial": "TEST-SN", "led": "blauw", "error_code": "geen", "app_online": "online", "app_status": "Waiting for authorization", "vehicle_tested": "nee", "schedule_active": "ja", "equalizer_present": "nee", "last_successful": "Gisteren om 18:00", "photo_present": False}
        first = engine.assess("Laadpaal", "Het laden start niet", extra)
        row = json.loads(json.dumps({"type": "Laadpaal", "problem": "Het laden start niet", "manufacturer": "Easee", "model": "Test", "serial_no": "TEST-SN", **engine.case_fields(first)}))
        again = engine.for_case(row)
        self.assertEqual(again["observations"], engine.clean_extra(extra))
        for key in engine.PERSISTED:
            self.assertEqual(again[key], first[key], key)
        self.assertFalse(any("Ouder dossier" in w for w in again["warnings"]))

    def test_legacy_presence_tags_do_not_invent_observations_or_write(self):
        row = {"type": "Laadpaal", "problem": "Laden lukt niet", "manufacturer": "Easee", "model": "Test", "serial_no": "TEST", "facts": ["Klant & locatie", "Foutcode / screenshot", "LED/status", "Easee app/cloudstatus"], "score": 100}
        original = copy.deepcopy(row)
        result = engine.for_case(row)
        self.assertIn("Foutmelding", result["missing"])
        self.assertIn("LED/status", result["missing"])
        self.assertIn("App/cloudstatus", result["missing"])
        self.assertTrue(any("Ouder dossier" in w for w in result["warnings"]))
        self.assertEqual(row, original)

    def test_unrecognized_brand_has_no_claimed_integration(self):
        result = engine.assess("Laadpaal", "Laden start niet", {"manufacturer": "Ander merk"})
        self.assertEqual(result["knowledge_url"], "")
        self.assertEqual(result["api_targets"], [])
        self.assertTrue(result["warnings"])

    def test_invalid_input_fails_before_classification(self):
        for t, text, extra in (("Onbekend", "melding", {}), ("Laadpaal", "", {}), ("Laadpaal", "x" * 8001, {}), ("Laadpaal", "melding", []), ("Laadpaal", "melding", {"model": {"bad": "object"}}), ("Laadpaal", "melding", {"model": "x" * 501})):
            with self.subTest(type=t), self.assertRaises(ValueError):
                engine.assess(t, text, extra)


class FakeQuery:
    def __init__(self, case):
        self.case, self.update_payload, self.filters, self.calls = case, None, [], 0
    def table(self, name):
        assert name == "cases"
        return self
    def update(self, payload):
        self.update_payload = payload
        return self
    def eq(self, column, value):
        self.filters.append((column, value))
        return self
    def execute(self):
        self.calls += 1
        if not all(self.case.get(k) == v for k, v in self.filters):
            return SimpleNamespace(data=[])
        return SimpleNamespace(data=[{**self.case, **self.update_payload}])


class AnalysisEndpointTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(Path("cloud_server.py").read_text())
        nodes = [n for n in tree.body if getattr(n, "name", "") in ("Handler", "case_actor_in_organization", "organization_write_path", "can_access_case")]
        self.case = {"id": 7, "organization_id": 3, "type": "Laadpaal", "problem": "Laden lukt niet", "manufacturer": "Easee", "model": "TEST", "serial_no": "TEST-SN", "version": 2, "status": "Review", "assigned_to": 22, "source": "planner", "case_no": "WS-TEST-7", "facts": []}
        self.query = FakeQuery(self.case)
        self.audit = []
        self.ns = {"BaseHTTPRequestHandler": BaseHTTPRequestHandler, "urlparse": urlparse, "_set_org_context": lambda value: None, "_record_server_error": lambda *args: None, "analysis_engine": engine, "json": json, "get_case": lambda cid: self.case if cid == 7 else None, "current_org_id": lambda **kwargs: 3, "first": lambda r: r.data[0] if r.data else None, "enrich_case": lambda r: r, "sb": self.query, "now_iso": lambda: "2026-10-05T12:00:00Z", "create_audit": lambda *args: self.audit.append(args)}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "cloud_server.py", "exec"), self.ns)
        self.user = {"id": 1, "role": "planner", "organization_id": 3, "base_organization_id": 3}
        self.responses = []

    def request(self, path, body, user=True):
        handler = object.__new__(self.ns["Handler"])
        handler.path = path
        handler._check_origin = lambda: True
        handler._body = lambda: body
        def need(*args):
            if user is False:
                handler._json({"error": "unauthorized"}, 401)
                return None
            return self.user
        handler._need = need
        handler._json = lambda payload, status=200: self.responses.append((status, payload))
        handler.do_POST()
        return self.responses[-1]

    def test_preview_does_not_write_database_or_audit(self):
        status, result = self.request("/api/analysis-preview", {"type": "Laadpaal", "problem": "Rook uit lader", "extra": {"manufacturer": "Easee"}})
        self.assertEqual(status, 200)
        self.assertEqual(result["triage_level"], "veiligheidsreview")
        self.assertIsNone(self.query.update_payload)
        self.assertEqual(self.audit, [])

    def test_preview_requires_login_and_planning_role(self):
        status, _ = self.request("/api/analysis-preview", {}, user=False)
        self.assertEqual(status, 401)
        self.user["role"] = "technician"
        status, _ = self.request("/api/analysis-preview", {})
        self.assertEqual(status, 403)

    def test_preview_invalid_input_returns_400(self):
        status, _ = self.request("/api/analysis-preview", {"type": "Laadpaal", "problem": "melding", "extra": []})
        self.assertEqual(status, 400)
        self.assertIsNone(self.query.update_payload)

    def test_foreign_owner_cannot_rewrite_analysis(self):
        self.user.update(base_organization_id=1, is_platform_owner=True, role="admin")
        status, _ = self.request("/api/cases/7/analysis", {"version": 2})
        self.assertEqual(status, 403)
        self.assertIsNone(self.query.update_payload)

    def test_technician_cannot_rewrite_analysis(self):
        self.user["role"] = "technician"
        status, _ = self.request("/api/cases/7/analysis", {"version": 2})
        self.assertEqual(status, 403)
        self.assertIsNone(self.query.update_payload)

    def test_stale_or_invalid_version_does_not_write(self):
        for version, expected in ((1, 409), ("bad", 400)):
            status, _ = self.request("/api/cases/7/analysis", {"version": version})
            self.assertEqual(status, expected)
            self.assertIsNone(self.query.update_payload)

    def test_missing_case_is_not_accessible(self):
        status, _ = self.request("/api/cases/8/analysis", {"version": 2})
        self.assertEqual(status, 404)

    def test_analysis_write_is_scoped_and_preserves_operational_fields(self):
        extra = {"manufacturer": "Easee", "model": "TEST", "serial": "TEST-SN", "led": "blauw", "error_code": "geen", "app_online": "online", "app_status": "Waiting for authorization", "vehicle_tested": "nee"}
        status, row = self.request("/api/cases/7/analysis", {"version": 2, "problem": "Laden start niet", "extra": extra})
        self.assertEqual(status, 200)
        self.assertEqual(self.query.filters, [("organization_id", 3), ("id", 7), ("version", 2)])
        self.assertEqual(row["version"], 3)
        for key in ("id", "organization_id", "status", "assigned_to", "source", "case_no"):
            self.assertNotIn(key, self.query.update_payload)
            self.assertEqual(row[key], self.case[key])
        self.assertEqual(engine.observations_for_case(row), engine.clean_extra(extra))
        self.assertEqual(len(self.audit), 1)

    def test_atomic_conflict_does_not_report_success(self):
        def conflicting_execute():
            return SimpleNamespace(data=[])
        self.query.execute = conflicting_execute
        status, _ = self.request("/api/cases/7/analysis", {"version": 2, "problem": "melding", "extra": {"manufacturer": "Easee"}})
        self.assertEqual(status, 409)
        self.assertEqual(self.audit, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
