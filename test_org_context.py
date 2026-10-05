"""Verify case-write guards without contacting a database or using credentials."""
import ast
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import subprocess
import unittest
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
TREE = ast.parse((ROOT / "cloud_server.py").read_text())
NODES = [n for n in TREE.body if getattr(n, "name", "") in ("case_actor_in_organization", "organization_write_path", "Handler")]
NS = {
    "BaseHTTPRequestHandler": BaseHTTPRequestHandler,
    "urlparse": urlparse,
    "_set_org_context": lambda value: None,
    "_record_server_error": lambda *args: None,
}
exec(compile(ast.Module(body=NODES, type_ignores=[]), "cloud_server.py", "exec"), NS)


class OrganizationContextTests(unittest.TestCase):
    def test_member_and_home_owner_can_write(self):
        for role in ("admin", "planner", "technician"):
            with self.subTest(role=role):
                self.assertTrue(NS["case_actor_in_organization"]({"organization_id": 3, "base_organization_id": 3, "role": role}))
        self.assertTrue(NS["case_actor_in_organization"]({"organization_id": 1, "base_organization_id": 1, "is_platform_owner": True}))

    def test_foreign_context_and_missing_organization_cannot_write(self):
        self.assertFalse(NS["case_actor_in_organization"]({"organization_id": 3, "base_organization_id": 1, "is_platform_owner": True}))
        self.assertFalse(NS["case_actor_in_organization"]({}))

    def test_http_writes_reject_before_any_database_work(self):
        routes = [
            ("do_POST", "/api/cases"),
            ("do_POST", "/api/cases/2/notes"),
            ("do_POST", "/api/cases/2/attachments"),
            ("do_POST", "/api/cases/2/outcome"),
            ("do_PATCH", "/api/cases/2"),
        ]
        for method, path in routes:
            with self.subTest(method=method, path=path):
                handler = object.__new__(NS["Handler"])
                handler.path = path
                handler._check_origin = lambda: True
                handler._body = lambda: {}
                handler._need = lambda: {"id": 1, "organization_id": 3, "base_organization_id": 1, "is_platform_owner": True}
                responses = []
                handler._json = lambda data, status=200: responses.append((status, data))
                getattr(handler, method)()
                self.assertEqual(responses[0][0], 403)
                self.assertEqual(responses[0][1]["code"], "organization_member_required")

    def test_frontend_preserves_member_access_and_explains_owner_context(self):
        script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const src=fs.readFileSync('app.js','utf8');
const helpers=src.slice(src.indexOf('function caseWriteAllowed'),src.indexOf('function toast('));
const warnings=[]; const ctx={me:{organization_id:3,base_organization_id:3},toast:(...args)=>warnings.push(args)};
vm.createContext(ctx);vm.runInContext(helpers,ctx);
assert.equal(ctx.requireCaseWrite(),true);assert.equal(warnings.length,0);
ctx.me={organization_id:3,base_organization_id:1,is_platform_owner:true};
assert.equal(ctx.requireCaseWrite(),false);assert.equal(warnings.length,1);
assert.equal(warnings[0][1],'warn');assert.ok(warnings[0][0].includes('teamaccount'));
ctx.me={organization_id:1};assert.equal(ctx.requireCaseWrite(),true);
'''
        result = subprocess.run(["node", "-e", script], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
