#!/usr/bin/env python3
"""
Werkstuur Cloud v1
Stateless Python web/API service backed by Supabase Postgres + private Storage.

The Supabase secret key is SERVER-ONLY. It must never be added to static files.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import mimetypes
import os
import smtplib
import ssl
import html as html_lib
import re
import secrets
import sys
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta, date
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from urllib.parse import urlparse, parse_qs, quote

from supabase import create_client, Client
import httpx

import server as core
import analysis_engine
import backup_archive

ROOT = Path(__file__).resolve().parent
STATIC = (ROOT / "static") if (ROOT / "static").is_dir() else ROOT

APP_NAME = "Werkstuur"
APP_VERSION = "2.1.0-command"
APP_BUILD = "2026-10-05"
BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "preflight-attachments")
MAX_BODY = 7 * 1024 * 1024
SESSION_HOURS = int(os.environ.get("SESSION_HOURS", "12"))
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "1") not in ("0","false","False")
PORT = int(os.environ.get("PORT", "10000"))

def _env_int(name, default):
    try:return int(os.environ.get(name,str(default)))
    except Exception:return int(default)

SMTP_HOST = os.environ.get("SMTP_HOST", "mail.werkstuur.nl").strip()
SMTP_PORT = _env_int("SMTP_PORT", 465)
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_SECURITY = os.environ.get("SMTP_SECURITY", "ssl").strip().lower()
SMTP_FROM_EMAIL = os.environ.get("SMTP_FROM_EMAIL", SMTP_USERNAME).strip()
SMTP_FROM_NAME = os.environ.get("SMTP_FROM_NAME", "Werkstuur").strip() or "Werkstuur"
SMTP_REPLY_TO = os.environ.get("SMTP_REPLY_TO", "support@werkstuur.nl").strip()
MAIL_TRANSPORT = os.environ.get("MAIL_TRANSPORT", "smtp").strip().lower()
WEBMAIL_RELAY_URL = os.environ.get("WEBMAIL_RELAY_URL", "").strip()
WEBMAIL_RELAY_SECRET = os.environ.get("WEBMAIL_RELAY_SECRET", "")
MAIL_NOTIFICATIONS_ENABLED = os.environ.get("MAIL_NOTIFICATIONS_ENABLED", "1") not in ("0","false","False","no","off")
APP_PUBLIC_URL = (os.environ.get("APP_PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "https://app.werkstuur.nl").rstrip("/")
WEBSITE_URL = (os.environ.get("WEBSITE_URL") or "https://werkstuur.nl").rstrip("/")
PASSWORD_RESET_MINUTES = max(10, min(120, _env_int("PASSWORD_RESET_MINUTES", 30)))
PUBLIC_SITE_ORIGINS = {x.strip().rstrip("/") for x in os.environ.get("PUBLIC_SITE_ORIGINS", "https://werkstuur.nl,https://www.werkstuur.nl").split(",") if x.strip()}
SALES_EMAIL = os.environ.get("SALES_EMAIL", "manuel@werkstuur.nl").strip()

_MAIL_LOCK = threading.Lock()
_LAST_MAIL_ERROR = None
_LAST_MAIL_SUCCESS = None

_PROCESS_STARTED_AT = time.time()
_PROCESS_STARTED_ISO = now_marker = datetime.now(timezone.utc).isoformat()
_STATUS_LOCK = threading.Lock()
_LAST_SERVER_ERROR = None
_LAST_SUCCESSFUL_STATUS_CHECK = None

def _sanitize_error_message(exc):
    msg = f"{type(exc).__name__}: {str(exc)}"
    msg = re.sub(r"sb_secret_[A-Za-z0-9._-]+", "[REDACTED]", msg)
    msg = re.sub(r"([?&]token=)[^&\s]+", r"\1[REDACTED]", msg)
    return msg[:240]

def _record_server_error(scope, exc):
    global _LAST_SERVER_ERROR
    with _STATUS_LOCK:
        _LAST_SERVER_ERROR = {
            "at": datetime.now(timezone.utc).isoformat(),
            "scope": str(scope)[:80],
            "message": _sanitize_error_message(exc),
        }

def _record_status_success():
    global _LAST_SUCCESSFUL_STATUS_CHECK
    with _STATUS_LOCK:
        _LAST_SUCCESSFUL_STATUS_CHECK = datetime.now(timezone.utc).isoformat()

def _count_rows(table, filters=None):
    count_column = "user_id" if table == "sessions" else "id"
    q = sb.table(table).select(count_column, count="exact").limit(1)
    for op, column, value in (filters or []):
        q = getattr(q, op)(column, value)
    r = q.execute()
    count = getattr(r, "count", None)
    if count is None:
        return len(resp_data(r))
    return int(count)

def system_status_payload(user=None):
    checked_at = datetime.now(timezone.utc).isoformat()
    db_started = time.perf_counter()
    database = {"status": "online", "latency_ms": None}
    storage = {"status": "online", "bucket": BUCKET}
    counts = {}
    current_error = None

    try:
        sb.table("settings").select("key").limit(1).execute()
        database["latency_ms"] = round((time.perf_counter() - db_started) * 1000, 1)

        org_id=current_org_id()
        filters=[("eq","organization_id",org_id)] if org_id else []
        counts = {
            "cases": _count_rows("cases",filters),
            "active_users": _count_rows("users",filters+[("eq","active",True)]),
            "active_sessions": _count_rows("sessions",[("eq","active_organization_id",org_id),("gt","expires_at",checked_at)]) if org_id else 0,
            "attachments": _count_rows("attachments",filters),
            "pilots": _count_rows("pilots",filters),
        }
        if user and user.get("is_platform_owner"):
            counts["organizations"]=_count_rows("organizations")
    except Exception as exc:
        database = {"status": "unavailable", "latency_ms": None}
        current_error = exc
        _reset_supabase_client()

    storage_started = time.perf_counter()
    if database["status"] == "online":
        try:
            sb.storage.from_(BUCKET).list(f"org/{current_org_id()}" if current_org_id() else "", {"limit": 1, "offset": 0})
            storage["latency_ms"] = round((time.perf_counter() - storage_started) * 1000, 1)
        except Exception as exc:
            storage = {"status": "unavailable", "bucket": BUCKET, "latency_ms": None}
            current_error = current_error or exc
            _reset_supabase_client()
    else:
        storage = {"status": "unknown", "bucket": BUCKET, "latency_ms": None}

    mail = mail_status_payload()
    core_ok = database["status"] == "online" and storage["status"] == "online"
    mail_ok = mail["status"] in ("ready","disabled")
    overall = "healthy" if core_ok and mail_ok else "degraded"
    if current_error:
        _record_server_error("system_status", current_error)
    else:
        _record_status_success()

    with _STATUS_LOCK:
        last_error = dict(_LAST_SERVER_ERROR) if _LAST_SERVER_ERROR else None
        last_success = _LAST_SUCCESSFUL_STATUS_CHECK

    uptime_seconds = max(0, int(time.time() - _PROCESS_STARTED_AT))
    return {
        "overall": overall,
        "checked_at": checked_at,
        "app": {
            "status": "online",
            "name": APP_NAME,
            "version": APP_VERSION,
            "build": APP_BUILD,
            "uptime_seconds": uptime_seconds,
            "started_at": _PROCESS_STARTED_ISO,
        },
        "database": database,
        "storage": storage,
        "mail": mail,
        "counts": counts,
        "hosting": {
            "provider": "Render",
            "service_id": os.environ.get("RENDER_SERVICE_ID", ""),
            "commit": (os.environ.get("RENDER_GIT_COMMIT", "") or "")[:12],
            "external_url": os.environ.get("RENDER_EXTERNAL_URL", ""),
        },
        "organization": current_organization(),
        "monitoring": {
            "last_successful_check": last_success,
            "last_error": last_error,
        },
    }

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

def _valid_email(value):
    value=str(value or "").strip()
    return value if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value) else ""

def _mail_configured():
    if not MAIL_NOTIFICATIONS_ENABLED or not SMTP_FROM_EMAIL:
        return False
    if MAIL_TRANSPORT == "https":
        return bool(WEBMAIL_RELAY_URL == "https://werkstuur.nl/app-mail.php" and len(WEBMAIL_RELAY_SECRET) >= 32)
    return bool(MAIL_TRANSPORT == "smtp" and SMTP_HOST and SMTP_PORT and SMTP_USERNAME and SMTP_PASSWORD)

def _record_mail_result(ok, detail=""):
    global _LAST_MAIL_ERROR, _LAST_MAIL_SUCCESS
    with _MAIL_LOCK:
        if ok:
            _LAST_MAIL_SUCCESS=datetime.now(timezone.utc).isoformat()
            _LAST_MAIL_ERROR=None
        else:
            _LAST_MAIL_ERROR={"at":datetime.now(timezone.utc).isoformat(),"message":str(detail or "onbekende e-mailfout")[:220]}

def mail_status_payload():
    with _MAIL_LOCK:
        last_success=_LAST_MAIL_SUCCESS
        last_error=dict(_LAST_MAIL_ERROR) if _LAST_MAIL_ERROR else None
    if not MAIL_NOTIFICATIONS_ENABLED:
        status="disabled"
    elif _mail_configured():
        status="ready"
    else:
        status="not_configured"
    return {
        "status":status,
        "configured":_mail_configured(),
        "enabled":MAIL_NOTIFICATIONS_ENABLED,
        "transport":MAIL_TRANSPORT,
        "host":"werkstuur.nl" if MAIL_TRANSPORT == "https" else SMTP_HOST,
        "port":443 if MAIL_TRANSPORT == "https" else SMTP_PORT,
        "security":"https" if MAIL_TRANSPORT == "https" else SMTP_SECURITY,
        "from_email":SMTP_FROM_EMAIL,
        "last_success":last_success,
        "last_error":last_error,
    }

def _email_shell(title, intro, rows=None, cta_label=None, cta_url=None, footer=None):
    safe_title=html_lib.escape(str(title))
    safe_intro=html_lib.escape(str(intro))
    row_html=""
    for label,value in (rows or []):
        row_html += f'<tr><td style="padding:7px 0;color:#667987;font-size:13px">{html_lib.escape(str(label))}</td><td style="padding:7px 0;text-align:right;color:#0b1b2b;font-size:13px;font-weight:700">{html_lib.escape(str(value))}</td></tr>'
    table_html=(f'<table style="width:100%;border-collapse:collapse;border-top:1px solid #e8eef2;border-bottom:1px solid #e8eef2;margin:18px 0">{row_html}</table>' if row_html else '')
    cta=""
    if cta_label and cta_url:
        cta=f'<p style="margin:24px 0 8px"><a href="{html_lib.escape(str(cta_url),quote=True)}" style="display:inline-block;background:#0b1b2b;color:#fff;text-decoration:none;border-radius:10px;padding:12px 16px;font-size:13px;font-weight:700">{html_lib.escape(str(cta_label))}</a></p>'
    footer_html=html_lib.escape(str(footer or "Werkstuur · van melding naar een werkbare opdracht."))
    return ('<!doctype html><html><body style="margin:0;background:#f3f7f9;font-family:Arial,sans-serif;color:#0b1b2b">'
            '<div style="max-width:620px;margin:0 auto;padding:28px 14px"><div style="background:#fff;border:1px solid #dfe8ee;border-radius:18px;padding:26px">'
            '<div style="font-size:11px;letter-spacing:.14em;color:#3084a8;font-weight:800;margin-bottom:10px">WERKSTUUR</div>'
            f'<h1 style="font-size:24px;line-height:1.2;margin:0 0 12px">{safe_title}</h1>'
            f'<p style="font-size:14px;line-height:1.65;color:#526978;margin:0 0 16px">{safe_intro}</p>'
            f'{table_html}{cta}<p style="font-size:11px;color:#82929d;line-height:1.55;margin:22px 0 0">{footer_html}</p>'
            '</div></div></body></html>')

def _send_via_https(recipients, subject, text_body, html_body, reply_to):
    payload = {"recipients":recipients, "subject":str(subject)[:180],
               "text":str(text_body), "html":str(html_body or ""),
               "reply_to":_valid_email(reply_to or SMTP_REPLY_TO)}
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    nonce = secrets.token_hex(16)
    timestamp = str(int(time.time()))
    signed = (timestamp + "\n" + nonce + "\n" + hashlib.sha256(body).hexdigest()).encode("ascii")
    signature = hmac.new(WEBMAIL_RELAY_SECRET.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    headers = {"Content-Type":"application/json", "X-Werkstuur-Timestamp":timestamp,
               "X-Werkstuur-Nonce":nonce, "X-Werkstuur-Signature":signature}
    # The same nonce makes a retry safe if delivery succeeded but the response was lost.
    for attempt in range(2):
        try:
            response = httpx.post(WEBMAIL_RELAY_URL, content=body, headers=headers,
                                  timeout=20, follow_redirects=False)
            if response.status_code != 200:
                _record_mail_result(False, "HTTPS-mailroute gaf HTTP " + str(response.status_code))
                return {"ok":False, "reason":"send_failed"}
            result = response.json()
            if result.get("ok") is not True or result.get("id") != nonce:
                _record_mail_result(False, "HTTPS-mailroute gaf geen geldige ontvangstbevestiging")
                return {"ok":False, "reason":"send_failed"}
            _record_mail_result(True)
            return {"ok":True, "recipients":len(recipients)}
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            if attempt == 0:
                continue
            _record_mail_result(False, "HTTPS-mailroute niet bereikbaar: " + type(exc).__name__)
        except Exception as exc:
            _record_mail_result(False, "HTTPS-mailroute: " + type(exc).__name__)
            break
    return {"ok":False, "reason":"send_failed"}

def _send_email(to, subject, text_body, html_body=None, reply_to=None):
    recipients=[]
    for item in (to if isinstance(to,(list,tuple,set)) else [to]):
        addr=_valid_email(item)
        if addr and addr.lower() not in [x.lower() for x in recipients]:recipients.append(addr)
    if not recipients:return {"ok":False,"reason":"no_recipients"}
    if not _mail_configured():return {"ok":False,"reason":"not_configured"}
    if "\r" in str(subject) or "\n" in str(subject):
        return {"ok":False,"reason":"invalid_subject"}
    if MAIL_TRANSPORT == "https":
        return _send_via_https(recipients, subject, text_body, html_body, reply_to)
    msg=EmailMessage()
    msg["Subject"]=str(subject)[:180]
    msg["From"]=formataddr((SMTP_FROM_NAME,SMTP_FROM_EMAIL))
    msg["To"]=", ".join(recipients)
    rt=_valid_email(reply_to or SMTP_REPLY_TO)
    if rt:msg["Reply-To"]=rt
    msg.set_content(str(text_body))
    if html_body:msg.add_alternative(str(html_body),subtype="html")
    context=ssl.create_default_context()
    try:
        if SMTP_SECURITY=="ssl":
            with smtplib.SMTP_SSL(SMTP_HOST,SMTP_PORT,timeout=15,context=context) as client:
                client.login(SMTP_USERNAME,SMTP_PASSWORD);client.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST,SMTP_PORT,timeout=15) as client:
                client.ehlo()
                if SMTP_SECURITY in ("tls","starttls"):
                    client.starttls(context=context);client.ehlo()
                client.login(SMTP_USERNAME,SMTP_PASSWORD);client.send_message(msg)
        _record_mail_result(True)
        return {"ok":True,"recipients":len(recipients)}
    except Exception as exc:
        _record_mail_result(False,_sanitize_error_message(exc))
        return {"ok":False,"reason":"send_failed"}

def _queue_email(to, subject, text_body, html_body=None, reply_to=None):
    if not _mail_configured():return False
    def runner():
        try:_send_email(to,subject,text_body,html_body,reply_to)
        except Exception as exc:_record_mail_result(False,_sanitize_error_message(exc))
    threading.Thread(target=runner,daemon=True,name="werkstuur-mail").start()
    return True

def _organization_contact(org_id):
    org=organization_by_id(org_id) or {}
    support=_valid_email(org.get("support_email") or get_setting("support_email","",organization_id=org_id) or SMTP_REPLY_TO)
    return org,support

def queue_public_intake_emails(org_id,row,missing,score):
    if not _mail_configured():return {"customer":False,"planner":False}
    org,support=_organization_contact(org_id)
    org_name=org.get("name") or get_setting("company_name","de serviceorganisatie",organization_id=org_id)
    case_no=row.get("case_no") or "—"
    customer_email=_valid_email(row.get("email"))
    queued_customer=False
    if customer_email:
        subject=f"Melding ontvangen · {case_no}"
        intro=f"Je servicemelding bij {org_name} is ontvangen. Bewaar onderstaande referentie; je hoeft de melding niet opnieuw te versturen."
        rows=[("Referentie",case_no),("Type",row.get("type") or "—"),("Status","Wordt beoordeeld")]
        if missing:rows.append(("Vervolg",f"Mogelijk nog {len(missing)} aanvulling(en) nodig"))
        text=f"{intro}\n\nReferentie: {case_no}\nType: {row.get('type') or '—'}\n\n{('Er kan contact met je worden opgenomen voor aanvullende informatie.' if missing else 'De melding bevat voldoende informatie voor de eerste beoordeling.')}"
        queued_customer=_queue_email(customer_email,subject,text,_email_shell("Melding ontvangen",intro,rows,footer=f"Vragen? Neem contact op via {support or 'de serviceorganisatie'}."),reply_to=support)
    users=resp_data(sb.table("users").select("email,role,active").eq("organization_id",org_id).eq("active",True).execute())
    planner_recipients=[_valid_email(x.get("email")) for x in users if x.get("role") in ("admin","planner")]
    planner_recipients=[x for x in planner_recipients if x]
    if support:planner_recipients.append(support)
    planner_recipients=list(dict.fromkeys(planner_recipients))[:12]
    queued_planner=False
    if planner_recipients:
        subject=f"Nieuwe klantintake · {case_no} · {row.get('customer') or 'Klant'}"
        intro="Er is een nieuwe klantintake binnengekomen in Werkstuur. Open de omgeving om de melding te beoordelen en waar nodig informatie aan te vullen."
        rows=[("Case",case_no),("Klant",row.get("customer") or "—"),("Type",row.get("type") or "—"),("Gereedheid",f"{int(score or 0)}%"),("Ontbreekt",str(len(missing or [])))]
        text=f"Nieuwe Werkstuur-intake\nCase: {case_no}\nKlant: {row.get('customer') or '—'}\nType: {row.get('type') or '—'}\nGereedheid: {int(score or 0)}%\nOntbrekende punten: {len(missing or [])}\n\nOpen: {APP_PUBLIC_URL}"
        queued_planner=_queue_email(planner_recipients,subject,text,_email_shell("Nieuwe klantintake",intro,rows,"Open Werkstuur",APP_PUBLIC_URL),reply_to=customer_email or support)
    return {"customer":queued_customer,"planner":queued_planner}

def queue_account_welcome(row):
    if not _mail_configured():return False
    email=_valid_email(row.get("email"))
    if not email:return False
    try:org=organization_by_id(row.get("organization_id")) or {}
    except Exception:org={}
    intro=f"Er is een Werkstuur-account voor je aangemaakt voor {org.get('name') or 'jouw organisatie'}. Gebruik het tijdelijke wachtwoord dat je van je beheerder ontvangt en wijzig dit na je eerste login."
    rows=[("Account",email),("Rol",row.get("role") or "gebruiker")]
    text=f"Je Werkstuur-account is aangemaakt.\n\nInloggen: {APP_PUBLIC_URL}\nAccount: {email}\n\nGebruik het tijdelijke wachtwoord van je beheerder en wijzig dit na de eerste login."
    return _queue_email(email,"Je Werkstuur-account is aangemaakt",text,_email_shell("Welkom bij Werkstuur",intro,rows,"Inloggen",APP_PUBLIC_URL))

def queue_password_changed_notice(row,by_admin=False):
    if not _mail_configured():return False
    email=_valid_email(row.get("email"))
    if not email:return False
    intro="Het wachtwoord van je Werkstuur-account is gewijzigd." + (" Dit is uitgevoerd door een beheerder." if by_admin else "") + " Was jij dit niet, neem dan direct contact op met je beheerder."
    text=f"{intro}\n\nWerkstuur: {APP_PUBLIC_URL}"
    return _queue_email(email,"Werkstuur-wachtwoord gewijzigd",text,_email_shell("Wachtwoord gewijzigd",intro,[("Account",email)],"Naar Werkstuur",APP_PUBLIC_URL))

def _reset_secret():
    raw=os.environ.get("PASSWORD_RESET_SECRET") or SUPABASE_SECRET_KEY
    return hashlib.sha256(("werkstuur-password-reset|"+raw).encode()).digest()

def _b64url(data):return base64.urlsafe_b64encode(data).rstrip(b"=").decode()
def _b64url_decode(value):
    value=str(value);return base64.urlsafe_b64decode(value+"="*((4-len(value)%4)%4))

def create_password_reset_token(row):
    fp=hashlib.sha256(str(row.get("password_hash") or "").encode()).hexdigest()[:24]
    payload={"uid":int(row["id"]),"exp":int(time.time())+PASSWORD_RESET_MINUTES*60,"fp":fp,"nonce":secrets.token_hex(8)}
    raw=json.dumps(payload,separators=(",",":"),sort_keys=True).encode()
    part=_b64url(raw);sig=_b64url(hmac.new(_reset_secret(),part.encode(),hashlib.sha256).digest())
    return part+"."+sig

def verify_password_reset_token(token):
    try:
        part,sig=str(token or "").split(".",1)
        expected=_b64url(hmac.new(_reset_secret(),part.encode(),hashlib.sha256).digest())
        if not hmac.compare_digest(sig,expected):return None
        payload=json.loads(_b64url_decode(part))
        if int(payload.get("exp") or 0)<int(time.time()):return None
        row=first(sb.table("users").select("*").eq("id",int(payload.get("uid") or 0)).limit(1).execute())
        if not row or not row.get("active"):return None
        fp=hashlib.sha256(str(row.get("password_hash") or "").encode()).hexdigest()[:24]
        if not hmac.compare_digest(str(payload.get("fp") or ""),fp):return None
        return row
    except Exception:return None

def queue_password_reset(row):
    if not _mail_configured():return False
    email=_valid_email(row.get("email"))
    if not email:return False
    token=create_password_reset_token(row)
    reset_url=f"{APP_PUBLIC_URL}/?reset={quote(token)}"
    intro=f"Er is een verzoek gedaan om het wachtwoord van je Werkstuur-account opnieuw in te stellen. De link is {PASSWORD_RESET_MINUTES} minuten geldig."
    text=f"{intro}\n\nWachtwoord herstellen: {reset_url}\n\nHeb je dit niet aangevraagd? Dan kun je deze e-mail negeren."
    return _queue_email(email,"Werkstuur · wachtwoord herstellen",text,_email_shell("Wachtwoord herstellen",intro,[("Geldig",f"{PASSWORD_RESET_MINUTES} minuten")],"Nieuw wachtwoord instellen",reset_url,"Heb je dit niet aangevraagd? Dan hoef je niets te doen."))

_org_local = threading.local()

def _set_org_context(org_id):
    _org_local.organization_id = int(org_id) if org_id not in (None, "") else None

def current_org_id(required=False):
    org_id = getattr(_org_local, "organization_id", None)
    if required and not org_id:
        raise RuntimeError("organization context ontbreekt")
    return org_id

def organization_by_id(org_id):
    if not org_id:
        return None
    return first(sb.table("organizations").select("*").eq("id", int(org_id)).limit(1).execute())

def current_organization():
    return organization_by_id(current_org_id())

def resolve_public_organization(token):
    token = str(token or "")
    if not token:
        return None
    row = first(
        sb.table("organization_settings")
        .select("organization_id")
        .eq("key", "intake_token")
        .eq("value", token)
        .limit(1)
        .execute()
    )
    if not row:
        return None
    org = organization_by_id(row["organization_id"])
    if not org or org.get("status") in ("suspended", "archived"):
        return None
    _set_org_context(org["id"])
    return org

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def sha_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def resp_data(resp):
    return getattr(resp, "data", None) or []

def first(resp):
    data = resp_data(resp)
    return data[0] if data else None

def get_setting(key, default=None, organization_id=None):
    org_id = organization_id if organization_id is not None else current_org_id()
    if org_id:
        row = first(
            sb.table("organization_settings")
            .select("value")
            .eq("organization_id", int(org_id))
            .eq("key", key)
            .limit(1)
            .execute()
        )
        if row:
            return row["value"]
    row = first(sb.table("settings").select("value").eq("key", key).limit(1).execute())
    return row["value"] if row else default

def set_setting(key, value, organization_id=None):
    org_id = organization_id if organization_id is not None else current_org_id()
    if org_id:
        sb.table("organization_settings").upsert({
            "organization_id": int(org_id),
            "key": key,
            "value": str(value)
        }, on_conflict="organization_id,key").execute()
        return
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
    org_id = current_org_id(required=True)
    sb.table("audit").insert({
        "organization_id": org_id,
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
        "company_name": "Werkstuur Pilot",
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
        "brand_name":"Werkstuur",
        "brand_accent":"#62d0ff",
        "support_email":"",
        "privacy_url":"",
        "customer_portal_title":"Service-intake",
    }
    existing = {r["key"] for r in resp_data(sb.table("settings").select("key").execute())}
    missing = [{"key":k,"value":v} for k,v in defaults.items() if k not in existing]
    if missing:
        sb.table("settings").insert(missing).execute()

    internal = first(sb.table("organizations").select("*").eq("slug","werkstuur-internal").limit(1).execute())
    if not internal:
        internal = first(sb.table("organizations").insert({
            "name":"Werkstuur Internal","slug":"werkstuur-internal","status":"active","plan":"internal",
            "created_at":now_iso(),"updated_at":now_iso()
        }).execute())
    org_id = internal["id"]
    org_settings = {r["key"] for r in resp_data(
        sb.table("organization_settings").select("key").eq("organization_id",org_id).execute()
    )}
    org_missing = [{"organization_id":org_id,"key":k,"value":v} for k,v in defaults.items() if k not in org_settings]
    if org_missing:
        sb.table("organization_settings").insert(org_missing).execute()

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
                "organization_id":org_id,
                "is_platform_owner":True,
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
    return first(sb.table("users").select("id,email,display_name,role,active,created_at,organization_id,is_platform_owner").eq("id", uid).limit(1).execute())

def create_session(user_id):
    token = secrets.token_urlsafe(40)
    expires = datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)
    u = find_user(user_id)
    sb.table("sessions").insert({
        "token_hash": sha_token(token),
        "user_id": user_id,
        "active_organization_id": u.get("organization_id") if u else None,
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
    row = first(
        sb.table("sessions")
        .select("user_id,expires_at,active_organization_id")
        .eq("token_hash", sha_token(token))
        .limit(1).execute()
    )
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

    base_org_id = u.get("organization_id")
    effective_org_id = row.get("active_organization_id") if u.get("is_platform_owner") else base_org_id
    effective_org_id = effective_org_id or base_org_id
    org = organization_by_id(effective_org_id)
    if not org:
        return None
    if not u.get("is_platform_owner") and org.get("status") in ("suspended","archived"):
        return None

    u["base_organization_id"] = base_org_id
    u["organization_id"] = effective_org_id
    u["organization_name"] = org.get("name")
    u["organization_slug"] = org.get("slug")
    u["organization_status"] = org.get("status")
    u["organization_plan"] = org.get("plan")
    _set_org_context(effective_org_id)
    return u

def public_config():
    return {
        "company": get_setting("company_name","Werkstuur Pilot"),
        "enabled_service_types": setting_json("enabled_service_types",["Laadpaal","Zonnepanelen","Thuisbatterij","Elektro"]),
        "enabled_brands": setting_json("enabled_brands",{}),
        "brand_name": get_setting("brand_name","Werkstuur"),
        "brand_accent": get_setting("brand_accent","#62d0ff"),
        "support_email": get_setting("support_email",""),
        "privacy_url": get_setting("privacy_url",""),
        "customer_portal_title": get_setting("customer_portal_title","Service-intake"),
    }

def onboarding_payload():
    return {
        "complete": get_setting("onboarding_complete","0") == "1",
        "company_name": get_setting("company_name","Werkstuur Pilot"),
        "enabled_service_types": setting_json("enabled_service_types",["Laadpaal","Zonnepanelen","Thuisbatterij","Elektro"]),
        "enabled_brands": setting_json("enabled_brands",{}),
        "assumptions": economic_assumptions(),
        "branding":{
            "brand_name":get_setting("brand_name","Werkstuur"),
            "brand_accent":get_setting("brand_accent","#62d0ff"),
            "support_email":get_setting("support_email",""),
            "privacy_url":get_setting("privacy_url",""),
            "customer_portal_title":get_setting("customer_portal_title","Service-intake"),
        },
        "intake_token":get_setting("intake_token"),
    }

def safe_filename(name):
    name = Path(name or "attachment").name
    name = re.sub(r"[^A-Za-z0-9._-]+","_",name)[:120]
    return name or "attachment"

def get_case(cid):
    return first(sb.table("cases").select("*").eq("organization_id",current_org_id(required=True)).eq("id", cid).limit(1).execute())

def can_access_case(user, case):
    if not case:
        return False
    if user["role"] in ("admin","planner"):
        return True
    return case.get("assigned_to") == user["id"]

def case_actor_in_organization(user):
    org_id = user.get("organization_id")
    return bool(org_id) and user.get("base_organization_id", org_id) == org_id

def visible_cases(user):
    q = sb.table("cases").select("*").eq("organization_id",current_org_id(required=True)).order("updated_at", desc=True)
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
    try:
        c["analysis"]=analysis_engine.for_case(c)
    except (ValueError, TypeError):
        c["analysis"]={"unavailable":True,"warnings":["Deze oudere melding heeft onvoldoende geldige invoer. Laat de planner de klacht en het installatietype controleren."]}
    return c

def calculate_metrics():
    cases = resp_data(sb.table("cases").select("*").eq("organization_id",current_org_id(required=True)).execute())
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
    cases = cases if cases is not None else resp_data(sb.table("cases").select("*").eq("organization_id",current_org_id(required=True)).execute())
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
    return first(sb.table("pilots").select("*").eq("organization_id",current_org_id(required=True)).eq("active",True).order("id",desc=True).limit(1).execute())

def pilot_progress():
    p=active_pilot()
    if not p:
        return {"active":False}
    m=calculate_metrics()
    start=date.fromisoformat(p["start_date"]); end=date.fromisoformat(p["end_date"]); today=date.today()
    total=max(1,(end-start).days+1); elapsed=max(0,min(total,(today-start).days+1))
    avg_plan=None
    outcome_cases=[c for c in resp_data(sb.table("cases").select("outcome_planner_minutes,outcome_recorded_at").eq("organization_id",current_org_id(required=True)).execute()) if c.get("outcome_recorded_at") and c.get("outcome_planner_minutes") is not None]
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
    cases=[c for c in resp_data(sb.table("cases").select("*").eq("organization_id",current_org_id(required=True)).execute()) if c.get("outcome_recorded_at")]
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
        x,cnt=info.most_common(1)[0]; rec.append(f"Maak '{x}' een expliciet voorcheckveld; {cnt} keer als ontbrekend geregistreerd.")
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
    org_id=current_org_id(required=True)
    return {
        "meta":{"app_name":APP_NAME,"app_version":APP_VERSION,"exported_at":now_iso(),"contains_passwords":False,"contains_attachment_bytes":False,"organization_id":org_id},
        "organization":organization_by_id(org_id),
        "settings":resp_data(sb.table("organization_settings").select("key,value").eq("organization_id",org_id).execute()),
        "users":resp_data(sb.table("users").select("id,email,display_name,role,active,created_at").eq("organization_id",org_id).execute()),
        "customers":resp_data(sb.table("customer_records").select("*").eq("organization_id",org_id).execute()),
        "support_tickets":resp_data(sb.table("support_tickets").select("id,organization_id,created_by,ticket_no,subject,description,category,status,resolution,version,created_at,updated_at,resolved_at").eq("organization_id",org_id).execute()),
        "pilots":resp_data(sb.table("pilots").select("*").eq("organization_id",org_id).execute()),
        "pilot_snapshots":resp_data(sb.table("pilot_snapshots").select("*").eq("organization_id",org_id).execute()),
        "cases":resp_data(sb.table("cases").select("*").eq("organization_id",org_id).execute()),
        "notes":resp_data(sb.table("notes").select("*").eq("organization_id",org_id).execute()),
        "attachments":resp_data(sb.table("attachments").select("id,case_id,filename,storage_path,content_type,size_bytes,created_by,created_at").eq("organization_id",org_id).execute()),
        "audit":resp_data(sb.table("audit").select("*").eq("organization_id",org_id).execute()),
    }

def create_team_user(email,name,role,password):
    email=(email or "").lower().strip(); name=(name or "").strip()
    if not email or "@" not in email:raise ValueError("ongeldig e-mailadres")
    if not name:raise ValueError("naam ontbreekt")
    if role not in ("admin","planner","technician"):raise ValueError("ongeldige rol")
    if not password or len(password)<12:raise ValueError("wachtwoord minimaal 12 tekens")
    existing=find_user_by_email(email)
    if existing:
        if existing.get("organization_id") != current_org_id(required=True):
            raise ValueError("dit e-mailadres is al in gebruik")
        return existing,False
    row=first(sb.table("users").insert({
        "email":email,"display_name":name,"role":role,"organization_id":current_org_id(required=True),"is_platform_owner":False,
        "password_hash":core.hash_password(password),"active":True,"created_at":now_iso()
    }).execute())
    queue_account_welcome(row)
    return row,True


def _slugify(value):
    slug=re.sub(r"[^a-z0-9]+","-",str(value or "").lower()).strip("-")
    return slug[:60] or "organisatie"

def initialize_organization_settings(org_id, name, support_email="", privacy_url=""):
    global_defaults = resp_data(sb.table("settings").select("key,value").execute())
    rows=[]
    for item in global_defaults:
        value=item["value"]
        if item["key"]=="company_name": value=name
        elif item["key"]=="onboarding_complete": value="0"
        elif item["key"]=="intake_token": value=secrets.token_urlsafe(24)
        elif item["key"]=="brand_name": value="Werkstuur"
        elif item["key"]=="support_email": value=support_email or ""
        elif item["key"]=="privacy_url": value=privacy_url or ""
        elif item["key"]=="software_monthly_cost": value="0"
        rows.append({"organization_id":org_id,"key":item["key"],"value":str(value)})
    if rows:
        sb.table("organization_settings").upsert(rows,on_conflict="organization_id,key").execute()

def owner_organizations_payload():
    orgs=resp_data(sb.table("organizations").select("*").order("created_at").execute())
    result=[]
    for org in orgs:
        oid=org["id"]
        users_count=len(resp_data(sb.table("users").select("id").eq("organization_id",oid).eq("active",True).execute()))
        cases_rows=resp_data(sb.table("cases").select("id,created_at").eq("organization_id",oid).order("created_at",desc=True).limit(1).execute())
        cases_count=_count_rows("cases",[("eq","organization_id",oid)])
        active_pilots=_count_rows("pilots",[("eq","organization_id",oid),("eq","active",True)])
        onboarding=get_setting("onboarding_complete","0",organization_id=oid)=="1"
        result.append({
            **org,
            "active_users":users_count,
            "cases":cases_count,
            "active_pilot":active_pilots>0,
            "onboarding_complete":onboarding,
            "last_activity":cases_rows[0]["created_at"] if cases_rows else None,
        })
    return result

def create_organization(body):
    name=str(body.get("name") or "").strip()
    if not name:
        raise ValueError("organisatienaam verplicht")
    slug=_slugify(body.get("slug") or name)
    if first(sb.table("organizations").select("id").eq("slug",slug).limit(1).execute()):
        raise ValueError("slug bestaat al")
    status=str(body.get("status") or "onboarding")
    plan=str(body.get("plan") or "pilot")
    if status not in ("onboarding","pilot","active","suspended","archived"):
        raise ValueError("ongeldige status")
    if plan not in ("internal","pilot","starter","growth","enterprise"):
        raise ValueError("ongeldig plan")
    support=str(body.get("support_email") or "").strip()
    privacy=str(body.get("privacy_url") or "").strip()
    if support and "@" not in support:
        raise ValueError("ongeldig support e-mailadres")
    if privacy and not re.match(r"^https?://",privacy,re.I):
        raise ValueError("ongeldige privacy-URL")
    admin_email=str(body.get("admin_email") or "").lower().strip()
    admin_name=str(body.get("admin_name") or "").strip()
    admin_password=str(body.get("admin_password") or "")
    if not _valid_email(admin_email):raise ValueError("geldig beheerder e-mailadres verplicht")
    if not admin_name:raise ValueError("beheerdernaam verplicht")
    if len(admin_password)<12:raise ValueError("tijdelijk beheerderwachtwoord minimaal 12 tekens")
    if find_user_by_email(admin_email):raise ValueError("e-mailadres bestaat al")
    org=first(sb.table("organizations").insert({
        "name":name,"slug":slug,"status":status,"plan":plan,
        "support_email":support or None,"privacy_url":privacy or None,
        "created_at":now_iso(),"updated_at":now_iso()
    }).execute())
    initialize_organization_settings(org["id"],name,support,privacy)

    admin_row=first(sb.table("users").insert({
        "email":admin_email,"display_name":admin_name,"role":"admin",
        "organization_id":org["id"],"is_platform_owner":False,
        "password_hash":core.hash_password(admin_password),"active":True,"created_at":now_iso()
    }).execute())
    queue_account_welcome(admin_row)
    return org


def organization_write_path(path):
    return (path.startswith(("/api/accounts", "/api/customers", "/api/cases", "/api/pilot"))
            or path in ("/api/settings", "/api/onboarding"))


def clean_customer(body, partial=False):
    fields={"name":160,"email":254,"phone":60,"address":240,"postal_code":30,"city":100,"notes":3000}
    if set(body)-set(fields)-{"version","active"}:raise ValueError("onbekend klantveld")
    clean={}
    for field,limit in fields.items():
        if partial and field not in body:continue
        value=str(body.get(field) or "").strip()
        if len(value)>limit:raise ValueError(f"{field}: maximaal {limit} tekens")
        clean[field]=value
    if (not partial or "name" in body) and not clean.get("name"):raise ValueError("klantnaam verplicht")
    if clean.get("email") and not _valid_email(clean["email"]):raise ValueError("ongeldig e-mailadres")
    if "email" in clean:clean["email"]=clean["email"].lower()
    if "active" in body:
        if not isinstance(body["active"],bool):raise ValueError("ongeldige klantstatus")
        clean["active"]=body["active"]
    return clean


def customer_by_id(customer_id):
    return first(sb.table("customer_records").select("*").eq("organization_id",current_org_id(required=True)).eq("id",int(customer_id)).limit(1).execute())


def update_team_account(actor, uid, body):
    if set(body)-{"display_name","role","active"}:raise ValueError("onbekend accountveld")
    target=first(sb.table("users").select("*").eq("organization_id",current_org_id(required=True)).eq("id",uid).limit(1).execute())
    if not target:raise LookupError("account niet gevonden")
    if target.get("is_platform_owner"):raise PermissionError("het eigenaarsaccount wordt niet via klantbeheer gewijzigd")
    update={}
    if "display_name" in body:
        name=str(body["display_name"] or "").strip()
        if not name or len(name)>160:raise ValueError("naam verplicht, maximaal 160 tekens")
        update["display_name"]=name
    if "role" in body:
        if body["role"] not in ("admin","planner","technician"):raise ValueError("ongeldige rol")
        update["role"]=body["role"]
    if "active" in body:
        if not isinstance(body["active"],bool):raise ValueError("ongeldige accountstatus")
        update["active"]=body["active"]
    if uid==actor["id"] and (update.get("active") is False or update.get("role",target["role"])!="admin"):
        raise ValueError("je eigen beheerderstoegang moet actief blijven")
    losing_admin=target["role"]=="admin" and target.get("active") and (update.get("active") is False or update.get("role","admin")!="admin")
    if losing_admin:
        admins=resp_data(sb.table("users").select("id").eq("organization_id",current_org_id(required=True)).eq("role","admin").eq("active",True).execute())
        if len(admins)<=1:raise ValueError("minstens één actieve bedrijfsbeheerder is verplicht")
    if not update:return {k:v for k,v in target.items() if k!="password_hash"}
    row=first(sb.table("users").update(update).eq("organization_id",current_org_id(required=True)).eq("id",uid).execute())
    if update.get("role",target["role"])!=target["role"] or update.get("active") is False:
        sb.table("sessions").delete().eq("user_id",uid).execute()
    create_audit(None,actor["id"],"account_updated",json.dumps({"target_user_id":uid,"changes":update}))
    return {k:v for k,v in row.items() if k!="password_hash"}


def support_tickets_payload(user, owner=False):
    query=sb.table("support_tickets").select("*")
    if not owner:
        query=query.eq("organization_id",current_org_id(required=True))
        if user["role"]=="technician":query=query.eq("created_by",user["id"])
    rows=resp_data(query.order("created_at",desc=True).execute())
    if owner:
        organizations={o["id"]:o["name"] for o in resp_data(sb.table("organizations").select("id,name").execute())}
        for row in rows:row["organization_name"]=organizations.get(row["organization_id"],"Klantbedrijf")
    for row in rows:
        row.pop("request_key",None);row.pop("fingerprint",None)
    return rows


def create_support_ticket(user, body):
    if not case_actor_in_organization(user):raise PermissionError("gebruik het eigen teamaccount om een melding te maken")
    subject=str(body.get("subject") or "").strip();description=str(body.get("description") or "").strip()
    category=body.get("category");request_key=str(body.get("request_key") or "")
    if not 4<=len(subject)<=180:raise ValueError("onderwerp: 4 tot 180 tekens")
    if not 10<=len(description)<=6000:raise ValueError("omschrijving: 10 tot 6000 tekens")
    if category not in ("technical","question","incident"):raise ValueError("ongeldige categorie")
    if not re.fullmatch(r"[a-zA-Z0-9-]{16,80}",request_key):raise ValueError("ongeldige aanvraagcode")
    org_id=current_org_id(required=True)
    fingerprint=hashlib.sha256(json.dumps([subject,description,category],ensure_ascii=False).encode()).hexdigest()
    existing=first(sb.table("support_tickets").select("*").eq("organization_id",org_id).eq("created_by",user["id"]).eq("request_key",request_key).limit(1).execute())
    if existing:
        if existing["fingerprint"]!=fingerprint:raise ValueError("deze aanvraagcode is al gebruikt; open een nieuwe melding")
        row=existing;created=False
    else:
        row=first(sb.table("support_tickets").insert({
            "organization_id":org_id,"created_by":user["id"],"ticket_no":"WS-SUP-"+secrets.token_hex(5).upper(),
            "subject":subject,"description":description,"category":category,"status":"open","resolution":"",
            "version":1,"request_key":request_key,"fingerprint":fingerprint,"created_at":now_iso(),"updated_at":now_iso()
        }).execute());created=True
        create_audit(None,user["id"],"support_ticket_created",row["ticket_no"])
    return {k:v for k,v in row.items() if k not in ("request_key","fingerprint")},created


class Handler(BaseHTTPRequestHandler):
    server_version="WerkstuurCloud/1.4"

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

    def _cors_headers(self):
        origin=(self.headers.get("Origin") or "").rstrip("/")
        path=urlparse(self.path).path
        if path=="/api/public-contact" and origin in PUBLIC_SITE_ORIGINS:
            return {"Access-Control-Allow-Origin":origin,"Vary":"Origin","Access-Control-Allow-Headers":"Content-Type","Access-Control-Allow-Methods":"POST, OPTIONS"}
        return {}

    def _json(self,obj,status=200,extra_headers=None):
        raw=json.dumps(obj,ensure_ascii=False,default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(raw)))
        self.send_header("Cache-Control","no-store")
        self._security_headers()
        headers={**self._cors_headers(),**(extra_headers or {})}
        for k,v in headers.items():self.send_header(k,v)
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
        _set_org_context(None)
        return user_from_token(self._cookie_token())

    def _need(self,roles=None):
        u=self._user()
        if not u:self._json({"error":"unauthorized"},401);return None
        if roles and u["role"] not in roles:self._json({"error":"forbidden"},403);return None
        return u

    def _need_owner(self):
        u=self._user()
        if not u:self._json({"error":"unauthorized"},401);return None
        if not u.get("is_platform_owner"):self._json({"error":"forbidden"},403);return None
        return u

    def _check_origin(self):
        if self.command in ("GET","HEAD","OPTIONS"):return True
        origin=(self.headers.get("Origin") or "").rstrip("/")
        host=self.headers.get("Host")
        if not origin:return True
        path=urlparse(self.path).path
        if path=="/api/public-contact" and origin in PUBLIC_SITE_ORIGINS:return True
        try:return urlparse(origin).netloc==host
        except:return False

    def do_OPTIONS(self):
        path=urlparse(self.path).path
        if path=="/api/public-contact":
            origin=(self.headers.get("Origin") or "").rstrip("/")
            if origin not in PUBLIC_SITE_ORIGINS:
                self.send_response(403);self.end_headers();return
            self.send_response(204)
            for k,v in self._cors_headers().items():self.send_header(k,v)
            self._security_headers();self.end_headers();return
        self.send_response(204);self._security_headers();self.end_headers()

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
        public_files = {"/index.html", "/intake.html", "/app.js", "/workspace-v200.css",
                        "/command-v210.css", "/command-v210.js",
                        "/analysis-ui-v201.css", "/refinements-v203.js", "/refinements-v203.css",
                        "/intake-ui-v200.js", "/manifest.webmanifest", "/apple-touch-icon.png",
                        "/icon-192.png", "/icon-512.png"}
        if path not in public_files:self.send_error(404);return
        safe=(STATIC/path.lstrip("/")).resolve()
        if STATIC.resolve() not in safe.parents and safe!=STATIC.resolve():self.send_error(403);return
        if not safe.exists() or not safe.is_file():self.send_error(404);return
        data=safe.read_bytes();ctype=mimetypes.guess_type(str(safe))[0] or "application/octet-stream"
        self.send_response(200);self.send_header("Content-Type",ctype);self.send_header("Content-Length",str(len(data)))
        self.send_header("Cache-Control","public, max-age=300" if path not in ("/index.html","/intake.html","/app.js") else "no-cache")
        self._security_headers();self.end_headers();self.wfile.write(data)

    def do_GET(self):
        _set_org_context(None)
        try:
            p=urlparse(self.path);path=p.path;q=parse_qs(p.query)
            if path=="/api/health":
                try:
                    sb.table("settings").select("key").limit(1).execute()
                    return self._json({"ok":True,"name":APP_NAME,"version":APP_VERSION,"backend":"supabase","database":"ok"})
                except Exception:
                    _reset_supabase_client()
                    return self._json({"ok":False,"name":APP_NAME,"version":APP_VERSION,"backend":"supabase","database":"unavailable"},503)
            if path=="/api/version":return self._json({"name":APP_NAME,"version":APP_VERSION,"build":APP_BUILD})
            if path=="/api/analysis-status":
                u=self._need(("admin","planner"))
                if not u:return
                return self._json(analysis_engine.self_check())
            if path=="/api/system-status":
                u=self._need(("admin",))
                if not u:return
                return self._json(system_status_payload(u))
            if path=="/api/public-info":
                token=q.get("token",[""])[0]
                org=resolve_public_organization(token)
                if not org:return self._json({"error":"invalid token"},403)
                return self._json(public_config())
            if path=="/api/owner/organizations":
                u=self._need_owner()
                if not u:return
                return self._json(owner_organizations_payload())
            if path=="/api/owner/support":
                u=self._need_owner()
                if not u:return
                return self._json(support_tickets_payload(u,owner=True))
            if path=="/api/support":
                u=self._need()
                if not u:return
                return self._json(support_tickets_payload(u))
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
                    "brand_name":get_setting("brand_name","Werkstuur"),
                    "brand_accent":get_setting("brand_accent","#62d0ff"),
                    "support_email":get_setting("support_email",""),
                    "privacy_url":get_setting("privacy_url",""),
                    "customer_portal_title":get_setting("customer_portal_title","Service-intake"),
                    "app_version":APP_VERSION,**economic_assumptions()
                })
            if path in ("/api/users","/api/accounts"):
                u=self._need(("admin","planner") if path=="/api/users" else ("admin",))
                if not u:return
                rows=resp_data(sb.table("users").select("id,email,display_name,role,active,created_at,is_platform_owner").eq("organization_id",current_org_id(required=True)).order("role").order("display_name").execute())
                return self._json(rows)
            if path=="/api/customers":
                u=self._need(("admin","planner"))
                if not u:return
                return self._json(resp_data(sb.table("customer_records").select("*").eq("organization_id",current_org_id(required=True)).order("name").execute()))
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
                rows=resp_data(sb.table("pilot_snapshots").select("*").eq("organization_id",current_org_id(required=True)).eq("pilot_id",p["id"]).order("snapshot_date").execute()) if p else []
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
                rows=resp_data(sb.table("audit").select("*").eq("organization_id",current_org_id(required=True)).order("created_at",desc=True).limit(250).execute())
                # enrich user display
                for r in rows:
                    if r.get("user_id"):
                        x=find_user(r["user_id"]);r["display_name"]=x["display_name"] if x else None
                return self._json(rows)
            if path=="/api/export":
                u=self._need(("admin",))
                if u:
                    if q.get("format",[""])[0]=="zip":
                        payload=export_payload()
                        try:
                            raw=backup_archive.build_archive(payload,lambda key:sb.storage.from_(BUCKET).download(key))
                        except ValueError as exc:
                            return self._json({"error":str(exc)},422)
                        self.send_response(200)
                        self.send_header("Content-Type","application/zip")
                        self.send_header("Content-Disposition",f'attachment; filename="werkstuur-backup-{date.today().isoformat()}.zip"')
                        self.send_header("Content-Length",str(len(raw)))
                        self.send_header("Cache-Control","no-store")
                        self._security_headers();self.end_headers();self.wfile.write(raw);return
                    headers={"Content-Disposition":f'attachment; filename="werkstuur-export-{date.today().isoformat()}.json"'} if q.get("download",[""])[0]=="1" else None
                    return self._json(export_payload(),extra_headers=headers)
                return
            if path=="/api/pilot-reset-summary":
                u=self._need(("admin",))
                if not u:return
                result={}
                for table in ("cases","notes","attachments","audit","pilots","pilot_snapshots"):
                    result[table if table!="audit" else "audit_events"]=len(resp_data(sb.table(table).select("id").eq("organization_id",current_org_id(required=True)).execute()))
                return self._json(result)
            if path.startswith("/api/cases/") and path.endswith("/notes"):
                u=self._need()
                if not u:return
                cid=int(path.split("/")[3]);c=get_case(cid)
                if not can_access_case(u,c):return self._json({"error":"not found"},404)
                rows=resp_data(sb.table("notes").select("*").eq("organization_id",current_org_id(required=True)).eq("case_id",cid).order("created_at").execute())
                for r in rows:
                    x=find_user(r["created_by"]);r["display_name"]=x["display_name"] if x else "Onbekend";r["email"]=x["email"] if x else ""
                return self._json(rows)
            if path.startswith("/api/cases/") and path.endswith("/attachments"):
                u=self._need()
                if not u:return
                cid=int(path.split("/")[3]);c=get_case(cid)
                if not can_access_case(u,c):return self._json({"error":"not found"},404)
                rows=resp_data(sb.table("attachments").select("id,case_id,filename,content_type,size_bytes,created_at").eq("organization_id",current_org_id(required=True)).eq("case_id",cid).order("created_at").execute())
                return self._json(rows)
            if path.startswith("/api/attachments/"):
                u=self._need()
                if not u:return
                aid=int(path.split("/")[3]);a=first(sb.table("attachments").select("*").eq("organization_id",current_org_id(required=True)).eq("id",aid).limit(1).execute())
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
            _record_server_error("GET "+str(locals().get("path","unknown")), e)
            print("GET ERROR",repr(e),file=sys.stderr)
            return self._json({"error":"server_error"},500)

    def do_POST(self):
        _set_org_context(None)
        if not self._check_origin():return self._json({"error":"invalid origin"},403)
        try:
            path=urlparse(self.path).path
            # Public attack surface: bound repeated login attempts and intake spam.
            if path=="/api/login" and not self._rate_limit("login",10,600):return
            if path=="/api/forgot-password" and not self._rate_limit("forgot-password",5,900):return
            if path=="/api/reset-password" and not self._rate_limit("reset-password",10,900):return
            if path=="/api/public-intake" and not self._rate_limit("public-intake",30,3600):return
            if path=="/api/public-contact" and not self._rate_limit("public-contact",8,3600):return
            body=self._body()
            if path=="/api/public-contact":
                # Honeypot: bots usually populate hidden website fields.
                if str(body.get("website") or "").strip():return self._json({"ok":True})
                name=str(body.get("name") or "").strip()[:120]
                email=_valid_email(body.get("email"))
                company=str(body.get("company") or "").strip()[:160]
                message=str(body.get("message") or "").strip()[:3000]
                if not name or not email or len(message)<8:
                    return self._json({"error":"vul naam, geldig e-mailadres en een kort bericht in"},400)
                if not _mail_configured():
                    return self._json({"error":"contactformulier tijdelijk niet beschikbaar; mail naar manuel@werkstuur.nl"},503)
                intro="Er is een nieuwe kennismakingsaanvraag binnengekomen via werkstuur.nl."
                rows=[("Naam",name),("Bedrijf",company or "—"),("E-mail",email)]
                text=f"{intro}\n\nNaam: {name}\nBedrijf: {company or '-'}\nE-mail: {email}\n\nBericht:\n{message}"
                html=_email_shell("Nieuwe kennismakingsaanvraag",intro,rows,footer=message)
                result=_send_email(SALES_EMAIL,"Nieuwe kennismakingsaanvraag · Werkstuur",text,html,reply_to=email)
                if not result.get("ok"):
                    return self._json({"error":"verzenden is tijdelijk niet gelukt; mail naar manuel@werkstuur.nl"},503)
                return self._json({"ok":True})
            if path=="/api/login":
                email=str(body.get("email","")).lower().strip();pwd=str(body.get("password",""))
                row=find_user_by_email(email)
                if not row or not row.get("active") or not core.verify_password(pwd,row["password_hash"]):
                    return self._json({"error":"ongeldige inloggegevens"},401)
                login_org=organization_by_id(row.get("organization_id"))
                if not row.get("is_platform_owner") and (not login_org or login_org.get("status") in ("suspended","archived")):
                    return self._json({"error":"deze organisatie is momenteel gepauzeerd"},403)
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
            if path=="/api/forgot-password":
                email=str(body.get("email") or "").lower().strip()
                row=find_user_by_email(email) if _valid_email(email) else None
                if row and row.get("active"):
                    _set_org_context(row.get("organization_id"))
                    queue_password_reset(row)
                    try:create_audit(None,row["id"],"password_reset_requested","self-service")
                    except Exception:pass
                return self._json({"ok":True,"message":"Als dit e-mailadres bij een actief account hoort, is een herstelmail verstuurd."})
            if path=="/api/reset-password":
                row=verify_password_reset_token(body.get("token"))
                new_password=str(body.get("new_password") or "")
                if not row:return self._json({"error":"de herstel-link is ongeldig of verlopen"},400)
                if len(new_password)<12:return self._json({"error":"nieuw wachtwoord minimaal 12 tekens"},400)
                _set_org_context(row.get("organization_id"))
                sb.table("users").update({"password_hash":core.hash_password(new_password)}).eq("id",row["id"]).execute()
                sb.table("sessions").delete().eq("user_id",row["id"]).execute()
                create_audit(None,row["id"],"password_reset_completed","self-service")
                queue_password_changed_notice(row)
                return self._json({"ok":True})
            if path=="/api/public-intake":
                if body.get("privacy_acknowledged") is not True:return self._json({"error":"privacy-informatie moet eerst worden bevestigd"},400)
                token=str(body.get("token",""))
                org=resolve_public_organization(token)
                if not org:return self._json({"error":"invalid token"},403)
                org_id=org["id"]
                typ=str(body.get("type","Onbekend"));problem=str(body.get("problem",""));extra=body.get("extra") or {}
                try:facts,missing,score,dispatch,prep,fault=analysis_engine.analyze(typ,problem,extra)
                except ValueError as e:return self._json({"error":str(e)},400)
                extra=analysis_engine.clean_extra(extra)
                brand=analysis_engine.canonical_brand(extra.get("manufacturer"));src=analysis_engine.source_for(brand);rk=analysis_engine.route_knowledge(fault["category"],typ,brand);fk=core.ftf_knowledge(fault["category"])
                case_no="WS-"+str(int(time.time()*1000))[-8:]
                row=first(sb.table("cases").insert({
                    "organization_id":org_id,"case_no":case_no,"source":"customer","customer":str(body.get("customer") or "Nieuwe klant"),
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
                        name=safe_filename(file.get("name"));storage_path=f"org/{org_id}/cases/{row['id']}/{secrets.token_hex(12)}-{name}"
                        sb.storage.from_(BUCKET).upload(path=storage_path,file=raw,file_options={"content-type":file.get("type") or "application/octet-stream","upsert":"false"})
                        sb.table("attachments").insert({"organization_id":org_id,"case_id":row["id"],"filename":name,"storage_path":storage_path,"content_type":file.get("type") or "application/octet-stream","size_bytes":len(raw),"created_at":now_iso()}).execute()
                create_audit(row["id"],None,"public_intake","customer self-service; privacy_notice_acknowledged")
                try:mail_queued=queue_public_intake_emails(org_id,row,missing,score)
                except Exception as exc:
                    _record_mail_result(False,_sanitize_error_message(exc));mail_queued={"customer":False,"planner":False}
                return self._json({"ok":True,"case_no":case_no,"score":score,"missing":missing,"route":fault["category"],"confirmation_email_queued":bool(mail_queued.get("customer")),"planner_email_queued":bool(mail_queued.get("planner"))},201)


            if path=="/api/owner/organizations":
                owner=self._need_owner()
                if not owner:return
                try:org=create_organization(body)
                except ValueError as e:return self._json({"error":str(e)},400)
                return self._json(org,201)
            if path=="/api/owner/context":
                owner=self._need_owner()
                if not owner:return
                oid=int(body.get("organization_id") or 0)
                org=organization_by_id(oid)
                if not org:return self._json({"error":"organisatie niet gevonden"},404)
                token=self._cookie_token()
                sb.table("sessions").update({"active_organization_id":oid}).eq("token_hash",sha_token(token)).execute()
                _set_org_context(oid)
                return self._json({"ok":True,"organization":org})

            u=self._need()
            if not u:return

            if organization_write_path(path) and not case_actor_in_organization(u):
                return self._json({"error":"Je bekijkt deze organisatie als eigenaar. Gebruik een teamaccount van deze organisatie om cases bij te werken.","code":"organization_member_required"},403)
            if path=="/api/support":
                try:row,created=create_support_ticket(u,body)
                except PermissionError as e:return self._json({"error":str(e)},403)
                except ValueError as e:return self._json({"error":str(e)},400)
                return self._json(row,201 if created else 200)
            if path=="/api/customers":
                if u["role"] not in ("admin","planner"):return self._json({"error":"forbidden"},403)
                try:values=clean_customer(body)
                except ValueError as e:return self._json({"error":str(e)},400)
                row=first(sb.table("customer_records").insert({**values,"organization_id":current_org_id(required=True),"active":True,"version":1,"created_at":now_iso(),"updated_at":now_iso()}).execute())
                create_audit(None,u["id"],"customer_created",str(row["id"]))
                return self._json(row,201)

            if path=="/api/analysis-preview":
                if u["role"] not in ("admin","planner"):return self._json({"error":"forbidden"},403)
                try:result=analysis_engine.assess(body.get("type"),body.get("problem"),body.get("extra"))
                except ValueError as e:return self._json({"error":str(e)},400)
                return self._json(result)
            if path.startswith("/api/cases/") and path.endswith("/analysis"):
                if u["role"] not in ("admin","planner"):return self._json({"error":"forbidden"},403)
                cid=int(path.split("/")[3]);c=get_case(cid)
                if not can_access_case(u,c):return self._json({"error":"not found"},404)
                try:expected=int(body.get("version",0))
                except (ValueError,TypeError):return self._json({"error":"ongeldige dossierversie"},400)
                if int(c.get("version") or 1)!=expected:return self._json({"error":"version_conflict","remote":enrich_case(c)},409)
                try:result=analysis_engine.assess(c["type"],body.get("problem",c.get("problem")),body.get("extra"))
                except ValueError as e:return self._json({"error":str(e)},400)
                extra=result["observations"]
                update=analysis_engine.case_fields(result)
                update.update({"problem":result["problem"],"manufacturer":result["manufacturer"],"model":extra.get("model", ""),"serial_no":extra.get("serial", ""),"asset":" ".join(x for x in (result["manufacturer"],extra.get("model")) if x and x!="Onbekend") or "Nog te identificeren","version":expected+1,"updated_at":now_iso()})
                row=first(sb.table("cases").update(update).eq("organization_id",current_org_id(required=True)).eq("id",cid).eq("version",expected).execute())
                if not row:return self._json({"error":"version_conflict","remote":enrich_case(get_case(cid))},409)
                create_audit(cid,u["id"],"analysis_updated",json.dumps({"engine_version":result["engine_version"],"triage":result["triage_level"]}))
                return self._json(enrich_case(row))
            if path=="/api/test-email":
                if u["role"]!="admin":return self._json({"error":"forbidden"},403)
                if not _mail_configured():return self._json({"error":"de e-mailverbinding is nog niet volledig geconfigureerd"},503)
                intro="Deze test bevestigt dat Werkstuur transactionele e-mail via de ingestelde mailverbinding kan versturen."
                result=_send_email(u.get("email"),"Werkstuur · testmail",intro,_email_shell("E-mailkoppeling werkt",intro,[('Account',u.get('email') or '—')]),reply_to=SMTP_REPLY_TO)
                return self._json({"ok":bool(result.get("ok"))},200 if result.get("ok") else 503)
            if path=="/api/change-password":
                current=str(body.get("current_password") or "");new=str(body.get("new_password") or "")
                if len(new)<12:return self._json({"error":"nieuw wachtwoord minimaal 12 tekens"},400)
                row=find_user_by_email(u["email"])
                if not core.verify_password(current,row["password_hash"]):return self._json({"error":"huidig wachtwoord onjuist"},403)
                sb.table("users").update({"password_hash":core.hash_password(new)}).eq("id",u["id"]).execute()
                sb.table("sessions").delete().eq("user_id",u["id"]).execute()
                create_audit(None,u["id"],"password_changed","self-service")
                queue_password_changed_notice(row)
                cookie="pf_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0"
                if COOKIE_SECURE:cookie+="; Secure"
                return self._json({"ok":True,"relogin_required":True},200,{"Set-Cookie":cookie})
            if path=="/api/accounts":
                if u["role"]!="admin":return self._json({"error":"forbidden"},403)
                try:row,created=create_team_user(body.get("email"),body.get("display_name"),body.get("role"),body.get("password"))
                except ValueError as e:return self._json({"error":str(e)},400)
                return self._json({"created":created,"user":{k:v for k,v in row.items() if k!="password_hash"}},201 if created else 200)
            if path.startswith("/api/accounts/") and path.endswith("/send-reset-link"):
                if u["role"]!="admin":return self._json({"error":"forbidden"},403)
                uid=int(path.split("/")[3])
                target=first(sb.table("users").select("*").eq("organization_id",current_org_id(required=True)).eq("id",uid).limit(1).execute())
                if not target:return self._json({"error":"account niet gevonden"},404)
                if target.get("is_platform_owner"):return self._json({"error":"gebruik het eigen eigenaarsaccount voor wachtwoordherstel"},403)
                if not _mail_configured():return self._json({"error":"transactionele e-mail is nog niet geconfigureerd"},503)
                queued=queue_password_reset(target)
                if queued:create_audit(None,u["id"],"password_reset_link_sent",str(uid))
                return self._json({"ok":bool(queued)},200 if queued else 503)
            if path.startswith("/api/accounts/") and path.endswith("/reset-password"):
                if u["role"]!="admin":return self._json({"error":"forbidden"},403)
                uid=int(path.split("/")[3]);new=str(body.get("new_password") or "")
                if len(new)<12:return self._json({"error":"nieuw wachtwoord minimaal 12 tekens"},400)
                target=first(sb.table("users").select("*").eq("organization_id",current_org_id(required=True)).eq("id",uid).limit(1).execute())
                if not target:return self._json({"error":"account niet gevonden"},404)
                if target.get("is_platform_owner"):return self._json({"error":"gebruik het eigen eigenaarsaccount voor wachtwoordherstel"},403)
                sb.table("users").update({"password_hash":core.hash_password(new)}).eq("organization_id",current_org_id(required=True)).eq("id",uid).execute()
                sb.table("sessions").delete().eq("user_id",uid).execute()
                create_audit(None,u["id"],"admin_password_reset",str(uid))
                queue_password_changed_notice(target,by_admin=True)
                return self._json({"ok":True})
            if path=="/api/onboarding":
                if u["role"]!="admin":return self._json({"error":"forbidden"},403)
                company=str(body.get("company_name") or "").strip()
                service_types=[x for x in body.get("enabled_service_types",[]) if x in ("Laadpaal","Zonnepanelen","Thuisbatterij","Elektro")]
                if not company or not service_types:return self._json({"error":"bedrijfsnaam en servicetype verplicht"},400)
                set_setting("company_name",company);set_setting("enabled_service_types",json.dumps(service_types,ensure_ascii=False))
                support_email=str(body.get("support_email") or "").strip()
                privacy_url=str(body.get("privacy_url") or "").strip()
                if support_email and "@" not in support_email:return self._json({"error":"ongeldig support e-mailadres"},400)
                if privacy_url and not re.match(r"^https?://",privacy_url,re.I):return self._json({"error":"privacy-URL moet met http:// of https:// beginnen"},400)
                set_setting("support_email",support_email)
                set_setting("privacy_url",privacy_url)
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
                    sb.table("pilots").update({"active":False,"updated_at":now_iso()}).eq("organization_id",current_org_id(required=True)).eq("active",True).execute()
                    sb.table("pilots").insert({
                        "organization_id":current_org_id(required=True),"name":str(pilot.get("name") or "Launch Partner Pilot"),"start_date":pilot.get("start_date") or date.today().isoformat(),
                        "end_date":pilot.get("end_date") or (date.today()+timedelta(days=42)).isoformat(),
                        "baseline_planner_minutes":pilot.get("baseline_planner_minutes"),"baseline_first_time_fix_pct":pilot.get("baseline_first_time_fix_pct"),
                        "baseline_second_visit_pct":pilot.get("baseline_second_visit_pct"),"baseline_remote_resolved_pct":pilot.get("baseline_remote_resolved_pct"),
                        "target_planner_minutes":pilot.get("target_planner_minutes"),"target_first_time_fix_pct":pilot.get("target_first_time_fix_pct"),
                        "target_second_visit_pct":pilot.get("target_second_visit_pct"),"target_remote_resolved_pct":pilot.get("target_remote_resolved_pct"),
                        "notes":str(pilot.get("notes") or ""),"active":True,"created_at":now_iso(),"updated_at":now_iso()
                    }).execute()
                set_setting("onboarding_complete","1")
                org=current_organization()
                if org and org.get("status")=="onboarding":
                    sb.table("organizations").update({
                        "status":"pilot" if pilot.get("create") else "active",
                        "updated_at":now_iso()
                    }).eq("id",org["id"]).execute()
                return self._json({"ok":True,"onboarding":onboarding_payload(),"team_members_created":created,"intake_path":"/intake.html?token="+get_setting("intake_token")},201)
            if path=="/api/pilot":
                if u["role"] not in ("admin","planner"):return self._json({"error":"forbidden"},403)
                sb.table("pilots").update({"active":False,"updated_at":now_iso()}).eq("organization_id",current_org_id(required=True)).eq("active",True).execute()
                row=first(sb.table("pilots").insert({
                    "organization_id":current_org_id(required=True),"name":str(body.get("name") or "Werkstuur Pilot"),"start_date":body.get("start_date") or date.today().isoformat(),
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
                outcome_cases=[c for c in resp_data(sb.table("cases").select("outcome_planner_minutes,outcome_recorded_at").eq("organization_id",current_org_id(required=True)).execute()) if c.get("outcome_recorded_at") and c.get("outcome_planner_minutes") is not None]
                avg=round(sum(float(c["outcome_planner_minutes"]) for c in outcome_cases)/len(outcome_cases),2) if outcome_cases else None
                e=m["economics"]["measured"]
                row=first(sb.table("pilot_snapshots").upsert({
                    "organization_id":current_org_id(required=True),"pilot_id":p["id"],"snapshot_date":date.today().isoformat(),"outcomes":m["outcomes"],"avg_planner_minutes":avg,
                    "first_time_fix_pct":m["first_time_fix_pct"],"second_visit_pct":m["second_visit_pct"],"remote_resolved_pct":m["remote_resolved_pct"],
                    "preventable_second_visit_pct":m["preventable_second_visit_pct"],"measured_planner_value_eur":e["planner_time_value_eur"],
                    "estimated_remote_value_eur":e["estimated_remote_visit_value_eur"],"avoidable_waste_eur":e["estimated_avoidable_waste_eur"]
                },on_conflict="pilot_id,snapshot_date").execute())
                return self._json(row)
            if path=="/api/pilot/close":
                if u["role"] not in ("admin","planner"):return self._json({"error":"forbidden"},403)
                p=active_pilot()
                if not p:return self._json({"error":"no active pilot"},404)
                sb.table("pilots").update({"active":False,"updated_at":now_iso()}).eq("organization_id",current_org_id(required=True)).eq("id",p["id"]).execute()
                r=management_report()
                r.update({"available":True,"pilot":p,"sample_quality":{"outcomes":r["sample_quality"]["outcomes"],"minimum_for_conclusion":10,"sufficient":r["sample_quality"]["outcomes"]>=10},"conclusion":{"status":"positief" if r["decision"]["status"]=="positief_signaal" else "verbeteren" if r["decision"]["status"]!="onvoldoende_data" else "onvoldoende_data","text":r["decision"]["reason"]},"goals":[]})
                return self._json(r)
            if path=="/api/pilot-reset":
                if u["role"]!="admin":return self._json({"error":"forbidden"},403)
                if str(body.get("confirm") or "")!="RESET PILOT DATA":return self._json({"error":"bevestigingstekst klopt niet"},400)
                org_id=current_org_id(required=True)
                atts=resp_data(sb.table("attachments").select("storage_path").eq("organization_id",org_id).execute())
                for table in ("pilot_snapshots","pilots","notes","attachments","audit","cases"):
                    sb.table(table).delete().eq("organization_id",org_id).neq("id",0).execute()
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
                customer=None
                if body.get("customer_id") is not None:
                    try:customer=customer_by_id(body["customer_id"])
                    except (TypeError,ValueError):return self._json({"error":"ongeldige klant"},400)
                    if not customer or not customer.get("active"):return self._json({"error":"klant niet gevonden"},404)
                typ=str(body.get("type","Onbekend"));extra=body.get("extra") or {};problem=str(body.get("problem") or "")
                try:facts,missing,score,dispatch,prep,fault=analysis_engine.analyze(typ,problem,extra)
                except ValueError as e:return self._json({"error":str(e)},400)
                extra=analysis_engine.clean_extra(extra)
                brand=analysis_engine.canonical_brand(extra.get("manufacturer"));src=analysis_engine.source_for(brand);rk=analysis_engine.route_knowledge(fault["category"],typ,brand);fk=core.ftf_knowledge(fault["category"])
                row=first(sb.table("cases").insert({
                    "organization_id":current_org_id(required=True),"case_no":"WS-"+str(int(time.time()*1000))[-8:],"source":"planner","customer":body.get("customer") or "Nieuwe klant",
                    "city":body.get("city"),"phone":body.get("phone"),"email":body.get("email"),"customer_id":customer["id"] if customer else None,"type":typ,"asset":((brand+" "+str(extra.get("model") or "")).strip() if brand!="Onbekend" else "Nog te identificeren"),
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
                row=first(sb.table("cases").update(update).eq("organization_id",current_org_id(required=True)).eq("id",cid).execute())
                create_audit(cid,u["id"],"outcome_recorded",json.dumps({"second_visit_required":update["outcome_second_visit_required"],"preventable":update["outcome_preventable"]}))
                return self._json(row)
            if path.startswith("/api/cases/") and path.endswith("/notes"):
                cid=int(path.split("/")[3]);c=get_case(cid)
                if not can_access_case(u,c):return self._json({"error":"not found"},404)
                text=str(body.get("body") or "").strip()
                if not text:return self._json({"error":"empty note"},400)
                sb.table("notes").insert({"organization_id":current_org_id(required=True),"case_id":cid,"body":text,"created_by":u["id"],"created_at":now_iso()}).execute()
                create_audit(cid,u["id"],"note_added","");return self._json({"ok":True},201)
            if path.startswith("/api/cases/") and path.endswith("/attachments"):
                cid=int(path.split("/")[3]);c=get_case(cid)
                if not can_access_case(u,c):return self._json({"error":"not found"},404)
                raw=base64.b64decode(str(body.get("data_base64") or ""),validate=True)
                if len(raw)>5*1024*1024:return self._json({"error":"bestand groter dan 5 MB"},400)
                name=safe_filename(body.get("filename"));storage_path=f"org/{current_org_id(required=True)}/cases/{cid}/{secrets.token_hex(12)}-{name}"
                ctype=body.get("content_type") or "application/octet-stream"
                sb.storage.from_(BUCKET).upload(path=storage_path,file=raw,file_options={"content-type":ctype,"upsert":"false"})
                row=first(sb.table("attachments").insert({"organization_id":current_org_id(required=True),"case_id":cid,"filename":name,"storage_path":storage_path,"content_type":ctype,"size_bytes":len(raw),"created_by":u["id"],"created_at":now_iso()}).execute())
                create_audit(cid,u["id"],"attachment_added",name);return self._json(row,201)
            return self._json({"error":"not found"},404)
        except Exception as e:
            _record_server_error("POST "+str(locals().get("path","unknown")), e)
            print("POST ERROR",repr(e),file=sys.stderr);return self._json({"error":"server_error"},500)

    def do_PATCH(self):
        _set_org_context(None)
        if not self._check_origin():return self._json({"error":"invalid origin"},403)
        try:
            path=urlparse(self.path).path;body=self._body();u=self._need()
            if not u:return
            if organization_write_path(path) and not case_actor_in_organization(u):
                return self._json({"error":"Je bekijkt deze organisatie als eigenaar. Gebruik een teamaccount van deze organisatie om cases bij te werken.","code":"organization_member_required"},403)
            if path.startswith("/api/owner/support/"):
                if not u.get("is_platform_owner"):return self._json({"error":"forbidden"},403)
                try:
                    tid=int(path.split("/")[4]);version=int(body.get("version",0))
                    if isinstance(body.get("version"),bool):raise ValueError()
                except (TypeError,ValueError):return self._json({"error":"ongeldige melding of versie"},400)
                status=body.get("status");resolution=str(body.get("resolution") or "").strip()
                if status not in ("open","in_progress","resolved") or len(resolution)>6000:return self._json({"error":"ongeldige status of reactie"},400)
                if status=="resolved" and not resolution:return self._json({"error":"vul de oplossing in voordat je afrondt"},400)
                target=first(sb.table("support_tickets").select("*").eq("id",tid).limit(1).execute())
                if not target:return self._json({"error":"melding niet gevonden"},404)
                row=first(sb.table("support_tickets").update({"status":status,"resolution":resolution,"version":version+1,"updated_at":now_iso(),"resolved_at":now_iso() if status=="resolved" else None}).eq("id",tid).eq("version",version).execute())
                if not row:return self._json({"error":"version_conflict"},409)
                return self._json({k:v for k,v in row.items() if k not in ("request_key","fingerprint")})
            if path.startswith("/api/customers/"):
                if u["role"] not in ("admin","planner"):return self._json({"error":"forbidden"},403)
                try:
                    cid=int(path.split("/")[3]);target=customer_by_id(cid)
                    if not target:return self._json({"error":"klant niet gevonden"},404)
                    values=clean_customer(body,partial=True)
                    if isinstance(body.get("version"),bool):raise ValueError("ongeldige versie")
                    version=int(body.get("version",0))
                except (TypeError,ValueError) as e:return self._json({"error":str(e)},400)
                if version!=int(target.get("version",1)):return self._json({"error":"version_conflict"},409)
                values.update({"version":version+1,"updated_at":now_iso()})
                row=first(sb.table("customer_records").update(values).eq("organization_id",current_org_id(required=True)).eq("id",cid).eq("version",version).execute())
                if not row:return self._json({"error":"version_conflict"},409)
                create_audit(None,u["id"],"customer_updated",str(cid))
                return self._json(row)
            if path.startswith("/api/owner/organizations/"):
                if not u.get("is_platform_owner"):return self._json({"error":"forbidden"},403)
                oid=int(path.split("/")[4])
                org=organization_by_id(oid)
                if not org:return self._json({"error":"organisatie niet gevonden"},404)
                upd={}
                if "name" in body and str(body["name"]).strip():upd["name"]=str(body["name"]).strip()
                if "status" in body:
                    if body["status"] not in ("onboarding","pilot","active","suspended","archived"):return self._json({"error":"ongeldige status"},400)
                    upd["status"]=body["status"]
                if "plan" in body:
                    if body["plan"] not in ("internal","pilot","starter","growth","enterprise"):return self._json({"error":"ongeldig plan"},400)
                    upd["plan"]=body["plan"]
                for k in ("support_email","privacy_url"):
                    if k in body:upd[k]=str(body[k] or "").strip() or None
                if upd.get("support_email") and "@" not in upd["support_email"]:return self._json({"error":"ongeldig support e-mailadres"},400)
                if upd.get("privacy_url") and not re.match(r"^https?://",upd["privacy_url"],re.I):return self._json({"error":"ongeldige privacy-URL"},400)
                upd["updated_at"]=now_iso()
                row=first(sb.table("organizations").update(upd).eq("id",oid).execute())
                if "name" in upd:set_setting("company_name",upd["name"],organization_id=oid)
                if "support_email" in upd:set_setting("support_email",upd["support_email"] or "",organization_id=oid)
                if "privacy_url" in upd:set_setting("privacy_url",upd["privacy_url"] or "",organization_id=oid)
                return self._json(row)

            if path=="/api/settings":
                if u["role"] not in ("admin","planner"):return self._json({"error":"forbidden"},403)
                admin_fields={"company_name","brand_name","brand_accent","support_email","privacy_url","customer_portal_title"}
                if u["role"]!="admin" and set(body)&admin_fields:return self._json({"error":"alleen de bedrijfsbeheerder kan bedrijfsinstellingen wijzigen"},403)
                allowed={"company_name":str,"baseline_planner_minutes":float,"planner_hourly_cost":float,"technician_hourly_cost":float,"avg_site_visit_minutes":float,"avg_roundtrip_km":float,"cost_per_km":float,"software_monthly_cost":float,"monthly_case_volume":float,"brand_name":str,"brand_accent":str,"support_email":str,"privacy_url":str,"customer_portal_title":str}
                for k,t in allowed.items():
                    if k not in body:continue
                    v=str(body[k]) if t is str else str(max(0,float(body[k])))
                    if k=="brand_accent" and not re.fullmatch(r"#[0-9a-fA-F]{6}",v):return self._json({"error":"ongeldige accentkleur"},400)
                    if k=="support_email" and v and "@" not in v:return self._json({"error":"ongeldig support e-mailadres"},400)
                    if k=="privacy_url" and v and not re.match(r"^https?://",v,re.I):return self._json({"error":"privacy-URL moet met http:// of https:// beginnen"},400)
                    set_setting(k,v)
                return self._json({"company_name":get_setting("company_name"),"brand_name":get_setting("brand_name"),"brand_accent":get_setting("brand_accent"),"support_email":get_setting("support_email"),"privacy_url":get_setting("privacy_url"),"customer_portal_title":get_setting("customer_portal_title"),**economic_assumptions()})
            if path.startswith("/api/accounts/"):
                if u["role"]!="admin":return self._json({"error":"forbidden"},403)
                uid=int(path.split("/")[3])
                try:return self._json(update_team_account(u,uid,body))
                except LookupError as e:return self._json({"error":str(e)},404)
                except PermissionError as e:return self._json({"error":str(e)},403)
                except ValueError as e:return self._json({"error":str(e)},400)
            if path.startswith("/api/cases/"):
                cid=int(path.split("/")[3]);c=get_case(cid)
                if not can_access_case(u,c):return self._json({"error":"not found"},404)
                allowed={"version","status"}
                if u["role"] in ("admin","planner"):allowed.add("assigned_to")
                if set(body)-allowed:
                    return self._json({"error":"Gebruik de analysefunctie voor waarnemingen en advies. Toewijzing is alleen voor beheerder of planner."},403)
                if "status" in body and body["status"] not in ("Info ontbreekt","Review","Ingepland","Afgerond"):
                    return self._json({"error":"ongeldige dossierstatus"},400)
                try:
                    if isinstance(body.get("version"),bool):raise ValueError()
                    expected=int(body.get("version",0))
                except (ValueError,TypeError):return self._json({"error":"ongeldige dossierversie"},400)
                if int(c.get("version") or 1)!=expected:return self._json({"error":"version_conflict","remote":c},409)
                upd={}
                for k in ("status",):
                    if k in body:upd[k]=body[k]
                if "assigned_to" in body and u["role"] in ("admin","planner"):upd["assigned_to"]=body["assigned_to"]
                new_status=body.get("status",c.get("status"))
                if new_status in ("Review","Ingepland","Afgerond") and not c.get("planner_ready_at"):upd["planner_ready_at"]=now_iso()
                if new_status=="Ingepland" and not c.get("scheduled_at"):upd["scheduled_at"]=now_iso()
                if new_status=="Afgerond" and not c.get("closed_at"):upd["closed_at"]=now_iso()
                upd["version"]=expected+1;upd["updated_at"]=now_iso()
                row=first(sb.table("cases").update(upd).eq("organization_id",current_org_id(required=True)).eq("id",cid).eq("version",expected).execute())
                if not row:return self._json({"error":"version_conflict","remote":get_case(cid)},409)
                create_audit(cid,u["id"],"case_updated",json.dumps({"status":new_status}))
                return self._json(row)
            return self._json({"error":"not found"},404)
        except Exception as e:
            _record_server_error("PATCH "+str(locals().get("path","unknown")), e)
            print("PATCH ERROR",repr(e),file=sys.stderr);return self._json({"error":"server_error"},500)

if __name__=="__main__":
    bootstrap()
    print(f"{APP_NAME} {APP_VERSION} cloud server")
    print(f"Listening on 0.0.0.0:{PORT}")
    ThreadingHTTPServer(("0.0.0.0",PORT),Handler).serve_forever()
