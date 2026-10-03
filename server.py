#!/usr/bin/env python3
from collections import Counter
import base64, hashlib, hmac, json, mimetypes, os, secrets, socket, sqlite3, sys, threading, time, re
from datetime import datetime, timezone, date, timedelta
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT=Path(__file__).resolve().parent
STATIC=ROOT/'static'; DATA=ROOT/'data'; UPLOADS=ROOT/'uploads'; DB_PATH=DATA/'preflight.db'
MAX_BODY=7*1024*1024; SESSIONS={}; SESSION_LOCK=threading.Lock()
APP_NAME='Project Preflight'
APP_VERSION='1.0.0-pilot'
APP_BUILD='2026-10-03'

def now_iso(): return datetime.now(timezone.utc).isoformat()
def db():
    con=sqlite3.connect(DB_PATH,timeout=10,check_same_thread=False); con.row_factory=sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON'); con.execute('PRAGMA journal_mode=WAL'); return con

def hash_password(password,salt=None):
    salt=salt or secrets.token_bytes(16); key=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,200_000)
    return base64.b64encode(salt).decode()+'$'+base64.b64encode(key).decode()
def verify_password(password,stored):
    try:
        salt_b64,key_b64=stored.split('$',1); salt=base64.b64decode(salt_b64); expected=base64.b64decode(key_b64)
        got=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,200_000); return hmac.compare_digest(expected,got)
    except Exception:return False


TECH_SOURCES = {
    "Easee": {
        "title": "Easee Developer Platform — Observations & enumerations",
        "url": "https://developer.easee.com/docs/charger-observation-ids",
        "api_targets": ["Op mode (109)", "Reason for no current (96)", "Error code (119)", "Total power (120)", "Wi-Fi RSSI (132)", "Connected to cloud (250)"]
    },
    "SolarEdge": {
        "title": "SolarEdge Knowledge Center / Developer API",
        "url": "https://developer.solaredge.com/",
        "api_targets": ["Live power", "Historical energy", "Inventory", "Device telemetry", "Monitoring error context"]
    },
    "GoodWe": {
        "title": "GoodWe Support — SEMS/SolarGo troubleshooting",
        "url": "https://nl.goodwe.com/support-service",
        "api_targets": ["SEMS device status", "Historical curves", "Output power", "AC/DC parameters", "Battery/BMS status", "Firmware version"]
    }
}

def canonical_brand(value):
    v=(value or '').strip()
    low=v.lower()
    if 'easee' in low: return 'Easee'
    if 'solaredge' in low or 'solar edge' in low: return 'SolarEdge'
    if 'goodwe' in low or 'good we' in low: return 'GoodWe'
    return v or 'Onbekend'

def source_for(manufacturer):
    return TECH_SOURCES.get(canonical_brand(manufacturer), {
        "title":"Generieke technische intake — fabrikantdocumentatie vereist",
        "url":"",
        "api_targets":["Merk/model", "Serienummer", "Foutmelding", "Status/LED", "Historie", "Foto/typeplaat"]
    })


def norm(s):
    return (s or '').strip().lower()

def classify_fault(t, manufacturer, text, extra=None):
    """Conservative, read-only fault-family classification from customer/OEM observations."""
    extra=extra or {}
    brand=canonical_brand(manufacturer)
    corpus=' '.join([
        norm(text), norm(extra.get('error_code')), norm(extra.get('app_status')),
        norm(extra.get('monitoring_status')), norm(extra.get('recent_event')),
        norm(extra.get('bms_warning'))
    ])
    evidence=[]
    category='Onvoldoende gespecificeerd'
    confidence='laag'
    triage='standaard'

    if brand=='Easee' and t=='Laadpaal':
        online=norm(extra.get('app_online'))
        status=norm(extra.get('app_status'))
        error=norm(extra.get('error_code'))
        if online=='offline' or 'offline' in corpus:
            category='Offline / connectiviteit'
            evidence.append('Easee app/cloudstatus offline')
            confidence='hoog' if online=='offline' else 'middel'
        elif any(k in corpus for k in ['authenticat','authorization','authorisation','rfid','pending authorization']):
            category='Wachten op authenticatie'
            evidence.append('App/status verwijst naar authenticatie')
            confidence='hoog' if any(k in status for k in ['auth','rfid']) else 'middel'
        elif any(k in corpus for k in ['schedule','schema','scheduled','uitgesteld','pending scheduled']):
            category='Laadschema / wachten'
            evidence.append('Status verwijst naar laadschema/wachten')
            confidence='middel'
        elif any(k in corpus for k in ['load balancing','equalizer','queue','current limit','stroomlimiet']):
            category='Load balancing / stroomlimiet'
            evidence.append('Melding/status verwijst naar load balancing of limiet')
            confidence='middel'
        elif error or status in ('error','fout','fault') or norm(extra.get('led'))=='rood':
            category='Laderfout / foutstatus'
            if error: evidence.append('Foutcode aanwezig')
            if status: evidence.append('App-status: '+extra.get('app_status',''))
            if norm(extra.get('led'))=='rood': evidence.append('Rode LED/status')
            confidence='hoog' if error else 'middel'
        elif extra.get('vehicle_tested')=='ja':
            category='Geen laadstroom — laadpuntgericht'
            evidence.append('Auto laadt elders wel')
            confidence='middel'
        else:
            category='Geen laadstroom — oorzaak nog open'
            evidence.append('Geen specifieke OEM-foutfamilie vastgesteld')

    elif brand=='SolarEdge' and t in ('Zonnepanelen','Thuisbatterij'):
        error=norm(extra.get('error_code'))
        mon=norm(extra.get('monitoring_status'))
        if any(k in corpus for k in ['18x86','8x58','isolation','isolatie']):
            category='Isolatiefout'
            evidence.append('SolarEdge isolatiecode/-melding')
            confidence='hoog'
            triage='veiligheidsreview'
        elif mon=='offline' or any(k in corpus for k in ['no communication','geen communicatie','communication','offline']):
            category='Communicatiestoring'
            evidence.append('Monitoring/communicatie offline')
            confidence='hoog' if mon=='offline' else 'middel'
        elif any(k in corpus for k in ['grid','vac','voltage','spanning','frequency','frequentie']):
            category='Net-/gridgerelateerde fout'
            evidence.append('Fouttekst verwijst naar netspanning/frequentie')
            confidence='middel'
            triage='technische review'
        elif error:
            category='Omvormerfout — exacte code aanwezig'
            evidence.append('SolarEdge foutcode: '+extra.get('error_code',''))
            confidence='hoog'
        elif str(extra.get('production','')).strip().lower() in ('0 w','0','0w') or 'geen productie' in corpus:
            category='Geen productie'
            evidence.append('Productie is 0 W / geen productie gemeld')
            confidence='middel'
        else:
            category='Prestatie-/monitoringafwijking'
            evidence.append('Geen specifieke SolarEdge foutfamilie herkend')

    elif brand=='GoodWe' and t in ('Zonnepanelen','Thuisbatterij'):
        error=norm(extra.get('error_code'))
        mon=norm(extra.get('monitoring_status'))
        families=[
            (['utility loss'],'Utility Loss — net afwezig/onderbroken','hoog','technische review'),
            (['vac failure','vac fail'],'VAC Failure — netspanning buiten bereik','hoog','technische review'),
            (['fac failure','fac fail'],'FAC Failure — netfrequentie buiten bereik','hoog','technische review'),
            (['isolation failure','isolation fail','isolatie'],'Isolation Failure — isolatie naar aarde','hoog','veiligheidsreview'),
            (['ground i failure','ground failure','ground leakage'],'Ground leakage / aardlekfout','hoog','veiligheidsreview'),
            (['pv over voltage','pv overvoltage'],'PV Over Voltage','hoog','veiligheidsreview'),
            (['over temperature','overtemperature'],'Over Temperature','hoog','technische review'),
            (['battery communication failure','battery communication'],'Battery Communication Failure','hoog','technische review'),
            (['spi failure'],'Interne communicatiefout (SPI)','hoog','technische review'),
        ]
        matched=False
        for keys,label,conf,tri in families:
            if any(k in corpus for k in keys):
                category=label; confidence=conf; triage=tri
                evidence.append('GoodWe foutmelding: '+(extra.get('error_code') or text or label))
                matched=True; break
        if not matched:
            if mon=='offline':
                category='SEMS/SolarGo communicatiestoring'
                evidence.append('Monitoringstatus offline')
                confidence='hoog'
            elif error:
                category='GoodWe alarm/fout — overige'
                evidence.append('Foutmelding aanwezig: '+extra.get('error_code',''))
                confidence='hoog'
            elif str(extra.get('production','')).strip().lower() in ('0 w','0','0w') or 'geen productie' in corpus:
                category='Geen productie'
                evidence.append('Productie is 0 W / geen productie gemeld')
                confidence='middel'
            else:
                category='Prestatie-/monitoringafwijking'
                evidence.append('Geen specifieke GoodWe foutfamilie herkend')
    else:
        if any(k in corpus for k in ['rook','brandlucht','vonken','schok','brandschade']):
            category='Mogelijk veiligheidsincident'
            confidence='hoog'
            triage='veiligheidsreview'
            evidence.append('Klantmelding bevat veiligheidsindicator')
        else:
            category='Generieke technische storing'
            evidence.append('Geen ondersteund OEM-profiel voor foutfamilie')

    return {
        'category':category,
        'confidence':confidence,
        'triage':triage,
        'evidence':evidence
    }

def fault_specific_prep(fault):
    category=fault.get('category','')
    items=[]
    if category=='Offline / connectiviteit':
        items=['Controleer charger offline reason en connected-to-cloud observation','Controleer laatste succesvolle communicatie/observations vóór dispatch']
    elif category=='Wachten op authenticatie':
        items=['Controleer operation mode en ReasonForNoCurrent voor authenticatiecontext','Controleer autorisatiemethode/whitelist zonder instellingen automatisch te wijzigen']
    elif category=='Laadschema / wachten':
        items=['Controleer ReasonForNoCurrent en actief laadschema read-only','Bevestig of de case remote verklaarbaar is vóór monteurdispatch']
    elif category=='Load balancing / stroomlimiet':
        items=['Controleer ReasonForNoCurrent en relevante current-limit observations','Controleer Equalizer/load-balancing context read-only']
    elif category=='Isolatiefout':
        items=['Behandel als veiligheidsreview door bevoegde PV-technicus','Controleer monitoring-isolatiewaarde/foutcode read-only vóór locatiebezoek']
    elif category=='Communicatiestoring':
        items=['Controleer SolarEdge monitoring communication status en laatste succesvolle rapportage','Scheid communicatieprobleem van daadwerkelijke productiestoring vóór dispatch']
    elif category=='Geen productie':
        items=['Vergelijk live vermogen met recente productiehistorie','Controleer foutcode/status en asset telemetry vóór dispatch']
    elif category.startswith('Utility Loss'):
        items=['Controleer GoodWe monitoringtijdlijn rond Utility Loss','Laat net-/aansluitcontrole uitsluitend door bevoegde technicus uitvoeren']
    elif category.startswith('VAC Failure') or category.startswith('FAC Failure'):
        items=['Controleer fouttijdlijn en monitoringwaarden read-only','Routeer naar bevoegde technicus voor netgerelateerde diagnose']
    elif category.startswith('Isolation Failure') or category.startswith('Ground leakage') or category=='PV Over Voltage':
        items=['Veiligheidsreview door bevoegde PV-technicus vóór werkzaamheden','Gebruik monitoring/foutcontext uitsluitend voor voorbereiding; geen klantmetingen']
    elif category.startswith('Battery Communication Failure'):
        items=['Controleer BMS/ESS monitoringstatus en firmwarecontext read-only','Routeer naar batterij/ESS-technicus indien fout aanhoudt']
    return items



FTF_KNOWLEDGE = {
    "Offline / connectiviteit": {
        "critical_before_departure": ["Laatste succesvolle cloudcommunicatie", "Actuele online/offline-status", "Of laden ondanks offline-status nog werkt"],
        "common_avoidable_gap": ["Geen onderscheid tussen alleen offline en ook niet laden", "Geen app-/connectiviteitscontext vastgelegd"],
        "parts_categories": ["Geen onderdelen vooraf aannemen; eerst remote oorzaak scheiden van hardwareprobleem"]
    },
    "Wachten op authenticatie": {
        "critical_before_departure": ["Exacte appstatus", "Autorisatiemethode/operatorcontext", "ReasonForNoCurrent indien API gekoppeld"],
        "common_avoidable_gap": ["Autorisatieprobleem als hardwarestoring ingepland", "Geen operator-/RFID-context bekend"],
        "parts_categories": ["Normaal geen hardwareonderdeel vooraf reserveren zonder aanvullende foutindicatie"]
    },
    "Laadschema / wachten": {
        "critical_before_departure": ["Actief schema/smart charging", "Operatorcontext", "Laatste succesvolle laadsessie"],
        "common_avoidable_gap": ["Schedule/smart-charging niet vooraf gecontroleerd"],
        "parts_categories": ["Geen standaardonderdeel; eerst remote status verklaren"]
    },
    "Load balancing / stroomlimiet": {
        "critical_before_departure": ["Load-balancing/Equalizer-context", "Current-limit observaties", "Site-topologie"],
        "common_avoidable_gap": ["Stroomlimiet niet onderscheiden van laadpaaldefect"],
        "parts_categories": ["Geen onderdelen vooraf zonder bevestigde hardwarefout"]
    },
    "Laderfout / foutstatus": {
        "critical_before_departure": ["Exacte foutcode", "Model/serienummer", "Laatste succesvolle sessie", "Installatiehistorie"],
        "common_avoidable_gap": ["Foutcode of serienummer ontbreekt", "Verkeerde monteurcompetentie ingepland"],
        "parts_categories": ["OEM-serviceonderdeelcategorie alleen na code/modelbevestiging"]
    },
    "Isolatiefout": {
        "critical_before_departure": ["Exacte foutcode", "Isolatiewaarde indien remote beschikbaar", "String-/layoutdocumentatie", "Weer-/herhalingscontext"],
        "common_avoidable_gap": ["Geen string-/layoutdocumentatie beschikbaar", "Geen isolatiecontext uit monitoring verzameld"],
        "parts_categories": ["Geen onderdeel vooraf diagnosticeren; juiste PV/DC-meet- en veiligheidsmiddelen volgens bedrijfsprocedure"]
    },
    "Communicatiestoring": {
        "critical_before_departure": ["Laatste succesvolle rapportage", "Communicatiemethode", "Router/netwerkcontext", "Productie wel/niet actief"],
        "common_avoidable_gap": ["Communicatieprobleem verward met productiestoring", "Netwerkcontext niet vooraf uitgevraagd"],
        "parts_categories": ["Alleen communicatie-/netwerkcomponentcategorie voorbereiden wanneer monitoringcontext daar aanleiding toe geeft"]
    },
    "Net-/gridgerelateerde fout": {
        "critical_before_departure": ["Exacte foutcode", "Eventtijdlijn", "Frequentie/herhaling", "Installatiegegevens"],
        "common_avoidable_gap": ["Geen eventtijdlijn", "Tijdelijke netevent niet onderscheiden van installatieprobleem"],
        "parts_categories": ["Geen onderdeel vooraf; bevoegde elektrotechnische meetmiddelen volgens bedrijfsprocedure"]
    },
    "Omvormerfout — exacte code aanwezig": {
        "critical_before_departure": ["Exacte foutcode", "Model/serienummer", "Firmware/statuscontext", "Recente events"],
        "common_avoidable_gap": ["Foutcode niet gekoppeld aan exact model", "Geen OEM-documentatie voorbereid"],
        "parts_categories": ["OEM-serviceonderdeelcategorie alleen na code/modelbevestiging"]
    },
    "Geen productie": {
        "critical_before_departure": ["Live vermogen", "Productiehistorie", "Monitoringstatus", "Foutcode/status"],
        "common_avoidable_gap": ["Geen onderscheid tussen monitoringuitval en echte 0-productie", "Geen historische curve"],
        "parts_categories": ["Geen onderdeel vooraf zonder foutcode/telemetrie"]
    },
    "Utility Loss — net afwezig/onderbroken": {
        "critical_before_departure": ["Exact alarmtijdstip", "SEMS/SolarGo historie", "Of overige installatie/gebouw normaal spanning heeft als klantobservatie"],
        "common_avoidable_gap": ["Algemene netonderbreking niet uitgesloten", "Geen alarmhistorie"],
        "parts_categories": ["Geen onderdeel vooraf; bevoegde net-/installatiediagnose voorbereiden"]
    },
    "VAC Failure — netspanning buiten bereik": {
        "critical_before_departure": ["Alarmhistorie", "Tijdstip/herhaling", "Monitoringcurve", "Installatiedocumentatie"],
        "common_avoidable_gap": ["Geen trend/tijdlijn verzameld", "Incident als permanent hardwaredefect behandeld"],
        "parts_categories": ["Geen onderdeel vooraf; bevoegde meetmiddelen volgens bedrijfsprocedure"]
    },
    "FAC Failure — netfrequentie buiten bereik": {
        "critical_before_departure": ["Alarmhistorie", "Herhalingsfrequentie", "Tijdstip/context"],
        "common_avoidable_gap": ["Geen context of fout incidenteel/structureel is"],
        "parts_categories": ["Geen onderdeel vooraf"]
    },
    "Isolation Failure — isolatie naar aarde": {
        "critical_before_departure": ["Alarmhistorie", "String-/installatiedocumentatie", "Herhalings-/weercontext"],
        "common_avoidable_gap": ["Geen installatielayout/documentatie", "Geen eerdere foutgeschiedenis beschikbaar"],
        "parts_categories": ["Geen onderdeel vooraf diagnosticeren; juiste PV/DC-meet- en veiligheidsmiddelen volgens bedrijfsprocedure"]
    },
    "Ground leakage / aardlekfout": {
        "critical_before_departure": ["Exact alarm", "Herhaling/tijdlijn", "Installatiedocumentatie"],
        "common_avoidable_gap": ["Geen foutgeschiedenis of documentatie beschikbaar"],
        "parts_categories": ["Geen onderdeel vooraf; veiligheids- en meetmiddelen volgens bedrijfsprocedure"]
    },
    "PV Over Voltage": {
        "critical_before_departure": ["Exact alarm", "Model/stringconfiguratie", "Moment/omstandigheden"],
        "common_avoidable_gap": ["Geen string-/configuratiecontext"],
        "parts_categories": ["Geen onderdeel vooraf; PV/DC-diagnosemiddelen volgens bedrijfsprocedure"]
    },
    "Battery Communication Failure": {
        "critical_before_departure": ["BMS-status", "Firmwareversie", "Laatste succesvolle batterijcommunicatie", "ESS-topologie"],
        "common_avoidable_gap": ["Firmware/BMS-context ontbreekt", "Geen ESS-topologie bekend"],
        "parts_categories": ["Communicatie-/BMS-componentcategorie alleen na bevestigde diagnose"]
    },
    "SEMS/SolarGo communicatiestoring": {
        "critical_before_departure": ["Laatste rapportage", "SEMS/SolarGo status", "Netwerk-/loggercontext"],
        "common_avoidable_gap": ["Platformstoring niet onderscheiden van lokale communicatie"],
        "parts_categories": ["Geen onderdeel vooraf zonder communicatiecontext"]
    }
}
DEFAULT_FTF = {
    "critical_before_departure": ["Exacte storingomschrijving", "Merk/model/serienummer", "Foto's/status", "Historie"],
    "common_avoidable_gap": ["Onvolledig servicedossier", "Onjuiste monteurcompetentie"],
    "parts_categories": ["Geen onderdelen vooraf aannemen zonder bevestigde diagnose"]
}
def ftf_knowledge(fault_category):
    return dict(FTF_KNOWLEDGE.get(fault_category, DEFAULT_FTF))

ROUTE_KNOWLEDGE = {
    # Easee
    "Offline / connectiviteit": {
        "service_route":"remote-first",
        "competence":"EV laadinfra servicemedewerker; installateursbevoegdheid alleen nodig bij elektrische vervolgactie",
        "remote_checks":["Cloud-/appstatus", "laatste succesvolle communicatie", "Bluetooth/lokale bereikbaarheid indien klant dit al kan zien"],
        "site_trigger":"Locatiebezoek pas wanneer laden/power óók faalt, lokale toegang ontbreekt of de offline-status na ondersteunde remote checks blijft bestaan.",
        "prep_categories":["Serienummer en operator/site-context", "Easee app/Control toegang indien beschikbaar", "Netwerk-/connectiviteitscontext", "Vorige werkorders"],
        "escalation":"Easee Technical Support bij aanhoudende offline-status na relevante connectiviteitschecks.",
        "source_title":"Easee Help — charger offline / Wi-Fi & LTE-M",
        "source_url":"https://support.easee.com/hc/en-gb/articles/26385019138449-Easee-charger-offline-troubleshoot-Wi-Fi-and-LTE-M-connections"
    },
    "Wachten op authenticatie": {
        "service_route":"remote-first",
        "competence":"EV laadinfra servicemedewerker / beheerder",
        "remote_checks":["Exacte appstatus", "ReasonForNoCurrent / operation mode indien API gekoppeld", "autorisatie-/operatorcontext"],
        "site_trigger":"Locatiebezoek wanneer autorisatiecontext niet remote verklaard kan worden of de laadpaal daarnaast een hardware-/powerfout meldt.",
        "prep_categories":["Site-/operatorinformatie", "RFID/autorisatiebeleid", "Serienummer", "Appstatus screenshot"],
        "escalation":"Operator/Easee support wanneer authenticatiebackend of operatorintegratie de blokkade veroorzaakt.",
        "source_title":"Easee Help — charging doesn't start / status in Easee App",
        "source_url":"https://support.easee.com/hc/en-gb/articles/44493587474961-Car-not-charging-or-stops-check-the-status-in-the-Easee-App"
    },
    "Laadschema / wachten": {
        "service_route":"remote-first",
        "competence":"EV laadinfra servicemedewerker / sitebeheerder",
        "remote_checks":["Actief schema", "smart charging/operatorcontext", "ReasonForNoCurrent indien API gekoppeld"],
        "site_trigger":"Locatiebezoek alleen wanneer schema/operator de situatie niet verklaart en laden fysiek niet start.",
        "prep_categories":["Schema-/smart-chargingstatus", "Operatorinformatie", "Appstatus", "Vorige laadsessie"],
        "escalation":"Operator/Easee support wanneer schedule/smart-chargingstatus niet verklaarbaar is.",
        "source_title":"Easee Help — Schedule & Smart Charge",
        "source_url":"https://support.easee.com/hc/en-gb/articles/4413246412561-Schedule-Smart-Charge"
    },
    "Load balancing / stroomlimiet": {
        "service_route":"remote-first",
        "competence":"EV laadinfra technicus met kennis van load balancing / Equalizer",
        "remote_checks":["ReasonForNoCurrent", "current-limit context", "Equalizer/load-balancing status"],
        "site_trigger":"Locatiebezoek als read-only data een blijvende lokale installatie-/meetfout suggereert.",
        "prep_categories":["Equalizer/site-topologie", "Current-limit observations", "Serienummer", "Installatiedocumentatie"],
        "escalation":"Easee support of installateur afhankelijk van bron van de beperking.",
        "source_title":"Easee Developer Platform — Charger Observation IDs",
        "source_url":"https://developer.easee.com/docs/charger-observation-ids"
    },
    "Laderfout / foutstatus": {
        "service_route":"site-likely",
        "competence":"Bevoegde EV-laadinfra technicus / elektricien",
        "remote_checks":["Foutcode", "operation mode", "cloudstatus", "laatste laadsessie"],
        "site_trigger":"Locatiebezoek wanneer foutcode/hardwarestatus niet remote oplosbaar of veilig verklaarbaar is.",
        "prep_categories":["Foutcode en screenshots", "Serienummer", "Installatiehistorie", "OEM-documentatie", "Passende PBM en fabrikantgoedgekeurde diagnosemiddelen"],
        "escalation":"Easee Technical Support bij persistente hardware-/platformfout.",
        "source_title":"Easee Help — charging status & troubleshooting",
        "source_url":"https://support.easee.com/hc/en-gb/articles/44493587474961-Car-not-charging-or-stops-check-the-status-in-the-Easee-App"
    },

    # SolarEdge
    "Isolatiefout": {
        "service_route":"site-required",
        "competence":"Bevoegde PV-technicus met kennis van DC-zijde en isolatiefouten",
        "remote_checks":["Exacte foutcode", "Last Isolation Value / monitoring indien beschikbaar", "tijdstip en herhaling van fout"],
        "site_trigger":"Veiligheidsreview en locatiebezoek door gekwalificeerde PV-technicus wanneer isolatiefout actueel/persisterend is.",
        "prep_categories":["SetApp/monitoring foutcode", "Laatste isolatiewaarde indien beschikbaar", "String-/layoutdocumentatie", "OEM-isolatiefoutdocumentatie", "Passende PBM en meetmiddelen volgens bedrijfsprocedure"],
        "escalation":"SolarEdge Support bij onduidelijke/persistente fout na bevoegde diagnose.",
        "source_title":"SolarEdge — Isolation Fault Troubleshooting",
        "source_url":"https://knowledge-center.solaredge.com/sites/kc/files/application_note_isolation_fault_troubleshooting.pdf"
    },
    "Communicatiestoring": {
        "service_route":"remote-first",
        "competence":"PV servicemedewerker met monitoring/netwerkkennis",
        "remote_checks":["Monitoringstatus", "laatste succesvolle rapportage", "router/modem/platformcontext"],
        "site_trigger":"Locatiebezoek wanneer communicatie fysiek lokaal onderzocht moet worden of productie-impact niet remote te scheiden is.",
        "prep_categories":["Monitoring screenshot", "Netwerk-/routercontext", "Communicatiemethode", "Serienummer/inventory"],
        "escalation":"SolarEdge Support bij persistente communicatiefout na standaard remote checks.",
        "source_title":"SolarEdge — Troubleshooting Communication",
        "source_url":"https://knowledge-center.solaredge.com/sites/kc/files/se_installation_guide_safety_monitoring.pdf"
    },
    "Net-/gridgerelateerde fout": {
        "service_route":"site-likely",
        "competence":"Bevoegde PV-/elektrotechnicus",
        "remote_checks":["Foutcode", "monitoring-eventtijdlijn", "frequentie van optreden"],
        "site_trigger":"Locatiebezoek wanneer netgerelateerde fout blijft terugkomen of monitoring geen tijdelijke netevent verklaart.",
        "prep_categories":["Foutcode/eventtijdlijn", "Monitoringdata", "Installatiegegevens", "OEM-handleiding", "Passende PBM/meetmiddelen volgens bedrijfsprocedure"],
        "escalation":"SolarEdge support of net-/installatieonderzoek afhankelijk van bevindingen.",
        "source_title":"SolarEdge — Troubleshooting Alerts in Monitoring Platform",
        "source_url":"https://knowledge-center.solaredge.com/sites/kc/files/se-troubleshooting-alert-application-note.pdf"
    },
    "Omvormerfout — exacte code aanwezig": {
        "service_route":"remote-triage",
        "competence":"PV servicemedewerker; bevoegde technicus bij hardware-/veiligheidsroute",
        "remote_checks":["Exacte foutcode", "monitoring event", "firmware/statuscontext"],
        "site_trigger":"Afhankelijk van OEM-code; hardware- of veiligheidsfout naar locatiebezoek.",
        "prep_categories":["Exacte code", "Model/serienummer", "Monitoringevent", "OEM foutcode-documentatie"],
        "escalation":"SolarEdge Support wanneer code een interne hardware/softwarefout aanduidt of blijft terugkomen.",
        "source_title":"SolarEdge — Troubleshooting Alerts / Error Codes",
        "source_url":"https://knowledge-center.solaredge.com/sites/kc/files/se-troubleshooting-alert-application-note.pdf"
    },
    "Geen productie": {
        "service_route":"remote-first",
        "competence":"PV servicemedewerker",
        "remote_checks":["Live vermogen", "productiehistorie", "monitoringstatus", "foutcode/event"],
        "site_trigger":"Locatiebezoek als monitoring/telemetrie geen remote oorzaak geeft of installatie niet rapporteert.",
        "prep_categories":["Live/history grafiek", "Foutcode", "Monitoringstatus", "Model/serienummer", "Vorige werkorders"],
        "escalation":"PV-technicus of OEM-support afhankelijk van foutcontext.",
        "source_title":"SolarEdge Developer API / Monitoring",
        "source_url":"https://developer.solaredge.com/"
    },

    # GoodWe
    "Utility Loss — net afwezig/onderbroken": {
        "service_route":"remote-triage",
        "competence":"Bevoegde PV-/elektrotechnicus voor fysieke net-/aansluitdiagnose",
        "remote_checks":["SEMS/SolarGo eventtijdlijn", "of andere apparatuur op hetzelfde aansluitpunt normaal werkt (klantobservatie)", "frequentie van fout"],
        "site_trigger":"Locatiebezoek door bevoegde technicus wanneer Utility Loss blijft bestaan en geen algemene netstoring zichtbaar is.",
        "prep_categories":["Exacte alarmtekst", "SEMS/SolarGo historie", "Installatie-/aansluitdocumentatie", "Passende PBM en meetmiddelen volgens bedrijfsprocedure"],
        "escalation":"GoodWe support wanneer foutcontext niet overeenkomt met installatie-/netstatus.",
        "source_title":"GoodWe SDT G2 User Manual — Maintenance/Troubleshooting",
        "source_url":"https://nl.goodwe.com/Public/Uploads/sersups/GW_SDT%20G2_User%20Manual-EN.pdf"
    },
    "VAC Failure — netspanning buiten bereik": {
        "service_route":"site-likely",
        "competence":"Bevoegde PV-/elektrotechnicus",
        "remote_checks":["SEMS/SolarGo alarmtijdlijn", "frequentie en tijdstip van fout", "eventuele andere netevents"],
        "site_trigger":"Locatiebezoek voor bevoegde net-/installatiecontrole wanneer fout terugkeert.",
        "prep_categories":["Exacte alarmtekst", "Historische monitoringcurve", "Installatiedocumentatie", "Passende PBM/meetmiddelen volgens bedrijfsprocedure"],
        "escalation":"GoodWe support na bevoegde diagnose wanneer fout blijft bestaan.",
        "source_title":"GoodWe SDT G2 User Manual — VAC Fail",
        "source_url":"https://nl.goodwe.com/Public/Uploads/sersups/GW_SDT%20G2_User%20Manual-EN.pdf"
    },
    "FAC Failure — netfrequentie buiten bereik": {
        "service_route":"remote-triage",
        "competence":"PV servicemedewerker + bevoegde technicus indien fout persisteert",
        "remote_checks":["Foutfrequentie", "SEMS/SolarGo tijdlijn", "algemene neteventcontext"],
        "site_trigger":"Locatiebezoek wanneer fout structureel/persisterend is.",
        "prep_categories":["Alarmhistorie", "Tijdstippen/frequentie", "Installatiedocumentatie"],
        "escalation":"GoodWe support of netgerelateerde analyse na technische review.",
        "source_title":"GoodWe SDT G2 User Manual — FAC Fail",
        "source_url":"https://nl.goodwe.com/Public/Uploads/sersups/GW_SDT%20G2_User%20Manual-EN.pdf"
    },
    "Isolation Failure — isolatie naar aarde": {
        "service_route":"site-required",
        "competence":"Bevoegde PV-technicus met DC-/isolatiediagnosecompetentie",
        "remote_checks":["Exacte alarmtekst", "SEMS/SolarGo eventtijdlijn", "weer-/herhalingscontext"],
        "site_trigger":"Veiligheidsreview en locatiebezoek door bevoegde PV-technicus.",
        "prep_categories":["Alarmhistorie", "String-/installatiedocumentatie", "OEM-handleiding", "Passende PBM/meetmiddelen volgens bedrijfsprocedure"],
        "escalation":"GoodWe support bij persistente fout na bevoegde diagnose.",
        "source_title":"GoodWe ESA User Manual — Isolation Failure",
        "source_url":"https://nl.goodwe.com/Public/Uploads/sersups/GW_ESA_Installation%20Manual-EN.pdf"
    },
    "Ground leakage / aardlekfout": {
        "service_route":"site-required",
        "competence":"Bevoegde PV-/elektrotechnicus",
        "remote_checks":["Exacte alarmtekst", "tijdlijn/herhaling"],
        "site_trigger":"Veiligheidsreview op locatie.",
        "prep_categories":["Alarmhistorie", "Installatiedocumentatie", "OEM-handleiding", "Passende PBM/meetmiddelen volgens bedrijfsprocedure"],
        "escalation":"GoodWe support na veilige technische diagnose.",
        "source_title":"GoodWe ESA User Manual — Ground I Failure",
        "source_url":"https://nl.goodwe.com/Public/Uploads/sersups/GW_ESA_Installation%20Manual-EN.pdf"
    },
    "Battery Communication Failure": {
        "service_route":"remote-first",
        "competence":"ESS/batterijservicetechnicus",
        "remote_checks":["SEMS/SolarGo BMS-status", "firmware/context", "laatste succesvolle batterijcommunicatie"],
        "site_trigger":"Locatiebezoek als communicatie niet remote verklaarbaar is of hardwareverbinding moet worden gecontroleerd.",
        "prep_categories":["BMS-warning", "Firmwareversie", "ESS-topologie", "Monitoringhistorie"],
        "escalation":"GoodWe support bij persistente batterijcommunicatiefout.",
        "source_title":"GoodWe ESA User Manual — Battery Communication Failure",
        "source_url":"https://nl.goodwe.com/Public/Uploads/sersups/GW_ESA_Installation%20Manual-EN.pdf"
    },
    "SEMS/SolarGo communicatiestoring": {
        "service_route":"remote-first",
        "competence":"PV/ESS servicemedewerker met monitoringkennis",
        "remote_checks":["SEMS+ status", "laatste rapportage", "communicatie-/netwerkcontext"],
        "site_trigger":"Locatiebezoek wanneer fysieke logger/netwerkverbinding lokaal moet worden onderzocht.",
        "prep_categories":["SEMS/SolarGo screenshots", "Serienummer", "Communicatieconfiguratie", "Vorige werkorders"],
        "escalation":"GoodWe support bij persistente platform-/communicatiefout.",
        "source_title":"GoodWe SEMS+ / Support",
        "source_url":"https://nl.goodwe.com/support-service"
    }
}

DEFAULT_ROUTE_KNOWLEDGE = {
    "service_route":"remote-triage",
    "competence":"Technische servicemedewerker; specialist bepalen na eerste review",
    "remote_checks":["Foutmelding", "asset-identiteit", "monitoring/status", "historie"],
    "site_trigger":"Locatiebezoek wanneer remote informatie onvoldoende is of fysieke diagnose nodig is.",
    "prep_categories":["Model/serienummer", "Foutmelding", "Foto's", "Vorige werkorders", "OEM-documentatie"],
    "escalation":"Fabrikantsupport of bevoegde vaktechnicus afhankelijk van foutcontext.",
    "source_title":"OEM documentatie",
    "source_url":""
}

def route_knowledge(fault_category):
    d=ROUTE_KNOWLEDGE.get(fault_category,DEFAULT_ROUTE_KNOWLEDGE)
    return dict(d)

def prep_for(t, manufacturer='', extra=None, fault=None):
    extra=extra or {}
    fault=fault or {}
    brand=canonical_brand(manufacturer)
    generic={
        'Laadpaal':['Controleer asset-identiteit en klantobservaties','Controleer eerdere werkorders en installatiegegevens','Bepaal of remote diagnose mogelijk is vóór dispatch'],
        'Zonnepanelen':['Controleer asset-identiteit, actuele productie en foutcontext','Controleer monitoring/productiehistorie','Koppel relevante OEM-documentatie aan de werkorder'],
        'Thuisbatterij':['Controleer SoC, foutmelding en systeemcontext','Controleer firmware/BMS-context indien beschikbaar','Koppel relevante OEM-documentatie aan de werkorder'],
        'Elektro':['Controleer groep/aardlek-informatie uit de melding','Beoordeel veiligheidsrisico vóór werkzaamheden','Neem passende meet- en veiligheidsmiddelen mee']
    }.get(t,['Controleer servicedossier vóór vertrek'])
    if brand=='Easee':
        specific=[
            'Read-only diagnose: controleer operation mode, error code en reason-for-no-current',
            'Controleer cloudconnectiviteit en signaalstatus voordat een rit wordt ingepland',
            'Controleer laatste/actieve laadsessie en vermogensoverdracht indien partnerdata beschikbaar is'
        ]
    elif brand=='SolarEdge':
        specific=[
            'Controleer monitoring: live vermogen, historische productie en device telemetry',
            'Controleer foutcode en LED/statuscontext; koppel recente gebeurtenissen aan de case',
            'Controleer inverter inventory/model/serienummer vóór support- of garantie-escalatie'
        ]
    elif brand=='GoodWe':
        specific=[
            'Controleer SEMS/SolarGo status, foutmelding en historische curve rond het storingsmoment',
            'Controleer output power en relevante AC/DC- of batterijstatus uit monitoring',
            'Controleer firmware/BMS-warning context indien het een ESS/batterijsysteem betreft'
        ]
    else:
        specific=[]
    return generic+specific+fault_specific_prep(fault)

def analyze(t,text,extra=None):
    extra=extra or {}
    l=(text or '').lower()
    manufacturer=canonical_brand(extra.get('manufacturer'))
    model=(extra.get('model') or '').strip()
    serial=(extra.get('serial') or '').strip()
    facts=['Klant & locatie']; missing=[]
    if manufacturer!='Onbekend': facts.append('Merk: '+manufacturer)
    else: missing.append('Merk/fabrikant')
    if model: facts.append('Model: '+model)
    else: missing.append('Model')
    if serial: facts.append('Serienummer')
    else: missing.append('Serienummer')

    if t=='Laadpaal':
        if extra.get('led') or any(x in l for x in ['rood','groen','blauw','oranje']): facts.append('LED/status')
        else: missing.append('LED/status')
        if extra.get('vehicle_tested')=='ja' or any(x in l for x in ['elders','andere paal','werk wel']): facts.append('Voertuig elders getest')
        else: missing.append('Voertuig elders getest')
        if extra.get('error_code') or 'foutcode' in l or 'error' in l: facts.append('Foutcode / screenshot')
        else: missing.append('Foutcode / screenshot')
        if manufacturer=='Easee':
            if extra.get('app_online'): facts.append('Easee app/cloudstatus')
            else: missing.append('Easee app/cloudstatus')
            if extra.get('app_status'): facts.append('Easee laadstatus in app')
            else: missing.append('Easee laadstatus in app')
        dispatch='Laadpuntgericht serviceonderzoek'

    elif t=='Zonnepanelen':
        if extra.get('production') or any(x in l for x in ['productie','opbrengst','0 w']): facts.append('Productiestatus')
        else: missing.append('Productiestatus')
        if extra.get('error_code') or 'foutcode' in l or 'error' in l: facts.append('Foutcode')
        else: missing.append('Foutcode')
        if extra.get('photo_present'): facts.append('Foto display/typeplaat')
        else: missing.append('Foto display/typeplaat')
        if manufacturer=='SolarEdge':
            if extra.get('monitoring_status'): facts.append('SolarEdge monitoringstatus')
            else: missing.append('SolarEdge monitoringstatus')
            led_parts=[extra.get('red_led'),extra.get('green_led'),extra.get('blue_led')]
            if any(led_parts): facts.append('SolarEdge LED-combinatie')
            else: missing.append('SolarEdge LED-combinatie')
            if extra.get('recent_event'): facts.append('Recent event / gedrag')
        elif manufacturer=='GoodWe':
            if extra.get('fault_led'): facts.append('GoodWe fault-LED')
            else: missing.append('GoodWe fault-LED')
            if extra.get('monitoring_status'): facts.append('SEMS/SolarGo monitoringstatus')
            else: missing.append('SEMS/SolarGo monitoringstatus')
        dispatch='PV-serviceteam'

    elif t=='Thuisbatterij':
        if extra.get('soc') or '%' in l or 'soc' in l: facts.append('State of Charge')
        else: missing.append('State of Charge')
        if extra.get('firmware') or 'firmware' in l or 'versie' in l: facts.append('Firmware/context')
        else: missing.append('Firmware/context')
        if manufacturer=='GoodWe':
            if extra.get('monitoring_status'): facts.append('SEMS/SolarGo monitoringstatus')
            else: missing.append('SEMS/SolarGo monitoringstatus')
            if extra.get('bms_warning'): facts.append('BMS warning/status')
        elif manufacturer=='SolarEdge':
            if extra.get('monitoring_status'): facts.append('SolarEdge monitoringstatus')
            else: missing.append('SolarEdge monitoringstatus')
        dispatch='Batterij/energieopslag specialist'
    else:
        facts.append('Klachtomschrijving')
        if extra.get('breaker') or any(x in l for x in ['automaat','aardlek','groep']): facts.append('Automaat/aardlek status')
        else: missing.append('Automaat/aardlek status')
        dispatch='Bevoegde elektromonteur'

    score=round(len(facts)/max(1,len(facts)+len(missing))*100)
    fault=classify_fault(t,manufacturer,text,extra)
    if fault['triage']=='veiligheidsreview': dispatch='Bevoegde technicus — veiligheidsreview vóór dispatch'
    elif fault['triage']=='technische review' and 'review' not in dispatch.lower(): dispatch=dispatch+' — technische review'
    return facts,missing,score,dispatch,prep_for(t,manufacturer,extra,fault),fault



def setting_float(key, default=0.0):
    try:
        v=setting(key)
        return float(v) if v is not None else float(default)
    except Exception:
        return float(default)

def economic_assumptions():
    return {
        'baseline_planner_minutes':setting_float('baseline_planner_minutes',13),
        'planner_hourly_cost':setting_float('planner_hourly_cost',40),
        'technician_hourly_cost':setting_float('technician_hourly_cost',55),
        'avg_site_visit_minutes':setting_float('avg_site_visit_minutes',90),
        'avg_roundtrip_km':setting_float('avg_roundtrip_km',35),
        'cost_per_km':setting_float('cost_per_km',0.35),
        'software_monthly_cost':setting_float('software_monthly_cost',299),
        'monthly_case_volume':setting_float('monthly_case_volume',150)
    }

def calculate_economic_impact(con):
    a=economic_assumptions()
    outcome_rows=con.execute("""SELECT outcome_planner_minutes,outcome_remote_resolved,
        outcome_second_visit_required,outcome_preventable
        FROM cases WHERE outcome_recorded_at IS NOT NULL""").fetchall()

    planner_minutes_saved=0.0
    planner_measured_cases=0
    remote_count=0
    preventable_second_count=0
    second_count=0

    for r in outcome_rows:
        if r['outcome_planner_minutes'] is not None:
            planner_measured_cases+=1
            planner_minutes_saved += max(0.0,a['baseline_planner_minutes']-float(r['outcome_planner_minutes']))
        if r['outcome_remote_resolved']:
            remote_count+=1
        if r['outcome_second_visit_required']:
            second_count+=1
        if r['outcome_second_visit_required'] and r['outcome_preventable']:
            preventable_second_count+=1

    planner_value=planner_minutes_saved/60.0*a['planner_hourly_cost']
    visit_cost=(a['avg_site_visit_minutes']/60.0*a['technician_hourly_cost'])+(a['avg_roundtrip_km']*a['cost_per_km'])
    remote_value=remote_count*visit_cost
    avoidable_waste=preventable_second_count*visit_cost

    outcomes=len(outcome_rows)
    avg_planner_minutes_saved=(planner_minutes_saved/planner_measured_cases) if planner_measured_cases else 0.0
    remote_rate=(remote_count/outcomes) if outcomes else 0.0
    preventable_rate=(preventable_second_count/outcomes) if outcomes else 0.0

    projected_planner_value=avg_planner_minutes_saved*a['monthly_case_volume']/60.0*a['planner_hourly_cost']
    projected_remote_value=remote_rate*a['monthly_case_volume']*visit_cost
    projected_avoidable_waste=preventable_rate*a['monthly_case_volume']*visit_cost
    projected_gross=projected_planner_value+projected_remote_value
    projected_net=projected_gross-a['software_monthly_cost']

    return {
        'assumptions':a,
        'measured':{
            'planner_cases_measured':planner_measured_cases,
            'planner_minutes_saved':round(planner_minutes_saved,1),
            'planner_time_value_eur':round(planner_value,2),
            'remote_resolved_count':remote_count,
            'estimated_remote_visit_value_eur':round(remote_value,2),
            'avoidable_second_visits_observed':preventable_second_count,
            'estimated_avoidable_waste_eur':round(avoidable_waste,2),
            'second_visits_observed':second_count
        },
        'projection':{
            'monthly_case_volume':a['monthly_case_volume'],
            'projected_planner_value_eur':round(projected_planner_value,2),
            'projected_remote_value_eur':round(projected_remote_value,2),
            'projected_gross_value_eur':round(projected_gross,2),
            'software_monthly_cost_eur':round(a['software_monthly_cost'],2),
            'projected_net_value_eur':round(projected_net,2),
            'projected_avoidable_waste_eur':round(projected_avoidable_waste,2),
            'break_even':(projected_gross>=a['software_monthly_cost']) if outcomes else None
        },
        'method':{
            'measured_planner_savings':'Baseline planner minutes minus manually recorded actual planner minutes, never below zero.',
            'remote_value':'Remote-resolved cases multiplied by configurable estimated technician visit + travel cost.',
            'avoidable_waste':'Second visits marked preventable multiplied by the same configurable visit estimate. This is opportunity loss, not realised savings.',
            'projection':'Pilot averages/rates projected to configurable monthly case volume. This is an estimate, not measured value.'
        }
    }


def _split_reason_text(value):
    text=(value or '').strip()
    if not text:
        return []
    parts=[]
    for chunk in text.replace(';',',').split(','):
        c=chunk.strip()
        if c:
            parts.append(c)
    return parts

def generate_management_report(con):
    metrics = {
        'total_cases': con.execute("SELECT COUNT(*) n FROM cases").fetchone()['n'],
        'outcomes': con.execute("SELECT COUNT(*) n FROM cases WHERE outcome_recorded_at IS NOT NULL").fetchone()['n'],
        'first_time_fix': con.execute("SELECT COUNT(*) n FROM cases WHERE outcome_resolved_first_visit=1").fetchone()['n'],
        'second_visits': con.execute("SELECT COUNT(*) n FROM cases WHERE outcome_second_visit_required=1").fetchone()['n'],
        'remote_resolved': con.execute("SELECT COUNT(*) n FROM cases WHERE outcome_remote_resolved=1").fetchone()['n'],
        'preventable_second': con.execute("SELECT COUNT(*) n FROM cases WHERE outcome_second_visit_required=1 AND outcome_preventable=1").fetchone()['n'],
        'wrong_skill': con.execute("SELECT COUNT(*) n FROM cases WHERE outcome_wrong_skill=1").fetchone()['n'],
    }

    outcomes=max(1,metrics['outcomes'])
    metrics.update({
        'first_time_fix_pct': round(100*metrics['first_time_fix']/outcomes,1) if metrics['outcomes'] else 0.0,
        'second_visit_pct': round(100*metrics['second_visits']/outcomes,1) if metrics['outcomes'] else 0.0,
        'remote_resolved_pct': round(100*metrics['remote_resolved']/outcomes,1) if metrics['outcomes'] else 0.0,
        'preventable_second_visit_pct': round(100*metrics['preventable_second']/max(1,metrics['second_visits']),1) if metrics['second_visits'] else 0.0,
    })

    rows=con.execute("""SELECT case_no,fault_category,service_route,outcome_missing_info,
        outcome_missing_material,outcome_wrong_skill,outcome_preventable,outcome_second_visit_required,
        outcome_remote_resolved,outcome_resolved_first_visit
        FROM cases WHERE outcome_recorded_at IS NOT NULL""").fetchall()

    info_counter=Counter()
    material_counter=Counter()
    route_counter=Counter()
    fault_counter=Counter()
    for r in rows:
        for item in _split_reason_text(r['outcome_missing_info']):
            info_counter[item]+=1
        for item in _split_reason_text(r['outcome_missing_material']):
            material_counter[item]+=1
        if r['service_route']:
            route_counter[r['service_route']]+=1
        if r['fault_category']:
            fault_counter[r['fault_category']]+=1

    economics=calculate_economic_impact(con)
    e=economics['projection']
    min_outcomes=10

    if metrics['outcomes'] < min_outcomes:
        decision={
            'status':'onvoldoende_data',
            'label':'Nog onvoldoende data',
            'reason':f"Er zijn {metrics['outcomes']} outcomes geregistreerd; minimaal {min_outcomes} wordt aangeraden voor een eerste financiële pilotsignalering.",
            'criterion':'Geen financiële go/no-go vóór minimaal 10 geregistreerde outcomes.'
        }
    elif e['projected_net_value_eur'] > 0:
        decision={
            'status':'positief_signaal',
            'label':'Positief financieel pilotsignaal',
            'reason':f"De geprojecteerde netto maandwaarde is €{e['projected_net_value_eur']:.0f} boven de ingestelde softwarekosten, op basis van de huidige pilotratios en aannames.",
            'criterion':'Positief wanneer geprojecteerde bruto waarde hoger is dan ingestelde softwarekosten.'
        }
    else:
        decision={
            'status':'negatief_signaal',
            'label':'Nog geen positief financieel pilotsignaal',
            'reason':f"De geprojecteerde netto maandwaarde is €{e['projected_net_value_eur']:.0f}; de huidige pilotdata en aannames dekken de ingestelde softwarekosten nog niet.",
            'criterion':'Negatief wanneer geprojecteerde bruto waarde niet hoger is dan ingestelde softwarekosten.'
        }

    recommendations=[]
    if metrics['second_visits']:
        if metrics['preventable_second_visit_pct'] >= 30:
            recommendations.append("Prioriteer het terugdringen van voorkombare tweede bezoeken; dit is momenteel de duidelijkste operationele verbeterkans.")
        else:
            recommendations.append("Blijf tweede-bezoekoorzaken registreren; het huidige aandeel als voorkombaar gemarkeerde ritten is nog beperkt.")
    if info_counter:
        top=info_counter.most_common(1)[0]
        recommendations.append(f"Maak '{top[0]}' een expliciet preflight-veld; dit was de meest genoemde ontbrekende informatie ({top[1]} keer).")
    if material_counter:
        top=material_counter.most_common(1)[0]
        recommendations.append(f"Onderzoek voorbereiding rond '{top[0]}'; dit was het meest genoemde ontbrekende materiaal/onderdeel ({top[1]} keer).")
    if metrics['wrong_skill']:
        recommendations.append(f"Verbeter skill-based dispatch; bij {metrics['wrong_skill']} outcome(s) is verkeerde expertise vastgelegd.")
    if metrics['remote_resolved']:
        recommendations.append(f"Borg remote-first triage: {metrics['remote_resolved']} case(s) zijn volledig remote opgelost.")
    if not recommendations:
        recommendations.append("Blijf outcomes, plannertijd en tweede-bezoekoorzaken registreren om de businesscase te verfijnen.")

    return {
        'generated_at':now_iso(),
        'company_name':setting('company_name') or 'Organisatie',
        'sample_quality':{
            'outcomes':metrics['outcomes'],
            'minimum_for_signal':min_outcomes,
            'sufficient_for_signal':metrics['outcomes']>=min_outcomes
        },
        'operations':metrics,
        'economics':economics,
        'top_causes':{
            'missing_information':[{'label':k,'count':v} for k,v in info_counter.most_common(5)],
            'missing_material':[{'label':k,'count':v} for k,v in material_counter.most_common(5)],
            'service_routes':[{'label':k,'count':v} for k,v in route_counter.most_common(5)],
            'fault_categories':[{'label':k,'count':v} for k,v in fault_counter.most_common(5)]
        },
        'decision':decision,
        'recommendations':recommendations,
        'interpretation_notes':[
            'Gemeten plannerwaarde gebruikt alleen cases met handmatig geregistreerde werkelijke planner-/voorbereidingstijd.',
            'Remote ritwaarde en maandprojectie gebruiken instelbare aannames en zijn schattingen.',
            'Voorkombare tweede ritten zijn gemiste kansen/opportunity loss, geen gerealiseerde besparing.',
            'Een pilotsignaal is geen garantie voor structurele ROI; valideer over een langere periode en grotere steekproef.'
        ]
    }


def active_pilot(con):
    return con.execute("SELECT * FROM pilots WHERE active=1 ORDER BY id DESC LIMIT 1").fetchone()

def pilot_current_metrics(con):
    rows=con.execute("""SELECT outcome_planner_minutes,outcome_resolved_first_visit,outcome_second_visit_required,
      outcome_remote_resolved,outcome_preventable
      FROM cases WHERE outcome_recorded_at IS NOT NULL""").fetchall()
    n=len(rows)
    planner=[float(r['outcome_planner_minutes']) for r in rows if r['outcome_planner_minutes'] is not None]
    return {
      'outcomes':n,
      'avg_planner_minutes': round(sum(planner)/len(planner),2) if planner else None,
      'first_time_fix_pct': round(100*sum(1 for r in rows if r['outcome_resolved_first_visit'])/n,1) if n else 0.0,
      'second_visit_pct': round(100*sum(1 for r in rows if r['outcome_second_visit_required'])/n,1) if n else 0.0,
      'remote_resolved_pct': round(100*sum(1 for r in rows if r['outcome_remote_resolved'])/n,1) if n else 0.0,
      'preventable_second_visit_pct': round(
         100*sum(1 for r in rows if r['outcome_second_visit_required'] and r['outcome_preventable'])/
         max(1,sum(1 for r in rows if r['outcome_second_visit_required'])),1
      ) if n else 0.0
    }

def pilot_progress_payload(con):
    p=active_pilot(con)
    if not p:
        return {'active':False}
    p=dict(p)
    cur=pilot_current_metrics(con)
    econ=calculate_economic_impact(con)
    today=date.today()
    start=date.fromisoformat(p['start_date'])
    end=date.fromisoformat(p['end_date'])
    total_days=max(1,(end-start).days+1)
    elapsed=max(0,min(total_days,(today-start).days+1))
    elapsed_pct=round(100*elapsed/total_days,1)

    def delta(current, baseline):
        if current is None or baseline is None:
            return None
        return round(current-baseline,2)

    progress={
      'active':True,
      'pilot':p,
      'days':{'elapsed':elapsed,'total':total_days,'elapsed_pct':elapsed_pct,'remaining':max(0,total_days-elapsed)},
      'current':cur,
      'delta':{
        'planner_minutes':delta(cur['avg_planner_minutes'],p['baseline_planner_minutes']),
        'first_time_fix_pct':delta(cur['first_time_fix_pct'],p['baseline_first_time_fix_pct']),
        'second_visit_pct':delta(cur['second_visit_pct'],p['baseline_second_visit_pct']),
        'remote_resolved_pct':delta(cur['remote_resolved_pct'],p['baseline_remote_resolved_pct']),
      },
      'goals':{
        'planner_minutes':{'target':p['target_planner_minutes'],'met': cur['avg_planner_minutes'] is not None and p['target_planner_minutes'] is not None and cur['avg_planner_minutes']<=p['target_planner_minutes']},
        'first_time_fix_pct':{'target':p['target_first_time_fix_pct'],'met':p['target_first_time_fix_pct'] is not None and cur['first_time_fix_pct']>=p['target_first_time_fix_pct']},
        'second_visit_pct':{'target':p['target_second_visit_pct'],'met':p['target_second_visit_pct'] is not None and cur['second_visit_pct']<=p['target_second_visit_pct']},
        'remote_resolved_pct':{'target':p['target_remote_resolved_pct'],'met':p['target_remote_resolved_pct'] is not None and cur['remote_resolved_pct']>=p['target_remote_resolved_pct']},
      },
      'economics':econ
    }
    return progress

def save_pilot_snapshot(con,pilot_id):
    cur=pilot_current_metrics(con)
    econ=calculate_economic_impact(con)
    m=econ['measured']
    con.execute("""INSERT INTO pilot_snapshots(
      pilot_id,snapshot_date,outcomes,avg_planner_minutes,first_time_fix_pct,second_visit_pct,
      remote_resolved_pct,preventable_second_visit_pct,measured_planner_value_eur,
      estimated_remote_value_eur,avoidable_waste_eur
    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(pilot_id,snapshot_date) DO UPDATE SET
      outcomes=excluded.outcomes,
      avg_planner_minutes=excluded.avg_planner_minutes,
      first_time_fix_pct=excluded.first_time_fix_pct,
      second_visit_pct=excluded.second_visit_pct,
      remote_resolved_pct=excluded.remote_resolved_pct,
      preventable_second_visit_pct=excluded.preventable_second_visit_pct,
      measured_planner_value_eur=excluded.measured_planner_value_eur,
      estimated_remote_value_eur=excluded.estimated_remote_value_eur,
      avoidable_waste_eur=excluded.avoidable_waste_eur""",
      (pilot_id,date.today().isoformat(),cur['outcomes'],cur['avg_planner_minutes'],cur['first_time_fix_pct'],
       cur['second_visit_pct'],cur['remote_resolved_pct'],cur['preventable_second_visit_pct'],
       m['planner_time_value_eur'],m['estimated_remote_visit_value_eur'],m['estimated_avoidable_waste_eur']))

def pilot_final_report(con):
    p=active_pilot(con)
    if not p:
        # fall back to most recent inactive pilot
        p=con.execute("SELECT * FROM pilots ORDER BY id DESC LIMIT 1").fetchone()
    if not p:
        return {'available':False}
    p=dict(p)
    cur=pilot_current_metrics(con)
    econ=calculate_economic_impact(con)
    snapshots=[dict(r) for r in con.execute("SELECT * FROM pilot_snapshots WHERE pilot_id=? ORDER BY snapshot_date",(p['id'],))]
    outcomes=cur['outcomes']
    min_outcomes=10
    goals=[]
    goal_defs=[
      ('Planner-/voorbereidingstijd','avg_planner_minutes','target_planner_minutes','lower'),
      ('First-time-fix','first_time_fix_pct','target_first_time_fix_pct','higher'),
      ('Tweede bezoek','second_visit_pct','target_second_visit_pct','lower'),
      ('Remote opgelost','remote_resolved_pct','target_remote_resolved_pct','higher'),
    ]
    for label,current_key,target_key,direction in goal_defs:
        target=p.get(target_key)
        current=cur.get(current_key)
        met=False
        if target is not None and current is not None:
            met=current<=target if direction=='lower' else current>=target
        goals.append({'label':label,'current':current,'target':target,'met':met,'direction':direction})

    if outcomes<min_outcomes:
        conclusion='onvoldoende_data'
        conclusion_text=f'Pilot bevat {outcomes} geregistreerde outcomes; minimaal {min_outcomes} wordt aangeraden voor een eerste eindoordeel.'
    else:
        met_count=sum(1 for g in goals if g['target'] is not None and g['met'])
        defined_count=sum(1 for g in goals if g['target'] is not None)
        financial_positive=econ['projection']['projected_net_value_eur']>0
        if defined_count and met_count>=max(1,(defined_count+1)//2) and financial_positive:
            conclusion='positief'
            conclusion_text='Meerderheid van de gedefinieerde pilotdoelen is gehaald en de huidige economische projectie is positief.'
        else:
            conclusion='verbeteren'
            conclusion_text='Niet genoeg pilotdoelen zijn gehaald en/of de huidige economische projectie is nog niet positief.'

    return {
      'available':True,
      'pilot':p,
      'current':cur,
      'baseline':{
        'planner_minutes':p['baseline_planner_minutes'],
        'first_time_fix_pct':p['baseline_first_time_fix_pct'],
        'second_visit_pct':p['baseline_second_visit_pct'],
        'remote_resolved_pct':p['baseline_remote_resolved_pct'],
      },
      'goals':goals,
      'economics':econ,
      'snapshots':snapshots,
      'sample_quality':{'outcomes':outcomes,'minimum_for_conclusion':min_outcomes,'sufficient':outcomes>=min_outcomes},
      'conclusion':{'status':conclusion,'text':conclusion_text}
    }



def setting_json(key, default):
    try:
        raw=setting(key)
        return json.loads(raw) if raw else default
    except Exception:
        return default

def onboarding_payload():
    return {
        'complete': setting('onboarding_complete')=='1',
        'company_name': setting('company_name') or 'Demo Installatietechniek',
        'enabled_service_types': setting_json('enabled_service_types',["Laadpaal","Zonnepanelen","Thuisbatterij","Elektro"]),
        'enabled_brands': setting_json('enabled_brands',{}),
        'assumptions': economic_assumptions(),
        'branding':{'brand_name':setting('brand_name') or 'Project Preflight','brand_accent':setting('brand_accent') or '#62d0ff','support_email':setting('support_email') or '','customer_portal_title':setting('customer_portal_title') or 'Service-intake'},
        'intake_token': setting('intake_token')
    }

def create_team_user(con,email,display_name,role,password):
    email=(email or '').strip().lower()
    display_name=(display_name or '').strip()
    role=(role or '').strip().lower()
    if not email or '@' not in email:
        raise ValueError('ongeldig e-mailadres')
    if not display_name:
        raise ValueError('naam ontbreekt')
    if role not in ('admin','planner','technician'):
        raise ValueError('ongeldige rol')
    if not password or len(password)<8:
        raise ValueError('wachtwoord moet minimaal 8 tekens zijn')
    exists=con.execute("SELECT id FROM users WHERE email=?",(email,)).fetchone()
    if exists:
        return exists['id'],False
    cur=con.execute(
        "INSERT INTO users(email,display_name,role,password_hash,created_at) VALUES(?,?,?,?,?)",
        (email,display_name,role,hash_password(password),now_iso())
    )
    return cur.lastrowid,True



def valid_hex_color(value):
    return bool(re.fullmatch(r'#[0-9a-fA-F]{6}',str(value or '')))

def export_operational_data(con):
    def rows(sql,args=()): return [dict(r) for r in con.execute(sql,args)]
    return {
      'meta':{'app_name':APP_NAME,'app_version':APP_VERSION,'exported_at':now_iso(),'contains_passwords':False,'contains_attachment_bytes':False},
      'settings':rows('SELECT key,value FROM settings ORDER BY key'),
      'users':rows('SELECT id,email,display_name,role,active,created_at FROM users ORDER BY id'),
      'pilots':rows('SELECT * FROM pilots ORDER BY id'),
      'pilot_snapshots':rows('SELECT * FROM pilot_snapshots ORDER BY id'),
      'cases':[row_case(r) for r in con.execute('SELECT * FROM cases ORDER BY id')],
      'notes':rows('SELECT * FROM notes ORDER BY id'),
      'attachments':rows('SELECT id,case_id,filename,content_type,size_bytes,created_by,created_at FROM attachments ORDER BY id'),
      'audit':rows('SELECT * FROM audit ORDER BY id')
    }

def pilot_reset_summary(con):
    return {
      'cases':con.execute('SELECT COUNT(*) n FROM cases').fetchone()['n'],
      'notes':con.execute('SELECT COUNT(*) n FROM notes').fetchone()['n'],
      'attachments':con.execute('SELECT COUNT(*) n FROM attachments').fetchone()['n'],
      'audit_events':con.execute('SELECT COUNT(*) n FROM audit').fetchone()['n'],
      'pilots':con.execute('SELECT COUNT(*) n FROM pilots').fetchone()['n'],
      'pilot_snapshots':con.execute('SELECT COUNT(*) n FROM pilot_snapshots').fetchone()['n']
    }

def init_db():
    DATA.mkdir(exist_ok=True); UPLOADS.mkdir(exist_ok=True); con=db()
    con.executescript('''
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,email TEXT UNIQUE NOT NULL,display_name TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('admin','planner','technician')),password_hash TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS cases(id INTEGER PRIMARY KEY AUTOINCREMENT,case_no TEXT UNIQUE NOT NULL,source TEXT NOT NULL DEFAULT 'planner',customer TEXT NOT NULL,city TEXT,phone TEXT,email TEXT,type TEXT NOT NULL,asset TEXT,status TEXT NOT NULL,score INTEGER NOT NULL,problem TEXT,facts_json TEXT NOT NULL,missing_json TEXT NOT NULL,dispatch TEXT,prep_json TEXT NOT NULL DEFAULT '[]',assigned_to INTEGER REFERENCES users(id),intake_seconds INTEGER,version INTEGER NOT NULL DEFAULT 1,created_by INTEGER REFERENCES users(id),created_at TEXT NOT NULL,planner_ready_at TEXT,scheduled_at TEXT,closed_at TEXT,updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY AUTOINCREMENT,case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,body TEXT NOT NULL,created_by INTEGER NOT NULL REFERENCES users(id),created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS attachments(id INTEGER PRIMARY KEY AUTOINCREMENT,case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,filename TEXT NOT NULL,stored_name TEXT NOT NULL,content_type TEXT,size_bytes INTEGER NOT NULL,created_by INTEGER REFERENCES users(id),created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,case_id INTEGER REFERENCES cases(id) ON DELETE CASCADE,user_id INTEGER REFERENCES users(id),action TEXT NOT NULL,detail TEXT,created_at TEXT NOT NULL);
    ''')


    con.execute("""CREATE TABLE IF NOT EXISTS pilots(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      start_date TEXT NOT NULL,
      end_date TEXT NOT NULL,
      baseline_planner_minutes REAL,
      baseline_first_time_fix_pct REAL,
      baseline_second_visit_pct REAL,
      baseline_remote_resolved_pct REAL,
      target_planner_minutes REAL,
      target_first_time_fix_pct REAL,
      target_second_visit_pct REAL,
      target_remote_resolved_pct REAL,
      notes TEXT,
      active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS pilot_snapshots(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      pilot_id INTEGER NOT NULL REFERENCES pilots(id) ON DELETE CASCADE,
      snapshot_date TEXT NOT NULL,
      outcomes INTEGER NOT NULL,
      avg_planner_minutes REAL,
      first_time_fix_pct REAL,
      second_visit_pct REAL,
      remote_resolved_pct REAL,
      preventable_second_visit_pct REAL,
      measured_planner_value_eur REAL,
      estimated_remote_value_eur REAL,
      avoidable_waste_eur REAL,
      UNIQUE(pilot_id,snapshot_date)
    )""")

    cols={r['name'] for r in con.execute("PRAGMA table_info(cases)")}
    for col,definition in [
        ('manufacturer','TEXT'),('model','TEXT'),('serial_no','TEXT'),
        ('knowledge_title','TEXT'),('knowledge_url','TEXT'),('api_targets_json',"TEXT NOT NULL DEFAULT '[]'"),
        ('fault_category','TEXT'),('fault_confidence','TEXT'),('triage_level','TEXT'),('fault_evidence_json',"TEXT NOT NULL DEFAULT '[]'"),
        ('service_route','TEXT'),('required_competence','TEXT'),('remote_checks_json',"TEXT NOT NULL DEFAULT '[]'"),
        ('site_trigger','TEXT'),('prep_categories_json',"TEXT NOT NULL DEFAULT '[]'"),('escalation_path','TEXT'),
        ('route_source_title','TEXT'),('route_source_url','TEXT'),
        ('ftf_critical_json',"TEXT NOT NULL DEFAULT '[]'"),('ftf_gaps_json',"TEXT NOT NULL DEFAULT '[]'"),
        ('ftf_parts_json',"TEXT NOT NULL DEFAULT '[]'"),
        ('outcome_resolved_first_visit','INTEGER'),('outcome_second_visit_required','INTEGER'),
        ('outcome_remote_resolved','INTEGER'),('outcome_missing_info','TEXT'),('outcome_missing_material','TEXT'),
        ('outcome_wrong_skill','INTEGER'),('outcome_preventable','INTEGER'),('outcome_notes','TEXT'),
        ('outcome_planner_minutes','REAL'),('outcome_recorded_at','TEXT')
    ]:
        if col not in cols:
            con.execute(f"ALTER TABLE cases ADD COLUMN {col} {definition}")

    if con.execute("SELECT COUNT(*) n FROM settings WHERE key='intake_token'").fetchone()['n']==0: con.execute("INSERT INTO settings(key,value) VALUES('intake_token',?)",(secrets.token_urlsafe(18),))
    if con.execute("SELECT COUNT(*) n FROM settings WHERE key='company_name'").fetchone()['n']==0: con.execute("INSERT INTO settings(key,value) VALUES('company_name','Demo Installatietechniek')")
    onboarding_defaults={
        'onboarding_complete':'0',
        'enabled_service_types':'["Laadpaal","Zonnepanelen","Thuisbatterij","Elektro"]',
        'enabled_brands':'{"Laadpaal":["Easee","Alfen","Wallbox","Zaptec","Anders/onbekend"],"Zonnepanelen":["SolarEdge","GoodWe","Growatt","SMA","Enphase","Anders/onbekend"],"Thuisbatterij":["SolarEdge","GoodWe","BYD","Huawei","Tesla","Anders/onbekend"],"Elektro":["Anders/onbekend"]}'
    }
    for k,v in onboarding_defaults.items():
        if con.execute("SELECT COUNT(*) n FROM settings WHERE key=?",(k,)).fetchone()['n']==0:
            con.execute("INSERT INTO settings(key,value) VALUES(?,?)",(k,v))

    defaults={
        'baseline_planner_minutes':'13',
        'planner_hourly_cost':'40',
        'technician_hourly_cost':'55',
        'avg_site_visit_minutes':'90',
        'avg_roundtrip_km':'35',
        'cost_per_km':'0.35',
        'software_monthly_cost':'299',
        'monthly_case_volume':'150',
        'brand_name':'Project Preflight',
        'brand_accent':'#62d0ff',
        'support_email':'',
        'customer_portal_title':'Service-intake'
    }
    for k,v in defaults.items():
        if con.execute("SELECT COUNT(*) n FROM settings WHERE key=?",(k,)).fetchone()['n']==0:
            con.execute("INSERT INTO settings(key,value) VALUES(?,?)",(k,v))

    if con.execute('SELECT COUNT(*) n FROM users').fetchone()['n']==0:
        for email,name,role,pwd in [('planner@preflight.local','Planner Demo','planner','Pilot2026!'),('monteur@preflight.local','Monteur Demo','technician','Pilot2026!'),('admin@preflight.local','Admin Demo','admin','Pilot2026!')]:
            con.execute('INSERT INTO users(email,display_name,role,password_hash,created_at) VALUES(?,?,?,?,?)',(email,name,role,hash_password(pwd),now_iso()))
        planner=con.execute("SELECT id FROM users WHERE role='planner'").fetchone()['id']; tech=con.execute("SELECT id FROM users WHERE role='technician'").fetchone()['id']
        seed=[('PF-01011','planner','J. Jansen','Nijmegen','Laadpaal','Easee Charge Lite','Review',92,'Laadpaal laadt niet; LED rood.',['Klant & locatie','LED/status','Voertuig elders getest'],['Foutcode / screenshot'],'Laadpuntgericht serviceonderzoek',prep_for('Laadpaal'),tech,planner),('PF-01012','planner','Peters','Wijchen','Zonnepanelen','SolarEdge SE8K-RWS','Info ontbreekt',66,'Geen productie sinds vanochtend.',['Klant & locatie','Productiestatus'],['Foutcode','Foto display/typeplaat'],'PV-serviceteam',prep_for('Zonnepanelen'),None,planner)]
        for r in seed:
            con.execute('''INSERT INTO cases(case_no,source,customer,city,type,asset,status,score,problem,facts_json,missing_json,dispatch,prep_json,assigned_to,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(r[0],r[1],r[2],r[3],r[4],r[5],r[6],r[7],r[8],json.dumps(r[9]),json.dumps(r[10]),r[11],json.dumps(r[12]),r[13],r[14],now_iso(),now_iso()))
    con.commit(); con.close()

def setting(key):
    con=db(); r=con.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone(); con.close(); return r['value'] if r else None

def audit(con,case_id,user_id,action,detail=''): con.execute('INSERT INTO audit(case_id,user_id,action,detail,created_at) VALUES(?,?,?,?,?)',(case_id,user_id,action,detail,now_iso()))
def row_case(r):
    d=dict(r)
    for src,tgt in [('facts_json','facts'),('missing_json','missing'),('prep_json','prep'),('api_targets_json','api_targets'),('fault_evidence_json','fault_evidence'),('remote_checks_json','remote_checks'),('prep_categories_json','prep_categories'),('ftf_critical_json','ftf_critical'),('ftf_gaps_json','ftf_gaps'),('ftf_parts_json','ftf_parts')]:
        if src in d: d[tgt]=json.loads(d.pop(src) or '[]')
    return d

class Handler(BaseHTTPRequestHandler):
    server_version='PreflightPilotPro/1.0'
    def log_message(self,fmt,*args): sys.stdout.write('[%s] %s\n'%(self.log_date_time_string(),fmt%args))
    def _json(self,obj,status=200):
        raw=json.dumps(obj,ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(raw))); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(raw)
    def _read_json(self):
        n=int(self.headers.get('Content-Length','0'))
        if n>MAX_BODY: raise ValueError('request too large')
        return json.loads(self.rfile.read(n) or b'{}')
    def _user(self):
        auth=self.headers.get('Authorization','')
        if not auth.startswith('Bearer '): return None
        with SESSION_LOCK: uid=SESSIONS.get(auth[7:])
        if not uid:return None
        con=db();r=con.execute('SELECT id,email,display_name,role,active FROM users WHERE id=?',(uid,)).fetchone();con.close();return dict(r) if r and r['active'] else None
    def _need(self,roles=None):
        u=self._user()
        if not u:self._json({'error':'unauthorized'},401);return None
        if roles and u['role'] not in roles:self._json({'error':'forbidden'},403);return None
        return u
    def _serve(self,path):
        if path=='/':path='/index.html'
        safe=(STATIC/path.lstrip('/')).resolve()
        if STATIC.resolve() not in safe.parents and safe!=STATIC.resolve():self.send_error(403);return
        if not safe.exists():self.send_error(404);return
        data=safe.read_bytes();ctype=mimetypes.guess_type(str(safe))[0] or 'application/octet-stream';self.send_response(200);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def _case_access(self,con,cid,u):
        c=con.execute('SELECT * FROM cases WHERE id=?',(cid,)).fetchone()
        if not c:return None
        if u['role']=='technician' and c['assigned_to']!=u['id']:return None
        return c
    def do_GET(self):
        p=urlparse(self.path);path=p.path;q=parse_qs(p.query)
        if path=='/api/health':return self._json({'ok':True,'time':now_iso()})
        if path=='/api/public-info':
            token=q.get('token',[''])[0]
            if not hmac.compare_digest(token,setting('intake_token') or ''):return self._json({'error':'invalid token'},403)
            return self._json({
                'company':setting('company_name'),
                'enabled_service_types':setting_json('enabled_service_types',["Laadpaal","Zonnepanelen","Thuisbatterij","Elektro"]),
                'enabled_brands':setting_json('enabled_brands',{}),
                'brand_name':setting('brand_name') or 'Project Preflight',
                'brand_accent':setting('brand_accent') or '#62d0ff',
                'support_email':setting('support_email') or '',
                'customer_portal_title':setting('customer_portal_title') or 'Service-intake'
            })
        if path=='/api/me':
            u=self._need();
            if u:self._json(u)
            return
        if path=='/api/onboarding-status':
            u=self._need(('admin','planner'))
            if not u:return
            return self._json(onboarding_payload())
        if path=='/api/settings':
            u=self._need(('admin','planner'))
            if u:return self._json({'company_name':setting('company_name'),'intake_token':setting('intake_token'),'brand_name':setting('brand_name') or 'Project Preflight','brand_accent':setting('brand_accent') or '#62d0ff','support_email':setting('support_email') or '','customer_portal_title':setting('customer_portal_title') or 'Service-intake','app_version':APP_VERSION,**economic_assumptions()})
            return
        if path=='/api/users':
            u=self._need(('admin','planner'))
            if not u:return
            con=db();rows=[dict(r) for r in con.execute('SELECT id,email,display_name,role,active FROM users ORDER BY role,display_name')];con.close();return self._json(rows)
        if path=='/api/cases':
            u=self._need();
            if not u:return
            con=db();sql='''SELECT c.*,u.display_name assigned_name FROM cases c LEFT JOIN users u ON u.id=c.assigned_to''';args=[]
            if u['role']=='technician':sql+=' WHERE c.assigned_to=?';args=[u['id']]
            sql+=' ORDER BY c.updated_at DESC';rows=[row_case(r) for r in con.execute(sql,args)];con.close();return self._json(rows)
        if path=='/api/metrics':
            u=self._need(('admin','planner'))
            if not u:return
            con=db();total=con.execute('SELECT COUNT(*) n FROM cases').fetchone()['n'];public_n=con.execute("SELECT COUNT(*) n FROM cases WHERE source='customer'").fetchone()['n'];avg=con.execute('SELECT AVG(intake_seconds) v FROM cases WHERE intake_seconds IS NOT NULL').fetchone()['v'];complete=con.execute("SELECT COUNT(*) n FROM cases WHERE missing_json='[]'").fetchone()['n'];scheduled=con.execute('SELECT COUNT(*) n FROM cases WHERE scheduled_at IS NOT NULL').fetchone()['n'];outcomes=con.execute('SELECT COUNT(*) n FROM cases WHERE outcome_recorded_at IS NOT NULL').fetchone()['n'];ftf=con.execute('SELECT COUNT(*) n FROM cases WHERE outcome_resolved_first_visit=1').fetchone()['n'];second=con.execute('SELECT COUNT(*) n FROM cases WHERE outcome_second_visit_required=1').fetchone()['n'];preventable=con.execute('SELECT COUNT(*) n FROM cases WHERE outcome_preventable=1').fetchone()['n'];remote=con.execute('SELECT COUNT(*) n FROM cases WHERE outcome_remote_resolved=1').fetchone()['n'];economics=calculate_economic_impact(con);con.close();payload={'total':total,'customer_intakes':public_n,'avg_intake_seconds':round(avg or 0,1),'complete_pct':round(100*complete/max(1,total),1),'scheduled_pct':round(100*scheduled/max(1,total),1),'outcomes':outcomes,'first_time_fix_pct':round(100*ftf/max(1,outcomes),1),'second_visit_pct':round(100*second/max(1,outcomes),1),'preventable_second_visit_pct':round(100*preventable/max(1,second),1),'remote_resolved_pct':round(100*remote/max(1,outcomes),1)};payload['economics']=economics;return self._json(payload)
        if path.startswith('/api/cases/') and path.endswith('/notes'):
            u=self._need();
            if not u:return
            cid=int(path.split('/')[3]);con=db();c=self._case_access(con,cid,u)
            if not c:con.close();return self._json({'error':'not found'},404)
            rows=[dict(r) for r in con.execute('''SELECT n.*,u.display_name,u.email FROM notes n JOIN users u ON u.id=n.created_by WHERE case_id=? ORDER BY n.created_at''',(cid,))];con.close();return self._json(rows)
        if path.startswith('/api/cases/') and path.endswith('/attachments'):
            u=self._need();
            if not u:return
            cid=int(path.split('/')[3]);con=db();c=self._case_access(con,cid,u)
            if not c:con.close();return self._json({'error':'not found'},404)
            rows=[dict(r) for r in con.execute('SELECT id,case_id,filename,content_type,size_bytes,created_at FROM attachments WHERE case_id=? ORDER BY created_at',(cid,))];con.close();return self._json(rows)
        if path.startswith('/api/attachments/'):
            u=self._need();
            if not u:return
            aid=int(path.split('/')[3]);con=db();a=con.execute('''SELECT a.*,c.assigned_to FROM attachments a JOIN cases c ON c.id=a.case_id WHERE a.id=?''',(aid,)).fetchone();con.close()
            if not a or (u['role']=='technician' and a['assigned_to']!=u['id']):return self._json({'error':'not found'},404)
            f=UPLOADS/a['stored_name']
            if not f.exists():return self._json({'error':'file missing'},404)
            data=f.read_bytes();self.send_response(200);self.send_header('Content-Type',a['content_type'] or 'application/octet-stream');self.send_header('Content-Disposition',f'''attachment; filename="{a['filename'].replace(chr(34),'')}"''');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
        if path=='/api/pilot':
            u=self._need(('admin','planner'))
            if not u:return
            con=db();payload=pilot_progress_payload(con);con.close();return self._json(payload)
        if path=='/api/pilot/snapshots':
            u=self._need(('admin','planner'))
            if not u:return
            con=db();p=active_pilot(con)
            rows=[dict(r) for r in con.execute("SELECT * FROM pilot_snapshots WHERE pilot_id=? ORDER BY snapshot_date",(p['id'],))] if p else []
            con.close();return self._json(rows)
        if path=='/api/pilot/final-report':
            u=self._need(('admin','planner'))
            if not u:return
            con=db();payload=pilot_final_report(con);con.close();return self._json(payload)
        if path=='/api/report':
            u=self._need(('admin','planner'))
            if not u:return
            con=db()
            try:
                report=generate_management_report(con)
            finally:
                con.close()
            return self._json(report)
        if path=='/api/version':
            return self._json({'name':APP_NAME,'version':APP_VERSION,'build':APP_BUILD})
        if path=='/api/accounts':
            u=self._need(('admin',))
            if not u:return
            con=db();rows=[dict(r) for r in con.execute('SELECT id,email,display_name,role,active,created_at FROM users ORDER BY role,display_name')];con.close();return self._json(rows)
        if path=='/api/export':
            u=self._need(('admin',))
            if not u:return
            con=db();payload=export_operational_data(con);con.close();return self._json(payload)
        if path=='/api/pilot-reset-summary':
            u=self._need(('admin',))
            if not u:return
            con=db();payload=pilot_reset_summary(con);con.close();return self._json(payload)
        if path=='/api/audit':
            u=self._need(('admin','planner'))
            if not u:return
            con=db();rows=[dict(r) for r in con.execute('''SELECT a.*,u.display_name FROM audit a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.created_at DESC LIMIT 250''')];con.close();return self._json(rows)
        return self._serve(path)
    def do_POST(self):
        path=urlparse(self.path).path
        try:body=self._read_json()
        except Exception:return self._json({'error':'invalid json'},400)
        if path=='/api/login':
            email=str(body.get('email','')).lower().strip();pwd=str(body.get('password',''));con=db();r=con.execute('SELECT * FROM users WHERE email=? AND active=1',(email,)).fetchone();con.close()
            if not r or not verify_password(pwd,r['password_hash']):return self._json({'error':'ongeldige inloggegevens'},401)
            token=secrets.token_urlsafe(32)
            with SESSION_LOCK:SESSIONS[token]=r['id']
            return self._json({'token':token,'user':{'id':r['id'],'email':r['email'],'display_name':r['display_name'],'role':r['role']}})
        if path=='/api/public-intake':
            token=str(body.get('token',''))
            if not hmac.compare_digest(token,setting('intake_token') or ''):return self._json({'error':'invalid token'},403)
            typ=str(body.get('type','Onbekend'));problem=str(body.get('problem',''));extra=body.get('extra') or {};facts,missing,score,dispatch,prep,fault=analyze(typ,problem,extra);brand=canonical_brand(extra.get('manufacturer'));src=source_for(brand);rk=route_knowledge(fault['category']);fk=ftf_knowledge(fault['category']);case_no='PF-'+str(int(time.time()*1000))[-6:];created=now_iso();con=db();cur=con.execute('''INSERT INTO cases(case_no,source,customer,city,phone,email,type,asset,status,score,problem,facts_json,missing_json,dispatch,prep_json,intake_seconds,created_at,updated_at,manufacturer,model,serial_no,knowledge_title,knowledge_url,api_targets_json,fault_category,fault_confidence,triage_level,fault_evidence_json,service_route,required_competence,remote_checks_json,site_trigger,prep_categories_json,escalation_path,route_source_title,route_source_url,ftf_critical_json,ftf_gaps_json,ftf_parts_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(case_no,'customer',str(body.get('customer','Nieuwe klant')),str(body.get('city','')),str(body.get('phone','')),str(body.get('email','')),typ,(brand+' '+str(extra.get('model') or '')).strip() if brand!='Onbekend' else 'Nog te identificeren','Review' if not missing else 'Info ontbreekt',score,problem,json.dumps(facts),json.dumps(missing),dispatch,json.dumps(prep),int(body.get('intake_seconds') or 0),created,created,brand,str(extra.get('model') or ''),str(extra.get('serial') or ''),src['title'],src['url'],json.dumps(src['api_targets']),fault['category'],fault['confidence'],fault['triage'],json.dumps(fault['evidence']),rk['service_route'],rk['competence'],json.dumps(rk['remote_checks']),rk['site_trigger'],json.dumps(rk['prep_categories']),rk['escalation'],rk['source_title'],rk['source_url'],json.dumps(fk['critical_before_departure']),json.dumps(fk['common_avoidable_gap']),json.dumps(fk['parts_categories'])));cid=cur.lastrowid
            file=body.get('file')
            if file and file.get('data_base64'):
                try:
                    raw=base64.b64decode(file['data_base64'],validate=True)
                    if len(raw)<=5*1024*1024:
                        stored=secrets.token_hex(16)+Path(file.get('name','upload')).suffix[:10];(UPLOADS/stored).write_bytes(raw);con.execute('''INSERT INTO attachments(case_id,filename,stored_name,content_type,size_bytes,created_at) VALUES(?,?,?,?,?,?)''',(cid,file.get('name','upload'),stored,file.get('type','application/octet-stream'),len(raw),created))
                except Exception:pass
            audit(con,cid,None,'public_intake','customer self-service');con.commit();con.close();return self._json({'ok':True,'case_no':case_no,'score':score,'missing':missing,'route':fault['category']},201)
        if path=='/api/logout':
            auth=self.headers.get('Authorization','')
            if auth.startswith('Bearer '):
                with SESSION_LOCK:SESSIONS.pop(auth[7:],None)
            return self._json({'ok':True})
        u=self._need();
        if not u:return
        if path=='/api/change-password':
            current=str(body.get('current_password') or '');new_password=str(body.get('new_password') or '')
            if len(new_password)<10:return self._json({'error':'nieuw wachtwoord moet minimaal 10 tekens zijn'},400)
            con=db();row=con.execute('SELECT * FROM users WHERE id=?',(u['id'],)).fetchone()
            if not row or not verify_password(current,row['password_hash']):con.close();return self._json({'error':'huidig wachtwoord is onjuist'},403)
            con.execute('UPDATE users SET password_hash=? WHERE id=?',(hash_password(new_password),u['id']));audit(con,None,u['id'],'password_changed','self-service');con.commit();con.close();return self._json({'ok':True})
        if path=='/api/accounts':
            if u['role']!='admin':return self._json({'error':'forbidden'},403)
            try:
                con=db();uid,created=create_team_user(con,body.get('email'),body.get('display_name'),body.get('role'),body.get('password'));con.commit();row=con.execute('SELECT id,email,display_name,role,active,created_at FROM users WHERE id=?',(uid,)).fetchone();con.close();return self._json({'created':created,'user':dict(row)},201 if created else 200)
            except ValueError as e:
                try:con.close()
                except:pass
                return self._json({'error':str(e)},400)
        if path.startswith('/api/accounts/') and path.endswith('/reset-password'):
            if u['role']!='admin':return self._json({'error':'forbidden'},403)
            uid=int(path.split('/')[3]);pwd=str(body.get('new_password') or '')
            if len(pwd)<10:return self._json({'error':'nieuw wachtwoord moet minimaal 10 tekens zijn'},400)
            con=db();target=con.execute('SELECT id FROM users WHERE id=?',(uid,)).fetchone()
            if not target:con.close();return self._json({'error':'user not found'},404)
            con.execute('UPDATE users SET password_hash=? WHERE id=?',(hash_password(pwd),uid));audit(con,None,u['id'],'admin_password_reset',str(uid));con.commit();con.close();return self._json({'ok':True})
        if path=='/api/pilot-reset':
            if u['role']!='admin':return self._json({'error':'forbidden'},403)
            if str(body.get('confirm') or '')!='RESET PILOT DATA':return self._json({'error':'bevestigingstekst klopt niet'},400)
            con=db();summary=pilot_reset_summary(con);stored=[r['stored_name'] for r in con.execute('SELECT stored_name FROM attachments')]
            try:
                con.execute('DELETE FROM pilot_snapshots');con.execute('DELETE FROM pilots');con.execute('DELETE FROM notes');con.execute('DELETE FROM attachments');con.execute('DELETE FROM audit');con.execute('DELETE FROM cases');con.execute("INSERT INTO settings(key,value) VALUES('onboarding_complete','0') ON CONFLICT(key) DO UPDATE SET value='0'");con.commit()
            except Exception:
                con.rollback();con.close();return self._json({'error':'reset failed'},500)
            con.close()
            for name in stored:
                try:(UPLOADS/name).unlink(missing_ok=True)
                except Exception:pass
            return self._json({'ok':True,'deleted':summary})
        if path=='/api/onboarding':
            if u['role'] not in ('admin','planner'):return self._json({'error':'forbidden'},403)
            company=str(body.get('company_name') or '').strip()
            if not company:return self._json({'error':'bedrijfsnaam ontbreekt'},400)

            service_types=body.get('enabled_service_types') or []
            allowed_types={'Laadpaal','Zonnepanelen','Thuisbatterij','Elektro'}
            service_types=[x for x in service_types if x in allowed_types]
            if not service_types:return self._json({'error':'selecteer minimaal één servicetype'},400)

            brands=body.get('enabled_brands') or {}
            clean_brands={}
            for t in service_types:
                vals=brands.get(t) or []
                clean=[str(v).strip() for v in vals if str(v).strip()]
                clean_brands[t]=clean or ['Anders/onbekend']

            con=db()
            try:
                con.execute("INSERT INTO settings(key,value) VALUES('company_name',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(company,))
                con.execute("INSERT INTO settings(key,value) VALUES('enabled_service_types',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(service_types,ensure_ascii=False),))
                con.execute("INSERT INTO settings(key,value) VALUES('enabled_brands',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(clean_brands,ensure_ascii=False),))

                assumptions=body.get('assumptions') or {}
                for k in ('baseline_planner_minutes','planner_hourly_cost','technician_hourly_cost','avg_site_visit_minutes','avg_roundtrip_km','cost_per_km','software_monthly_cost','monthly_case_volume'):
                    if k in assumptions:
                        try:value=str(max(0.0,float(assumptions[k])))
                        except Exception:
                            return self._json({'error':'ongeldige aanname: '+k},400)
                        con.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(k,value))

                created_count=0
                for member in body.get('team') or []:
                    _,created=create_team_user(con,member.get('email'),member.get('display_name'),member.get('role'),member.get('password'))
                    created_count+=1 if created else 0

                pilot=body.get('pilot') or {}
                if pilot.get('create'):
                    start_date=str(pilot.get('start_date') or date.today().isoformat())
                    end_date=str(pilot.get('end_date') or (date.today()+timedelta(days=42)).isoformat())
                    try:
                        date.fromisoformat(start_date); date.fromisoformat(end_date)
                    except Exception:
                        return self._json({'error':'ongeldige pilotdatum'},400)
                    if date.fromisoformat(end_date) < date.fromisoformat(start_date):
                        return self._json({'error':'einddatum ligt vóór startdatum'},400)

                    con.execute("UPDATE pilots SET active=0,updated_at=? WHERE active=1",(now_iso(),))
                    con.execute("""INSERT INTO pilots(
                      name,start_date,end_date,baseline_planner_minutes,baseline_first_time_fix_pct,baseline_second_visit_pct,
                      baseline_remote_resolved_pct,target_planner_minutes,target_first_time_fix_pct,target_second_visit_pct,
                      target_remote_resolved_pct,notes,active,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)""",
                    (str(pilot.get('name') or 'Launch Partner Pilot'),start_date,end_date,
                     pilot.get('baseline_planner_minutes'),pilot.get('baseline_first_time_fix_pct'),pilot.get('baseline_second_visit_pct'),
                     pilot.get('baseline_remote_resolved_pct'),pilot.get('target_planner_minutes'),pilot.get('target_first_time_fix_pct'),
                     pilot.get('target_second_visit_pct'),pilot.get('target_remote_resolved_pct'),str(pilot.get('notes') or ''),
                     now_iso(),now_iso()))

                con.execute("INSERT INTO settings(key,value) VALUES('onboarding_complete','1') ON CONFLICT(key) DO UPDATE SET value='1'")
                con.commit()
            except ValueError as e:
                con.rollback()
                return self._json({'error':'teamlid: '+str(e)},400)
            finally:
                con.close()

            return self._json({
                'ok':True,
                'onboarding':onboarding_payload(),
                'team_members_created':created_count,
                'intake_path':'/intake.html?token='+str(setting('intake_token'))
            },201)
        if path=='/api/pilot':
            if u['role'] not in ('admin','planner'):return self._json({'error':'forbidden'},403)
            name=str(body.get('name') or 'Preflight Pilot').strip()
            start_date=str(body.get('start_date') or date.today().isoformat())
            end_date=str(body.get('end_date') or (date.today()+timedelta(days=42)).isoformat())
            try:
                date.fromisoformat(start_date);date.fromisoformat(end_date)
            except Exception:return self._json({'error':'invalid date'},400)
            con=db()
            con.execute("UPDATE pilots SET active=0,updated_at=? WHERE active=1",(now_iso(),))
            cur=con.execute("""INSERT INTO pilots(
              name,start_date,end_date,baseline_planner_minutes,baseline_first_time_fix_pct,baseline_second_visit_pct,
              baseline_remote_resolved_pct,target_planner_minutes,target_first_time_fix_pct,target_second_visit_pct,
              target_remote_resolved_pct,notes,active,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)""",
            (name,start_date,end_date,
             body.get('baseline_planner_minutes'),body.get('baseline_first_time_fix_pct'),body.get('baseline_second_visit_pct'),
             body.get('baseline_remote_resolved_pct'),body.get('target_planner_minutes'),body.get('target_first_time_fix_pct'),
             body.get('target_second_visit_pct'),body.get('target_remote_resolved_pct'),str(body.get('notes') or ''),
             now_iso(),now_iso()))
            pilot_id=cur.lastrowid
            con.commit();payload=pilot_progress_payload(con);con.close();return self._json(payload,201)
        if path=='/api/pilot/snapshot':
            if u['role'] not in ('admin','planner'):return self._json({'error':'forbidden'},403)
            con=db();p=active_pilot(con)
            if not p:con.close();return self._json({'error':'no active pilot'},404)
            save_pilot_snapshot(con,p['id']);con.commit()
            row=con.execute("SELECT * FROM pilot_snapshots WHERE pilot_id=? AND snapshot_date=?",(p['id'],date.today().isoformat())).fetchone()
            con.close();return self._json(dict(row))
        if path=='/api/pilot/close':
            if u['role'] not in ('admin','planner'):return self._json({'error':'forbidden'},403)
            con=db();p=active_pilot(con)
            if not p:con.close();return self._json({'error':'no active pilot'},404)
            save_pilot_snapshot(con,p['id'])
            con.execute("UPDATE pilots SET active=0,updated_at=? WHERE id=?",(now_iso(),p['id']))
            con.commit();payload=pilot_final_report(con);con.close();return self._json(payload)

        if path=='/api/cases':
            if u['role'] not in ('admin','planner'):return self._json({'error':'forbidden'},403)
            typ=str(body.get('type','Onbekend'));extra=body.get('extra') or {};facts,missing,score,dispatch,prep,fault=analyze(typ,str(body.get('problem','')),extra);brand=canonical_brand(extra.get('manufacturer'));src=source_for(brand);rk=route_knowledge(fault['category']);fk=ftf_knowledge(fault['category']);case_no='PF-'+str(int(time.time()*1000))[-6:];created=now_iso();con=db();cur=con.execute('''INSERT INTO cases(case_no,source,customer,city,type,asset,status,score,problem,facts_json,missing_json,dispatch,prep_json,assigned_to,created_by,created_at,updated_at,manufacturer,model,serial_no,knowledge_title,knowledge_url,api_targets_json,fault_category,fault_confidence,triage_level,fault_evidence_json,service_route,required_competence,remote_checks_json,site_trigger,prep_categories_json,escalation_path,route_source_title,route_source_url,ftf_critical_json,ftf_gaps_json,ftf_parts_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(case_no,'planner',body.get('customer') or 'Nieuwe klant',body.get('city'),typ,(brand+' '+str(extra.get('model') or '')).strip() if brand!='Onbekend' else (body.get('asset') or 'Nog te identificeren'),'Review' if not missing else 'Info ontbreekt',score,body.get('problem') or '',json.dumps(facts),json.dumps(missing),dispatch,json.dumps(prep),body.get('assigned_to'),u['id'],created,created,brand,str(extra.get('model') or ''),str(extra.get('serial') or ''),src['title'],src['url'],json.dumps(src['api_targets']),fault['category'],fault['confidence'],fault['triage'],json.dumps(fault['evidence']),rk['service_route'],rk['competence'],json.dumps(rk['remote_checks']),rk['site_trigger'],json.dumps(rk['prep_categories']),rk['escalation'],rk['source_title'],rk['source_url'],json.dumps(fk['critical_before_departure']),json.dumps(fk['common_avoidable_gap']),json.dumps(fk['parts_categories'])));cid=cur.lastrowid;audit(con,cid,u['id'],'case_created',case_no);con.commit();r=con.execute('SELECT * FROM cases WHERE id=?',(cid,)).fetchone();con.close();return self._json(row_case(r),201)
        if path.startswith('/api/cases/') and path.endswith('/outcome'):
            cid=int(path.split('/')[3]);con=db();c=self._case_access(con,cid,u)
            if not c:con.close();return self._json({'error':'not found'},404)
            resolved=1 if body.get('resolved_first_visit') else 0
            second=1 if body.get('second_visit_required') else 0
            remote=1 if body.get('remote_resolved') else 0
            wrong_skill=1 if body.get('wrong_skill') else 0
            preventable=1 if body.get('preventable') else 0
            planner_minutes=body.get('planner_minutes')
            try:planner_minutes=float(planner_minutes) if planner_minutes not in (None,'') else None
            except Exception:planner_minutes=None
            con.execute("""UPDATE cases SET outcome_resolved_first_visit=?,outcome_second_visit_required=?,outcome_remote_resolved=?,outcome_missing_info=?,outcome_missing_material=?,outcome_wrong_skill=?,outcome_preventable=?,outcome_notes=?,outcome_planner_minutes=?,outcome_recorded_at=?,updated_at=? WHERE id=?""",
                        (resolved,second,remote,str(body.get('missing_info','')),str(body.get('missing_material','')),wrong_skill,preventable,str(body.get('notes','')),planner_minutes,now_iso(),now_iso(),cid))
            audit(con,cid,u['id'],'outcome_recorded',json.dumps({'resolved_first_visit':bool(resolved),'second_visit_required':bool(second),'preventable':bool(preventable)}))
            con.commit();r=con.execute('SELECT * FROM cases WHERE id=?',(cid,)).fetchone();con.close();return self._json(row_case(r))
        if path.startswith('/api/cases/') and path.endswith('/notes'):
            cid=int(path.split('/')[3]);text=str(body.get('body','')).strip()
            if not text:return self._json({'error':'empty note'},400)
            con=db();c=self._case_access(con,cid,u)
            if not c:con.close();return self._json({'error':'not found'},404)
            con.execute('INSERT INTO notes(case_id,body,created_by,created_at) VALUES(?,?,?,?)',(cid,text,u['id'],now_iso()));audit(con,cid,u['id'],'note_added','');con.commit();con.close();return self._json({'ok':True},201)
        if path.startswith('/api/cases/') and path.endswith('/attachments'):
            cid=int(path.split('/')[3]);con=db();c=self._case_access(con,cid,u)
            if not c:con.close();return self._json({'error':'not found'},404)
            try:raw=base64.b64decode(str(body.get('data_base64','')),validate=True)
            except Exception:con.close();return self._json({'error':'invalid base64'},400)
            if len(raw)>5*1024*1024:con.close();return self._json({'error':'bestand groter dan 5 MB'},400)
            filename=str(body.get('filename','attachment'));stored=secrets.token_hex(16)+Path(filename).suffix[:10];(UPLOADS/stored).write_bytes(raw);cur=con.execute('''INSERT INTO attachments(case_id,filename,stored_name,content_type,size_bytes,created_by,created_at) VALUES(?,?,?,?,?,?,?)''',(cid,filename,stored,body.get('content_type','application/octet-stream'),len(raw),u['id'],now_iso()));audit(con,cid,u['id'],'attachment_added',filename);con.commit();aid=cur.lastrowid;con.close();return self._json({'id':aid},201)
        return self._json({'error':'not found'},404)
    def do_PATCH(self):
        path=urlparse(self.path).path
        try:body=self._read_json()
        except Exception:return self._json({'error':'invalid json'},400)
        u=self._need();
        if not u:return
        if path=='/api/settings':
            if u['role'] not in ('admin','planner'):return self._json({'error':'forbidden'},403)
            allowed={
                'company_name':str,
                'baseline_planner_minutes':float,
                'planner_hourly_cost':float,
                'technician_hourly_cost':float,
                'avg_site_visit_minutes':float,
                'avg_roundtrip_km':float,
                'cost_per_km':float,
                'software_monthly_cost':float,
                'monthly_case_volume':float,
                'brand_name':str,
                'brand_accent':str,
                'support_email':str,
                'customer_portal_title':str
            }
            con=db()
            for k,typ in allowed.items():
                if k not in body:continue
                try:value=str(body[k]) if typ is str else str(max(0.0,float(body[k])))
                except Exception:
                    con.close();return self._json({'error':'invalid setting: '+k},400)
                if k=='brand_accent' and not valid_hex_color(value):
                    con.close();return self._json({'error':'brand_accent moet hexkleur zijn, bijv. #62d0ff'},400)
                if k=='support_email' and value and '@' not in value:
                    con.close();return self._json({'error':'ongeldig support e-mailadres'},400)
                con.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(k,value))
            con.commit();con.close()
            return self._json({'company_name':setting('company_name'),'brand_name':setting('brand_name') or 'Project Preflight','brand_accent':setting('brand_accent') or '#62d0ff','support_email':setting('support_email') or '','customer_portal_title':setting('customer_portal_title') or 'Service-intake',**economic_assumptions()})
        if path.startswith('/api/accounts/'):
            if u['role']!='admin':return self._json({'error':'forbidden'},403)
            uid=int(path.split('/')[3])
            if uid==u['id'] and body.get('active') is False:return self._json({'error':'je kunt je eigen adminaccount niet deactiveren'},400)
            con=db();target=con.execute('SELECT id FROM users WHERE id=?',(uid,)).fetchone()
            if not target:con.close();return self._json({'error':'user not found'},404)
            updates=[];args=[]
            if 'active' in body:updates.append('active=?');args.append(1 if body['active'] else 0)
            if 'role' in body:
                role=str(body['role'])
                if role not in ('admin','planner','technician'):con.close();return self._json({'error':'invalid role'},400)
                updates.append('role=?');args.append(role)
            if 'display_name' in body:updates.append('display_name=?');args.append(str(body['display_name']).strip())
            if not updates:con.close();return self._json({'error':'no changes'},400)
            args.append(uid);con.execute('UPDATE users SET '+','.join(updates)+' WHERE id=?',args);audit(con,None,u['id'],'account_updated',json.dumps({'target_user_id':uid,'changes':body}));con.commit();row=con.execute('SELECT id,email,display_name,role,active,created_at FROM users WHERE id=?',(uid,)).fetchone();con.close();return self._json(dict(row))
        if path.startswith('/api/cases/'):
            cid=int(path.split('/')[3]);expected=int(body.get('version',0));con=db();c=self._case_access(con,cid,u)
            if not c:con.close();return self._json({'error':'not found'},404)
            if c['version']!=expected:remote=row_case(c);con.close();return self._json({'error':'version_conflict','remote':remote},409)
            updates=[];args=[]
            for k in ('status','score','problem','dispatch'):
                if k in body:updates.append(f'{k}=?');args.append(body[k])
            for k,col in (('facts','facts_json'),('missing','missing_json')):
                if k in body:updates.append(f'{col}=?');args.append(json.dumps(body[k]))
            if 'assigned_to' in body and u['role'] in ('admin','planner'):updates.append('assigned_to=?');args.append(body['assigned_to'])
            new_status=body.get('status',c['status'])
            if new_status in ('Review','Ingepland','Afgerond') and not c['planner_ready_at']:updates.append('planner_ready_at=?');args.append(now_iso())
            if new_status=='Ingepland' and not c['scheduled_at']:updates.append('scheduled_at=?');args.append(now_iso())
            if new_status=='Afgerond' and not c['closed_at']:updates.append('closed_at=?');args.append(now_iso())
            updates+=['version=version+1','updated_at=?'];args.append(now_iso());args.append(cid);con.execute('UPDATE cases SET '+','.join(updates)+' WHERE id=?',args);audit(con,cid,u['id'],'case_updated',json.dumps({'status':new_status}));con.commit();r=con.execute('SELECT * FROM cases WHERE id=?',(cid,)).fetchone();con.close();return self._json(row_case(r))
        return self._json({'error':'not found'},404)

def get_lan_ip():
    try:
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect(('8.8.8.8',80));ip=s.getsockname()[0];s.close();return ip
    except Exception:return '127.0.0.1'

if __name__=='__main__':
    init_db();port=int(os.environ.get('PORT','8765'));lan=get_lan_ip();token=setting('intake_token')
    print('\nPROJECT PREFLIGHT V10 — PILOT PRO\n--------------------------------')
    print(f'Planner: http://127.0.0.1:{port}');print(f'Telefoon: http://{lan}:{port}');print(f'Klant-intake: http://{lan}:{port}/intake.html?token={token}')
    print('\nDemo accounts:\n planner@preflight.local / Pilot2026!\n monteur@preflight.local / Pilot2026!\n admin@preflight.local   / Pilot2026!')
    print('\nLAN-pilot only. Niet port-forwarden naar internet.\n')
    ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
