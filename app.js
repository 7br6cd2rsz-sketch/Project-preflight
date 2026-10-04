let token=null,me=null,cases=[],users=[],current=null,settings=null,attachmentFiles=[],systemTimer=null,ownerOrganizations=[];
const $=id=>document.getElementById(id);
function toast(message,type=""){
 const stack=$("toastStack");
 if(!stack){console.log(message);return}
 const el=document.createElement("div");el.className=`ws-toast ${type}`.trim();el.textContent=message;stack.appendChild(el);
 setTimeout(()=>{el.style.opacity="0";el.style.transform="translateY(6px)"},2800);
 setTimeout(()=>el.remove(),3150);
}
function syncGlobalSearch(value){
 if($("caseSearch"))$("caseSearch").value=value||"";
 renderCasesView();
 if(String(value||"").trim().length>=2 && $("casesView")?.classList.contains("hidden"))show("cases");
}
function focusCaseSearch(){setTimeout(()=>$("caseSearch")?.focus(),80)}
function clearCaseFilters(){
 if($("caseSearch"))$("caseSearch").value="";
 if($("globalSearch"))$("globalSearch").value="";
 if($("caseStatusFilter"))$("caseStatusFilter").value="all";
 if($("caseSort"))$("caseSort").value="priority";
 renderCasesView();
}
function caseHaystack(c){return [c.customer,c.case_no,c.city,c.type,c.asset,c.manufacturer,c.model,c.problem,c.status].filter(Boolean).join(" ").toLowerCase()}
function caseTime(c){let v=c.updated_at||c.created_at||0;let t=Date.parse(v);return Number.isFinite(t)?t:Number(c.id||0)}
function priorityRank(c){if(c.status==="Info ontbreekt")return 0;if(c.status==="Review")return 1;if(c.status==="Ingepland")return 3;if(c.status==="Afgerond")return 5;return Number(c.score||0)<80?2:4}
function filteredCases(){
 let q=String($("caseSearch")?.value||"").trim().toLowerCase(),st=$("caseStatusFilter")?.value||"all",sort=$("caseSort")?.value||"priority";
 let rows=cases.filter(c=>(!q||caseHaystack(c).includes(q))&&(st==="all"||(st==="attention"?(c.status!=="Afgerond"&&(c.status==="Info ontbreekt"||c.status==="Review"||Number(c.score||0)<80)):c.status===st)));
 rows=[...rows];
 if(sort==="recent")rows.sort((a,b)=>caseTime(b)-caseTime(a));
 else if(sort==="readinessAsc")rows.sort((a,b)=>Number(a.score||0)-Number(b.score||0)||caseTime(b)-caseTime(a));
 else if(sort==="readinessDesc")rows.sort((a,b)=>Number(b.score||0)-Number(a.score||0)||caseTime(b)-caseTime(a));
 else rows.sort((a,b)=>priorityRank(a)-priorityRank(b)||Number(a.score||0)-Number(b.score||0)||caseTime(b)-caseTime(a));
 return rows;
}
function recentCases(){return [...cases].sort((a,b)=>caseTime(b)-caseTime(a)).slice(0,7)}
function priorityCases(){
 return [...cases].filter(c=>c.status!=="Afgerond"&&(c.status==="Info ontbreekt"||c.status==="Review"||Number(c.score||0)<80))
  .sort((a,b)=>priorityRank(a)-priorityRank(b)||Number(a.score||0)-Number(b.score||0)||caseTime(b)-caseTime(a)).slice(0,5)
}

function updateWorkspaceChrome(){
 if(!me)return;
 let org=me.organization_name||"Werkstuur";
 let plan=(me.organization_plan||"").toUpperCase()||"OMGEVING";
 if($("workspaceName"))$("workspaceName").textContent=org;
 if($("workspacePlan"))$("workspacePlan").textContent=plan;
 if($("dashOrgName"))$("dashOrgName").textContent=org;
 if($("userDisplay"))$("userDisplay").textContent=me.display_name||"Gebruiker";
 if($("userInitials")){
   let parts=String(me.display_name||"WS").trim().split(/\s+/).filter(Boolean);
   $("userInitials").textContent=(parts[0]?.[0]||"W")+(parts.length>1?(parts[parts.length-1]?.[0]||""):"");
 }
 if($("pageLabel")){
   let active=document.querySelector('nav button.active');
   $("pageLabel").textContent=active?(active.querySelector("span:last-child")?.textContent.trim()||active.textContent.trim()):"Overzicht";
 }
 if($("dashboardGreeting")){
   let h=new Date().getHours(),g=h<12?"Goedemorgen":h<18?"Goedemiddag":"Goedenavond";
   let first=String(me.display_name||"").trim().split(/\s+/)[0]||"";
   $("dashboardGreeting").textContent=`${g}${first?", "+first:""}`;
 }
 if($("ownerQuick"))$("ownerQuick").style.display=me.is_platform_owner?"":"none";
 if($("switchOrgQuick"))$("switchOrgQuick").style.display=me.is_platform_owner?"":"none";
 if($("systemQuick"))$("systemQuick").style.display=me.role==="admin"?"":"none";
}
async function logoutNow(){
 try{await api("/api/logout",{method:"POST",body:JSON.stringify({})})}catch(e){}
 location.reload();
}
async function api(path,opts={}){let h={"Content-Type":"application/json",...(opts.headers||{})};let r=await fetch(path,{...opts,headers:h,credentials:"same-origin"});let t=await r.text(),d;try{d=t?JSON.parse(t):null}catch{d=t}if(!r.ok){let e=new Error(d?.error||t||r.status);e.status=r.status;e.data=d;throw e}return d}
function show(v){
 if(systemTimer){clearInterval(systemTimer);systemTimer=null}
 document.querySelectorAll("main>section").forEach(x=>x.classList.add("hidden"));
 let target=$(v+"View");if(!target)return;target.classList.remove("hidden");
 const parentView=({case:"cases",metrics:"pilotHub",pilot:"pilotHub",report:"pilotHub",product:"beheer",system:"beheer",audit:"beheer",onboarding:"beheer"})[v]||v;
 document.querySelectorAll("nav button").forEach(b=>b.classList.toggle("active",b.dataset.view===parentView));
 if($("pageLabel")){
   const detailLabels={case:"Case",metrics:"KPI's & businesscase",pilot:"Pilot beheren",report:"Directierapport",product:"Productinstellingen",system:"Systeemstatus",audit:"Auditlog",onboarding:"Onboarding"};
   let active=document.querySelector(`nav button[data-view="${parentView}"]`);
   $("pageLabel").textContent=detailLabels[v]||(active?(active.querySelector("span:last-child")?.textContent.trim()||active.textContent.trim()):v);
 }
 window.scrollTo(0,0);
 if(v==="pilotHub")loadPilotHub();
 if(v==="metrics")loadMetrics();
 if(v==="pilot")loadPilot();
 if(v==="report")loadReport();
 if(v==="product")loadProductManagement();
 if(v==="audit")loadAudit();
 if(v==="owner")loadOwnerConsole();
 if(v==="beheer")configureManageHub();
 if(v==="system"){
   loadSystemStatus();
   systemTimer=setInterval(()=>{if(!$("systemView").classList.contains("hidden"))loadSystemStatus(true)},60000);
 }
}
document.querySelectorAll("nav button").forEach(b=>b.onclick=()=>show(b.dataset.view));
document.addEventListener("keydown",e=>{
 if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==="k"){e.preventDefault();show("cases");focusCaseSearch();return}
 if(e.key==="/"&&!/input|textarea|select/i.test(document.activeElement?.tagName||"")){e.preventDefault();show("cases");focusCaseSearch()}
 if(e.key==="Escape"){$("newModal")?.classList.add("hidden")}
});
function pill(s){let c=s==="Ingepland"||s==="Afgerond"?"good":s==="Info ontbreekt"?"warn":s==="Review"?"review":"";return `<span class="pill ${c}">${escapeReport(s)}</span>`}
async function loginNow(){try{let d=await api("/api/login",{method:"POST",body:JSON.stringify({email:email.value,password:password.value})});me=d.user;await boot()}catch(e){loginMsg.textContent=e.message}}
async function boot(){try{
 me=await api("/api/me");login.classList.add("hidden");app.classList.remove("hidden");
 who.textContent=`${me.display_name} · ${me.is_platform_owner?"eigenaar · ":""}${me.role} · ${me.organization_name||""}`;
 const tech=me.role==="technician",admin=me.role==="admin",owner=!!me.is_platform_owner;
 const vis=(id,on)=>{let el=$(id);if(el)el.classList.toggle("hidden",!on)};
 vis("dashboardNav",!tech);vis("casesNav",!tech);vis("workordersNav",tech);vis("pilotHubNav",!tech);vis("settingsNav",!tech);vis("teamNav",!tech);vis("ownerNav",owner);vis("beheerNav",!tech&&(admin||owner));
 let platform=$("platformNavGroup");if(platform)platform.classList.toggle("hidden",tech||!(admin||owner));
 vis("newBtn",!tech);vis("newBtn2",!tech);
 updateWorkspaceChrome();
 await Promise.all([loadCases(),tech?Promise.resolve():loadUsers(),tech?Promise.resolve():loadSettings()]);
 if(settings)applyBranding(settings);render();configureManageHub();
 if(tech){show("workorders");return}
 let ob=await api("/api/onboarding-status");
 if(!ob.complete&&(admin||owner)){initOnboarding(ob);show("onboarding");return}
 show("dashboard");
 }catch(e){console.error(e);token=null}}
async function loadCases(){cases=await api("/api/cases")}
async function loadUsers(){users=await api("/api/users")}
async function loadSettings(){settings=await api("/api/settings")}
function fmtDateTime(v){
 if(!v)return "—";
 try{return new Date(v).toLocaleString("nl-NL")}catch{return String(v)}
}
function fmtUptime(sec){
 sec=Math.max(0,Number(sec)||0);
 let d=Math.floor(sec/86400),h=Math.floor((sec%86400)/3600),m=Math.floor((sec%3600)/60);
 if(d)return `${d}d ${h}u ${m}m`;
 if(h)return `${h}u ${m}m`;
 return `${m}m`;
}
function setStatusDot(el,status){
 el.classList.remove("ok","bad","warn");
 el.classList.add(status==="online"||status==="healthy"?"ok":status==="unknown"?"warn":"bad");
}
async function loadSystemStatus(silent=false){
 if(me?.role!=="admin")return;
 try{
  let s=await api("/api/system-status");
  sysOverall.textContent=s.overall==="healthy"?"Alles operationeel":"Aandacht nodig";
  sysOverall.className=s.overall==="healthy"?"good":"warn";
  setStatusDot(sysOverallDot,s.overall);
  sysChecked.textContent=`Gecontroleerd ${fmtDateTime(s.checked_at)}`;

  sysDb.textContent=s.database?.status==="online"?"Online":"Niet beschikbaar";
  sysDb.className=s.database?.status==="online"?"good":"warn";
  sysDbLatency.textContent=s.database?.latency_ms!=null?`${s.database.latency_ms} ms`:"—";

  sysStorage.textContent=s.storage?.status==="online"?"Online":s.storage?.status==="unknown"?"Onbekend":"Niet beschikbaar";
  sysStorage.className=s.storage?.status==="online"?"good":"warn";
  sysStorageLatency.textContent=s.storage?.latency_ms!=null?`${s.storage.latency_ms} ms · ${s.storage.bucket||""}`:(s.storage?.bucket||"");

  sysVersion.textContent=s.app?.version||"—";
  sysCommit.textContent=s.hosting?.commit?`commit ${s.hosting.commit}`:"";
  sysUptime.textContent=fmtUptime(s.app?.uptime_seconds);
  sysCases.textContent=String(s.counts?.cases??"—");
  sysUsers.textContent=String(s.counts?.active_users??"—");
  sysSessions.textContent=String(s.counts?.active_sessions??"—");
  sysAttachments.textContent=String(s.counts?.attachments??"—");
  sysPilots.textContent=String(s.counts?.pilots??"—");
  sysLastGood.textContent=fmtDateTime(s.monitoring?.last_successful_check);
  sysStarted.textContent=fmtDateTime(s.app?.started_at);
  sysHosting.textContent=`${s.hosting?.provider||"Render"} · ${s.organization?.name||me.organization_name||""}`;

  let e=s.monitoring?.last_error;
  if(e){
    sysLastError.textContent=`${fmtDateTime(e.at)} · ${e.scope}: ${e.message}`;
    sysLastError.className="warn";
  }else{
    sysLastError.textContent="Geen geregistreerde serverfout sinds de huidige runtime is gestart.";
    sysLastError.className="good";
  }
 }catch(e){
  sysOverall.textContent="Statuscheck mislukt";
  sysOverall.className="warn";
  setStatusDot(sysOverallDot,"bad");
  sysChecked.textContent=e.message||"Onbekende fout";
  if(!silent)console.error(e);
 }
}

function escAttr(v){return escapeReport(v??"")}
async function loadOwnerConsole(){
 if(!me?.is_platform_owner)return;
 ownerOrganizations=await api("/api/owner/organizations");
 ownOrganizations.textContent=ownerOrganizations.length;
 ownActive.textContent=ownerOrganizations.filter(o=>["active","pilot"].includes(o.status)).length;
 ownOnboarding.textContent=ownerOrganizations.filter(o=>o.status==="onboarding").length;
 ownCases.textContent=ownerOrganizations.reduce((n,o)=>n+Number(o.cases||0),0);
 ownerCurrentOrg.textContent=`${me.organization_name||"—"} · ${me.organization_status||""}`;
 ownerOrgList.innerHTML=ownerOrganizations.map(o=>`<article class="cc-orgcard">
   <div class="cc-orgname"><b>${escapeReport(o.name)}</b><small>${escapeReport(o.slug)}</small></div>
   <div class="cc-orgstatus"><i class="${escapeReport(o.status)}"></i><span>${escapeReport(o.status)} · ${escapeReport(o.plan)}</span></div>
   <div class="cc-orgmeta"><b>${Number(o.cases||0)} cases</b><small>${Number(o.active_users||0)} actieve gebruikers · ${o.active_pilot?"actieve pilot":"geen actieve pilot"} · ${o.onboarding_complete?"onboarding gereed":"onboarding open"}</small></div>
   <div class="cc-orgactions"><button class="btn" onclick="switchOrganization(${Number(o.id)})">Open</button>${o.plan!=="internal"?`<button class="btn" onclick="toggleOrganization(${Number(o.id)},'${o.status==="suspended"?"active":"suspended"}')">${o.status==="suspended"?"Activeer":"Pauzeer"}</button>`:""}</div>
 </article>`).join("") || `<div class="sub">Nog geen organisaties.</div>`;
}
async function switchOrganization(id){
 await api("/api/owner/context",{method:"POST",body:JSON.stringify({organization_id:Number(id)})});
 me=await api("/api/me");
 await Promise.all([loadCases(),loadUsers(),loadSettings()]);
 if(settings)applyBranding(settings);
 render();
 who.textContent=`${me.display_name} · eigenaar · ${me.role} · ${me.organization_name||""}`;
 updateWorkspaceChrome();
 show("owner");
}
async function toggleOrganization(id,status){
 await api(`/api/owner/organizations/${Number(id)}`,{method:"PATCH",body:JSON.stringify({status})});
 await loadOwnerConsole();
}
async function createOrganization(){
 let payload={
  name:ownNewName.value.trim(),slug:ownNewSlug.value.trim(),status:ownNewStatus.value,plan:ownNewPlan.value,
  admin_name:ownAdminName.value.trim(),admin_email:ownAdminEmail.value.trim(),admin_password:ownAdminPassword.value
 };
 try{
  let org=await api("/api/owner/organizations",{method:"POST",body:JSON.stringify(payload)});
  ownNewName.value=ownNewSlug.value=ownAdminName.value=ownAdminEmail.value=ownAdminPassword.value="";
  await loadOwnerConsole();
  toast(`Organisatie ${org.name} is aangemaakt.`,"good");
 }catch(e){alert(e.message)}
}

function table(rows=cases){
 if(!rows.length)return `<div class="ws-empty"><b>Geen cases gevonden</b>Pas je zoekopdracht of filters aan.</div>`;
 return `<div class="row head"><div>Klant / case</div><div>Type / asset</div><div>Status</div><div>Gereedheid</div><div></div></div>`+rows.map(c=>{let score=Math.max(0,Math.min(100,Number(c.score)||0));return `<div class="row case" onclick="openCase(${Number(c.id)})"><div><b>${escapeReport(c.customer||"Nieuwe klant")}</b><br><span class="sub">${escapeReport(c.case_no)}${c.city?` · ${escapeReport(c.city)}`:""}</span></div><div class="ws-type"><b>${escapeReport(c.type||"—")}</b><br><span class="sub">${escapeReport(c.asset||[c.manufacturer,c.model].filter(Boolean).join(" ")||"Nog te identificeren")}</span></div><div>${pill(c.status)}</div><div class="ws-score"><b>${score}%</b><span class="ws-scorebar"><i style="width:${score}%"></i></span></div><div class="ws-action">Open →</div></div>`}).join("")
}
function renderCasesView(){
 if(!$("casesTable"))return;
 let rows=filteredCases();
 $("casesTable").innerHTML=table(rows);
 if($("caseResultsMeta"))$("caseResultsMeta").textContent=rows.length===cases.length?`${rows.length} cases`:`${rows.length} van ${cases.length} cases`;
}
function renderCaseTables(){renderCasesView()}
function renderPriorityList(){
 let el=$("attentionQueue");if(!el)return;let rows=priorityCases();
 el.innerHTML=rows.length?rows.map(c=>{let klass=c.status==="Review"?"review":"";return `<div class="cc-priorityitem ${klass}" onclick="openCase(${Number(c.id)})"><i></i><div><b>${escapeReport(c.customer||c.case_no)}</b><small>${escapeReport(c.case_no)} · ${escapeReport(c.status)}${(c.missing||[]).length?` · ${(c.missing||[]).length} ontbrekend`:""}</small></div><span class="cc-priorityscore">${Number(c.score)||0}%</span></div>`}).join(""):`<div class="cc-priorityempty">Geen urgente cases. De operationele wachtrij is op orde.</div>`;
}
function render(){
 updateWorkspaceChrome();mCases.textContent=cases.length;mReview.textContent=cases.filter(c=>c.status==="Review"||c.status==="Info ontbreekt").length;mScheduled.textContent=cases.filter(c=>c.status==="Ingepland").length;mReady.textContent=(cases.length?Math.round(cases.reduce((a,c)=>a+(Number(c.score)||0),0)/cases.length):0)+"%";
 dashTable.innerHTML=table(recentCases());renderCaseTables();renderPriorityList();renderWorkorders();
 if(me.role!=="technician"){renderTeam();if(settings){intakeLink.textContent=`${location.origin}/intake.html?token=${encodeURIComponent(settings.intake_token)}`}}
}
function renderTeam(){teamList.innerHTML=`<div class="row head"><div>Naam</div><div>E-mail</div><div>Rol</div><div></div><div></div></div>`+users.map(u=>`<div class="row"><div>${escapeReport(u.display_name)}</div><div>${escapeReport(u.email)}</div><div>${escapeReport(u.role)}</div><div></div><div></div></div>`).join("")}
function renderWorkorders(){workorders.innerHTML=cases.length?cases.map(c=>`<div class="card section" onclick="openCase(${Number(c.id)})" style="cursor:pointer"><div class="eyebrow">${escapeReport(c.case_no)}</div><h3>${escapeReport(c.customer)} · ${escapeReport(c.type)}</h3><div class="kv"><span>Merk/model</span><span>${escapeReport([c.manufacturer,c.model].filter(Boolean).join(' ')||c.asset||'Onbekend')}</span></div><div class="kv"><span>Locatie</span><span>${escapeReport(c.city||"")}</span></div><div class="kv"><span>Klacht</span><span>${escapeReport(c.problem||"")}</span></div><div class="kv"><span>Werkadvies</span><span>${escapeReport(c.dispatch||"")}</span></div>${(c.prep||[]).map(x=>`<div class="check">✓ ${escapeReport(x)}</div>`).join("")}</div>`).join(""):`<div class="sub">Geen toegewezen werkorders.</div>`}
function openNew(){newModal.classList.remove("hidden")}
function plannerBrands(){let opts=nType.value==="Laadpaal"?["Easee","Alfen","Wallbox","Zaptec","Anders/onbekend"]:nType.value==="Zonnepanelen"?["SolarEdge","GoodWe","Growatt","SMA","Enphase","Anders/onbekend"]:nType.value==="Thuisbatterij"?["SolarEdge","GoodWe","BYD","Huawei","Tesla","Anders/onbekend"]:["Anders/onbekend"];nManufacturer.innerHTML=opts.map(x=>`<option>${x}</option>`).join("")}
plannerBrands();
async function createCase(){let c=await api("/api/cases",{method:"POST",body:JSON.stringify({customer:nCustomer.value,city:nCity.value,type:nType.value,asset:"Nog te identificeren",problem:nProblem.value,extra:{manufacturer:nManufacturer.value,model:nModel.value,serial:nSerial.value}})});newModal.classList.add("hidden");await loadCases();render();toast("Case aangemaakt.","good");openCase(c.id)}
async function openCase(id){
 current=cases.find(c=>c.id===id);if(!current)return;
 const sourceLink=current.knowledge_url?`<a href="${safeHref(current.knowledge_url)}" target="_blank" rel="noopener noreferrer" style="color:#1684b8">${escapeReport(current.knowledge_title||"OEM documentatie")}</a>`:escapeReport(current.knowledge_title||"Generiek");
 const routeLink=current.route_source_url?`<a href="${safeHref(current.route_source_url)}" target="_blank" rel="noopener noreferrer" style="color:#1684b8">${escapeReport(current.route_source_title||"OEM documentatie")}</a>`:escapeReport(current.route_source_title||"—");
 if($("caseHero")){let score=Math.max(0,Math.min(100,Number(current.score)||0));$("caseHero").innerHTML=`<div><div class="ws-caseid">${escapeReport(current.case_no)}</div><h2>${escapeReport(current.customer||"Nieuwe klant")}</h2><div class="ws-casefacts"><span>${escapeReport(current.type||"—")}</span><span>${escapeReport(current.city||"Geen plaats")}</span><span>${pill(current.status)}</span><span>${escapeReport(current.manufacturer||"Merk onbekend")}${current.model?` · ${escapeReport(current.model)}`:""}</span></div></div><div class="ws-scoreorb" style="--score:${score}%"><b>${score}%</b><small>GEREED</small></div>`}
 caseMain.innerHTML=`<div class="eyebrow">${escapeReport(current.case_no)}</div><h3>${escapeReport(current.customer)} · ${escapeReport(current.type)}</h3><div class="kv"><span>Plaats</span><span>${escapeReport(current.city||"")}</span></div><div class="kv"><span>Asset</span><span>${escapeReport(current.asset||"")}</span></div><div class="kv"><span>Merk</span><span>${escapeReport(current.manufacturer||"Onbekend")}</span></div><div class="kv"><span>Model</span><span>${escapeReport(current.model||"Onbekend")}</span></div><div class="kv"><span>Serienummer</span><span>${escapeReport(current.serial_no||"Onbekend")}</span></div><div class="kv"><span>Melding</span><span>${escapeReport(current.problem||"")}</span></div><div class="field"><label>Status</label><select id="caseStatus"><option ${current.status==="Info ontbreekt"?"selected":""}>Info ontbreekt</option><option ${current.status==="Review"?"selected":""}>Review</option><option ${current.status==="Ingepland"?"selected":""}>Ingepland</option><option ${current.status==="Afgerond"?"selected":""}>Afgerond</option></select></div>`;
 prep.innerHTML=`<div class="eyebrow" style="margin-bottom:7px">Kritisch vóór vertrek</div>${(current.ftf_critical||[]).map(x=>`<div class="check">★ ${escapeReport(x)}</div>`).join("")}<div class="eyebrow" style="margin:12px 0 7px">Veelvoorkomende vermijdbare gaten</div>${(current.ftf_gaps||[]).map(x=>`<div class="check warn">! ${escapeReport(x)}</div>`).join("")}<div class="eyebrow" style="margin:12px 0 7px">Onderdelen-/middelenstrategie</div>${(current.ftf_parts||[]).map(x=>`<div class="check">◇ ${escapeReport(x)}</div>`).join("")}<div class="eyebrow" style="margin:12px 0 7px">Monteurbriefing</div>${(current.prep||[]).map(x=>`<div class="check">• ${escapeReport(x)}</div>`).join("")}`;
 caseSide.innerHTML=`<div class="eyebrow">Voorbereiding</div><h3>Gereedheid</h3><div style="font-size:42px;font-weight:900">${Number(current.score)||0}%</div><div class="kv"><span>Werkadvies</span><span>${escapeReport(current.dispatch||"Nog geen werkadvies")}</span></div><div class="kv"><span>Storingsroute</span><b>${escapeReport(current.fault_category||"Nog niet geclassificeerd")}</b></div><div class="kv"><span>Service-route</span><b>${escapeReport(current.service_route||"Nog te bepalen")}</b></div><div class="kv"><span>Benodigde expertise</span><span>${escapeReport(current.required_competence||"Technische review")}</span></div><div class="kv"><span>Wanneer locatie nodig is</span><span>${escapeReport(current.site_trigger||"—")}</span></div><div class="kv"><span>Escalatie</span><span>${escapeReport(current.escalation_path||"—")}</span></div><details class="cc-techdetails section"><summary>Technische details</summary><div class="kv"><span>Dossierversie</span><b>${Number(current.version)||1}</b></div><div class="kv"><span>Bron melding</span><span>${escapeReport(current.source)}</span></div><div class="kv"><span>Technische bron</span><span>${sourceLink}</span></div><div class="kv"><span>Integratiedoelen</span><span>${escapeReport((current.api_targets||[]).join(", ")||"—")}</span></div><div class="kv"><span>Zekerheid classificatie</span><span>${escapeReport(current.fault_confidence||"laag")}</span></div><div class="kv"><span>Triageniveau</span><span>${escapeReport(current.triage_level||"standaard")}</span></div><div class="kv"><span>Onderbouwing</span><span>${escapeReport((current.fault_evidence||[]).join(" · ")||"—")}</span></div><div class="kv"><span>Routebron</span><span>${routeLink}</span></div></details>`;
 assignedTo.innerHTML=`<option value="">Niet toegewezen</option>`+users.filter(u=>u.role==="technician").map(u=>`<option value="${Number(u.id)}" ${current.assigned_to===u.id?"selected":""}>${escapeReport(u.display_name)}</option>`).join("");
 assignBtn.style.display=me.role==="technician"?"none":"";assignedTo.disabled=me.role==="technician";await Promise.all([loadNotes(),loadAttachments()]);renderOutcome();show("case")
}
async function saveCase(){try{let d=await api(`/api/cases/${current.id}`,{method:"PATCH",body:JSON.stringify({version:current.version,status:caseStatus.value,score:current.score,facts:current.facts,missing:current.missing,dispatch:current.dispatch})});current=d;await loadCases();render();await openCase(current.id);toast("Case bijgewerkt.","good")}catch(e){if(e.status===409){alert("Conflict: deze case is ondertussen gewijzigd. De nieuwste versie wordt geladen.");await loadCases();render();openCase(current.id)}else alert(e.message)}}
async function assignCase(){try{let d=await api(`/api/cases/${current.id}`,{method:"PATCH",body:JSON.stringify({version:current.version,assigned_to:assignedTo.value?Number(assignedTo.value):null})});current=d;await loadCases();render();await openCase(current.id);toast("Toewijzing bijgewerkt.","good")}catch(e){alert(e.message)}}
async function loadNotes(){let n=await api(`/api/cases/${current.id}/notes`);notes.innerHTML=n.length?n.map(x=>`<div class="note"><b>${escapeReport(x.display_name)}</b><div>${escapeReport(x.body)}</div><small>${escapeReport(new Date(x.created_at).toLocaleString("nl-NL"))}</small></div>`).join(""):`<div class="sub">Geen notities.</div>`}
async function addNote(){let body=noteText.value.trim();if(!body)return;await api(`/api/cases/${current.id}/notes`,{method:"POST",body:JSON.stringify({body})});noteText.value="";await loadNotes();toast("Notitie toegevoegd.","good")}
async function loadAttachments(){attachmentFiles=await api(`/api/cases/${current.id}/attachments`);attachments.innerHTML=attachmentFiles.length?attachmentFiles.map(x=>`<div class="attachment"><b>${escapeReport(x.filename)}</b><small>${Math.round(Number(x.size_bytes||0)/1024)} KB</small><div><button class="btn" onclick="downloadAttachment(${Number(x.id)})">Open</button></div></div>`).join(""):`<div class="sub">Geen bijlagen.</div>`}
async function uploadFile(){let f=fileInput.files[0];if(!f)return;let b64=await new Promise((res,rej)=>{let r=new FileReader();r.onload=()=>res(String(r.result).split(",")[1]);r.onerror=rej;r.readAsDataURL(f)});await api(`/api/cases/${current.id}/attachments`,{method:"POST",body:JSON.stringify({filename:f.name,content_type:f.type||"application/octet-stream",data_base64:b64})});fileInput.value="";await loadAttachments();toast("Bijlage toegevoegd.","good")}
async function downloadAttachment(id){let meta=attachmentFiles.find(x=>x.id===id),name=meta?.filename||"bestand";let r=await fetch(`/api/attachments/${id}`,{credentials:"same-origin"});if(!r.ok)return alert("Bestand kon niet worden geopend.");let b=await r.blob(),u=URL.createObjectURL(b),a=document.createElement("a");a.href=u;a.download=name;a.rel="noopener";a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)}

function renderOutcome(){
 const recorded=!!current.outcome_recorded_at;
 outcomeCurrent.innerHTML=recorded?`<b>Outcome geregistreerd.</b><br>${current.outcome_resolved_first_visit?"First-time-fix · ":""}${current.outcome_remote_resolved?"Remote opgelost · ":""}${current.outcome_second_visit_required?"Tweede bezoek nodig · ":""}${current.outcome_preventable?"waarschijnlijk voorkombaar":""}`:`Nog geen outcome geregistreerd. Vul dit na afronding van de servicecase in.`;
 oResolved.checked=!!current.outcome_resolved_first_visit;
 oRemote.checked=!!current.outcome_remote_resolved;
 oSecond.checked=!!current.outcome_second_visit_required;
 oMissingInfo.value=current.outcome_missing_info||"";
 oMissingMaterial.value=current.outcome_missing_material||"";
 oWrongSkill.checked=!!current.outcome_wrong_skill;
 oPreventable.checked=!!current.outcome_preventable;
 oPlannerMinutes.value=current.outcome_planner_minutes??"";
 oNotes.value=current.outcome_notes||"";
}
async function saveOutcome(){
 if(oResolved.checked && oSecond.checked && !confirm("Je hebt zowel 'in één bezoek opgelost' als 'tweede bezoek nodig' aangevinkt. Toch opslaan?"))return;
 current=await api(`/api/cases/${current.id}/outcome`,{method:"POST",body:JSON.stringify({
   resolved_first_visit:oResolved.checked,
   remote_resolved:oRemote.checked,
   second_visit_required:oSecond.checked,
   missing_info:oMissingInfo.value,
   missing_material:oMissingMaterial.value,
   wrong_skill:oWrongSkill.checked,
   preventable:oPreventable.checked,
   planner_minutes:oPlannerMinutes.value,
   notes:oNotes.value
 })});
 await loadCases();render();renderOutcome();toast("Outcome opgeslagen.","good");
}

let lastMetrics=null;
function euro(v){return new Intl.NumberFormat("nl-NL",{style:"currency",currency:"EUR",maximumFractionDigits:0}).format(Number(v||0))}
function fillEconomicInputs(a){
 aBaselinePlanner.value=a.baseline_planner_minutes;
 aPlannerRate.value=a.planner_hourly_cost;
 aTechRate.value=a.technician_hourly_cost;
 aVisitMinutes.value=a.avg_site_visit_minutes;
 aKm.value=a.avg_roundtrip_km;
 aKmCost.value=a.cost_per_km;
 aSoftware.value=a.software_monthly_cost;
 aVolume.value=a.monthly_case_volume;
}
function renderEconomics(e){
 if(!e)return;
 ePlanner.textContent=euro(e.measured.planner_time_value_eur);
 eRemote.textContent=euro(e.measured.estimated_remote_visit_value_eur);
 eWaste.textContent=euro(e.measured.estimated_avoidable_waste_eur);
 eNet.textContent=euro(e.projection.projected_net_value_eur);
 ePlannerMinutes.textContent=(Math.round(e.measured.planner_minutes_saved*10)/10)+" min";
 eRemoteCount.textContent=e.measured.remote_resolved_count;
 ePreventableCount.textContent=e.measured.avoidable_second_visits_observed;
 eGross.textContent=euro(e.projection.projected_gross_value_eur);
 eSoftware.textContent=euro(e.projection.software_monthly_cost_eur);
 eBreakEven.textContent=e.projection.break_even===null?"Nog onvoldoende outcome-data":(e.projection.break_even?"Ja":"Nee");
 fillEconomicInputs(e.assumptions);
}
async function loadPilotHub(){
 try{
  let [m,p]=await Promise.all([api("/api/metrics"),api("/api/pilot")]);
  if($("phFTF"))phFTF.textContent=(m.first_time_fix_pct??0)+"%";
  if($("phSecond"))phSecond.textContent=(m.second_visit_pct??0)+"%";
  if($("phRemote"))phRemote.textContent=(m.remote_resolved_pct??0)+"%";
  if($("phNet"))phNet.textContent=euro(m.economics?.projection?.projected_net_value_eur||0);
  let active=p?.active?p.pilot:null;
  if($("phPilotName"))phPilotName.textContent=active?.name||"Nog geen actieve pilot";
  if($("phPilotStatus")){
    if(active){let bits=[active.start_date&&`start ${active.start_date}`,active.end_date&&`einde ${active.end_date}`,p?.days?.elapsed_pct!=null&&`${p.days.elapsed_pct}% voortgang`].filter(Boolean);phPilotStatus.textContent=bits.join(" · ")||"Pilot actief"}
    else phPilotStatus.textContent="Start een pilot om nulmeting, doelen en voortgang vast te leggen.";
  }
 }catch(e){console.error(e);if($("phPilotName"))phPilotName.textContent="Pilotgegevens niet beschikbaar"}
}
function configureManageHub(){
 if(!me)return;
 const admin=me.role==="admin",owner=!!me.is_platform_owner;
 const vis=(id,on)=>{let el=$(id);if(el)el.classList.toggle("hidden",!on)};
 vis("manageOrganizations",owner);vis("manageTeam",me.role!=="technician");vis("manageProduct",admin||owner);vis("manageSystem",admin||owner);vis("manageAudit",admin||owner);vis("manageOnboarding",admin||owner);
}
async function openOnboardingFromManage(){
 try{let ob=await api("/api/onboarding-status");initOnboarding(ob);show("onboarding")}catch(e){alert(e.message)}
}
function setAttentionFilter(){if($("caseStatusFilter"))caseStatusFilter.value="attention";renderCasesView()}
async function loadMetrics(){let m=await api("/api/metrics");lastMetrics=m;kTotal.textContent=m.total;kPublic.textContent=m.customer_intakes;kIntake.textContent=Math.round(m.avg_intake_seconds)+"s";kComplete.textContent=m.complete_pct+"%";kScheduled.textContent=m.scheduled_pct+"%";kFTF.textContent=m.first_time_fix_pct+"%";kSecond.textContent=m.second_visit_pct+"%";kPreventable.textContent=m.preventable_second_visit_pct+"%";kRemote.textContent=m.remote_resolved_pct+"%";kOutcomes.textContent=m.outcomes;renderEconomics(m.economics)}
async function saveEconomicAssumptions(){await api("/api/settings",{method:"PATCH",body:JSON.stringify({
 baseline_planner_minutes:aBaselinePlanner.value,
 planner_hourly_cost:aPlannerRate.value,
 technician_hourly_cost:aTechRate.value,
 avg_site_visit_minutes:aVisitMinutes.value,
 avg_roundtrip_km:aKm.value,
 cost_per_km:aKmCost.value,
 software_monthly_cost:aSoftware.value,
 monthly_case_volume:aVolume.value
})});await loadMetrics();toast("Businesscase-aannames opgeslagen.","good")}

function pct(v){return Number(v||0).toLocaleString("nl-NL",{maximumFractionDigits:1})+"%"}
function nfmt(v){return Number(v||0).toLocaleString("nl-NL")}
function reportList(items,emptyText){
 if(!items||!items.length)return `<div class="sub">${emptyText}</div>`;
 return items.map(x=>`<div class="kv"><span>${escapeReport(x.label)}</span><b>${x.count}</b></div>`).join("");
}
function escapeReport(s){return String(s??"").replace(/[&<>"\']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","\'":"&#39;"}[m]))}
function safeHref(u){try{let x=new URL(String(u||""),location.origin);return (x.protocol==="https:"||x.protocol==="http:")?escapeReport(x.href):"#"}catch{return "#"}}
async function loadReport(){
 let r=await api("/api/report");
 let e=r.economics,op=r.operations,q=r.sample_quality,d=r.decision;
 let decisionClass=d.status==="positief_signaal"?"good":d.status==="negatief_signaal"?"warn":"";
 reportContainer.innerHTML=`
 <div class="card">
   <div class="eyebrow">Pilotmanagement · ${escapeReport(r.company_name)}</div>
   <h2 style="font-size:24px;margin:5px 0">${escapeReport(d.label)}</h2>
   <div class="sub">${escapeReport(d.reason)}</div>
   <div class="section"><span class="pill ${decisionClass}">${q.outcomes} outcomes · minimum ${q.minimum_for_signal}</span></div>
 </div>
 <div class="grid4 section">
   <div class="card metric"><small>First-time-fix</small><b>${pct(op.first_time_fix_pct)}</b></div>
   <div class="card metric"><small>Tweede bezoek</small><b>${pct(op.second_visit_pct)}</b></div>
   <div class="card metric"><small>Voorkombaar van tweede ritten</small><b>${pct(op.preventable_second_visit_pct)}</b></div>
   <div class="card metric"><small>Remote opgelost</small><b>${pct(op.remote_resolved_pct)}</b></div>
 </div>
 <div class="section grid2">
   <div class="card">
     <h3>Gemeten & geschatte waarde</h3>
     <div class="kv"><span>Gemeten planner-minuten bespaard</span><b>${nfmt(e.measured.planner_minutes_saved)} min</b></div>
     <div class="kv"><span>Gemeten plannerwaarde</span><b>${euro(e.measured.planner_time_value_eur)}</b></div>
     <div class="kv"><span>Geschatte remote ritwaarde</span><b>${euro(e.measured.estimated_remote_visit_value_eur)}</b></div>
     <div class="kv"><span>Vermijdbare verspilling gezien</span><b>${euro(e.measured.estimated_avoidable_waste_eur)}</b></div>
   </div>
   <div class="card">
     <h3>Maandprojectie</h3>
     <div class="kv"><span>Cases / maand</span><b>${nfmt(e.projection.monthly_case_volume)}</b></div>
     <div class="kv"><span>Projected bruto waarde</span><b>${euro(e.projection.projected_gross_value_eur)}</b></div>
     <div class="kv"><span>Software referentie</span><b>${euro(e.projection.software_monthly_cost_eur)}</b></div>
     <div class="kv"><span>Projected netto waarde</span><b>${euro(e.projection.projected_net_value_eur)}</b></div>
   </div>
 </div>
 <div class="section grid2">
   <div class="card">
     <h3>Grootste ontbrekende informatie</h3>
     ${reportList(r.top_causes.missing_information,"Nog geen terugkerende informatiegaten geregistreerd.")}
     <div class="section"><h3>Ontbrekend materiaal / onderdeel</h3>${reportList(r.top_causes.missing_material,"Nog geen terugkerend materiaaltekort geregistreerd.")}</div>
   </div>
   <div class="card">
     <h3>Meest voorkomende storingsroutes</h3>
     ${reportList(r.top_causes.fault_categories,"Nog onvoldoende outcome-data voor rangschikking.")}
     <div class="section"><h3>Service-routeverdeling</h3>${reportList(r.top_causes.service_routes,"Nog onvoldoende data.")}</div>
   </div>
 </div>
 <div class="section grid2">
   <div class="card"><h3>Actiepunten uit pilotdata</h3>${(r.recommendations||[]).map(x=>`<div class="check">→ ${escapeReport(x)}</div>`).join("")}</div>
   <div class="card"><h3>Interpretatie & grensvoorwaarden</h3>${(r.interpretation_notes||[]).map(x=>`<div class="check">${escapeReport(x)}</div>`).join("")}<div class="section sub"><b>Beslisregel:</b> ${escapeReport(d.criterion)}</div></div>
 </div>
 <div class="section card"><div class="sub">Rapport gegenereerd: ${new Date(r.generated_at).toLocaleString("nl-NL")}. Financiële projecties gebruiken de op dat moment ingestelde businesscase-aannames.</div></div>`;
}
function printReport(){window.print()}



let obStep=1,obState=null;
const OB_BRAND_DEFAULTS={
 "Laadpaal":["Easee","Alfen","Wallbox","Zaptec","Anders/onbekend"],
 "Zonnepanelen":["SolarEdge","GoodWe","Growatt","SMA","Enphase","Anders/onbekend"],
 "Thuisbatterij":["SolarEdge","GoodWe","BYD","Huawei","Tesla","Anders/onbekend"],
 "Elektro":["Anders/onbekend"]
};
function initOnboarding(state){
 obState=state||{};
 obCompany.value=state?.company_name||"";obSupportEmail.value=state?.branding?.support_email||"";obPrivacyUrl.value=state?.branding?.privacy_url||"";
 document.querySelectorAll(".obService").forEach(x=>x.checked=(state?.enabled_service_types||["Laadpaal","Zonnepanelen"]).includes(x.value));
 let a=state?.assumptions||{};
 obBaselinePlanner.value=a.baseline_planner_minutes??13;
 obPlannerRate.value=a.planner_hourly_cost??40;
 obTechRate.value=a.technician_hourly_cost??55;
 obVisitMinutes.value=a.avg_site_visit_minutes??90;
 obKm.value=a.avg_roundtrip_km??35;
 obKmCost.value=a.cost_per_km??0.35;
 obSoftware.value=a.software_monthly_cost??299;
 obVolume.value=a.monthly_case_volume??150;
 let today=new Date(),end=new Date(Date.now()+42*86400000);
 obStart.value=today.toISOString().slice(0,10);
 obEnd.value=end.toISOString().slice(0,10);
 obResult.classList.add("hidden");obControls.classList.remove("hidden");
 obStep=1;renderObStep();
}
function selectedServices(){return [...document.querySelectorAll(".obService:checked")].map(x=>x.value)}
function renderBrandChoices(){
 let types=selectedServices();
 obBrands.innerHTML=types.map(t=>{
   let current=(obState?.enabled_brands?.[t])||OB_BRAND_DEFAULTS[t]||["Anders/onbekend"];
   let defaults=OB_BRAND_DEFAULTS[t]||["Anders/onbekend"];
   return `<div class="card section"><h3>${escapeReport(t)}</h3>${defaults.map(b=>`<label style="display:block;margin:5px 0"><input type="checkbox" class="obBrand" data-type="${escapeReport(t)}" value="${escapeReport(b)}" ${current.includes(b)?"checked":""}> ${escapeReport(b)}</label>`).join("")}</div>`;
 }).join("");
}
function renderObStep(){
 for(let i=1;i<=5;i++)$("obStep"+i).classList.toggle("hidden",i!==obStep);
 obStepNo.textContent=obStep;
 obBack.style.visibility=obStep===1?"hidden":"visible";
 obNext.textContent=obStep===5?"Onboarding afronden":"Volgende →";
 if(obStep===2)renderBrandChoices();
}
function obPrev(){if(obStep>1){obStep--;renderObStep()}}
async function obNext(){
 if(obStep===1){
   if(!obCompany.value.trim())return alert("Vul een bedrijfsnaam in.");
   if(!selectedServices().length)return alert("Selecteer minimaal één servicetype.");
 }
 if(obStep<5){obStep++;renderObStep();return}
 await finishOnboarding();
}
function collectBrands(){
 let out={};
 document.querySelectorAll(".obBrand:checked").forEach(x=>{
   if(!out[x.dataset.type])out[x.dataset.type]=[];
   out[x.dataset.type].push(x.value);
 });
 return out;
}
function teamPayload(){
 let arr=[];
 let pFilled=obPlannerName.value.trim()||obPlannerEmail.value.trim()||obPlannerPassword.value;
 let tFilled=obTechName.value.trim()||obTechEmail.value.trim()||obTechPassword.value;
 if(pFilled)arr.push({display_name:obPlannerName.value,email:obPlannerEmail.value,role:"planner",password:obPlannerPassword.value});
 if(tFilled)arr.push({display_name:obTechName.value,email:obTechEmail.value,role:"technician",password:obTechPassword.value});
 return arr;
}
async function finishOnboarding(){
 let body={
   company_name:obCompany.value.trim(),
   support_email:obSupportEmail.value.trim(),
   privacy_url:obPrivacyUrl.value.trim(),
   enabled_service_types:selectedServices(),
   enabled_brands:collectBrands(),
   team:teamPayload(),
   assumptions:{
     baseline_planner_minutes:Number(obBaselinePlanner.value),
     planner_hourly_cost:Number(obPlannerRate.value),
     technician_hourly_cost:Number(obTechRate.value),
     avg_site_visit_minutes:Number(obVisitMinutes.value),
     avg_roundtrip_km:Number(obKm.value),
     cost_per_km:Number(obKmCost.value),
     software_monthly_cost:Number(obSoftware.value),
     monthly_case_volume:Number(obVolume.value)
   },
   pilot:{
     create:true,name:obPilotName.value,start_date:obStart.value,end_date:obEnd.value,
     baseline_planner_minutes:Number(obBaselinePlanner.value),
     baseline_first_time_fix_pct:Number(obBaseFTF.value),
     baseline_second_visit_pct:Number(obBaseSecond.value),
     baseline_remote_resolved_pct:Number(obBaseRemote.value),
     target_planner_minutes:Number(obTargetPlanner.value),
     target_first_time_fix_pct:Number(obTargetFTF.value),
     target_second_visit_pct:Number(obTargetSecond.value),
     target_remote_resolved_pct:Number(obTargetRemote.value),
     notes:obPilotNotes.value
   }
 };
 try{
   let r=await api("/api/onboarding",{method:"POST",body:JSON.stringify(body)});
   let intake=`${location.origin}${r.intake_path}`;
   obResult.classList.remove("hidden");
   obResult.innerHTML=`<div class="card"><div class="eyebrow">Setup voltooid</div><h3>${escapeReport(r.onboarding.company_name)}</h3><div class="kv"><span>Nieuwe teamaccounts</span><b>${r.team_members_created}</b></div><div class="kv"><span>Servicetypen</span><b>${r.onboarding.enabled_service_types.join(", ")}</b></div><div class="sub">Klant-intakelink:</div><div class="linkbox section">${intake}</div><div class="section"><button class="btn" onclick="navigator.clipboard?.writeText('${intake}')">Link kopiëren</button> <button class="btn primary" onclick="window.open('${intake}','_blank')">Intake testen</button></div></div>`;
   obControls.classList.add("hidden");
   await Promise.all([loadUsers(),loadSettings()]);
   render();
 }catch(e){alert(e.message)}
}

function valueOrDash(v,suffix=""){return v===null||v===undefined?"—":`${Number(v).toLocaleString("nl-NL",{maximumFractionDigits:1})}${suffix}`}
function goalLine(label,current,target,met,direction){
 let symbol=met?"✓":"·";
 let css=met?"good":"";
 return `<div class="kv"><span>${label}</span><b class="${css}">${symbol} ${valueOrDash(current)} / doel ${valueOrDash(target)}</b></div>`;
}
async function loadPilot(){
 let p=await api("/api/pilot");
 if(!p.active){
   pilotNoActive.classList.remove("hidden");pilotActive.classList.add("hidden");
   let today=new Date(),end=new Date(Date.now()+42*86400000);
   pStart.value=today.toISOString().slice(0,10);pEnd.value=end.toISOString().slice(0,10);
   return;
 }
 pilotNoActive.classList.add("hidden");pilotActive.classList.remove("hidden");
 pProgress.textContent=p.days.elapsed_pct+"%";pRemaining.textContent=p.days.remaining;pOutcomes.textContent=p.current.outcomes;pProjectedNet.textContent=euro(p.economics.projection.projected_net_value_eur);
 let b=p.pilot,c=p.current,d=p.delta;
 pilotCompare.innerHTML=`
   <div class="kv"><span>Planner-/voorbereidingstijd</span><b>${valueOrDash(b.baseline_planner_minutes," min")} → ${valueOrDash(c.avg_planner_minutes," min")} ${d.planner_minutes!==null?`(${d.planner_minutes>0?"+":""}${d.planner_minutes} min)`:""}</b></div>
   <div class="kv"><span>First-time-fix</span><b>${valueOrDash(b.baseline_first_time_fix_pct,"%")} → ${valueOrDash(c.first_time_fix_pct,"%")} ${d.first_time_fix_pct!==null?`(${d.first_time_fix_pct>0?"+":""}${d.first_time_fix_pct} pp)`:""}</b></div>
   <div class="kv"><span>Tweede bezoek</span><b>${valueOrDash(b.baseline_second_visit_pct,"%")} → ${valueOrDash(c.second_visit_pct,"%")} ${d.second_visit_pct!==null?`(${d.second_visit_pct>0?"+":""}${d.second_visit_pct} pp)`:""}</b></div>
   <div class="kv"><span>Remote opgelost</span><b>${valueOrDash(b.baseline_remote_resolved_pct,"%")} → ${valueOrDash(c.remote_resolved_pct,"%")} ${d.remote_resolved_pct!==null?`(${d.remote_resolved_pct>0?"+":""}${d.remote_resolved_pct} pp)`:""}</b></div>`;
 pilotGoals.innerHTML=
   goalLine("Planner-/voorbereidingstijd",c.avg_planner_minutes,p.goals.planner_minutes.target,p.goals.planner_minutes.met,"lower")+
   goalLine("First-time-fix",c.first_time_fix_pct,p.goals.first_time_fix_pct.target,p.goals.first_time_fix_pct.met,"higher")+
   goalLine("Tweede bezoek",c.second_visit_pct,p.goals.second_visit_pct.target,p.goals.second_visit_pct.met,"lower")+
   goalLine("Remote opgelost",c.remote_resolved_pct,p.goals.remote_resolved_pct.target,p.goals.remote_resolved_pct.met,"higher");
 await loadPilotSnapshots();
}
async function startPilot(){
 let body={
   name:pName.value,start_date:pStart.value,end_date:pEnd.value,
   baseline_planner_minutes:Number(pBasePlanner.value),baseline_first_time_fix_pct:Number(pBaseFTF.value),
   baseline_second_visit_pct:Number(pBaseSecond.value),baseline_remote_resolved_pct:Number(pBaseRemote.value),
   target_planner_minutes:Number(pTargetPlanner.value),target_first_time_fix_pct:Number(pTargetFTF.value),
   target_second_visit_pct:Number(pTargetSecond.value),target_remote_resolved_pct:Number(pTargetRemote.value),
   notes:pNotes.value
 };
 await api("/api/pilot",{method:"POST",body:JSON.stringify(body)});await loadPilot();toast("Pilot gestart.","good");
}
async function takePilotSnapshot(){let r=await api("/api/pilot/snapshot",{method:"POST",body:"{}"});await loadPilotSnapshots();toast("Snapshot opgeslagen voor "+r.snapshot_date,"good")}
async function loadPilotSnapshots(){let rows=await api("/api/pilot/snapshots");pilotSnapshots.innerHTML=rows.length?`<div class="row head"><div>Datum</div><div>Outcomes</div><div>Planner min</div><div>FTF</div><div>Tweede bezoek</div></div>`+rows.map(r=>`<div class="row"><div>${r.snapshot_date}</div><div>${r.outcomes}</div><div>${valueOrDash(r.avg_planner_minutes)}</div><div>${valueOrDash(r.first_time_fix_pct,"%")}</div><div>${valueOrDash(r.second_visit_pct,"%")}</div></div>`).join(""):`<div class="sub">Nog geen snapshots.</div>`}
async function closePilot(){if(!confirm("Pilot afsluiten en eindrapport vastleggen?"))return;let r=await api("/api/pilot/close",{method:"POST",body:"{}"});showPilotFinal(r)}
function showPilotFinal(r){
 let goals=(r.goals||[]).map(g=>`<div class="kv"><span>${g.label}</span><b>${g.met?"✓":"·"} ${valueOrDash(g.current)} / doel ${valueOrDash(g.target)}</b></div>`).join("");
 reportContainer.innerHTML=`<div class="card"><div class="eyebrow">Pilot eindrapport</div><h2 style="font-size:24px">${escapeReport(r.pilot.name)}</h2><div class="sub">${escapeReport(r.conclusion.text)}</div><div class="section"><span class="pill ${r.conclusion.status==="positief"?"good":"warn"}">${escapeReport(r.conclusion.status)}</span></div></div><div class="grid2 section"><div class="card"><h3>Doelen</h3>${goals}</div><div class="card"><h3>Economische projectie</h3><div class="kv"><span>Projected bruto</span><b>${euro(r.economics.projection.projected_gross_value_eur)}</b></div><div class="kv"><span>Projected netto</span><b>${euro(r.economics.projection.projected_net_value_eur)}</b></div></div></div>`;
 show("report");
}

function applyBranding(s){if(!s)return;document.documentElement.style.setProperty('--accent',s.brand_accent||'#62d0ff');document.title=(s.brand_name||'Werkstuur')+' · Pilot';let brand=document.querySelector('.brand');if(brand&&s.brand_name)brand.childNodes[0].nodeValue=s.brand_name}
async function loadProductManagement(){let v=await api('/api/version');versionBadge.textContent=`${v.name} ${v.version}`;let s=await api('/api/settings');settings=s;applyBranding(s);pbBrandName.value=s.brand_name||'Werkstuur';pbAccent.value=s.brand_accent||'#62d0ff';pbSupportEmail.value=s.support_email||'';pbPrivacyUrl.value=s.privacy_url||'';pbPortalTitle.value=s.customer_portal_title||'Service-intake';accountAdminCard.style.display=me.role==='admin'?'':'none';if(me.role==='admin')await loadAccounts()}
async function saveBranding(){let s=await api('/api/settings',{method:'PATCH',body:JSON.stringify({brand_name:pbBrandName.value.trim()||'Werkstuur',brand_accent:pbAccent.value.trim(),support_email:pbSupportEmail.value.trim(),privacy_url:pbPrivacyUrl.value.trim(),customer_portal_title:pbPortalTitle.value.trim()||'Service-intake'})});settings={...(settings||{}),...s};applyBranding(settings);toast('Branding opgeslagen.','good')}
async function changeOwnPassword(){if(!pwCurrent.value||!pwNew.value)return alert('Vul huidig en nieuw wachtwoord in.');await api('/api/change-password',{method:'POST',body:JSON.stringify({current_password:pwCurrent.value,new_password:pwNew.value})});pwCurrent.value='';pwNew.value='';alert('Wachtwoord gewijzigd.')}
async function loadAccounts(){let rows=await api('/api/accounts');accountList.innerHTML=`<div class="row head"><div>Naam</div><div>E-mail</div><div>Rol</div><div>Status</div><div>Actie</div></div>`+rows.map(u=>`<div class="row"><div>${escapeReport(u.display_name)}</div><div>${escapeReport(u.email)}</div><div>${u.role}</div><div>${u.active?'Actief':'Uit'}</div><div>${u.id===me.id?'Eigen account':`<button class="btn" onclick="toggleAccount(${u.id},${u.active?0:1})">${u.active?'Deactiveer':'Activeer'}</button> <button class="btn" onclick="adminResetPassword(${u.id})">Reset ww</button>`}</div></div>`).join('')}
async function createAccount(){let r=await api('/api/accounts',{method:'POST',body:JSON.stringify({display_name:accName.value.trim(),email:accEmail.value.trim(),role:accRole.value,password:accPassword.value})});accName.value='';accEmail.value='';accPassword.value='';await loadAccounts();toast(r.created?'Account aangemaakt.':'Account bestond al.',r.created?'good':'')}
async function toggleAccount(id,active){await api(`/api/accounts/${id}`,{method:'PATCH',body:JSON.stringify({active:!!active})});await loadAccounts()}
async function adminResetPassword(id){let pwd=prompt('Nieuw tijdelijk wachtwoord (min. 12 tekens):');if(!pwd)return;await api(`/api/accounts/${id}/reset-password`,{method:'POST',body:JSON.stringify({new_password:pwd})});toast('Wachtwoord gereset.','good')}
async function downloadOperationalExport(){let d=await api('/api/export');let blob=new Blob([JSON.stringify(d,null,2)],{type:'application/json'});let url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`werkstuur-export-${new Date().toISOString().slice(0,10)}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
async function resetPilotData(){if(resetConfirm.value!=='RESET PILOT DATA')return alert('Bevestigingstekst is niet exact correct.');let summary=await api('/api/pilot-reset-summary');if(!confirm(`Dit verwijdert ${summary.cases} cases, ${summary.notes} notities, ${summary.attachments} bijlagen en ${summary.pilots} pilot(s). Doorgaan?`))return;await api('/api/pilot-reset',{method:'POST',body:JSON.stringify({confirm:'RESET PILOT DATA'})});alert('Pilotdata verwijderd.');resetConfirm.value='';await loadCases();render();let ob=await api('/api/onboarding-status');initOnboarding(ob);show('onboarding')}

async function loadAudit(){if(me.role==="technician")return;let a=await api("/api/audit");auditList.innerHTML=a.map(x=>`<div class="row"><div>${escapeReport(new Date(x.created_at).toLocaleString("nl-NL"))}</div><div>${escapeReport(x.display_name||"Klant")}</div><div>${escapeReport(x.action)}</div><div>${escapeReport(x.detail||"")}</div><div></div></div>`).join("")}
function copyIntakeLink(){navigator.clipboard?.writeText(intakeLink.textContent);toast("Intakelink gekopieerd.","good")}
boot();
