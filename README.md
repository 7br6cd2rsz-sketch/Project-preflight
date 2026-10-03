# Project Preflight V10 — Pilot Pro

Volledig gratis lokale multi-user pilot, zonder externe cloud.

## Nieuw
- publieke klant-intake via unieke lokale link;
- dynamische vervolgvragen per installatietype;
- optionele foto-upload vanuit klantintake;
- intake-duur wordt gemeten;
- bron (`customer` / `planner`) per case;
- KPI-scherm met gemiddelde klant-intaketijd;
- werkorderweergave met voorbereiding vóór vertrek;
- timestamps voor planner-ready / ingepland / afgerond;
- bestaande multi-user login, rollen, notities, uploads, audit en conflictcontrole.

## Starten
Windows: dubbelklik `start_windows.bat`

macOS/Linux: `./start_mac_linux.sh`

De terminal toont:
- planner URL;
- telefoon URL;
- unieke klant-intake URL.

## Demo accounts
- Planner: `planner@preflight.local` / `Pilot2026!`
- Monteur: `monteur@preflight.local` / `Pilot2026!`
- Admin: `admin@preflight.local` / `Pilot2026!`

## Pilotbeperking
Alleen binnen je eigen LAN/wifi gebruiken. Niet rechtstreeks aan internet blootstellen.
Gebruik voor echte klantdata pas na privacy- en securityreview.

## Technische Preflight Engine — merkprofielen

Deze build bevat actuele, read-only voorbereidende profielen voor:
- **Easee**: klantstatus + toekomstige observations (operation mode, reason-for-no-current, error code, power, Wi-Fi RSSI, cloudconnectiviteit).
- **SolarEdge**: foutcode, LED-combinatie, monitoringstatus, productie/history en device telemetry.
- **GoodWe**: fault-LED, display/app-foutmelding, SEMS/SolarGo status en historische curves/parameters.

De klantflow vraagt uitsluitend wat iemand veilig kan waarnemen. Er staan geen instructies in om behuizingen te openen, elektrische metingen te doen, beveiligingen te resetten of apparatuur op afstand te schakelen.

Officiële referenties:
- https://developer.easee.com/docs/charger-observation-ids
- https://developer.solaredge.com/
- https://knowledge-center.solaredge.com/sites/kc/files/se-inverter-installation-guide-error-codes.pdf
- https://nl.goodwe.com/support-service
- https://nl.goodwe.com/Ftp/Downloads/User%20Manual/GW_ESS%20Troubleshooting%20Guide-NL.pdf

## Storingsroutes

De engine classificeert conservatief in foutfamilies en toont altijd een confidence-niveau.

### Easee
- Offline / connectiviteit
- Wachten op authenticatie
- Laadschema / wachten
- Load balancing / stroomlimiet
- Laderfout / foutstatus
- Geen laadstroom — laadpuntgericht / oorzaak open

Bron: Easee Observations / Enumerations, met o.a. Op Mode (109), ReasonForNoCurrent (96), ConnectedToCloud (250).

### SolarEdge
- Isolatiefout (o.a. 18x86 / 8x58)
- Communicatiestoring
- Net-/gridgerelateerde fout
- Omvormerfout met exacte code
- Geen productie
- Prestatie-/monitoringafwijking

### GoodWe
- Utility Loss
- VAC Failure
- FAC Failure
- Isolation Failure
- Ground leakage / aardlekfout
- PV Over Voltage
- Over Temperature
- Battery Communication Failure
- SEMS/SolarGo communicatiestoring
- Overige GoodWe alarm/fout

De classificatie is een service-route, geen definitieve technische diagnose. Veiligheidsrelevante routes worden gemarkeerd voor menselijke review.

## Operationele kennislaag

Elke ondersteunde storingsroute krijgt nu:
- `service_route`: remote-first / remote-triage / site-likely / site-required
- `required_competence`: welk type vaktechnicus nodig is
- `remote_checks`: welke read-only informatie eerst verzameld moet worden
- `site_trigger`: wanneer een locatiebezoek gerechtvaardigd is
- `prep_categories`: welke informatie/middelen-categorieën voorbereid moeten worden
- `escalation_path`: wanneer OEM-support of specialistische escalatie passend is
- `route_source_title` en `route_source_url`: officiële bron

De tool beschrijft geen elektrische uitvoeringsstappen. Meet-/PBM-categorieën worden alleen op hoog niveau aan bevoegde technici gekoppeld.

## First-Time-Fix Intelligence

Per storingsroute bewaart V10 nu drie extra lijsten:
- kritische informatie vóór vertrek;
- veelvoorkomende vermijdbare informatiegaten;
- veilige onderdelen-/middelenstrategie op categorieniveau.

Na afloop kan de pilotgebruiker registreren:
- first-time-fix;
- remote opgelost;
- tweede bezoek nodig;
- ontbrekende informatie;
- ontbrekend materiaal/onderdeel;
- verkeerde expertise;
- of een betere preflight de tweede rit waarschijnlijk had kunnen voorkomen.

Het KPI-scherm rekent daarna first-time-fix-, second-visit- en preventable-second-visit-percentages uit op echte pilotcases.

## Economic Impact

Het dashboard houdt bewust drie verschillende categorieën uit elkaar:

- **Gemeten plannerwaarde**: baseline planner-/intaketijd minus de handmatig geregistreerde werkelijke planner-/voorbereidingstijd per outcome-case.
- **Geschatte remote ritwaarde**: remote opgeloste cases maal configureerbare monteur-, bezoekduur- en kilometerkosten.
- **Vermijdbare verspilling**: tweede bezoeken die achteraf als waarschijnlijk voorkombaar zijn geregistreerd. Dit is géén gerealiseerde besparing.

Een aparte projectie schaalt de pilotgemiddelden naar een instelbaar aantal cases per maand en vergelijkt dit met een instelbare softwareprijs. Alle aannames zijn zichtbaar en wijzigbaar.

## Directierapport

V10 genereert nu automatisch een managementrapport met:
- minimumdatadrempel van 10 geregistreerde outcomes;
- first-time-fix, tweede bezoek, preventable second visit en remote-resolved KPI's;
- gemeten plannerbesparing versus geschatte ritwaarde;
- maandprojectie versus softwarekosten;
- grootste oorzaken van informatie- en materiaaltekorten;
- belangrijkste storings-/service-routes;
- actiepunten uit de geregistreerde pilotdata;
- print/PDF-weergave.

Onder 10 outcomes wordt expliciet geen financieel positief/negatief pilotsignaal gegeven.

## Pilotbeheer

Een launch partner kan nu als formele pilot worden vastgelegd:
- start- en einddatum;
- nulmeting: planner-/voorbereidingstijd, first-time-fix, tweede bezoek, remote opgelost;
- doelen op dezelfde KPI's;
- dagelijkse/wekelijkse snapshots;
- voortgang voor versus na;
- automatisch eindrapport;
- geen eindoordeel vóór minimaal 10 outcomes.

De pilotlaag is bedoeld om producteffect en businesscase gecontroleerd te valideren bij de eerste klant.

## Launch Partner Onboarding

De vijfstappenwizard configureert:
1. bedrijf en servicetypen;
2. merken per servicetype;
3. optionele planner- en monteuraccounts;
4. businesscase-aannames;
5. nulmeting, doelen en pilotperiode.

Na afronding:
- klantintake toont alleen ingeschakelde servicetypen en merken;
- bedrijfsnaam wordt doorgevoerd;
- teamaccounts zijn direct bruikbaar;
- economische aannames zijn gevuld;
- een launch-partnerpilot is actief;
- de unieke klant-intakelink wordt getoond.

Onboarding opent automatisch voor admin/planner zolang de setup niet is afgerond.


# Pilot v1.0 productisation

Adds customer branding, secure account administration, self-service password change, operational JSON export without password hashes, explicit-confirmation pilot reset, and release/version metadata.
