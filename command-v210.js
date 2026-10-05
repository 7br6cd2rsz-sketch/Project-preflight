"use strict";
// Each workspace uses the real organisation-scoped API. No browser storage.
let customerRows=[],editingCustomer=null,platformLoadGeneration=0;
let supportRows=[],supportRequestKey=null;
function customerWriteAllowed(){return caseWriteAllowed()&&["admin","planner"].includes(me?.role)}
function teamWriteAllowed(){return caseWriteAllowed()&&me?.role==="admin"&&!me?.is_platform_owner}
function resetCustomerWorkspace(){customerRows=[];editingCustomer=null;$("customerEditor")?.classList.add("hidden");$("teamCreateForm")?.classList.add("hidden");for(const id of ["customerSearch","teamName","teamEmail","teamPassword","nCustomerId"]){if($(id))$(id).value=""}}
function configureRoleNavigation(view){
 if(!me)return;
 const owner=!!me.is_platform_owner,tech=me.role==="technician",operational=!owner||(!caseWriteAllowed()&&!["platform","owner","system","beheer","product"].includes(view));
 document.body.dataset.workspaceMode=owner?"owner":tech?"technician":"company";
 $("platformNav")?.classList.toggle("hidden",!owner);
 $("platformNavGroup")?.classList.remove("hidden");$("supportNav")?.classList.remove("hidden");
 document.querySelector(".cc-nav-main")?.classList.toggle("hidden",owner&&!operational);
 $("customersNav")?.classList.toggle("hidden",tech);
 $("teamAddButton")?.classList.toggle("hidden",!teamWriteAllowed());
 $("customerAddButton")?.classList.toggle("hidden",!customerWriteAllowed());
 $("ownerContextBanner")?.classList.toggle("hidden",!owner||caseWriteAllowed()||!operational);
 document.querySelector(".ws-global-search")?.classList.toggle("hidden",owner&&!operational);
 document.querySelector(".ws-mobile-search")?.classList.toggle("hidden",owner&&!operational);
 if(owner&&!operational){$("workspaceName").textContent="Werkstuur Control";$("workspacePlan").textContent="EIGENAAR"}
 else {$("workspaceName").textContent=me.organization_name||settings?.company_name||"Werkstuur";$("workspacePlan").textContent=owner?"SUPPORTINZAGE":"WERKRUIMTE"}
 const label=document.querySelector(".cc-workspace-label");if(label)label.textContent=owner&&!operational?"SOFTWAREBEHEER":owner?"KLANTOMGEVING · ALLEEN INZAGE":"JOUW WERKOMGEVING";
 document.querySelector(".cc-brandcopy span").textContent=owner?"Control center":tech?"Mijn opdrachten":"Intelligent workspace";
 if(owner)document.title="Werkstuur · Control";
 if(!teamWriteAllowed())$("teamCreateForm")?.classList.add("hidden");
}
async function loadPlatform(){
 if(!me?.is_platform_owner)return;
 const generation=++platformLoadGeneration,org=me.organization_id;
 const [orgResult,statusResult,supportResult]=await Promise.allSettled([api("/api/owner/organizations"),api("/api/system-status"),api("/api/owner/support")]);
 if(generation!==platformLoadGeneration||!me?.is_platform_owner||me.organization_id!==org)return;
 if(orgResult.status==="fulfilled"){
  ownerOrganizations=orgResult.value;
  const clients=ownerOrganizations.filter(o=>o.plan!=="internal"),active=clients.filter(o=>["active","pilot"].includes(o.status));
  $("platformClients").textContent=clients.length;$("platformActive").textContent=active.length;
  $("platformUsers").textContent=clients.reduce((n,o)=>n+Number(o.active_users||0),0);
  $("platformCompanies").innerHTML=clients.length?clients.slice(0,6).map(o=>`<article class="cmd-company"><span class="cmd-company-avatar">${escapeReport(initials(o.name))}</span><div><b>${escapeReport(o.name)}</b><small>${Number(o.active_users||0)} teamleden · ${Number(o.cases||0)} dossiers</small></div><span class="pill ${["active","pilot"].includes(o.status)?"good":"warn"}">${escapeReport(({active:"Actief",pilot:"Pilot",onboarding:"Inrichting",suspended:"Gepauzeerd",archived:"Archief"})[o.status]||o.status)}</span><button class="btn" type="button" onclick="switchOrganization(${Number(o.id)})">Inzien ↗</button></article>`).join(""):emptyState("Klaar voor je eerste klantbedrijf","Maak een klantomgeving met een eigen bedrijfsbeheerder. Daarna beheert het bedrijf zelf zijn team en klanten.","building",'<button class="btn primary" type="button" onclick="show(\'owner\')">Eerste bedrijf toevoegen</button>');
 }else{$("platformCompanies").innerHTML=emptyState("Bedrijven niet opgehaald",orgResult.reason.message,"alert")}
 if(statusResult.status==="fulfilled"){
  const s=statusResult.value,checks=[["Database",s.database?.status==="online"],["Private bijlagen",s.storage?.status==="online"],["E-mailmeldingen",s.mail?.status==="ready"]];
  $("platformHealth").innerHTML=`<div class="cmd-health-title ${s.overall==="healthy"?"good":"warn"}"><i></i>${s.overall==="healthy"?"Service operationeel":"Controle nodig"}</div>`+checks.map(([name,ok])=>`<div class="cmd-health-row"><span>${name}</span><b class="${ok?"good":"warn"}">${ok?"Online":"Controleer"}</b></div>`).join("")+`<p class="cmd-health-time">Gecontroleerd ${escapeReport(fmtDateTime(s.checked_at))}</p>`+(s.monitoring?.last_error?'<button class="btn full" type="button" onclick="show(\'system\')">Bekijk laatste foutmelding</button>':'<div class="cmd-health-ok">'+wsIcon("shield")+' Geen serverfout gemeld sinds deze start</div>');
 }else{$("platformHealth").innerHTML=emptyState("Status tijdelijk onbekend",statusResult.reason.message,"alert")}
 $("platformSetup").textContent=supportResult.status==="fulfilled"?supportResult.value.filter(t=>t.status!=="resolved").length:"—";
 configureRoleNavigation("platform");
}
function supportStatusLabel(status){return ({open:"Open",in_progress:"In behandeling",resolved:"Opgelost"})[status]||status}
async function loadSupport(){
 const owner=!!me?.is_platform_owner,org=me?.organization_id;
 const rows=await api(owner?"/api/owner/support":"/api/support");if(me?.organization_id!==org)return;supportRows=rows;
 $("supportTitle").textContent=owner?"Ondersteuning in beeld.":"We helpen je verder.";
 $("supportIntro").textContent=owner?"Softwarevragen en foutmeldingen uit je klantbedrijven. Hier pak je de ondersteuning op.":"Meld een softwareprobleem of stel een vraag. Je eigen bedrijf beheert het dagelijkse werk.";
 $("supportCreateForm").classList.toggle("hidden",owner);
 if(!supportRequestKey)supportRequestKey=crypto.randomUUID();
 if(!owner&&!wsScopeDirty("supportCreateForm"))wsResetScope("supportCreateForm");
 $("supportList").innerHTML=rows.length?rows.map(t=>`<article class="cmd-support-card"><div class="cmd-support-top"><span>${escapeReport(t.ticket_no)}${owner?" · "+escapeReport(t.organization_name):""}</span><span class="pill ${t.status==="resolved"?"good":t.status==="open"?"warn":"review"}">${escapeReport(supportStatusLabel(t.status))}</span></div><h3>${escapeReport(t.subject)}</h3><p class="cmd-support-description">${escapeReport(t.description)}</p><small>${escapeReport(fmtDateTime(t.created_at))}</small>${t.resolution?`<div class="cmd-support-resolution"><b>Reactie van Werkstuur</b><p>${escapeReport(t.resolution)}</p></div>`:""}${owner?`<details class="cmd-team-edit"><summary>Melding behandelen</summary><div class="field"><label for="ticketStatus${t.id}">Status</label><select id="ticketStatus${t.id}">${["open","in_progress","resolved"].map(s=>`<option value="${s}" ${s===t.status?"selected":""}>${escapeReport(supportStatusLabel(s))}</option>`).join("")}</select></div><div class="field"><label for="ticketResolution${t.id}">Reactie / oplossing</label><textarea id="ticketResolution${t.id}" maxlength="6000">${escapeReport(t.resolution||"")}</textarea></div><button class="btn primary" type="button" onclick="updateSupport(${t.id})">Reactie opslaan</button></details>`:""}</article>`).join(""):emptyState("Nog geen supportmeldingen",owner?"Je klantbedrijven melden hier vragen en softwareproblemen. Nieuwe meldingen worden zichtbaar wanneer je het overzicht vernieuwt.":"Je meldingen en reacties van Werkstuur verschijnen hier.","message");
}
function showSupportHelp(){const text=$("supportDescription").value.toLowerCase();let advice="";if(/opslaan|verbinding|netwerk|laden/.test(text))advice="Behoud je invoer en controleer de verbindingsmelding. Wacht op de opslagbevestiging voordat je dezelfde actie opnieuw uitvoert.";else if(/wachtwoord|inloggen|account/.test(text))advice="Je bedrijfsbeheerder kan een herstel-link sturen vanuit Team. Wachtwoord vergeten staat ook op het inlogscherm.";else if(/monteur|toewijz|opdracht/.test(text))advice="Een monteur ziet alleen de toegewezen dossiers. De planner controleert de toewijzing in het dossier.";$("supportHelp").textContent=advice?"Hulp op basis van je beschrijving: "+advice:""}
async function submitSupport(){
 if(me?.is_platform_owner||!caseWriteAllowed())return;
 const subject=$("supportSubject").value.trim(),description=$("supportDescription").value.trim();
 if(subject.length<4)return wsFieldError("supportSubject","Gebruik minstens 4 tekens.","supportMessage");if(description.length<10)return wsFieldError("supportDescription","Beschrijf de melding in minstens 10 tekens.","supportMessage");
 const result=await api("/api/support",{method:"POST",body:JSON.stringify({subject,description,category:$("supportCategory").value,request_key:supportRequestKey})});
 $("supportSubject").value="";$("supportDescription").value="";$("supportHelp").textContent="";supportRequestKey=crypto.randomUUID();wsResetScope("supportCreateForm");await loadSupport();toast("Melding opgeslagen: "+result.ticket_no,"good");
}
async function updateSupport(id){if(!me?.is_platform_owner)return;const t=supportRows.find(t=>Number(t.id)===Number(id));if(!t)return;await api(`/api/owner/support/${Number(id)}`,{method:"PATCH",body:JSON.stringify({status:$("ticketStatus"+id).value,resolution:$("ticketResolution"+id).value.trim(),version:t.version})});await loadSupport();toast("Supportmelding bijgewerkt.","good")}
async function loadTeamWorkspace(){await loadUsers();if(me)renderTeam()}
function renderTeam(){
 if(!me)return;
 const writable=teamWriteAllowed();$("teamAddButton")?.classList.toggle("hidden",!writable);
 $("teamList").innerHTML=users.length?users.map(u=>{
  const owner=!!u.is_platform_owner,editable=writable&&!owner,self=Number(u.id)===Number(me.id);
  return `<article class="cmd-team-card ${u.active?"":"cmd-inactive"}"><div class="cmd-team-card-top"><span class="cmd-team-avatar">${escapeReport(initials(u.display_name))}</span><span class="pill ${u.active?"good":""}">${u.active?"Actief":"Uitgeschakeld"}</span></div><h3>${escapeReport(u.display_name)}</h3><p class="cmd-team-email">${escapeReport(u.email)}</p><span class="cmd-role-badge">${wsIcon(owner?"shield":u.role==="technician"?"wrench":"users")}${owner?"Software-eigenaar":escapeReport(roleLabel(u.role))}</span>${editable?`<details class="cmd-team-edit"><summary>Teamlid beheren</summary><div class="field"><label for="memberName${u.id}">Naam</label><input id="memberName${u.id}" maxlength="160" value="${escAttr(u.display_name)}"></div><div class="field"><label for="memberRole${u.id}">Rol</label><select id="memberRole${u.id}" ${self?"disabled":""}>${["admin","planner","technician"].map(r=>`<option value="${r}" ${r===u.role?"selected":""}>${escapeReport(roleLabel(r))}</option>`).join("")}</select></div><div class="cc-inline-actions"><button class="btn primary" type="button" onclick="saveTeamMember(${u.id})">Opslaan</button>${self?"":`<button class="btn" type="button" onclick="toggleTeamMember(${u.id},${!u.active})">${u.active?"Deactiveer":"Activeer"}</button><button class="btn" type="button" onclick="sendResetLink(${u.id})">Herstel-link</button>`}</div></details>`:`<p class="cmd-team-caption">${owner?"Softwarebeheer en ondersteuning":writable&&self?"Je eigen account":""}</p>`}</article>`
 }).join(""):emptyState("Je team begint hier","Voeg een planner en een monteur toe zodra hun gegevens bekend zijn.","users");
}
function openTeamCreate(){if(!teamWriteAllowed())return;$("teamCreateForm").classList.remove("hidden");$("teamMessage").textContent="";wsResetScope("teamCreateForm");$("teamCreateForm").scrollIntoView({behavior:"smooth",block:"start"});$("teamName").focus()}
function closeTeamCreate(){if(wsScopeDirty("teamCreateForm")&&!wsConfirmLeave())return;$("teamCreateForm").classList.add("hidden");$("teamPassword").value=""}
async function createTeamMember(){
 if(!teamWriteAllowed())return;
 const name=$("teamName").value.trim(),email=$("teamEmail").value.trim(),password=$("teamPassword").value;
 if(!name)return wsFieldError("teamName","Vul een naam in.","teamMessage");
 if(!email||!$("teamEmail").checkValidity())return wsFieldError("teamEmail","Vul een geldig e-mailadres in.","teamMessage");
 if(password.length<12)return wsFieldError("teamPassword","Gebruik minimaal 12 tekens.","teamMessage");
 const result=await api("/api/accounts",{method:"POST",body:JSON.stringify({display_name:name,email,role:$("teamRole").value,password})});
 for(const id of ["teamName","teamEmail","teamPassword"])$(id).value="";wsResetScope("teamCreateForm");$("teamCreateForm").classList.add("hidden");await loadTeamWorkspace();toast(result.created?"Teamlid toegevoegd aan jouw bedrijf.":"Dit teamlid heeft al een account.","good");
}
async function saveTeamMember(id){if(!teamWriteAllowed())return;await api(`/api/accounts/${Number(id)}`,{method:"PATCH",body:JSON.stringify({display_name:$("memberName"+id).value.trim(),role:$("memberRole"+id).value})});await loadTeamWorkspace();toast("Teamlid bijgewerkt.","good")}
async function toggleTeamMember(id,active){if(!teamWriteAllowed())return;await api(`/api/accounts/${Number(id)}`,{method:"PATCH",body:JSON.stringify({active})});await loadTeamWorkspace();toast(active?"Account geactiveerd.":"Account gedeactiveerd.","good")}
async function loadCustomers(){const org=me?.organization_id;const rows=await api("/api/customers");if(me?.organization_id!==org)return;customerRows=rows;await loadCases();renderCustomers()}
function renderCustomers(){
 const q=String($("customerSearch").value).trim().toLowerCase(),archived=$("customerShowArchived").checked,writable=customerWriteAllowed();
 const rows=customerRows.filter(c=>(archived||c.active)&&(!q||[c.name,c.email,c.phone,c.address,c.city,c.postal_code].join(" ").toLowerCase().includes(q)));
 $("customerCount").textContent=`${rows.length} klanten`;$("customerAddButton").classList.toggle("hidden",!writable);
 $("customerList").innerHTML=rows.length?rows.map(c=>{
  const linked=cases.filter(d=>Number(d.customer_id)===Number(c.id)),open=linked.filter(d=>d.status!=="Afgerond").length;
  return `<article class="cmd-customer-card ${c.active?"":"cmd-inactive"}"><div class="cmd-customer-top"><span class="cmd-company-avatar">${escapeReport(initials(c.name))}</span><div><h3>${escapeReport(c.name)}</h3><small>${escapeReport([c.postal_code,c.city].filter(Boolean).join(" ")||"Plaats nog niet opgegeven")}</small></div><span class="pill">${c.active?`${linked.length} dossiers`:"Archief"}</span></div><div class="cmd-customer-contact"><span>${escapeReport(c.email||"Geen e-mail")}</span><span>${escapeReport(c.phone||"Geen telefoon")}</span></div><p class="cmd-customer-address">${escapeReport(c.address||"Adres nog niet opgegeven")}</p><div class="cmd-customer-footer"><small>${open} open dossiers</small><div class="cc-inline-actions">${writable?`<button class="btn" type="button" onclick="editCustomer(${c.id})">Bewerken</button>${c.active?`<button class="btn primary" type="button" onclick="newCustomerCase(${c.id})">Nieuw dossier ↗</button>`:""}<button class="cc-textbtn" type="button" onclick="archiveCustomer(${c.id},${!c.active})">${c.active?"Archiveren":"Herstellen"}</button>`:'<span class="sub">Supportinzage</span>'}</div></div>${linked.length?`<details class="cmd-customer-history"><summary>Dossierhistorie</summary>${linked.map(d=>`<button class="cmd-history-row" type="button" onclick="openCase(${Number(d.id)})"><span>${escapeReport(d.case_no)} · ${escapeReport(d.type)}</span>${pill(d.status)}</button>`).join("")}</details>`:""}</article>`
 }).join(""):emptyState(q?"Geen klanten gevonden":"Je klanten krijgen hier hun plek",q?"Pas je zoekopdracht aan.":"Voeg je eerste klant toe. Je team beheert contactgegevens en start van hieruit nieuwe servicedossiers.","users");
}
function editCustomer(id=null){
 if(!customerWriteAllowed())return;
 if(wsScopeDirty("customerEditor")&&!wsConfirmLeave())return;
 editingCustomer=id?customerRows.find(c=>Number(c.id)===Number(id)):null;
 if(id&&!editingCustomer)return;
 const map={name:"customerName",email:"customerEmail",phone:"customerPhone",address:"customerAddress",postal_code:"customerPostal",city:"customerCity",notes:"customerNotes"};
 for(const [key,control] of Object.entries(map))$(control).value=editingCustomer?.[key]||"";
 $("customerEditorTitle").textContent=id?"Klant bewerken":"Nieuwe klant";$("customerMessage").textContent="";$("customerEditor").classList.remove("hidden");wsResetScope("customerEditor");$("customerEditor").scrollIntoView({behavior:"smooth",block:"start"});$("customerName").focus();
}
function closeCustomerEditor(){if(wsScopeDirty("customerEditor")&&!wsConfirmLeave())return;$("customerEditor").classList.add("hidden");editingCustomer=null}
async function saveCustomer(){
 if(!customerWriteAllowed())return;
 const payload={},map={name:"customerName",email:"customerEmail",phone:"customerPhone",address:"customerAddress",postal_code:"customerPostal",city:"customerCity",notes:"customerNotes"};
 for(const [key,control] of Object.entries(map))payload[key]=$(control).value.trim();
 if(!payload.name)return wsFieldError("customerName","Vul de klantnaam in.","customerMessage");
 if(payload.email&&!$("customerEmail").checkValidity())return wsFieldError("customerEmail","Vul een geldig e-mailadres in.","customerMessage");
 const existing=editingCustomer; if(existing)payload.version=existing.version;
 const org=me.organization_id;
 try{await api(existing?`/api/customers/${existing.id}`:"/api/customers",{method:existing?"PATCH":"POST",body:JSON.stringify(payload)})}
 catch(e){if(e.status===409){await loadCustomers();const latest=customerRows.find(c=>c.id===existing?.id);$("customerMessage").innerHTML="Deze klant is intussen gewijzigd. Je invoer is bewaard. Open de nieuwste versie om de gegevens opnieuw te controleren. "+(latest?`<button class="btn" type="button" onclick="editCustomer(${Number(latest.id)})">Nieuwste versie openen</button>`:"");return}throw e}
 if(me?.organization_id!==org)return;wsResetScope("customerEditor");closeCustomerEditor();await loadCustomers();toast("Klantgegevens opgeslagen.","good");
}
async function archiveCustomer(id,active){if(!customerWriteAllowed())return;const c=customerRows.find(c=>Number(c.id)===Number(id));if(!c)return;await api(`/api/customers/${Number(id)}`,{method:"PATCH",body:JSON.stringify({active,version:c.version})});await loadCustomers();toast(active?"Klant hersteld.":"Klant gearchiveerd. Dossiers blijven bewaard.","good")}
function newCustomerCase(id){const c=customerRows.find(c=>Number(c.id)===Number(id));if(!c||!customerWriteAllowed())return;openNew();if($("newModal").classList.contains("hidden"))return;$("nCustomerId").value=c.id;$("nCustomer").value=c.name;$("nCity").value=c.city||"";$("nEmail").value=c.email||"";$("nPhone").value=c.phone||"";wsResetScope("newModal")}
const previousOpenNew=openNew;
openNew=function(...args){previousOpenNew(...args);if(!$("newModal").classList.contains("hidden"))$("nCustomerId").value=""};
if(typeof wsProtectedScopes!=="undefined")wsProtectedScopes.push("customerEditor","teamCreateForm","supportCreateForm");
for(const [name,fn] of Object.entries({createTeamMember,saveTeamMember,toggleTeamMember,saveCustomer,archiveCustomer,submitSupport,updateSupport}))window[name]=(...args)=>runWorkspaceAction(name,fn,args);
const previousProductManagement=loadProductManagement;
loadProductManagement=async function(){await previousProductManagement();if(!me)return;$("accountAdminCard").style.display=teamWriteAllowed()?"":"none";if(!caseWriteAllowed()){document.querySelectorAll("#productView input,#productView button[onclick='saveBranding()'],#productView button[onclick='resetPilotData()']").forEach(el=>el.disabled=true)}};

$("nCustomer")?.addEventListener("input",()=>{$("nCustomerId").value=""});
