"""Organisation, account and support boundaries through real HTTP handlers.

All accounts, customers and messages are synthetic and remain in memory.
"""
import unittest
import test_refinement_workflow as fixture


class CommandWorkspaceTests(unittest.TestCase):
    setUpClass=classmethod(fixture.RefinementWorkflowTests.setUpClass.__func__)
    tearDownClass=classmethod(fixture.RefinementWorkflowTests.tearDownClass.__func__)
    setUp=fixture.RefinementWorkflowTests.setUp
    request=fixture.RefinementWorkflowTests.request
    client=fixture.RefinementWorkflowTests.client

    def test_new_design_assets_are_served_and_private_sources_are_not(self):
        anonymous=self.client()
        for path,kind in (("/command-v210.css","text/css"),("/command-v210.js","javascript")):
            status,content,headers=self.request(anonymous,path)
            self.assertEqual(status,200)
            self.assertIn(kind,headers["Content-Type"])
            self.assertGreater(len(content),1000)
            self.assertIn("script-src 'self'",headers["Content-Security-Policy"])
        for path in ("/cloud_server.py","/.env","/test_command_workspace.py"):
            self.assertEqual(self.request(anonymous,path)[0],404)

    def test_customer_persists_and_links_to_a_case_in_its_company(self):
        planner=self.client(3)
        status,customer,_=self.request(planner,"/api/customers",{"name":"TEST Klant","email":"test@test.invalid","city":"Testplaats"})
        self.assertEqual(status,201)
        self.assertEqual(self.request(planner,"/api/customers")[1],[customer])
        status,case,_=self.request(planner,"/api/cases",{"customer_id":customer["id"],"customer":customer["name"],"email":customer["email"],"type":"Laadpaal","problem":"Laden start niet","extra":{"manufacturer":"Easee"}})
        self.assertEqual(status,201)
        self.assertEqual(case["customer_id"],customer["id"])
        self.assertEqual(case["email"],customer["email"])

    def test_customers_are_private_between_companies_and_roles(self):
        planner=self.client(3)
        _,customer,_=self.request(planner,"/api/customers",{"name":"TEST Klant"})
        foreign=self.client(6);tech=self.client(4)
        self.assertEqual(self.request(foreign,"/api/customers")[1],[])
        self.assertEqual(self.request(foreign,f'/api/customers/{customer["id"]}',{"version":1,"name":"Overnemen"},"PATCH")[0],404)
        self.assertEqual(self.request(tech,"/api/customers")[0],403)
        self.assertEqual(self.request(tech,"/api/customers",{"name":"Nieuwe klant"})[0],403)
        self.assertEqual(self.request(self.client(),"/api/customers")[0],401)
        self.assertEqual(self.request(foreign,"/api/cases",{"customer_id":customer["id"],"type":"Laadpaal","problem":"test"})[0],404)

    def test_archive_restore_and_conflicts_preserve_customer_data(self):
        planner=self.client(3)
        _,c,_=self.request(planner,"/api/customers",{"name":"TEST Klant","notes":"Bewaren"})
        path=f'/api/customers/{c["id"]}'
        status,archived,_=self.request(planner,path,{"version":1,"active":False},"PATCH")
        self.assertEqual(status,200);self.assertFalse(archived["active"])
        self.assertEqual(self.request(planner,path,{"version":1,"name":"Oude versie"},"PATCH")[0],409)
        status,restored,_=self.request(planner,path,{"version":2,"active":True},"PATCH")
        self.assertEqual(status,200);self.assertEqual(restored["notes"],"Bewaren");self.assertTrue(restored["active"])

    def test_customer_input_rejects_invalid_and_unscoped_fields(self):
        planner=self.client(3)
        for payload in ({"name":""},{"name":"Test","email":"ongeldig"},{"name":"Test","organization_id":3},{"name":"Test","notes":"x"*3001}):
            self.assertEqual(self.request(planner,"/api/customers",payload)[0],400)
        self.assertEqual(self.db.rows.get("customer_records",[]),[])

    def test_company_admin_manages_own_team_and_revokes_sessions(self):
        admin=self.client(2);planner=self.client(3)
        status,result,_=self.request(admin,"/api/accounts/3",{"display_name":"TEST Nieuwe naam","role":"technician"},"PATCH")
        self.assertEqual(status,200);self.assertNotIn("password_hash",result)
        self.assertEqual(self.request(planner,"/api/me")[0],401)
        self.assertEqual(self.request(admin,"/api/accounts/6",{"active":False},"PATCH")[0],404)
        self.assertEqual(self.request(self.client(4),"/api/accounts/5",{"active":False},"PATCH")[0],403)

    def test_admin_cannot_remove_own_access_or_grant_platform_ownership(self):
        admin=self.client(2)
        for payload in ({"role":"planner"},{"active":False},{"is_platform_owner":True},{"active":"false"}):
            self.assertEqual(self.request(admin,"/api/accounts/2",payload,"PATCH")[0],400)

    def test_saving_same_role_keeps_the_admin_session(self):
        admin=self.client(2)
        self.assertEqual(self.request(admin,"/api/accounts/2",{"display_name":"TEST beheerder","role":"admin","active":True},"PATCH")[0],200)
        status,profile,_=self.request(admin,"/api/me")
        self.assertEqual(status,200)
        self.assertEqual(profile["display_name"],"TEST beheerder")

    def test_company_admin_cannot_reset_platform_owner_password(self):
        self.db.rows["users"].append({**self.db.rows["users"][0],"id":20,"organization_id":2,"email":"test-owner@test.invalid","is_platform_owner":True})
        admin=self.client(2)
        for path,payload in (("/api/accounts/20/reset-password",{"new_password":self.password}),("/api/accounts/20/send-reset-link",{})):
            with self.subTest(path=path):self.assertEqual(self.request(admin,path,payload)[0],403)

    def test_team_creation_does_not_disclose_other_company_account(self):
        admin=self.client(2)
        status,result,_=self.request(admin,"/api/accounts",{"display_name":"TEST","email":"actor6@test.invalid","role":"planner","password":self.password})
        self.assertEqual(status,400);self.assertNotIn("user",result)
        status,result,_=self.request(admin,"/api/accounts",{"display_name":"TEST nieuw","email":"new@test.invalid","role":"planner","password":self.password})
        self.assertEqual(status,201);self.assertEqual(result["user"]["organization_id"],2)
        self.assertFalse(result["user"]["is_platform_owner"])

    def test_owner_support_context_can_read_but_not_manage_company(self):
        owner=self.client(1)
        self.assertEqual(self.request(owner,"/api/owner/context",{"organization_id":2})[0],200)
        for path,payload,method in (("/api/customers",{"name":"Test"},"POST"),("/api/accounts",{},"POST"),("/api/accounts/3",{"active":False},"PATCH"),("/api/settings",{"company_name":"Overnemen"},"PATCH"),("/api/onboarding",{},"POST")):
            with self.subTest(path=path):self.assertEqual(self.request(owner,path,payload,method)[0],403)
        self.assertEqual(self.request(owner,"/api/customers")[0],200)

    def test_planner_cannot_provision_team_through_setup(self):
        planner=self.client(3)
        self.assertEqual(self.request(planner,"/api/onboarding",{"company_name":"Test","enabled_service_types":["Laadpaal"]})[0],403)
        self.assertEqual(self.request(planner,"/api/settings",{"brand_name":"Test"},"PATCH")[0],403)

    def test_invalid_company_creation_has_no_partial_company_write(self):
        owner=self.client(1);before=len(self.db.rows["organizations"])
        status,_,_=self.request(owner,"/api/owner/organizations",{"name":"Test nieuw","slug":"test-new"})
        self.assertEqual(status,400);self.assertEqual(len(self.db.rows["organizations"]),before)

    def test_support_submissions_are_scoped_and_idempotent(self):
        tech=self.client(4);payload={"subject":"TEST melding","description":"Opslaan lukt in deze test niet.","category":"technical","request_key":"isolated-test-request-123"}
        status,ticket,_=self.request(tech,"/api/support",payload)
        self.assertEqual(status,201);self.assertNotIn("fingerprint",ticket)
        self.assertEqual(self.request(tech,"/api/support",payload)[0],200)
        self.assertEqual(len(self.db.rows["support_tickets"]),1)
        self.assertEqual(len(self.request(tech,"/api/support")[1]),1)
        self.assertEqual(self.request(self.client(5),"/api/support")[1],[])
        self.assertEqual(self.request(self.client(6),"/api/support")[1],[])
        self.assertEqual(len(self.request(self.client(2),"/api/support")[1]),1)
        self.assertEqual(self.request(self.client(3),"/api/owner/support")[0],403)

    def test_owner_can_answer_support_without_company_impersonation(self):
        client=self.client(3);owner=self.client(1)
        _,ticket,_=self.request(client,"/api/support",{"subject":"TEST vraag","description":"Hoe werkt deze testomgeving?","category":"question","request_key":"isolated-test-request-456"})
        self.assertEqual(len(self.request(owner,"/api/owner/support")[1]),1)
        path=f'/api/owner/support/{ticket["id"]}'
        self.assertEqual(self.request(client,path,{"version":1,"status":"resolved","resolution":"test"},"PATCH")[0],403)
        self.assertEqual(self.request(owner,path,{"version":1,"status":"resolved"},"PATCH")[0],400)
        status,answered,_=self.request(owner,path,{"version":1,"status":"resolved","resolution":"TEST uitleg bij oplossing"},"PATCH")
        self.assertEqual(status,200);self.assertEqual(answered["status"],"resolved")
        self.assertEqual(self.request(client,"/api/support")[1][0]["resolution"],"TEST uitleg bij oplossing")
        self.assertEqual(self.request(owner,path,{"version":1,"status":"open"},"PATCH")[0],409)


if __name__=="__main__":unittest.main()
