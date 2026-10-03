#!/usr/bin/env python3
"""
Project Preflight Cloud v1
Stateless Python web/API service backed by Supabase Postgres + private Storage.

The Supabase secret key is SERVER-ONLY. It must never be added to static files.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import mimetypes
import os
import re
import secrets
import sys
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta, date
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from supabase import create_client, Client
import httpx

import server as core

ROOT = Path(__file__).resolve().parent
STATIC = (ROOT / "static") if (ROOT / "static").is_dir() else ROOT

APP_NAME = "Project Preflight"
APP_VERSION = "1.0.4-cloud-pilot"
APP_BUILD = "2026-10-03"
BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "preflight-attachments")
MAX_BODY = 7 * 1024 * 1024
SESSION_HOURS = int(os.environ.get("SESSION_HOURS", "12"))
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "1") not in ("0","false","False")
PORT = int(os.environ.get("PORT", "10000"))

# Lightweight, process-local abuse protection for the single-instance pilot.
# Keys are salted hashes of client IP + scope; raw IPs are not retained.
_RATE_LOCK = threading.Lock()
_RATE_STATE = {}
_RATE_SALT = secrets.token_bytes(16)

def _rate_allow(client_ip: str, scope: str, limit: int, window_seconds: int):
    now = int(time.time())
    bucket = now // window_seconds
    digest = hashlib.sha256(_RATE_SALT + f"{client_ip}|{scope}".encode()).hexdigest()
    with _RATE_LOCK:
        current = _RATE_STATE.get(digest)
        if not current or current[0] != bucket:
            _RATE_STATE[digest] = (bucket, 1)
            if len(_RATE_STATE) > 5000:
                stale = [k for k, (b, _) in _RATE_STATE.items() if b < bucket - 1]
                for k in stale[:2500]:
                    _RATE_STATE.pop(k, None)
            return True, 0
        if current[1] >= limit:
            retry_after = max(1, window_seconds - (now % window_seconds))
            return False, retry_after
        _RATE_STATE[digest] = (bucket, current[1] + 1)
        return True, 0

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY", "")
if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_SECRET_KEY are required.", file=sys.stderr)
    sys.exit(2)

_sb_local = threading.local()

def _get_supabase_client() -> Client:
    client = getattr(_sb_local, "client", None)
    if client is None:
        client = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)
        _sb_local.client = client
    return client

def _reset_supabase_client():
    # Drop the thread-local client after a transient transport failure.
    # A fresh client gets created lazily on the next Supabase call.
    if hasattr(_sb_local, "client"):
        try:
            delattr(_sb_local, "client")
        except Exception:
            _sb_local.client = None


class _SupabaseProxy:
    def __getattr__(self, name):
        return getattr(_get_supabase_client(), name)

sb = _SupabaseProxy()

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def sha_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def resp_data(resp):
    return getattr(resp, "data", None) or []

def first(resp):
    data = resp_data(resp)
    return data[0] if data else None

def get_setting(key, default=None):
    row = first(sb.table("settings").select("value").eq("key", key).limit(1).execute())
    return row["value"] if row else default

def set_setting(key, value):
    sb.table("settings").upsert({"key": key, "value": str(value)}, on_conflict="key").execute()

def setting_json(key, default):
    raw = get_setting(key)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default

def setting_float(key, default=0.0):
    try:
        return float(get_setting(key, default))
    except Exception:
        return float(default)

def economic_assumptions():
    return {
        "baseline_planner_minutes": setting_float("baseline_planner_minutes", 13),
        "planner_hourly_cost": setting_float("planner_hourly_cost", 40),
        "technician_hourly_cost": setting_float("technician_hourly_cost", 55),
        "avg_site_visit_minutes": setting_float("avg_site_visit_minutes", 90),
        "avg_roundtrip_km": setting_float("avg_roundtrip_km", 35),
        "cost_per_km": setting_float("cost_per_km", .35),
        "software_monthly_cost": setting_float("software_monthly_cost", 299),
        "monthly_case_volume": setting_float("monthly_case_volume", 150),
    }

def create_audit(case_id, user_id, action, detail=""):
    sb.table("audit").insert({
        "case_id": case_id,
        "user_id": user_id,
        "action": action,
        "detail": detail,
        "created_at": now_iso(),
    }).execute()

def bootstrap():
    # Insert required default settings.
    defaults = {
        "intake_token": secrets.token_urlsafe(24),
        "company_name": "Project Preflight Pilot",
        "onboarding_complete": "0",
        "enabled_service_types": json.dumps(["Laadpaal","Zonnepanelen","Thuisbatterij","Elektro"], ensure_ascii=False),
        "enabled_brands": json.dumps({
            "Laadpaal":["Easee","Alfen","Wallbox","Zaptec","Anders/onbekend"],
            "Zonnepanelen":["SolarEdge","GoodWe","Growatt","SMA","Enphase","Anders/onbekend"],
            "Thuisbatterij":["SolarEdge","GoodWe","BYD","Huawei","Tesla","Anders/onbekend"],
            "Elektro":["Anders/onbekend"]
        }, ensure_ascii=False),
        "baseline_planner_minutes":"13",
        "planner_hourly_cost":"40",
        "technician_hourly_cost":"55",
        "avg_site_visit_minutes":"90",
        "avg_roundtrip_km":"35",
        "cost_per_km":"0.35",
        "software_monthly_cost":"299",
        "monthly_case_volume":"150",
        "brand_name":"Project Preflight",
        "brand_accent":"#62d0ff",
        "support_email":"",
        "customer_portal_title":"Service-intake",
    }
    existing = {r["key"] for r in resp_data(sb.table("settings").select("key").execute())}
    missing = [{"key":k,"value":v} for k,v in defaults.items() if k not in existing]
    if missing:
        sb.table("settings").insert(missing).execute()

    # First administrator is created only when user table is empty and env vars exist.
    users = resp_data(sb.table("users").select("id").limit(1).execute())
    if not users:
        email = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
        password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")
        name = os.environ.get("BOOTSTRAP_ADMIN_NAME", "Administrator").strip() or "Administrator"
        if email and password:
            if len(password) < 12:
                raise RuntimeError("BOOTSTRAP_ADMIN_PASSWORD must contain at least 12 characters")
            sb.table("users").insert({
                "email":email,
                "display_name":name,
                "role":"admin",
                "password_hash":core.hash_password(password),
                "active":True,
                "created_at":now_iso()
            }).execute()
            print(f"Bootstrap admin created for {email}. Remove/rotate BOOTSTRAP_ADMIN_PASSWORD after first login.")
        else:
            print("WARNING: no users exist. Set BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD in Render.")

def find_user_by_email(email):
    return first(sb.table("users").select("*").eq("email", email.lower().strip()).limit(1).execute())

def find_user(uid):
    return first(sb.table("users").select("id,email,display_name,role,active,created_at").eq("id", uid).limit(1).execute())

def create_session(user_id):
    token = secrets.token_urlsafe(40)
    expires = datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)
    sb.table("sessions").insert({
        "token_hash": sha_token(token),
        "user_id": user_id,
        "expires_at": expires.isoformat(),
        "created_at": now_iso()
    }).execute()
    return token

def delete_session(token):
    if token:
        sb.table("sessions").delete().eq("token_hash", sha_token(token)).execute()

def user_from_token(token):
    if not token:
        return None
    row = first(sb.table("sessions").select("user_id,expires_at").eq("token_hash", sha_token(token)).limit(1).execute())
    if not row:
        return None
    try:
        exp = datetime.fromisoformat(row["expires_at"].replace("Z","+00:00"))
        if exp <= datetime.now(timezone.utc):
            sb.table("sessions").delete().eq("token_hash", sha_token(token)).execute()
            return None
    except Exception:
        return None
    u = find_user(row["user_id"])
    if not u or not u.get("active"):
        return None
    return u

def public_config():
    return {
        "company": get_setting("company_name","Project Preflight Pilot"),
        "enabled_service_types": setting_json("enabled_service_types",["Laadpaal","Zonnepanelen","Thuisbatterij","Elektro"]),
        "enabled_brands": setting_json("enabled_brands",{}),
        "brand_name": get_setting("brand_name","Project Preflight"),
        "brand_accent": get_setting("brand_accent","#62d0ff"),
        "support_email": get_setting("support_email",""),
        "customer_portal_title": get_setting("customer_portal_title","Service-intake"),
    }

def onboarding_payload():
    return {
        "complete": get_setting("onboarding_complete","0") == "1",
        "company_name": get_setting("company_name","Project Preflight Pilot"),
        "enabled_service_types": setting_json("enabled_service_types",["Laadpaal","Zonnepanelen","Thuisbatterij","Elektro"]),
        "enabled_brands": setting_json("enabled_brands",{}),
        "assumptions": economic_assumptions(),
        "branding":{
            "brand_name":get_setting("brand_name","Project Preflight"),
            "brand_accent":get_setting("brand_accent","#62d0ff"),
            "support_email":get_setting("support_email",""),
            "customer_portal_title":get_setting("customer_portal_title","Service-intake"),
        },
        "intake_token":get_setting("intake_token"),
    }

def safe_filename(name):
    name = Path(name or "attachment").name
    name = re.sub(r"[^A-Za-z0-9._-]+","_",name)[:120]
    return name or "attachment"

def get_case(cid):
    return first(sb.table("cases").select("*").eq("id", cid).limit(1).execute())

def can_access_case(user, case):
    if not case:
        return False
    if user["role"] in ("admin","planner"):
        return True
    return case.get("assigned_to") == user["id"]

def visible_cases(user):
    q = sb.table("cases").select("*").order("updated_at", desc=True)
    if user["role"] == "technician":
        q = q.eq("assigned_to", user["id"])
    rows = resp_data(q.execute())
    return rows

def enrich_case(c):
    if not c:
        return c
    if c.get("assigned_to"):
        u=find_user(c["assigned_to"])
        c["assigned_name"]=u["display_name"] if u else None
    return c

def calculate_metrics():
    cases = resp_data(sb.table("cases").select("*").execute())
    outcomes = [c for c in cases if c.get("outcome_recorded_at")]
    total=len(cases)
    customer_intakes=sum(1 for c in cases if c.get("source")=="customer")
    intake=[float(c["intake_seconds"]) for c in cases if c.get("intake_seconds") is not None]
    complete=sum(1 for c in cases if not (c.get("missing") or []))
    scheduled=sum(1 for c in cases if c.get("scheduled_at"))
    ftf=sum(1 for c in outcomes if c.get("outcome_resolved_first_visit"))
    second=sum(1 for c in outcomes if c.get("outcome_second_visit_required"))
    preventable=sum(1 for c in outcomes if c.get("outcome_second_visit_required") and c.get("outcome_preventable"))
    remote=sum(1 for c in outcomes if c.get("outcome_remote_resolved"))
    econ=calculate_economics(cases)
    n=len(outcomes)
    return {
        "total":total,
        "customer_intakes":customer_intakes,
        "avg_intake_seconds":round(sum(intake)/len(intake),1) if intake else 0,
        "complete_pct":round(100*complete/max(1,total),1),
        "scheduled_pct":round(100*scheduled/max(1,total),1),
        "outcomes":n,
        "first_time_fix_pct":round(100*ftf/max(1,n),1),
        "second_visit_pct":round(100*second/max(1,n),1),
        "preventable_second_visit_pct":round(100*preventable/max(1,second),1) if second else 0,
        "remote_resolved_pct":round(100*remote/max(1,n),1),
        "economics":econ,
    }

def calculate_economics(cases=None):
    cases = cases if cases is not None else resp_data(sb.table("cases").select("*").execute())
    outcomes=[c for c in cases if c.get("outcome_recorded_at")]
    a=economic_assumptions()
    measured=[float(c["outcome_planner_minutes"]) for c in outcomes if c.get("outcome_planner_minutes") is not None]
    saved=sum(max(0.0,a["baseline_planner_minutes"]-m) for m in measured)
    remote=sum(1 for c in outcomes if c.get("outcome_remote_resolved"))
    second=sum(1 for c in outcomes if c.get("outcome_second_visit_required"))
    preventable=sum(1 for c in outcomes if c.get("outcome_second_visit_required") and c.get("outcome_preventable"))
    visit=(a["avg_site_visit_minutes"]/60*a["technician_hourly_cost"])+(a["avg_roundtrip_km"]*a["cost_per_km"])
    planner_value=saved/60*a["planner_hourly_cost"]
    n=len(outcomes)
    avg_saved=saved/len(measured) if measured else 0
    remote_rate=remote/n if n else 0
    preventable_rate=preventable/n if n else 0
    proj_planner=avg_saved*a["monthly_case_volume"]/60*a["planner_hourly_cost"]
    proj_remote=remote_rate*a["monthly_case_volume"]*visit
    gross=proj_planner+proj_remote
    return {
        "assumptions":a,
        "measured":{
            "planner_cases_measured":len(measured),
            "planner_minutes_saved":round(saved,1),
            "planner_time_value_eur":round(planner_value,2),
            "remote_resolved_count":remote,
            "estimated_remote_visit_value_eur":round(remote*visit,2),
            "avoidable_second_visits_observed":preventable,
            "estimated_avoidable_waste_eur":round(preventable*visit,2),
            "second_visits_observed":second,
        },
        "projection":{
            "monthly_case_volume":a["monthly_case_volume"],
            "projected_planner_value_eur":round(proj_planner,2),
            "projected_remote_value_eur":round(proj_remote,2),
            "projected_gross_value_eur":round(gross,2),
            "software_monthly_cost_eur":round(a["software_monthly_cost"],2),
            "projected_net_value_eur":round(gross-a["software_monthly_cost"],2),
            "projected_avoidable_waste_eur":round(preventable_rate*a["monthly_case_volume"]*visit,2),
            "break_even":gross>=a["software_monthly_cost"] if n else None,
        },
        "method":{
            "measured_planner_savings":"Baseline planner minutes minus recorded actual planner minutes.",
            "remote_value":"Remote-resolved cases multiplied by configured visit/time/travel estimate.",
            "avoidable_waste":"Preventable second visits multiplied by configured visit estimate; opportunity loss, not realised savings.",
            "projection":"Pilot averages projected to configured monthly case volume.",
        }
    }

def active_pilot():
    return first(sb.table("pilots").select("*").eq("active",True).order("id",desc=True).limit(1).execute())

def pilot_progress():
    p=active_pilot()
    if not p:
        return {"active":False}
    m=calculate_metrics()
    start=date.fromisoformat(p["start_date"]); end=date.fromisoformat(p["end_date"]); today=date.today()
    total=max(1,(end-start).days+1); elapsed=max(0,min(total,(today-start).days+1))
    avg_plan=None
    outcome_cases=[c for c in resp_data(sb.table("cases").select("outcome_planner_minutes,outcome_recorded_at").execute()) if c.get("outcome_recorded_at") and c.get("outcome_planner_minutes") is not None]
    if outcome_cases:
        avg_plan=round(sum(float(c["outcome_planner_minutes"]) for c in outcome_cases)/len(outcome_cases),2)
    current={
        "outcomes":m["outcomes"],
        "avg_planner_minutes":avg_plan,
        "first_time_fix_pct":m["first_time_fix_pct"],
        "second_visit_pct":m["second_visit_pct"],
        "remote_resolved_pct":m["remote_resolved_pct"],
        "preventable_second_visit_pct":m["preventable_second_visit_pct"],
    }
    def delt(cur, base):
        return round(cur-float(base),2) if cur is not None and base is not None else None
    def met(cur,target,direction):
        if cur is None or target is None:return False
        return cur<=float(target) if direction=="lower" else cur>=float(target)
    return {
        "active":True,"pilot":p,
        "days":{"elapsed":elapsed,"total":total,"elapsed_pct":round(100*elapsed/total,1),"remaining":max(0,total-elapsed)},
        "current":current,
        "delta":{
            "planner_minutes":delt(avg_plan,p.get("baseline_planner_minutes")),
            "first_time_fix_pct":delt(current["first_time_fix_pct"],p.get("baseline_first_time_fix_pct")),
            "second_visit_pct":delt(current["second_visit_pct"],p.get("baseline_second_visit_pct")),
            "remote_resolved_pct":delt(current["remote_resolved_pct"],p.get("baseline_remote_resolved_pct")),
        },
        "goals":{
            "planner_minutes":{"target":p.get("target_planner_minutes"),"met":met(avg_plan,p.get("target_planner_minutes"),"lower")},
            "first_time_fix_pct":{"target":p.get("target_first_time_fix_pct"),"met":met(current["first_time_fix_pct"],p.get("target_first_time_fix_pct"),"higher")},
            "second_visit_pct":{"target":p.get("target_second_visit_pct"),"met":met(current["second_visit_pct"],p.get("target_second_visit_pct"),"lower")},
            "remote_resolved_pct":{"target":p.get("target_remote_resolved_pct"),"met":met(current["remote_resolved_pct"],p.get("target_remote_resolved_pct"),"higher")},
        },
        "economics":m["economics"],
    }

def management_report():
    m=calculate_metrics()
    cases=[c for c in resp_data(sb.table("cases").select("*").execute()) if c.get("outcome_recorded_at")]
    info=Counter(); mat=Counter(); faults=Counter(); routes=Counter()
    for c in cases:
        for x in re.split(r"[;,]", c.get("outcome_missing_info") or ""):
            if x.strip():info[x.strip()]+=1
        for x in re.split(r"[;,]", c.get("outcome_missing_material") or ""):
            if x.strip():mat[x.strip()]+=1
        if c.get("fault_category"):faults[c["fault_category"]]+=1
        if c.get("service_route"):routes[c["service_route"]]+=1
    n=m["outcomes"]; min_n=10
    net=m["economics"]["projection"]["projected_net_value_eur"]
    if n<min_n:
        decision={"status":"onvoldoende_data","label":"Nog onvoldoende data","reason":f"{n} outcomes geregistreerd; minimaal {min_n} aanbevolen.","criterion":"Geen financieel pilotsignaal vóór minimaal 10 outcomes."}
    elif net>0:
        decision={"status":"positief_signaal","label":"Positief financieel pilotsignaal","reason":f"Geprojecteerde netto maandwaarde €{net:.0f}.","criterion":"Positief wanneer projectie na softwarekosten > 0 is."}
    else:
        decision={"status":"negatief_signaal","label":"Nog geen positief financieel pilotsignaal","reason":f"Geprojecteerde netto maandwaarde €{net:.0f}.","criterion":"Nog niet positief wanneer projectie na softwarekosten ≤ 0 is."}
    rec=[]
    if info:
        x,cnt=info.most_common(1)[0]; rec.append(f"Maak '{x}' een expliciet preflight-veld; {cnt} keer als ontbrekend geregistreerd.")
    if m["preventable_second_visit_pct"]>=30 and m["outcomes"]:
        rec.append("Prioriteer het terugdringen van voorkombare tweede bezoeken.")
    if m["remote_resolved_pct"]>0:rec.append("Borg remote-first triage voor routes die aantoonbaar remote oplosbaar zijn.")
    if not rec:rec.append("Blijf outcomes en oorzaken registreren.")
    return {
        "generated_at":now_iso(),
        "company_name":get_setting("company_name","Organisatie"),
        "sample_quality":{"outcomes":n,"minimum_for_signal":min_n,"sufficient_for_signal":n>=min_n},
        "operations":{
            "total_cases":m["total"],"outcomes":n,"first_time_fix_pct":m["first_time_fix_pct"],
            "second_visit_pct":m["second_visit_pct"],"remote_resolved_pct":m["remote_resolved_pct"],
            "preventable_second_visit_pct":m["preventable_second_visit_pct"],
        },
        "economics":m["economics"],
        "top_causes":{
            "missing_information":[{"label":k,"count":v} for k,v in info.most_common(5)],
            "missing_material":[{"label":k,"count":v} for k,v in mat.most_common(5)],
            "service_routes":[{"label":k,"count":v} for k,v in routes.most_common(5)],
            "fault_categories":[{"label":k,"count":v} for k,v in faults.most_common(5)],
        },
        "decision":decision,"recommendations":rec,
        "interpretation_notes":[
            "Plannerwaarde uses recorded actual preparation time.",
            "Remote visit value and monthly projections use configurable assumptions.",
            "Preventable second visits are opportunity loss, not realised savings.",
        ]
    }

def export_payload():
    return {
        "meta":{"app_name":APP_NAME,"app_version":APP_VERSION,"exported_at":now_iso(),"contains_passwords":False,"contains_attachment_bytes":False},
        "settings":resp_data(sb.table("settings").select("*").execute()),
        "users":resp_data(sb.table("users").select("id,email,display_name,role,active,created_at").execute()),
        "pilots":resp_data(sb.table("pilots").select("*").execute()),
        "pilot_snapshots":resp_data(sb.table("pilot_snapshots").select("*").execute()),
        "cases":resp_data(sb.table("cases").select("*").execute()),
        "notes":resp_data(sb.table("notes").select("*").execute()),
        "attachments":resp_data(sb.table("attachments").select("id,case_id,filename,storage_path,content_type,size_bytes,created_by,created_at").execute()),
        "audit":resp_data(sb.table("audit").select("*").execute()),
    }

def create_team_user(email,name,role,password):
    email=(email or "").lower().strip(); name=(name or "").strip()
    if not email or "@" not in email:raise ValueError("ongeldig e-mailadres")
    if not name:raise ValueError("naam ontbreekt")
    if role not in ("admin","planner","technician"):raise ValueError("ongeldige rol")
    if not password or len(password)<12:raise ValueError("wachtwoord minimaal 12 tekens")
    existing=find_user_by_email(email)
    if existing:return existing,False
    row=first(sb.table("users").insert({
        "email":email,"display_name":name,"role":role,
        "password_hash":core.hash_password(password),"active":True,"created_at":now_iso()
    }).execute())
    return row,True

class Handler(BaseHTTPRequestHandler):
    server_version="ProjectPreflightCloud/1.0"

    def log_message(self, fmt, *args):
        message = fmt % args
        # Do not leak public intake tokens into hosting logs.
        message = re.sub(r"([?&]token=)[^&\s\"]+", r"\1[REDACTED]", message)
        sys.stdout.write("[%s] %s\n" % (self.log_date_time_string(), message))

    def _security_headers(self):
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("X-Frame-Options","DENY")
        self.send_header("Referrer-Policy","no-referrer")
        self.send_header("Permissions-Policy","camera=(self), microphone=(), geolocation=()")
        self.send_header("Strict-Transport-Security","max-age=31536000")
        self.send_header("X-Robots-Tag","noindex, nofollow, noarchive")
        self.send_header("Content-Security-Policy","default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'")

    def _json(self,obj,status=200,extra_headers=None):
        raw=json.dumps(obj,ensure_ascii=False,default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(raw)))
        self.send_header("Cache-Control","no-store")
        self._security_headers()
        for k,v in (extra_headers or {}).items():self.send_header(k,v)
        self.end_headers();self.wfile.write(raw)

    def _body(self):
        n=int(self.headers.get("Content-Length","0") or 0)
        if n>MAX_BODY:raise ValueError("request too large")
        return json.loads(self.rfile.read(n) or b"{}")

    def _cookie_token(self):
        auth=self.headers.get("Authorization","")
        if auth.startswith("Bearer "):return auth[7:]
        cookie=self.headers.get("Cookie","")
        for piece in cookie.split(";"):
            k,sep,v=piece.strip().partition("=")
            if sep and k=="pf_session":return v
        return None

    def _user(self):
        return user_from_token(self._cookie_token())

    def _need(self,roles=None):
        u=self._user()
        if not u:self._json({"error":"unauthorized"},401);return None
        if roles and u["role"] not in roles:self._json({"error":"forbidden"},403);return None
        return u

    def _check_origin(self):
        if self.command in ("GET","HEAD","OPTIONS"):return True
        origin=self.headers.get("Origin")
        host=self.headers.get("Host")
        if not origin:return True
        try:return urlparse(origin).netloc==host
        except:return False

    def _client_ip(self):
        forwarded=(self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        return forwarded or (self.client_address[0] if self.client_address else "unknown")

    def _rate_limit(self,scope,limit,window_seconds):
        allowed,retry_after=_rate_allow(self._client_ip(),scope,limit,window_seconds)
        if allowed:return True
        self._json({"error":"te veel verzoeken; probeer later opnieuw"},429,{"Retry-After":str(retry_after)})
        return False

    def _static(self,path):
        if path=="/":path="/index.html"
        safe=(STATIC/path.lstrip("/")).resolve()
        if STATIC.resolve() not in safe.parents and safe!=STATIC.resolve():self.send_error(403);return
        if not safe.exists() or not safe.is_file():self.send_error(404);return
        data=safe.read_bytes();ctype=mimetypes.guess_type(str(safe))[0] or "application/octet-stream"
        self.send_response(200);self.send_header("Content-Type",ctype);self.send_header("Content-Length",str(len(data)))
        self.send_header("Cache-Control","public, max-age=300" if path not in ("/index.html","/intake.html","/app.js") else "no-cache")
        self._security_headers();self.end_headers();self.wfile.write(data)

    def do_GET(self):
        try:
            p=urlparse(self.path);path=p.path;q=parse_qs(p.query)
            if path=="/api/health":
                return self._json({"ok":True,"name":APP_NAME,"version":APP_VERSION,"backend":"supabase"})
            if path=="/api/version":return self._json({"name":APP_NAME,"version":APP_VERSION,"build":APP_BUILD})
            if path=="/api/public-info":
                token=q.get("token",[""])[0]
                if not hmac.compare_digest(token,get_setting("intake_token","")):return self._json({"error":"invalid token"},403)
                return self._json(public_config())
            if path=="/api/me":
                u=self._need()
                if u:return self._json(u)
                return
            if path=="/api/onboarding-status":
                u=self._need(("admin","planner"))
                if u:return self._json(onboarding_payload())
                return
            if path=="/api/settings":
                u=self._need(("admin","planner"))
                if not u:return
                return self._json({
                    "company_name":get_setting("company_name"),
                    "intake_token":get_setting("intake_token"),
                    "brand_name":get_setting("brand_name","Project Preflight"),
                    "brand_accent":get_setting("brand_accent","#62d0ff"),
                    "support_email":get_setting("support_email",""),
                    "customer_portal_title":get_setting("customer_portal_title","Service-intake"),
                    "app_version":APP_VERSION,**economic_assumptions()
                })
            if path in ("/api/users","/api/accounts"):
                u=self._need(("admin","planner") if path=="/api/users" else ("admin",))
                if not u:return
                rows=resp_data(sb.table("users").select("id,email,display_name,role,active,created_at").order("role").order("display_name").execute())
                return self._json(rows)
            if path=="/api/cases":
                u=self._need()
                if not u:return
                return self._json([enrich_case(c) for c in visible_cases(u)])
            if path=="/api/metrics":
                u=self._need(("admin","planner"))
                if u:return self._json(calculate_metrics())
                return
            if path=="/api/pilot":
                u=self._need(("admin","planner"))
                if u:return self._json(pilot_progress())
                return
            if path=="/api/pilot/snapshots":
                u=self._need(("admin","planner"))
                if not u:return
                p=active_pilot()
                rows=resp_data(sb.table("pilot_snapshots").select("*").eq("pilot_id",p["id"]).order("snapshot_date").execute()) if p else []
                return self._json(rows)
            if path=="/api/pilot/final-report":
                u=self._need(("admin","planner"))
                if not u:return
                # management report is used as final report when pilot is closed.
                return self._json(management_report())
            if path=="/api/report":
                u=self._need(("admin","planner"))
                if u:return self._json(management_report())
                return
            if path=="/api/audit":
                u=self._need(("admin","planner"))
                if not u:return
                rows=resp_data(sb.table("audit").select("*").order("created_at",desc=True).limit(250).execute())
                # enrich user display
                for r in rows:
                    if r.get("user_id"):
                        x=find_user(r["user_id"]);r["display_name"]=x["display_name"] if x else None
                return self._json(rows)
            if path=="/api/export":
                u=self._need(("admin",))
                if u:return self._json(export_payload())
                return
            if path=="/api/pilot-reset-summary":
                u=self._need(("admin",))
                if not u:return
                result={}
                for table in ("cases","notes","attachments","audit","pilots","pilot_snapshots"):
                    result[table if table!="audit" else "audit_events"]=len(resp_data(sb.table(table).select("id").execute()))
                return self._json(result)
            if path.startswith("/api/cases/") and path.endswith("/notes"):
                u=self._need()
                if not u:return
                cid=int(path.split("/")[3]);c=get_case(cid)
                if not can_access_case(u,c):return self._json({"error":"not found"},404)
                rows=resp_data(sb.table("notes").select("*").eq("case_id",cid).order("created_at").execute())
                for r in rows:
                    x=find_user(r["created_by"]);r["display_name"]=x["display_name"] if x else "Onbekend";r["email"]=x["email"] if x else ""
                return self._json(rows)
            if path.startswith("/api/cases/") and path.endswith("/attachments"):
                u=self._need()
                if not u:return
                cid=int(path.split("/")[3]);c=get_case(cid)
                if not can_access_case(u,c):return self._json({"error":"not found"},404)
                rows=resp_data(sb.table("attachments").select("id,case_id,filename,content_type,size_bytes,created_at").eq("case_id",cid).order("created_at").execute())
                return self._json(rows)
            if path.startswith("/api/attachments/"):
                u=self._need()
                if not u:return
                aid=int(path.split("/")[3]);a=first(sb.table("attachments").select("*").eq("id",aid).limit(1).execute())
                if not a:return self._json({"error":"not found"},404)
                c=get_case(a["case_id"])
                if not can_access_case(u,c):return self._json({"error":"not found"},404)
                raw=sb.storage.from_(BUCKET).download(a["storage_path"])
                self.send_response(200);self.send_header("Content-Type",a.get("content_type") or "application/octet-stream")
                self.send_header("Content-Disposition",f'attachment; filename="{safe_filename(a["filename"])}"')
                self.send_header("Content-Length",str(len(raw)));self._security_headers();self.end_headers();self.wfile.write(raw);return
            return self._static(path)
        except Exception as e:
            transient = isinstance(e, (httpx.ReadError, httpx.ReadTimeout, httpx.ConnectError, httpx.ConnectTimeout)) or (
                "Resource temporarily unavailable" in repr(e)
            )
            retry_count = getattr(self, "_get_retry_count", 0)
            if transient and retry_count < 2:
                self._get_retry_count = retry_count + 1
                _reset_supabase_client()
                time.sleep(0.12 * (2 ** retry_count))
                print(f"GET RETRY {self._get_retry_count} after transient network error: {e!r}", file=sys.stderr)
                return self.do_GET()
            print("GET ERROR",repr(e),file=sys.stderr)
            return self._json({"error":"server_error"},500)

    def do_POST(self):
        if not self._check_origin():return self._json({"error":"invalid origin"},403)
        try:
            path=urlparse(self.path).path
            # Public attack surface: bound repeated login attempts and intake spam.
            if path=="/api/login" and not self._rate_limit("login",10,600):return
            if path=="/api/public-intake" and not self._rate_limit("public-intake",30,3600):return
            body=self._body()
            if path=="/api/login":
                email=str(body.get("email","")).lower().strip();pwd=str(body.get("password",""))
                row=find_user_by_email(email)
                if not row or not row.get("active") or not core.verify_password(pwd,row["password_hash"]):
                    return self._json({"error":"ongeldige inloggegevens"},401)
                token=create_session(row["id"])
                cookie=f"pf_session={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age={SESSION_HOURS*3600}"
                if COOKIE_SECURE:cookie+="; Secure"
                user=find_user(row["id"])
                return self._json({"user":user},200,{"Set-Cookie":cookie})
            if path=="/api/logout":
                token=self._cookie_token();delete_session(token)
                cookie="pf_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0"
                if COOKIE_SECURE:cookie+="; Secure"
                return self._json({"ok":True},200,{"Set-Cookie":cookie})
            if path=="/api/public-intake":
                token=str(body.get("token",""))
                if not hmac.compare_digest(token,get_setting("intake_token","")):return self._json({"error":"invalid token"},403)
                typ=str(body.get("type","Onbekend"));problem=str(body.get("problem",""));extra=body.get("extra") or {}
                facts,missing,score,dispatch,prep,fault=core.analyze(typ,problem,extra)
                brand=core.canonical_brand(extra.get("manufacturer"));src=core.source_for(brand);rk=core.route_knowledge(fault["category"]);fk=core.ftf_knowledge(fault["category"])
                case_no="PF-"+str(int(time.time()*1000))[-8:]
                row=first(sb.table("cases").insert({
                    "case_no":case_no,"source":"customer","customer":str(body.get("customer") or "Nieuwe klant"),
                    "city":str(body.get("city") or ""),"phone":str(body.get("phone") or ""),"email":str(body.get("email") or ""),
                    "type":typ,"asset":((brand+" "+str(extra.get("model") or "")).strip() if brand!="Onbekend" else "Nog te identificeren"),
                    "status":"Review" if not missing else "Info ontbreekt","score":score,"problem":problem,
                    "facts":facts,"missing":missing,"dispatch":dispatch,"prep":prep,
                    "intake_seconds":int(body.get("intake_seconds") or 0),"version":1,
                    "created_at":now_iso(),"updated_at":now_iso(),"manufacturer":brand,
                    "model":str(extra.get("model") or ""),"serial_no":str(extra.get("serial") or ""),
                    "knowledge_title":src["title"],"knowledge_url":src["url"],"api_targets":src["api_targets"],
                    "fault_category":fault["category"],"fault_confidence":fault["confidence"],"triage_level":fault["triage"],"fault_evidence":fault["evidence"],
                    "service_route":rk["service_route"],"required_competence":rk["competence"],"remote_checks":rk["remote_checks"],
                    "site_trigger":rk["site_trigger"],"prep_categories":rk["prep_categories"],"escalation_path":rk["escalation"],
                    "route_source_title":rk["source_title"],"route_source_url":rk["source_url"],
                    "ftf_critical":fk["critical_before_departure"],"ftf_gaps":fk["common_avoidable_gap"],"ftf_parts":fk["parts_categories"],
                }).execute())
                file=body.get("file")
                if file and file.get("data_base64"):
                    raw=base64.b64decode(file["data_base64"],validate=True)
                    if len(raw)<=5*1024*1024:
                        name=safe_filename(file.get("name"));storage_path=f"{row['id']}/{secrets.token_hex(12)}-{name}"
                        sb.storage.from_(BUCKET).upload(path=storage_path,file=io.BytesIO(raw),file_options={"content-type":file.get("type") or "application/octet-stream","upsert":"false"})
                        sb.table("attachments").insert({"case_id":row["id"],"filename":name,"storage_path":storage_path,"content_type":file.get("type") or "application/octet-stream","size_bytes":len(raw),"created_at":now_iso()}).execute()
                create_audit(row["id"],None,"public_intake","customer self-service")
                return self._json({"ok":True,"case_no":case_no,"score":score,"missing":missing,"route":fault["category"]},201)

            u=self._need()
            if not u:return

            if path=="/api/change-password":
                current=str(body.get("current_password") or "");new=str(body.get("new_password") or "")
                if len(new)<12:return self._json({"error":"nieuw wachtwoord minimaal 12 tekens"},400)
                row=find_user_by_email(u["email"])
                if not core.verify_password(current,row["password_hash"]):return self._json({"error":"huidig wachtwoord onjuist"},403)
                sb.table("users").update({"password_hash":core.hash_password(new)}).eq("id",u["id"]).execute()
                sb.table("sessions").delete().eq("user_id",u["id"]).execute()
                create_audit(None,u["id"],"password_changed","self-service")
                cookie="pf_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0"
                if COOKIE_SECURE:cookie+="; Secure"
                return self._json({"ok":True,"relogin_required":True},200,{"Set-Cookie":cookie})
            if path=="/api/accounts":
                if u["role"]!="admin":return self._json({"error":"forbidden"},403)
                try:row,created=create_team_user(body.get("email"),body.get("display_name"),body.get("role"),body.get("password"))
                except ValueError as e:return self._json({"error":str(e)},400)
                return self._json({"created":created,"user":{k:v for k,v in row.items() if k!="password_hash"}},201 if created else 200)
            if path.startswith("/api/accounts/") and path.endswith("/reset-password"):
                if u["role"]!="admin":return self._json({"error":"forbidden"},403)
                uid=int(path.split("/")[3]);new=str(body.get("new_password") or "")
                if len(new)<12:return self._json({"error":"nieuw wachtwoord minimaal 12 tekens"},400)
                sb.table("users").update({"password_hash":core.hash_password(new)}).eq("id",uid).execute()
                sb.table("sessions").delete().eq("user_id",uid).execute()
                create_audit(None,u["id"],"admin_password_reset",str(uid));return self._json({"ok":True})
            if path=="/api/onboarding":
                if u["role"] not in ("admin","planner"):return self._json({"error":"forbidden"},403)
                company=str(body.get("company_name") or "").strip()
                service_types=[x for x in body.get("enabled_service_types",[]) if x in ("Laadpaal","Zonnepanelen","Thuisbatterij","Elektro")]
                if not company or not service_types:return self._json({"error":"bedrijfsnaam en servicetype verplicht"},400)
                set_setting("company_name",company);set_setting("enabled_service_types",json.dumps(service_types,ensure_ascii=False))
                clean={}
                brands=body.get("enabled_brands") or {}
                for t in service_types:clean[t]=[str(v).strip() for v in brands.get(t,[]) if str(v).strip()] or ["Anders/onbekend"]
                set_setting("enabled_brands",json.dumps(clean,ensure_ascii=False))
                for k,v in (body.get("assumptions") or {}).items():
                    if k in economic_assumptions():set_setting(k,max(0,float(v)))
                created=0
                for member in body.get("team") or []:
                    try:_,was=create_team_user(member.get("email"),member.get("display_name"),member.get("role"),member.get("password"));created+=1 if was else 0
                    except ValueError as e:return self._json({"error":"teamlid: "+str(e)},400)
                pilot=body.get("pilot") or {}
                if pilot.get("create"):
                    sb.table("pilots").update({"active":False,"updated_at":now_iso()}).eq("active",True).execute()
                    sb.table("pilots").insert({
                        "name":str(pilot.get("name") or "Launch Partner Pilot"),"start_date":pilot.get("start_date") or date.today().isoformat(),
                        "end_date":pilot.get("end_date") or (date.today()+timedelta(days=42)).isoformat(),
                        "baseline_planner_minutes":pilot.get("baseline_planner_minutes"),"baseline_first_time_fix_pct":pilot.get("baseline_first_time_fix_pct"),
                        "baseline_second_visit_pct":pilot.get("baseline_second_visit_pct"),"baseline_remote_resolved_pct":pilot.get("baseline_remote_resolved_pct"),
                        "target_planner_minutes":pilot.get("target_planner_minutes"),"target_first_time_fix_pct":pilot.get("target_first_time_fix_pct"),
                        "target_second_visit_pct":pilot.get("target_second_visit_pct"),"target_remote_resolved_pct":pilot.get("target_remote_resolved_pct"),
                        "notes":str(pilot.get("notes") or ""),"active":True,"created_at":now_iso(),"updated_at":now_iso()
                    }).execute()
                set_setting("onboarding_complete","1")
                return self._json({"ok":True,"onboarding":onboarding_payload(),"team_members_created":created,"intake_path":"/intake.html?token="+get_setting("intake_token")},201)
            if path=="/api/pilot":
                if u["role"] not in ("admin","planner"):return self._json({"error":"forbidden"},403)
                sb.table("pilots").update({"active":False,"updated_at":now_iso()}).eq("active",True).execute()
                row=first(sb.table("pilots").insert({
                    "name":str(body.get("name") or "Preflight Pilot"),"start_date":body.get("start_date") or date.today().isoformat(),
                    "end_date":body.get("end_date") or (date.today()+timedelta(days=42)).isoformat(),
                    "baseline_planner_minutes":body.get("baseline_planner_minutes"),"baseline_first_time_fix_pct":body.get("baseline_first_time_fix_pct"),
                    "baseline_second_visit_pct":body.get("baseline_second_visit_pct"),"baseline_remote_resolved_pct":body.get("baseline_remote_resolved_pct"),
                    "target_planner_minutes":body.get("target_planner_minutes"),"target_first_time_fix_pct":body.get("target_first_time_fix_pct"),
                    "target_second_visit_pct":body.get("target_second_visit_pct"),"target_remote_resolved_pct":body.get("target_remote_resolved_pct"),
                    "notes":str(body.get("notes") or ""),"active":True,"created_at":now_iso(),"updated_at":now_iso()
                }).execute())
                return self._json(pilot_progress(),201)
            if path=="/api/pilot/snapshot":
                if u["role"] not in ("admin","planner"):return self._json({"error":"forbidden"},403)
                p=active_pilot()
                if not p:return self._json({"error":"no active pilot"},404)
                m=calculate_metrics()
                outcome_cases=[c for c in resp_data(sb.table("cases").select("outcome_planner_minutes,outcome_recorded_at").execute()) if c.get("outcome_recorded_at") and c.get("outcome_planner_minutes") is not None]
                avg=round(sum(float(c["outcome_planner_minutes"]) for c in outcome_cases)/len(outcome_cases),2) if outcome_cases else None
                e=m["economics"]["measured"]
                row=first(sb.table("pilot_snapshots").upsert({
                    "pilot_id":p["id"],"snapshot_date":date.today().isoformat(),"outcomes":m["outcomes"],"avg_planner_minutes":avg,
                    "first_time_fix_pct":m["first_time_fix_pct"],"second_visit_pct":m["second_visit_pct"],"remote_resolved_pct":m["remote_resolved_pct"],
                    "preventable_second_visit_pct":m["preventable_second_visit_pct"],"measured_planner_value_eur":e["planner_time_value_eur"],
                    "estimated_remote_value_eur":e["estimated_remote_visit_value_eur"],"avoidable_waste_eur":e["estimated_avoidable_waste_eur"]
                },on_conflict="pilot_id,snapshot_date").execute())
                return self._json(row)
            if path=="/api/pilot/close":
                if u["role"] not in ("admin","planner"):return self._json({"error":"forbidden"},403)
                p=active_pilot()
                if not p:return self._json({"error":"no active pilot"},404)
                sb.table("pilots").update({"active":False,"updated_at":now_iso()}).eq("id",p["id"]).execute()
                r=management_report()
                r.update({"available":True,"pilot":p,"sample_quality":{"outcomes":r["sample_quality"]["outcomes"],"minimum_for_conclusion":10,"sufficient":r["sample_quality"]["outcomes"]>=10},"conclusion":{"status":"positief" if r["decision"]["status"]=="positief_signaal" else "verbeteren" if r["decision"]["status"]!="onvoldoende_data" else "onvoldoende_data","text":r["decision"]["reason"]},"goals":[]})
                return self._json(r)
            if path=="/api/pilot-reset":
                if u["role"]!="admin":return self._json({"error":"forbidden"},403)
                if str(body.get("confirm") or "")!="RESET PILOT DATA":return self._json({"error":"bevestigingstekst klopt niet"},400)
                atts=resp_data(sb.table("attachments").select("storage_path").execute())
                for table in ("pilot_snapshots","pilots","notes","attachments","audit","cases"):
                    # neq id 0 is a portable "all normal rows" filter for identity ids.
                    sb.table(table).delete().neq("id",0).execute()
                paths=[a["storage_path"] for a in atts if a.get("storage_path")]
                if paths:
                    try:sb.storage.from_(BUCKET).remove(paths)
                    except Exception as e:print("storage cleanup warning",repr(e),file=sys.stderr)
                set_setting("onboarding_complete","0")
                # Invalidate every previously shared public intake link.
                set_setting("intake_token",secrets.token_urlsafe(24))
                return self._json({"ok":True})
            if path=="/api/cases":
                if u["role"] not in ("admin","planner"):return self._json({"error":"forbidden"},403)
                typ=str(body.get("type","Onbekend"));extra=body.get("extra") or {};problem=str(body.get("problem") or "")
                facts,missing,score,dispatch,prep,fault=core.analyze(typ,problem,extra)
                brand=core.canonical_brand(extra.get("manufacturer"));src=core.source_for(brand);rk=core.route_knowledge(fault["category"]);fk=core.ftf_knowledge(fault["category"])
                row=first(sb.table("cases").insert({
                    "case_no":"PF-"+str(int(time.time()*1000))[-8:],"source":"planner","customer":body.get("customer") or "Nieuwe klant",
                    "city":body.get("city"),"type":typ,"asset":((brand+" "+str(extra.get("model") or "")).strip() if brand!="Onbekend" else "Nog te identificeren"),
                    "status":"Review" if not missing else "Info ontbreekt","score":score,"problem":problem,"facts":facts,"missing":missing,"dispatch":dispatch,"prep":prep,
                    "assigned_to":body.get("assigned_to"),"created_by":u["id"],"version":1,"created_at":now_iso(),"updated_at":now_iso(),
                    "manufacturer":brand,"model":str(extra.get("model") or ""),"serial_no":str(extra.get("serial") or ""),
                    "knowledge_title":src["title"],"knowledge_url":src["url"],"api_targets":src["api_targets"],
                    "fault_category":fault["category"],"fault_confidence":fault["confidence"],"triage_level":fault["triage"],"fault_evidence":fault["evidence"],
                    "service_route":rk["service_route"],"required_competence":rk["competence"],"remote_checks":rk["remote_checks"],"site_trigger":rk["site_trigger"],
                    "prep_categories":rk["prep_categories"],"escalation_path":rk["escalation"],"route_source_title":rk["source_title"],"route_source_url":rk["source_url"],
                    "ftf_critical":fk["critical_before_departure"],"ftf_gaps":fk["common_avoidable_gap"],"ftf_parts":fk["parts_categories"]
                }).execute())
                create_audit(row["id"],u["id"],"case_created",row["case_no"]);return self._json(row,201)
            if path.startswith("/api/cases/") and path.endswith("/outcome"):
                cid=int(path.split("/")[3]);c=get_case(cid)
                if not can_access_case(u,c):return self._json({"error":"not found"},404)
                update={
                    "outcome_resolved_first_visit":bool(body.get("resolved_first_visit")),
                    "outcome_second_visit_required":bool(body.get("second_visit_required")),
                    "outcome_remote_resolved":bool(body.get("remote_resolved")),
                    "outcome_missing_info":str(body.get("missing_info") or ""),
                    "outcome_missing_material":str(body.get("missing_material") or ""),
                    "outcome_wrong_skill":bool(body.get("wrong_skill")),
                    "outcome_preventable":bool(body.get("preventable")),
                    "outcome_notes":str(body.get("notes") or ""),
                    "outcome_planner_minutes":float(body["planner_minutes"]) if body.get("planner_minutes") not in ("",None) else None,
                    "outcome_recorded_at":now_iso(),"updated_at":now_iso()
                }
                row=first(sb.table("cases").update(update).eq("id",cid).execute())
                create_audit(cid,u["id"],"outcome_recorded",json.dumps({"second_visit_required":update["outcome_second_visit_required"],"preventable":update["outcome_preventable"]}))
                return self._json(row)
            if path.startswith("/api/cases/") and path.endswith("/notes"):
                cid=int(path.split("/")[3]);c=get_case(cid)
                if not can_access_case(u,c):return self._json({"error":"not found"},404)
                text=str(body.get("body") or "").strip()
                if not text:return self._json({"error":"empty note"},400)
                sb.table("notes").insert({"case_id":cid,"body":text,"created_by":u["id"],"created_at":now_iso()}).execute()
                create_audit(cid,u["id"],"note_added","");return self._json({"ok":True},201)
            if path.startswith("/api/cases/") and path.endswith("/attachments"):
                cid=int(path.split("/")[3]);c=get_case(cid)
                if not can_access_case(u,c):return self._json({"error":"not found"},404)
                raw=base64.b64decode(str(body.get("data_base64") or ""),validate=True)
                if len(raw)>5*1024*1024:return self._json({"error":"bestand groter dan 5 MB"},400)
                name=safe_filename(body.get("filename"));storage_path=f"{cid}/{secrets.token_hex(12)}-{name}"
                ctype=body.get("content_type") or "application/octet-stream"
                sb.storage.from_(BUCKET).upload(path=storage_path,file=io.BytesIO(raw),file_options={"content-type":ctype,"upsert":"false"})
                row=first(sb.table("attachments").insert({"case_id":cid,"filename":name,"storage_path":storage_path,"content_type":ctype,"size_bytes":len(raw),"created_by":u["id"],"created_at":now_iso()}).execute())
                create_audit(cid,u["id"],"attachment_added",name);return self._json(row,201)
            return self._json({"error":"not found"},404)
        except Exception as e:
            print("POST ERROR",repr(e),file=sys.stderr);return self._json({"error":"server_error"},500)

    def do_PATCH(self):
        if not self._check_origin():return self._json({"error":"invalid origin"},403)
        try:
            path=urlparse(self.path).path;body=self._body();u=self._need()
            if not u:return
            if path=="/api/settings":
                if u["role"] not in ("admin","planner"):return self._json({"error":"forbidden"},403)
                allowed={"company_name":str,"baseline_planner_minutes":float,"planner_hourly_cost":float,"technician_hourly_cost":float,"avg_site_visit_minutes":float,"avg_roundtrip_km":float,"cost_per_km":float,"software_monthly_cost":float,"monthly_case_volume":float,"brand_name":str,"brand_accent":str,"support_email":str,"customer_portal_title":str}
                for k,t in allowed.items():
                    if k not in body:continue
                    v=str(body[k]) if t is str else str(max(0,float(body[k])))
                    if k=="brand_accent" and not re.fullmatch(r"#[0-9a-fA-F]{6}",v):return self._json({"error":"ongeldige accentkleur"},400)
                    if k=="support_email" and v and "@" not in v:return self._json({"error":"ongeldig support e-mailadres"},400)
                    set_setting(k,v)
                return self._json({"company_name":get_setting("company_name"),"brand_name":get_setting("brand_name"),"brand_accent":get_setting("brand_accent"),"support_email":get_setting("support_email"),"customer_portal_title":get_setting("customer_portal_title"),**economic_assumptions()})
            if path.startswith("/api/accounts/"):
                if u["role"]!="admin":return self._json({"error":"forbidden"},403)
                uid=int(path.split("/")[3])
                if uid==u["id"] and body.get("active") is False:return self._json({"error":"eigen adminaccount kan niet worden gedeactiveerd"},400)
                upd={}
                for k in ("display_name","role","active"):
                    if k in body:upd[k]=body[k]
                if "role" in upd and upd["role"] not in ("admin","planner","technician"):return self._json({"error":"invalid role"},400)
                row=first(sb.table("users").update(upd).eq("id",uid).execute());create_audit(None,u["id"],"account_updated",json.dumps({"target_user_id":uid,"changes":upd}))
                return self._json({k:v for k,v in row.items() if k!="password_hash"})
            if path.startswith("/api/cases/"):
                cid=int(path.split("/")[3]);c=get_case(cid)
                if not can_access_case(u,c):return self._json({"error":"not found"},404)
                expected=int(body.get("version",0))
                if int(c.get("version") or 1)!=expected:return self._json({"error":"version_conflict","remote":c},409)
                upd={}
                for k in ("status","score","problem","dispatch","facts","missing"):
                    if k in body:upd[k]=body[k]
                if "assigned_to" in body and u["role"] in ("admin","planner"):upd["assigned_to"]=body["assigned_to"]
                new_status=body.get("status",c.get("status"))
                if new_status in ("Review","Ingepland","Afgerond") and not c.get("planner_ready_at"):upd["planner_ready_at"]=now_iso()
                if new_status=="Ingepland" and not c.get("scheduled_at"):upd["scheduled_at"]=now_iso()
                if new_status=="Afgerond" and not c.get("closed_at"):upd["closed_at"]=now_iso()
                upd["version"]=expected+1;upd["updated_at"]=now_iso()
                row=first(sb.table("cases").update(upd).eq("id",cid).eq("version",expected).execute())
                if not row:return self._json({"error":"version_conflict","remote":get_case(cid)},409)
                create_audit(cid,u["id"],"case_updated",json.dumps({"status":new_status}))
                return self._json(row)
            return self._json({"error":"not found"},404)
        except Exception as e:
            print("PATCH ERROR",repr(e),file=sys.stderr);return self._json({"error":"server_error"},500)

if __name__=="__main__":
    bootstrap()
    print(f"{APP_NAME} {APP_VERSION} cloud server")
    print(f"Listening on 0.0.0.0:{PORT}")
    ThreadingHTTPServer(("0.0.0.0",PORT),Handler).serve_forever()
