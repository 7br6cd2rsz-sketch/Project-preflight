const wsIconPaths={"overview":"<rect x=\"3\" y=\"3\" width=\"7\" height=\"7\" rx=\"1.5\"/><rect x=\"14\" y=\"3\" width=\"7\" height=\"7\" rx=\"1.5\"/><rect x=\"3\" y=\"14\" width=\"7\" height=\"7\" rx=\"1.5\"/><rect x=\"14\" y=\"14\" width=\"7\" height=\"7\" rx=\"1.5\"/>","folder":"<path d=\"M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z\"/><path d=\"M3 11h18\"/>","work":"<rect x=\"4\" y=\"6\" width=\"16\" height=\"15\" rx=\"2\"/><path d=\"M9 6V3h6v3M8 11h8M8 15h4M8 18h6\"/>","chart":"<path d=\"M4 3v17h17M8 15v-4M13 15V7M18 15v-7\"/>","intake":"<rect x=\"5\" y=\"3\" width=\"14\" height=\"18\" rx=\"2\"/><path d=\"M9 7h6M9 11h6M9 15h3M16 17l2 2 4-4\"/>","users":"<circle cx=\"9\" cy=\"8\" r=\"3\"/><path d=\"M3 21v-3a6 6 0 0 1 12 0v3M16 5a3 3 0 0 1 0 6M18 15a5 5 0 0 1 3 5\"/>","building":"<rect x=\"4\" y=\"3\" width=\"16\" height=\"18\" rx=\"2\"/><path d=\"M8 7h2M14 7h2M8 11h2M14 11h2M8 15h2M14 15h2M10 21v-3h4v3\"/>","settings":"<path d=\"m10 3-.6 2.4-2 .9-2.2-.7-2 3.4 1.6 1.8v2.4L3.2 15l2 3.4 2.2-.7 2 .9.6 2.4h4l.6-2.4 2-.9 2.2.7 2-3.4-1.6-1.8v-2.4l1.6-1.8-2-3.4-2.2.7-2-.9L14 3z\"/><circle cx=\"12\" cy=\"12\" r=\"3\"/>","search":"<circle cx=\"10.5\" cy=\"10.5\" r=\"6.5\"/><path d=\"m16 16 5 5\"/>","menu":"<path d=\"M4 6h16M4 12h16M4 18h16\"/>","close":"<path d=\"m6 6 12 12M18 6 6 18\"/>","arrow-right":"<path d=\"M4 12h16m-6-6 6 6-6 6\"/>","arrow-left":"<path d=\"M20 12H4m6-6-6 6 6 6\"/>","external":"<path d=\"M14 3h7v7M21 3l-10 10M10 5H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5\"/>","logout":"<path d=\"M10 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h5M9 12h12m-4-4 4 4-4 4\"/>","check":"<path d=\"m5 12 4 4L19 6\"/>","check-circle":"<circle cx=\"12\" cy=\"12\" r=\"9\"/><path d=\"m8 12 3 3 5-6\"/>","alert":"<path d=\"m12 3 10 17H2zM12 9v4M12 17h.01\"/>","info":"<circle cx=\"12\" cy=\"12\" r=\"9\"/><path d=\"M12 11v6M12 7h.01\"/>","clock":"<circle cx=\"12\" cy=\"12\" r=\"9\"/><path d=\"M12 6v6l4 2\"/>","file":"<path d=\"M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M8 12h8M8 16h5\"/>","download":"<path d=\"M12 3v12m-5-5 5 5 5-5M4 16v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4\"/>","upload":"<path d=\"M12 16V4m-5 5 5-5 5 5M4 16v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4\"/>","message":"<path d=\"M4 3h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H8l-5 4V4a1 1 0 0 1 1-1zM7 7h10M7 11h7\"/>","shield":"<path d=\"m12 2 8 3v6c0 5-4 9-8 11-4-2-8-6-8-11V5zM8 11l3 3 5-6\"/>","refresh":"<path d=\"M20 8V3l-3 3a8 8 0 0 0-13 5M4 16v5l3-3a8 8 0 0 0 13-5M20 3h-5M4 21h5\"/>","plus":"<path d=\"M12 4v16M4 12h16\"/>","wrench":"<path d=\"M14 7a6 6 0 0 1 7-4l-4 4 2 2 4-4a6 6 0 0 1-7 7L7 21a3 3 0 0 1-4-4l9-9a6 6 0 0 1 2-1z\"/>","pin":"<path d=\"M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 0 1 16 0z\"/><circle cx=\"12\" cy=\"10\" r=\"3\"/>","cloud":"<path d=\"M6 19a5 5 0 0 1-1-10 7 7 0 0 1 13-2 6 6 0 0 1 1 12z\"/>","euro":"<path d=\"M18 5a7 7 0 0 0-11 7 7 7 0 0 0 11 7M4 10h11M4 14h10\"/>","eye":"<path d=\"M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7z\"/><circle cx=\"12\" cy=\"12\" r=\"3\"/>"};
function wsIcon(name){return `<svg class="ws-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${wsIconPaths[name]||wsIconPaths.info}</svg>`}
let workspaceRequests=0,lastModalFocus=null;
function roleLabel(role){return ({admin:"Bedrijfsbeheerder",planner:"Planner",technician:"Monteur"})[role]||"Gebruiker"}
function initials(name){const parts=String(name||"").trim().split(/\s+/).filter(Boolean);return (parts[0]?.[0]||"W")+(parts.length>1?parts[parts.length-1][0]:"")}
function markConnection(state){const status=$("connectionStatus"),label=$("connectionLabel");if(status){status.classList.toggle("busy",state==="busy");status.classList.toggle("offline",state==="offline")}if(label)label.textContent=state==="busy"?"Synchroniseren":state==="offline"?"Controleer verbinding":"Verbonden"}
function closeNavigation(){const aside=app.querySelector("aside"),mobile=window.matchMedia("(max-width: 760px)").matches;if(aside?.contains(document.activeElement))$("workspaceMenuToggle")?.focus();app.classList.remove("nav-open");if(aside){aside.inert=mobile;aside.setAttribute("aria-hidden",String(mobile))}$("workspaceMenuToggle")?.setAttribute("aria-expanded","false");$("workspaceMenuToggle")?.setAttribute("aria-label","Menu openen")}
function toggleNavigation(){const open=!app.classList.contains("nav-open");app.classList.toggle("nav-open",open);const aside=app.querySelector("aside");if(aside){aside.inert=!open;aside.setAttribute("aria-hidden",String(!open))}$("workspaceMenuToggle")?.setAttribute("aria-expanded",String(open));$("workspaceMenuToggle")?.setAttribute("aria-label",open?"Menu sluiten":"Menu openen")}
function openWorkspaceSearch(){show(me?.role==="technician"?"workorders":"cases");focusCaseSearch()}
function syncSearchFields(){const source=me?.role==="technician"?$("workorderSearch"):$("caseSearch");if($("globalSearch")&&source)$("globalSearch").value=source.value}
function backFromCase(){show(me?.role==="technician"?"workorders":"cases")}
function selectCaseTab(name,focus=false){const selected=document.getElementById("caseTab-"+name);if(!selected)return;document.querySelectorAll("[data-case-tab]").forEach(tab=>{const on=tab.dataset.caseTab===name;tab.classList.toggle("active",on);tab.setAttribute("aria-selected",String(on));tab.tabIndex=on?0:-1;$("casePane-"+tab.dataset.caseTab)?.classList.toggle("hidden",!on)});if(focus)selected.focus()}
function linkFieldLabels(){document.querySelectorAll(".field").forEach(field=>{const label=field.querySelector("label"),control=field.querySelector("input,textarea,select");if(label&&control?.id)label.htmlFor=control.id})}
function updateCasePermissions(){const writable=caseWriteAllowed();document.querySelectorAll("#caseView .case-write").forEach(el=>el.classList.toggle("hidden",!writable));document.querySelectorAll("#caseView input,#caseView textarea,#caseView select").forEach(el=>el.disabled=!writable);if(me?.role==="technician"){$("assignmentCard")?.classList.add("hidden")}else{$("assignmentCard")?.classList.remove("hidden");if($("assignedTo"))assignedTo.disabled=!writable}if($("assignmentHelp"))assignmentHelp.textContent=!writable?"Alleen een teamaccount kan de toewijzing wijzigen.":users.some(u=>u.role==="technician")?"De monteur ziet dit dossier bij Mijn opdrachten.":"Voeg eerst een monteur toe via accountbeheer.";linkFieldLabels()}
function closeNew(force=false){if(!force&&typeof wsConfirmLeave==="function"&&!wsConfirmLeave())return;newModal.classList.add("hidden");document.body.classList.remove("modal-open");lastModalFocus?.focus()}
async function refreshWorkorders(){await loadCases();renderWorkorders();toast("Je opdrachten zijn bijgewerkt.","good")}
function emptyState(title,message,name="folder",action=""){return `<div class="ws-empty">${wsIcon(name)}<b>${escapeReport(title)}</b><p>${escapeReport(message)}</p>${action}</div>`}
function showAuthScreen(){app.classList.add("hidden");login.classList.remove("hidden");$("sessionSplash")?.classList.add("hidden");document.body.classList.remove("modal-open");closeNavigation()}
async function runWorkspaceAction(name,task,args){if(runWorkspaceAction.pending.has(name))return;let button=document.activeElement?.closest("button");if(!button){button=[...document.querySelectorAll("button[onclick]")].find(el=>el.getAttribute("onclick")?.startsWith(name+"(")&&el.getClientRects().length)}const original=button?.innerHTML;runWorkspaceAction.pending.add(name);if(button){button.disabled=true;button.setAttribute("aria-busy","true");button.innerHTML='<span class="ws-spinner" aria-hidden="true"></span>Even wachten…'}let unlock=null;try{const result=task(...args);if(typeof wsLockAction==="function")unlock=wsLockAction(name);return await result}catch(error){toast(error.message||"De actie kon niet worden voltooid.","bad")}finally{unlock?.();runWorkspaceAction.pending.delete(name);if(typeof wsUpdateDraftState==="function")wsUpdateDraftState();if(button?.isConnected){button.disabled=false;button.removeAttribute("aria-busy");button.innerHTML=original}}}
runWorkspaceAction.pending=new Set();
let token=null,me=null,cases=[],users=[],current=null,settings=null,attachmentFiles=[],systemTimer=null,ownerOrganizations=[],passwordResetToken=new URLSearchParams(location.search).get("reset")||"";
const $=id=>document.getElementById(id);
function caseWriteAllowed(){return !!me && !!me.organization_id && (me.base_organization_id??me.organization_id)===me.organization_id}
function requireCaseWrite(){
 if(caseWriteAllowed())return true;
 toast("Je bekijkt deze organisatie als eigenaar. Gebruik een teamaccount van deze organisatie om cases bij te werken.","warn");
 return false;
}
function toast(message,type=""){
 const stack=$("toastStack");
 if(!stack){console.log(message);return}
 const el=document.createElement("div");el.className=`ws-toast ${type}`.trim();el.textContent=message;stack.appendChild(el);
 const duration=type==="warn"||type==="bad"?8000:3150;
 setTimeout(()=>{el.style.opacity="0";el.style.transform="translateY(6px)"},duration-350);
 setTimeout(()=>el.remove(),duration);
}
function syncGlobalSearch(value){
 const tech=me?.role==="technician",input=$(tech?"workorderSearch":"caseSearch");if(input)input.value=value||"";tech?renderWorkorders():renderCasesView();if(String(value||"").trim().length>=2&&$(tech?"workordersView":"casesView")?.classList.contains("hidden"))show(tech?"workorders":"cases",false)
}
function focusCaseSearch(){setTimeout(()=>$((me?.role==="technician")?"workorderSearch":"caseSearch")?.focus(),50)}

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
 const org=me.organization_name||"Werkstuur",owner=!!me.is_platform_owner;
 if($("workspaceName")){$("workspaceName").textContent=org;$("workspaceName").title=org}
 if($("workspacePlan"))$("workspacePlan").textContent=({internal:"WERKSTUUR",pilot:"PILOT",starter:"START",pro:"PRO"})[me.organization_plan]||"TEAM";
 if($("workspaceSwitch"))$("workspaceSwitch").classList.toggle("hidden",!owner);
 if($("userDisplay"))$("userDisplay").textContent=me.display_name||"Gebruiker";
 if($("userInitials"))$("userInitials").textContent=initials(me.display_name);
 if($("who")){$("who").textContent=owner?"Werkstuur-eigenaar":roleLabel(me.role);$("who").title=roleLabel(me.role)+" · "+org}
 if($("ownerContextBanner"))$("ownerContextBanner").classList.toggle("hidden",caseWriteAllowed());
 if($("newBtn"))$("newBtn").classList.toggle("hidden",me.role==="technician"||!caseWriteAllowed());
 if($("newBtn2"))$("newBtn2").classList.toggle("hidden",me.role==="technician"||!caseWriteAllowed());
 if($("dashboardGreeting")){const h=new Date().getHours(),g=h<12?"Goedemorgen":h<18?"Goedemiddag":"Goedenavond",first=String(me.display_name||"").trim().split(/\s+/)[0];$("dashboardGreeting").textContent=g+(first?", "+first:"")}
}

async function logoutNow(){
 if(typeof wsConfirmLeave==="function"&&!wsConfirmLeave())return;
 try{await api("/api/logout",{method:"POST",body:JSON.stringify({})})}catch(e){}
 location.reload();
}
async function api(path,opts={}){
 const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),45000);workspaceRequests++;markConnection("busy");
 try{const r=await fetch(path,{...opts,headers:{"Content-Type":"application/json",...(opts.headers||{})},credentials:"same-origin",signal:opts.signal||controller.signal});const text=await r.text();let data;try{data=text?JSON.parse(text):null}catch{data=null}if(!r.ok){let error=new Error(({unauthorized:"Je aanmelding is ongeldig of verlopen.",forbidden:"Je hebt geen toegang tot deze actie.","invalid token":"Deze link is ongeldig of verlopen.",server_error:"De service is tijdelijk niet beschikbaar. Probeer het zo opnieuw.",version_conflict:"Dit dossier is intussen gewijzigd. Controleer de nieuwste gegevens."})[data?.error]||data?.error||(r.status>=500?"De service is tijdelijk niet beschikbaar. Probeer het zo opnieuw.":"Deze actie kon niet worden uitgevoerd."));error.status=r.status;error.data=data;if(r.status===401&&me){me=null;showAuthScreen();$("loginMsg").textContent="Je sessie is verlopen. Log opnieuw in om verder te werken."}throw error}markConnection("online");return data}catch(error){if(error.name==="AbortError"){markConnection("offline");throw new Error("De bevestiging duurt langer dan verwacht. Vernieuw het overzicht voordat je dezelfde actie nogmaals uitvoert.")}if(error instanceof TypeError){markConnection("offline");throw new Error("Geen verbinding met de service. Controleer je verbinding en probeer opnieuw.")}throw error}finally{clearTimeout(timeout);workspaceRequests--;if(workspaceRequests>0)markConnection("busy")}
}
function show(v,refresh=true,internal=false){
 if(!me)return;
 const tech=me.role==="technician",admin=me.role==="admin"||me.is_platform_owner;
 if((tech&&!["workorders","case","support"].includes(v))||(["owner","platform"].includes(v)&&!me.is_platform_owner)||(["beheer","product","system","audit","onboarding"].includes(v)&&!admin)){toast("Dit onderdeel hoort niet bij je rol.","warn");return}
 if(systemTimer){clearInterval(systemTimer);systemTimer=null}
 const target=$(v+"View");if(!target)return false;
 if(!internal&&target.classList.contains("hidden")&&typeof wsConfirmLeave==="function"&&!wsConfirmLeave())return false;
 document.querySelectorAll("main>section").forEach(x=>x.classList.add("hidden"));target.classList.remove("hidden");
 const parent=({case:tech?"workorders":"cases",metrics:"pilotHub",pilot:"pilotHub",report:"pilotHub",product:"beheer",system:"beheer",audit:"beheer",onboarding:"beheer"})[v]||v;
 document.querySelectorAll(".cc-nav button").forEach(b=>{const on=b.dataset.view===parent;b.classList.toggle("active",on);if(on)b.setAttribute("aria-current","page");else b.removeAttribute("aria-current")});
 const labels={support:"Ondersteuning",platform:"Softwarebeheer",customers:"Klanten",dashboard:"Overzicht",cases:"Servicedossiers",workorders:"Mijn opdrachten",case:"Servicedossier",pilotHub:"Resultaten",metrics:"KPI's & businesscase",pilot:"Pilot beheren",report:"Directierapport",product:"Productinstellingen",system:"Systeemstatus",audit:"Activiteiten",onboarding:"Startinstellingen",owner:"Klantbedrijven",beheer:"Instellingen & beheer",team:"Team",settings:"Klantintake"};
 if($("pageLabel"))$("pageLabel").textContent=labels[v]||v;if($("breadcrumbLabel"))$("breadcrumbLabel").textContent=labels[v]||v;
 closeNavigation();window.scrollTo({top:0,behavior:"instant"});
 if(typeof configureRoleNavigation==="function")configureRoleNavigation(v);
 const loaders={support:loadSupport,platform:loadPlatform,customers:loadCustomers,team:loadTeamWorkspace,pilotHub:loadPilotHub,metrics:loadMetrics,pilot:loadPilot,report:loadReport,product:loadProductManagement,audit:loadAudit,owner:loadOwnerConsole,beheer:()=>configureManageHub(),system:()=>{const task=loadSystemStatus();systemTimer=setInterval(()=>{if(!$("systemView").classList.contains("hidden"))loadSystemStatus(true)},60000);return task}};
 let task;if(refresh&&["cases","dashboard","workorders"].includes(v))task=loadCases().then(()=>{if(me)render()});else if(loaders[v])task=loaders[v]();
 Promise.resolve(task).catch(error=>toast(error.message||"De gegevens konden niet worden geladen.","warn"));
 return true;
}

document.querySelectorAll(".cc-nav button[data-view]").forEach(b=>b.onclick=()=>show(b.dataset.view));
document.addEventListener("keydown",e=>{
 if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==="k"){if(!me)return;e.preventDefault();openWorkspaceSearch();return}
 if(e.key==="/"&&me&&!/input|textarea|select/i.test(document.activeElement?.tagName||"")){e.preventDefault();openWorkspaceSearch()}
 if(e.key==="Escape"){closeNavigation();if(!newModal.classList.contains("hidden"))closeNew()}
 if(!newModal.classList.contains("hidden")&&e.key==="Tab"){const controls=[...newModal.querySelectorAll("button,input,select,textarea,a[href]")].filter(el=>!el.disabled&&el.getClientRects().length);const first=controls[0],last=controls[controls.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus()}}
 const tab=e.target.closest?.("[data-case-tab]");if(tab&&["ArrowLeft","ArrowRight","Home","End"].includes(e.key)){e.preventDefault();const tabs=[...document.querySelectorAll("[data-case-tab]")],index=tabs.indexOf(tab),next=e.key==="Home"?0:e.key==="End"?tabs.length-1:(index+(e.key==="ArrowRight"?1:-1)+tabs.length)%tabs.length;selectCaseTab(tabs[next].dataset.caseTab,true)}
});

function pill(status){const style=status==="Ingepland"||status==="Afgerond"?"good":status==="Info ontbreekt"?"warn":status==="Review"?"review":"";return `<span class="pill ${style}">${wsIcon(status==="Afgerond"?"check":status==="Info ontbreekt"?"alert":status==="Ingepland"?"clock":"info")}${escapeReport(status||"Nieuwe melding")}</span>`}
function setAuthPanel(id){["loginPanel","forgotPanel","resetPanel"].forEach(x=>$(x)?.classList.toggle("hidden",x!==id))}
function showForgotPassword(){if($("forgotEmail"))$("forgotEmail").value=$("email")?.value||"";if($("forgotMsg"))$("forgotMsg").textContent="";setAuthPanel("forgotPanel")}
function showLoginPanel(clearReset=false){if(clearReset){passwordResetToken="";history.replaceState({},"",location.pathname)};if($("loginMsg"))$("loginMsg").textContent="";setAuthPanel("loginPanel")}
async function requestPasswordReset(){let addr=$("forgotEmail")?.value.trim()||"";if(!addr)return wsFieldError("forgotEmail","Vul je e-mailadres in.","forgotMsg");if(!$("forgotEmail").checkValidity())return wsFieldError("forgotEmail","Vul een geldig e-mailadres in.","forgotMsg");$("forgotEmail").removeAttribute("aria-invalid");try{let r=await api("/api/forgot-password",{method:"POST",body:JSON.stringify({email:addr})});$("forgotMsg").textContent=r.message||"Controleer je e-mail."}catch(e){$("forgotMsg").textContent=e.message}}
async function completePasswordReset(){let a=$("resetPassword")?.value||"",b=$("resetPassword2")?.value||"";if(a.length<12)return wsFieldError("resetPassword","Gebruik minimaal 12 tekens.","resetMsg");if(a!==b)return wsFieldError("resetPassword2","De wachtwoorden zijn niet gelijk.","resetMsg");try{await api("/api/reset-password",{method:"POST",body:JSON.stringify({token:passwordResetToken,new_password:a})});passwordResetToken="";history.replaceState({},"",location.pathname);$("email").value="";$("password").value="";setAuthPanel("loginPanel");$("loginMsg").textContent="Wachtwoord gewijzigd. Je kunt nu inloggen."}catch(e){$("resetMsg").textContent=e.message}}
async function loginNow(){try{loginMsg.textContent="";let d=await api("/api/login",{method:"POST",body:JSON.stringify({email:email.value,password:password.value})});me=d.user;await boot()}catch(e){loginMsg.textContent=e.message}}
async function boot(){
 try{
  me=await api("/api/me");login.classList.add("hidden");app.classList.remove("hidden");$("sessionSplash")?.classList.add("hidden");
  const tech=me.role==="technician",admin=me.role==="admin",owner=!!me.is_platform_owner,vis=(id,on)=>$(id)?.classList.toggle("hidden",!on);
  vis("dashboardNav",!tech);vis("casesNav",!tech);vis("workordersNav",tech);vis("pilotHubNav",!tech);vis("settingsNav",!tech);vis("teamNav",!tech);vis("ownerNav",owner);vis("beheerNav",!tech&&(admin||owner));vis("platformNavGroup",!tech&&(admin||owner));vis("workspaceSwitch",owner);
  if($("globalSearch"))$("globalSearch").placeholder=tech?"Zoek jouw opdrachten…":"Zoek een dossier…";
  updateWorkspaceChrome();await Promise.all([loadCases(),tech?Promise.resolve():loadUsers(),tech?Promise.resolve():loadSettings()]);if(settings)applyBranding(settings);render();configureManageHub();linkFieldLabels();
  if(tech){show("workorders",false);return}
  const ob=await api("/api/onboarding-status");vis("setupBanner",!ob.complete&&admin&&!owner);show(owner?"platform":"dashboard",false);
 }catch(error){$("sessionSplash")?.classList.add("hidden");if(error.status===401){showAuthScreen();return}showAuthScreen();$("loginMsg").textContent=error.message||"De werkomgeving kon niet worden geladen. Probeer opnieuw."}
}

function caseForDisplay(c){return c?.analysis&&!c.analysis.unavailable?{...c,...c.analysis,analysis:c.analysis}:c}
async function loadCases(){const organization=me?.organization_id,data=await api("/api/cases");if(me?.organization_id===organization)cases=Array.isArray(data)?data.map(caseForDisplay):[]}
async function loadUsers(){const organization=me?.organization_id,data=await api("/api/users");if(me?.organization_id===organization)users=Array.isArray(data)?data:[]}
async function loadSettings(){const organization=me?.organization_id,data=await api("/api/settings");if(me?.organization_id===organization)settings=data}
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
  let mailStatus=s.mail?.status||"not_configured",mailWorked=!!s.mail?.last_success;
  sysMail.textContent=mailStatus==="ready"?(mailWorked?"Actief":"Geconfigureerd"):mailStatus==="disabled"?"Uitgeschakeld":"Nog instellen";
  sysMail.className=mailStatus==="ready"?"good":mailStatus==="disabled"?"":"warn";
  sysMailLast.textContent=s.mail?.last_success?fmtDateTime(s.mail.last_success):(s.mail?.last_error?`Fout · ${fmtDateTime(s.mail.last_error.at)}`:"Nog geen succesvolle verzending");

  let e=s.monitoring?.last_error;
  if(e){
    sysLastError.textContent=`${fmtDateTime(e.at)} · ${e.scope}: ${e.message}`;
    sysLastError.className="warn";
  }else{
    sysLastError.textContent="Geen geregistreerde serverfout sinds de huidige runtime is gestart.";
    sysLastError.className="good";
  }
  await loadAnalysisStatus();
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
 if(!me?.is_platform_owner)return;ownerOrganizations=await api("/api/owner/organizations");ownOrganizations.textContent=ownerOrganizations.length;ownActive.textContent=ownerOrganizations.filter(org=>["active","pilot"].includes(org.status)).length;ownOnboarding.textContent=ownerOrganizations.filter(org=>org.status==="onboarding").length;ownCases.textContent=ownerOrganizations.reduce((sum,org)=>sum+Number(org.cases||0),0);ownerCurrentOrg.textContent=me.organization_name||"—";
 const statuses={active:"Actief",pilot:"Pilot",onboarding:"Startinstellingen",suspended:"Gepauzeerd"},plans={internal:"Werkstuur",pilot:"Pilot",starter:"Start",pro:"Pro"};ownerOrgList.innerHTML=ownerOrganizations.map(org=>{const active=Number(org.id)===Number(me.organization_id);return `<article class="cc-orgcard ${active?"current":""}"><div class="cc-orgname"><b>${escapeReport(org.name)}</b><small>${active?"Actieve werkomgeving":escapeReport(org.slug)}</small></div><div class="cc-orgstatus"><i class="${escAttr(org.status)}" aria-hidden="true"></i><span>${escapeReport(statuses[org.status]||org.status)} · ${escapeReport(plans[org.plan]||org.plan)}</span></div><div class="cc-orgmeta"><b>${Number(org.cases||0)} dossiers</b><small>${Number(org.active_users||0)} actieve gebruikers · ${org.active_pilot?"pilot actief":"geen actieve pilot"} · ${org.onboarding_complete?"ingericht":"inrichting open"}</small></div><div class="cc-orgactions"><button class="btn" type="button" onclick="switchOrganization(${Number(org.id)})" ${active?'disabled aria-current="page"':''}>${active?"Geopend":"Open omgeving"}</button>${org.plan!=="internal"?`<button class="btn" type="button" onclick="toggleOrganization(${Number(org.id)},'${org.status==="suspended"?"active":"suspended"}')">${org.status==="suspended"?"Activeer":"Pauzeer"}</button>`:""}</div></article>`}).join("")||emptyState("Nog geen organisaties","Voeg een organisatie toe zodra de klant- en teamgegevens bekend zijn.","building");
}

async function switchOrganization(id){
 if(typeof wsConfirmLeave==="function"&&!wsConfirmLeave())return;
 await api("/api/owner/context",{method:"POST",body:JSON.stringify({organization_id:Number(id)})});current=null;cases=[];users=[];settings=null;resetCustomerWorkspace();me=await api("/api/me");await Promise.all([loadCases(),loadUsers(),loadSettings()]);if(settings)applyBranding(settings);render();updateWorkspaceChrome();$("setupBanner")?.classList.add("hidden");show(Number(me.organization_id)===Number(me.base_organization_id)?"platform":"dashboard",false);toast("Omgeving geopend: "+(me.organization_name||"Werkstuur"),"good");
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
 if(!rows.length)return emptyState(cases.length?"Geen dossiers gevonden":"Nog geen servicedossiers",cases.length?"Pas je zoekopdracht of filters aan.":"Nieuwe meldingen verschijnen hier. Deel de klantintake of maak je eerste dossier aan.");
 return '<div class="row head"><div>Klant / dossier</div><div>Installatie</div><div>Status</div><div>Volledigheid</div><div></div></div>'+rows.map(c=>{const score=Math.max(0,Math.min(100,Number(c.score)||0));return `<button type="button" class="row case" onclick="openCase(${Number(c.id)})" aria-label="Open dossier ${escAttr(c.case_no)} van ${escAttr(c.customer)}"><span><b>${escapeReport(c.customer||"Nieuwe klant")}</b><br><span class="sub">${escapeReport(c.case_no)}${c.city?" · "+escapeReport(c.city):""}</span></span><span class="ws-type"><b>${escapeReport(c.type||"—")}</b><br><span class="sub">${escapeReport(c.asset||[c.manufacturer,c.model].filter(Boolean).join(" ")||"Nog te identificeren")}</span></span><span>${pill(c.status)}</span><span class="ws-score"><b>${score}%</b><span class="ws-scorebar" aria-hidden="true"><i style="width:${score}%"></i></span></span><span class="ws-action" aria-hidden="true">${wsIcon("arrow-right")}</span></button>`}).join("")
}

function renderCasesView(){
 if(!$("casesTable"))return;
 let rows=filteredCases();
 $("casesTable").innerHTML=table(rows);
 if($("caseResultsMeta"))$("caseResultsMeta").textContent=rows.length===cases.length?`${rows.length} dossiers`:`${rows.length} van ${cases.length} dossiers`;
}
function renderCaseTables(){renderCasesView()}
function renderPriorityList(){
 const el=$("attentionQueue");if(!el)return;const rows=priorityCases();el.innerHTML=rows.length?rows.map(c=>`<button type="button" class="cc-priorityitem ${c.status==="Review"?"review":""}" onclick="openCase(${Number(c.id)})"><i aria-hidden="true"></i><span><b>${escapeReport(c.customer||c.case_no)}</b><small>${escapeReport(c.case_no)} · ${escapeReport(c.status)}${(c.missing||[]).length?" · "+c.missing.length+" ontbrekend":""}</small></span><span class="cc-priorityscore">${Number(c.score)||0}%</span></button>`).join(""):'<div class="cc-priorityempty">'+(cases.length?"Geen dossiers die nu aandacht vragen.":"Je werkvoorraad verschijnt hier zodra er meldingen binnenkomen.")+'</div>';
}

function render(){
 if(!me)return;updateWorkspaceChrome();mCases.textContent=cases.length;mReview.textContent=cases.filter(c=>c.status!=="Afgerond"&&(c.status==="Review"||c.status==="Info ontbreekt"||Number(c.score||0)<80)).length;mScheduled.textContent=cases.filter(c=>c.status==="Ingepland").length;mReady.textContent=cases.length?Math.round(cases.reduce((sum,c)=>sum+(Number(c.score)||0),0)/cases.length)+"%":"—";
 dashTable.innerHTML=table(recentCases());renderCaseTables();renderPriorityList();renderWorkorders();if(me.role!=="technician"){renderTeam();if(settings)intakeLink.textContent=`${location.origin}/intake.html?token=${encodeURIComponent(settings.intake_token)}`}
}

function renderTeam(){teamList.innerHTML=users.length?'<div class="row head"><div>Naam</div><div>E-mail</div><div>Rol</div></div>'+users.map(user=>`<div class="row"><div class="ws-user"><span class="ws-user-avatar">${escapeReport(initials(user.display_name))}</span><b>${escapeReport(user.display_name)}</b></div><div>${escapeReport(user.email)}</div><div><span class="pill">${escapeReport(roleLabel(user.role))}</span></div></div>`).join(""):emptyState("Nog geen teamleden","De beheerder kan accounts toevoegen via accountbeheer.","users")}
function renderWorkorders(){
 let assigned=cases.filter(c=>me?.role!=="technician"||Number(c.assigned_to)===Number(me.id));if($("woOpen"))woOpen.textContent=assigned.filter(c=>c.status!=="Afgerond").length;if($("woPlanned"))woPlanned.textContent=assigned.filter(c=>c.status==="Ingepland").length;if($("woDone"))woDone.textContent=assigned.filter(c=>c.status==="Afgerond").length;
 const query=String($("workorderSearch")?.value||"").trim().toLowerCase(),rows=assigned.filter(c=>!query||caseHaystack(c).includes(query));workorders.innerHTML=rows.length?rows.sort((a,b)=>priorityRank(a)-priorityRank(b)).map(c=>`<article class="ws-work-card"><div class="ws-work-head"><span class="ws-caseid">${escapeReport(c.case_no)}</span>${pill(c.status)}</div><h3>${escapeReport(c.customer)}</h3><div class="ws-casefacts"><span>${wsIcon("pin")}${escapeReport(c.city||"Plaats niet opgegeven")}</span><span>${escapeReport(c.type||"Installatie")}</span></div><div class="ws-problem">${escapeReport(c.problem||"Geen klachtomschrijving beschikbaar.")}</div><div class="kv"><span>Merk / model</span><span>${escapeReport([c.manufacturer,c.model].filter(Boolean).join(" ")||c.asset||"Onbekend")}</span></div><div class="kv"><span>Werkadvies</span><span>${escapeReport(c.dispatch||"Bekijk de voorbereiding in het dossier.")}</span></div><button class="btn primary" type="button" onclick="openCase(${Number(c.id)})">Open werkdossier${wsIcon("arrow-right")}</button></article>`).join(""):emptyState(query?"Geen passende opdrachten":"Nog geen toegewezen opdrachten",query?"Pas je zoekopdracht aan.":"Zodra de planner een dossier aan jou toewijst, vind je het hier.","work");
}
function openNew(){if(!requireCaseWrite())return;if(typeof wsConfirmLeave==="function"&&!wsConfirmLeave())return;lastModalFocus=document.activeElement;newModal.classList.remove("hidden");document.body.classList.add("modal-open");linkFieldLabels();if(typeof wsResetScope==="function")wsResetScope("newModal");setTimeout(()=>nCustomer.focus(),30)}
function plannerBrands(){let opts=nType.value==="Laadpaal"?["Easee","Alfen","Wallbox","Zaptec","Anders/onbekend"]:nType.value==="Zonnepanelen"?["SolarEdge","GoodWe","Growatt","SMA","Enphase","Anders/onbekend"]:nType.value==="Thuisbatterij"?["SolarEdge","GoodWe","BYD","Huawei","Tesla","Anders/onbekend"]:["Anders/onbekend"];nManufacturer.innerHTML=opts.map(x=>`<option>${x}</option>`).join("")}
plannerBrands();
function analysisSummary(a){
 if(!a||a.unavailable)return emptyState("Analyse vraagt om aanvulling","Laat de planner de klachtomschrijving en het installatietype controleren.","alert");
 const warn=(a.warnings||[]).map(item=>`<div class="ws-analysis-warning">${wsIcon("alert")}<span>${escapeReport(item)}</span></div>`).join("");
 const questions=(a.followup_questions||[]).map(q=>`<li>${escapeReport(q)}</li>`).join("");
 const nextStep=typeof wsNextStep==="function"?wsNextStep(a):"Laat het advies beoordelen door de planner en monteur.";
 const evidence=(a.fault_evidence||[]).map(item=>`<li>${escapeReport(item)}</li>`).join("");
 return `<div class="ws-next-step ${a.triage_level==="veiligheidsreview"?"urgent":""}"><b>Aanbevolen vervolgstap</b>${escapeReport(nextStep)}</div><div class="ws-analysis-heading"><span>${wsIcon(a.triage_level==="veiligheidsreview"?"shield":"work")}<b>${escapeReport(a.fault_category)}</b></span><span class="pill">Zekerheid: ${escapeReport(a.fault_confidence)}</span></div><div class="ws-analysis-meta"><span>${escapeReport(a.dispatch)}</span><b>${Number(a.score)||0}% informatie compleet</b></div><div class="ws-analysis-confidence"><small>Volledigheid gaat over de ingevulde informatie. De zekerheid van het advies is een afzonderlijke beoordeling; laat het advies altijd controleren.</small></div>${evidence?`<details class="ws-analysis-evidence"><summary>Waarom dit advies?</summary><ul>${evidence}</ul></details>`:""}${a.triage_level==="veiligheidsreview"?'<div class="ws-analysis-warning urgent">'+wsIcon("shield")+'<span>Veiligheid heeft voorrang. Laat de verantwoordelijke serviceorganisatie de situatie beoordelen vóór gebruik of werkzaamheden.</span></div>':""}${warn}${questions?`<details class="ws-analysis-questions"><summary>${(a.followup_questions||[]).length} gerichte vervolgvragen</summary><ul>${questions}</ul></details>`:""}<p class="sub ws-analysis-notice">${escapeReport(a.notice||"")}</p>`;
}
function analysisInput(field,value){
 const id="analysisField-"+field.key,currentValue=String(value??""),required=field.required?' <small>nodig voor voorbereiding</small>':"";
 if(field.options?.length){const options=[...new Set(["",...field.options,...(currentValue&&!field.options.includes(currentValue)?[currentValue]:[])])];return `<div class="field"><label for="${id}">${escapeReport(field.label)}${required}</label><select id="${id}" data-analysis-key="${escAttr(field.key)}">${options.map(v=>`<option value="${escAttr(v)}"${v===currentValue?' selected':''}>${escapeReport(v||"Onbekend")}</option>`).join("")}</select></div>`}
 return `<div class="field"><label for="${id}">${escapeReport(field.label)}${required}</label><input id="${id}" data-analysis-key="${escAttr(field.key)}" maxlength="500" value="${escAttr(currentValue)}"${field.key==="soc"?' inputmode="decimal" placeholder="0–100%, of onbekend"':""}></div>`;
}
function renderCaseAnalysis(c){
 const a=c.analysis;
 if(!a)return "";
 const editable=caseWriteAllowed()&&["admin","planner"].includes(me?.role)&&!a.unavailable;
 const observations=a.observations||{},base=[{key:"manufacturer",label:"Merk / fabrikant"},{key:"model",label:"Model"},{key:"serial",label:"Serienummer"}];
 const editor=editable?`<details class="ws-analysis-editor"><summary>${wsIcon("intake")}Waarnemingen aanvullen</summary><div id="caseAnalysisForm"><div class="field"><label for="analysisProblem">Klachtomschrijving</label><textarea id="analysisProblem" maxlength="8000" rows="3">${escapeReport(c.problem||"")}</textarea></div><div class="grid2">${[...base,...(a.input_fields||[])].map(f=>analysisInput(f,observations[f.key])).join("")}</div><div class="cc-inline-actions"><button class="btn" type="button" onclick="previewCaseAnalysis()">Advies bekijken</button><button class="btn primary" type="button" onclick="saveCaseAnalysis()">Waarnemingen &amp; analyse opslaan</button></div><div class="ws-analysis-preview hidden" id="caseAnalysisPreview" aria-live="polite"></div></div></details>`:"";
 return `<div class="ws-analysis-panel"><div class="eyebrow">Slimme analyse</div><h3>Gericht advies voor dit dossier</h3>${analysisSummary(a)}${editor}<div class="ws-analysis-footnote">Kennisprofielen · geen automatische uitlezing van apparatuur of foto's</div></div>`;
}
function collectCaseAnalysis(){
 if(!current)throw new Error("Open eerst een servicedossier.");
 const extra={...(current.analysis?.observations||{})};document.querySelectorAll("#caseAnalysisForm [data-analysis-key]").forEach(el=>extra[el.dataset.analysisKey]=el.value.trim());
 return {type:current.type,problem:$("analysisProblem").value.trim(),extra};
}
async function previewCaseAnalysis(){
 if(!requireCaseWrite()||!["admin","planner"].includes(me?.role))return;
 const caseId=current.id,payload=collectCaseAnalysis(),a=await api("/api/analysis-preview",{method:"POST",body:JSON.stringify(payload)});
 if(current?.id!==caseId)return;
 $("caseAnalysisPreview").innerHTML='<div class="eyebrow">Voorbeeld · nog niet opgeslagen</div>'+analysisSummary(a);$("caseAnalysisPreview").classList.remove("hidden");
}
async function saveCaseAnalysis(){
 if(!requireCaseWrite()||!["admin","planner"].includes(me?.role))return;
 const caseId=current.id,organization=me.organization_id,payload=collectCaseAnalysis();payload.version=current.version;
 try{await api(`/api/cases/${caseId}/analysis`,{method:"POST",body:JSON.stringify(payload)});if(me?.organization_id!==organization)return;await loadCases();render();if(current?.id===caseId){await openCase(caseId,["analysis"]);selectCaseTab("prep")}toast("Waarnemingen bewaard en analyse bijgewerkt. Beoordeel het advies vóór uitvoering.","good")}
 catch(error){if(error.status===409){await loadCases();render();if(current?.id===caseId){await openCase(caseId);selectCaseTab("prep")}toast("Dit dossier is intussen gewijzigd. Je invoer is nog niet opgeslagen en blijft staan; beoordeel de nieuwste gegevens vóór je opnieuw opslaat.","warn")}else throw error}
}
async function loadAnalysisStatus(){
 const root=$("analysisHealthCard");if(!root)return;
 try{const s=await api("/api/analysis-status");$("analysisHealthState").textContent=s.healthy?"Analyse operationeel":"Analyse vraagt aandacht";$("analysisHealthState").className=s.healthy?"good":"warn";$("analysisHealthInfo").textContent=`${s.passed}/${s.total} storingsscenario’s geslaagd · versie ${s.version} · ${s.duration_ms} ms`;$("analysisHealthChecks").innerHTML=(s.checks||[]).map(c=>`<li>${wsIcon(c.passed?"check":"alert")}${escapeReport(c.name)}</li>`).join("")}
 catch(error){$("analysisHealthState").textContent="Analysecontrole niet beschikbaar";$("analysisHealthState").className="warn";$("analysisHealthInfo").textContent=error.message}
}
async function tryAnalysis(){
 const a=await api("/api/analysis-preview",{method:"POST",body:JSON.stringify({type:$("analysisTryType").value,problem:$("analysisTryProblem").value.trim(),extra:{manufacturer:$("analysisTryBrand").value.trim()}})});
 $("analysisTryResult").innerHTML=analysisSummary(a);$("analysisTryResult").classList.remove("hidden");
}
async function createCase(){if(!requireCaseWrite())return;const customer=nCustomer.value.trim(),problem=nProblem.value.trim();if(!customer||!problem){toast("Vul een klantnaam en een omschrijving van de melding in.","warn");(!customer?nCustomer:nProblem).focus();return}const data=await api("/api/cases",{method:"POST",body:JSON.stringify({customer,customer_id:$("nCustomerId").value?Number($("nCustomerId").value):null,email:$("nEmail").value.trim(),phone:$("nPhone").value.trim(),city:nCity.value.trim(),type:nType.value,asset:"Nog te identificeren",problem,extra:{manufacturer:nManufacturer.value,model:nModel.value.trim(),serial:nSerial.value.trim()}})});closeNew(true);[nCustomer,nCity,nProblem,nModel,nSerial,$("nCustomerId"),$("nEmail"),$("nPhone")].forEach(input=>input.value="");await loadCases();render();toast("Het dossier is aangemaakt.","good");await openCase(data.id,[],true)}
async function openCase(id,savedAreas=[],internal=false){
 const selected=cases.find(c=>Number(c.id)===Number(id));if(!selected)return;
 const sameCase=current?.id===selected.id,previousTab=document.querySelector("[data-case-tab].active")?.dataset.caseTab;
 if(!internal&&!sameCase&&typeof wsConfirmLeave==="function"&&!wsConfirmLeave())return;
 const drafts=sameCase&&typeof wsCaseDrafts==="function"?wsCaseDrafts(savedAreas):[];current=selected;
 if($("caseBack"))caseBack.innerHTML=wsIcon("arrow-left")+(me.role==="technician"?"Terug naar opdrachten":"Terug naar dossiers");
 const c=current,score=Math.max(0,Math.min(100,Number(c.score)||0));
 caseHero.innerHTML=`<div><div class="ws-caseid">${escapeReport(c.case_no)}</div><h2>${escapeReport(c.customer||"Nieuwe klant")}</h2><div class="ws-casefacts"><span>${escapeReport(c.type||"Installatie")}</span><span>${escapeReport(c.city||"Plaats niet opgegeven")}</span><span>${pill(c.status)}</span></div></div><div class="ws-scoreorb" style="--score:${score}%" aria-label="Volledigheid van dossier: ${score} procent"><b>${score}%</b><small>VOLLEDIGHEID</small></div>`;
 const kv=(label,value)=>`<div class="kv"><span>${escapeReport(label)}</span><span>${escapeReport(value||"Niet opgegeven")}</span></div>`;
 caseMain.innerHTML='<div class="eyebrow">Klantmelding</div><h3>Melding & installatie</h3><div class="ws-problem">'+escapeReport(c.problem||"Nog geen omschrijving van de klacht.")+'</div><div class="ws-kv-grid">'+kv("Klant",c.customer)+kv("Plaats",c.city)+kv("Installatie",c.type)+kv("Asset",c.asset)+kv("Merk",c.manufacturer)+kv("Model",c.model)+kv("Serienummer",c.serial_no)+kv("Dossierversie",String(c.version||1))+'</div><div class="field"><label for="caseStatus">Status van het dossier</label><select id="caseStatus">'+["Info ontbreekt","Review","Ingepland","Afgerond"].map(status=>'<option'+(c.status===status?' selected':'')+'>'+status+'</option>').join("")+'</select></div><div class="ws-case-note">'+wsIcon("shield")+'De planner en vakbekwame monteur houden de regie over beoordeling, veiligheid en uitvoering.</div>';
 const checks=(title,items,name="check",style="")=>items?.length?`<div class="eyebrow section">${escapeReport(title)}</div>`+items.map(item=>`<div class="check ${style}">${wsIcon(name)}<span>${escapeReport(item)}</span></div>`).join(""):"";
 prep.innerHTML=renderCaseAnalysis(c)+checks("Nog aan te vullen",c.missing,"alert","warn")+checks("Kritisch vóór vertrek",c.ftf_critical,"shield")+checks("Aandachtspunten",c.ftf_gaps,"alert","warn")+checks("Onderdelen & middelen",c.ftf_parts,"wrench")+checks("Monteurbriefing",c.prep,"check");if(!prep.innerHTML)prep.innerHTML=emptyState("Nog geen voorbereiding vastgelegd","Beoordeel de melding en leg relevante aandachtspunten voor de monteur vast.","work");
 const sourceLink=c.knowledge_url?`<a href="${safeHref(c.knowledge_url)}" target="_blank" rel="noopener noreferrer">${escapeReport(c.knowledge_title||"Documentatie")}</a>`:escapeReport(c.knowledge_title||"Generiek"),routeLink=c.route_source_url?`<a href="${safeHref(c.route_source_url)}" target="_blank" rel="noopener noreferrer">${escapeReport(c.route_source_title||"Routebron")}</a>`:"—";
 caseSide.innerHTML=`<div class="eyebrow">Voorbereiding</div><h3>Beoordeling & vervolgstap</h3><div class="ws-side-score"><div><small>Volledigheid van de intake</small><br><b>${score}%</b></div><span class="ws-scorebar" aria-hidden="true"><i style="width:${score}%"></i></span></div>${kv("Werkadvies",c.dispatch||"Nog te beoordelen")}${kv("Storingsroute",c.fault_category)}${kv("Service-route",c.service_route)}${kv("Expertise",c.required_competence||"Technische review")}${kv("Locatie nodig",c.site_trigger)}${kv("Escalatie",c.escalation_path)}<details class="cc-techdetails section"><summary>Bronnen & technische context</summary>${kv("Bron melding",c.source)}<div class="kv"><span>Technische bron</span><span>${sourceLink}</span></div>${kv("Integratiedoelen",(c.api_targets||[]).join(", "))}${kv("Zekerheid",c.fault_confidence)}${kv("Triageniveau",c.triage_level)}${kv("Onderbouwing",(c.fault_evidence||[]).join(" · "))}<div class="kv"><span>Routebron</span><span>${routeLink}</span></div></details>`;
 assignedTo.innerHTML='<option value="">Nog niet toegewezen</option>'+users.filter(user=>user.role==="technician").map(user=>`<option value="${Number(user.id)}" ${Number(c.assigned_to)===Number(user.id)?"selected":""}>${escapeReport(user.display_name)}</option>`).join("");
 noteText.value="";if(!drafts.some(d=>d.id==="fileInput"))fileInput.value="";notes.innerHTML=attachments.innerHTML='<div class="ws-skeleton"></div><div class="ws-skeleton"></div>';selectCaseTab(sameCase&&previousTab?previousTab:"dossier");renderOutcome();updateCasePermissions();
 if(typeof wsResetScope==="function"){wsResetScope("caseView");wsRestoreCaseDrafts(drafts)}show("case",false,true);
 await Promise.all([loadNotes(c.id).catch(error=>{if(current?.id===c.id)notes.innerHTML=emptyState("Notities konden niet worden geladen","Open het dossier opnieuw om het nogmaals te proberen.","message");toast(error.message,"warn")}),loadAttachments(c.id).catch(error=>{if(current?.id===c.id)attachments.innerHTML=emptyState("Bijlagen konden niet worden geladen","Open het dossier opnieuw om het nogmaals te proberen.","file");toast(error.message,"warn")})]);if(current?.id===c.id)updateCasePermissions();
}

async function saveCase(){if(!requireCaseWrite())return;try{const updated=await api(`/api/cases/${current.id}`,{method:"PATCH",body:JSON.stringify({version:current.version,status:caseStatus.value})});await loadCases();render();await openCase(updated.id,["status"]);toast("De status is opgeslagen. Andere invoer bewaar je met de knop bij dat onderdeel.","good")}catch(error){if(error.status===409){const id=current.id;await loadCases();render();await openCase(id);toast("Dit dossier is intussen gewijzigd. Je niet opgeslagen invoer blijft staan; controleer de nieuwste gegevens vóór je opnieuw opslaat.","warn")}else throw error}}
async function assignCase(){if(!requireCaseWrite())return;try{const updated=await api(`/api/cases/${current.id}`,{method:"PATCH",body:JSON.stringify({version:current.version,assigned_to:assignedTo.value?Number(assignedTo.value):null})});await loadCases();render();await openCase(updated.id,["assignment"]);toast("De toewijzing is opgeslagen.","good")}catch(error){if(error.status===409){const id=current.id;await loadCases();render();await openCase(id);toast("Dit dossier is intussen gewijzigd. Je niet opgeslagen invoer blijft staan; controleer de nieuwste toewijzing.","warn")}else throw error}}
async function loadNotes(caseId=current?.id){if(!caseId)return;const rows=await api(`/api/cases/${caseId}/notes`);if(current?.id!==caseId)return;notes.innerHTML=rows.length?rows.map(note=>`<div class="note"><b>${escapeReport(note.display_name)}</b><div>${escapeReport(note.body)}</div><small>${escapeReport(fmtDateTime(note.created_at))}</small></div>`).join(""):emptyState("Nog geen notities","Gebruik dit onderdeel voor relevante context en overdracht binnen je team.","message")}
async function addNote(){if(!requireCaseWrite())return;let body=noteText.value.trim();if(!body)return;await api(`/api/cases/${current.id}/notes`,{method:"POST",body:JSON.stringify({body})});noteText.value="";await loadNotes();if(typeof wsCommitArea==="function")wsCommitArea("caseView","note");toast("Notitie toegevoegd.","good")}
async function loadAttachments(caseId=current?.id){if(!caseId)return;const rows=await api(`/api/cases/${caseId}/attachments`);if(current?.id!==caseId)return;attachmentFiles=rows;attachments.innerHTML=rows.length?rows.map(file=>`<div class="attachment"><span class="ws-file-icon">${wsIcon("file")}</span><div class="ws-file-info"><b>${escapeReport(file.filename)}</b><small>${Math.max(1,Math.round(Number(file.size_bytes||0)/1024))} KB · private bijlage</small></div><a class="btn" href="/api/attachments/${Number(file.id)}" download="${escAttr(file.filename)}" aria-label="Download ${escAttr(file.filename)}">${wsIcon("download")}Download</a></div>`).join(""):emptyState("Nog geen bijlagen","Foto's, typeplaatjes en documenten blijven bij hetzelfde dossier.","file")}
async function uploadFile(){if(!requireCaseWrite())return;const file=fileInput.files[0];if(!file){toast("Selecteer eerst een afbeelding of PDF.","warn");return}if(file.size>5*1024*1024){toast("Het bestand is groter dan 5 MB. Kies een kleiner bestand.","warn");return}const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(",")[1]);reader.onerror=()=>reject(new Error("Het bestand kon niet worden gelezen."));reader.readAsDataURL(file)});await api(`/api/cases/${current.id}/attachments`,{method:"POST",body:JSON.stringify({filename:file.name,content_type:file.type||"application/octet-stream",data_base64:data})});fileInput.value="";await loadAttachments();if(typeof wsCommitArea==="function")wsCommitArea("caseView","file");toast("De bijlage is toegevoegd.","good")}
function downloadAttachment(id){const file=attachmentFiles.find(item=>Number(item.id)===Number(id));if(!file)return;const link=document.createElement("a");link.href=`/api/attachments/${Number(id)}`;link.download=file.filename||"bestand";document.body.appendChild(link);link.click();link.remove()}

function renderOutcome(){
 const recorded=!!current.outcome_recorded_at;
 outcomeCurrent.innerHTML=recorded?`<b>Uitkomst geregistreerd.</b><br>${current.outcome_resolved_first_visit?"First-time-fix · ":""}${current.outcome_remote_resolved?"Op afstand opgelost · ":""}${current.outcome_second_visit_required?"Tweede bezoek nodig · ":""}${current.outcome_preventable?"waarschijnlijk voorkombaar":""}`:`Nog geen uitkomst geregistreerd. Vul dit na afronding van de servicedossier in.`;
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
async function saveOutcome(){if(!requireCaseWrite())return;
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
 await loadCases();render();renderOutcome();if(typeof wsCommitArea==="function")wsCommitArea("caseView","outcome");toast("De uitkomst is opgeslagen.","good");
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
 eBreakEven.textContent=e.projection.break_even===null?"Nog onvoldoende uitkomsten":(e.projection.break_even?"Ja":"Nee");
 fillEconomicInputs(e.assumptions);
}
async function loadPilotHub(){
 try{
  let [m,p]=await Promise.all([api("/api/metrics"),api("/api/pilot")]);
  if($("phFTF"))phFTF.textContent=m.outcomes?(m.first_time_fix_pct??0)+"%":"—";
  if($("phSecond"))phSecond.textContent=m.outcomes?(m.second_visit_pct??0)+"%":"—";
  if($("phRemote"))phRemote.textContent=m.outcomes?(m.remote_resolved_pct??0)+"%":"—";
  if($("phNet"))phNet.textContent=m.outcomes?euro(m.economics?.projection?.projected_net_value_eur||0):"—";
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
async function loadMetrics(){const m=await api("/api/metrics");lastMetrics=m;kTotal.textContent=m.total;kPublic.textContent=m.customer_intakes;kIntake.textContent=m.total?Math.round(m.avg_intake_seconds)+"s":"—";kComplete.textContent=m.total?m.complete_pct+"%":"—";kScheduled.textContent=m.total?m.scheduled_pct+"%":"—";kFTF.textContent=m.outcomes?m.first_time_fix_pct+"%":"—";kSecond.textContent=m.outcomes?m.second_visit_pct+"%":"—";kPreventable.textContent=m.outcomes?m.preventable_second_visit_pct+"%":"—";kRemote.textContent=m.outcomes?m.remote_resolved_pct+"%":"—";kOutcomes.textContent=m.outcomes;renderEconomics(m.economics);linkFieldLabels()}
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
 <div class="card ws-report-header">
   ${wsIcon("chart")}<div class="eyebrow">Pilotmanagement · ${escapeReport(r.company_name)}</div>
   <h2 style="font-size:24px;margin:5px 0">${escapeReport(d.label)}</h2>
   <div class="sub">${escapeReport(d.reason)}</div>
   <div class="section"><span class="pill ${decisionClass}">${q.outcomes} uitkomsten · minimum ${q.minimum_for_signal}</span></div>
 </div>
 <div class="grid4 section">
   <div class="card metric"><small>First-time-fix</small><b>${q.outcomes?pct(op.first_time_fix_pct):"—"}</b></div>
   <div class="card metric"><small>Tweede bezoek</small><b>${q.outcomes?pct(op.second_visit_pct):"—"}</b></div>
   <div class="card metric"><small>Voorkombaar van tweede ritten</small><b>${q.outcomes?pct(op.preventable_second_visit_pct):"—"}</b></div>
   <div class="card metric"><small>Remote opgelost</small><b>${q.outcomes?pct(op.remote_resolved_pct):"—"}</b></div>
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
     <div class="kv"><span>Verwachte bruto waarde</span><b>${euro(e.projection.projected_gross_value_eur)}</b></div>
     <div class="kv"><span>Softwarekosten in berekening</span><b>${euro(e.projection.software_monthly_cost_eur)}</b></div>
     <div class="kv"><span>Verwachte netto waarde</span><b>${euro(e.projection.projected_net_value_eur)}</b></div>
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
     ${reportList(r.top_causes.fault_categories,"Nog onvoldoende uitkomsten voor rangschikking.")}
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
 obCreatePilot.checked=false;toggleOnboardingPilot();
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
 $("obNext").textContent=obStep===5?"Startinstellingen opslaan":"Volgende →";
 if(obStep===2)renderBrandChoices();
}
function toggleOnboardingPilot(){obPilotFields.classList.toggle("hidden",!obCreatePilot.checked)}
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
     create:obCreatePilot.checked,name:obPilotName.value,start_date:obStart.value,end_date:obEnd.value,
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
   $("setupBanner")?.classList.toggle("hidden",!!r.onboarding.complete);
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

function applyBranding(data){if(!data)return;const accent=/^#[0-9a-f]{6}$/i.test(data.brand_accent||"")?data.brand_accent:"#62d0ff";document.documentElement.style.setProperty("--accent",accent);const hex=accent.slice(1),rgb=[0,2,4].map(i=>parseInt(hex.slice(i,i+2),16)/255),l=rgb.map(v=>v<=.04045?v/12.92:Math.pow((v+.055)/1.055,2.4)),lum=.2126*l[0]+.7152*l[1]+.0722*l[2];document.documentElement.style.setProperty("--accent-ink",lum>.32?"#071522":"#fff");document.title=(data.brand_name||"Werkstuur")+" · Serviceomgeving";const brand=document.querySelector(".cc-brandcopy strong");if(brand)brand.textContent=data.brand_name||"Werkstuur"}
async function loadProductManagement(){let v=await api('/api/version');versionBadge.textContent=`${v.name} ${v.version}`;let s=await api('/api/settings');settings=s;applyBranding(s);pbBrandName.value=s.brand_name||'Werkstuur';pbAccent.value=s.brand_accent||'#62d0ff';pbSupportEmail.value=s.support_email||'';pbPrivacyUrl.value=s.privacy_url||'';pbPortalTitle.value=s.customer_portal_title||'Service-intake';accountAdminCard.style.display=me.role==='admin'?'':'none';if(me.role==='admin')await loadAccounts()}
async function saveBranding(){let s=await api('/api/settings',{method:'PATCH',body:JSON.stringify({brand_name:pbBrandName.value.trim()||'Werkstuur',brand_accent:pbAccent.value.trim(),support_email:pbSupportEmail.value.trim(),privacy_url:pbPrivacyUrl.value.trim(),customer_portal_title:pbPortalTitle.value.trim()||'Service-intake'})});settings={...(settings||{}),...s};applyBranding(settings);toast('Branding opgeslagen.','good')}
async function changeOwnPassword(){if(!pwCurrent.value||!pwNew.value)return alert('Vul huidig en nieuw wachtwoord in.');await api('/api/change-password',{method:'POST',body:JSON.stringify({current_password:pwCurrent.value,new_password:pwNew.value})});pwCurrent.value='';pwNew.value='';alert('Wachtwoord gewijzigd. Log opnieuw in om verder te gaan.');location.reload()}
async function loadAccounts(){let rows=await api('/api/accounts');accountList.innerHTML=`<div class="row head"><div>Naam</div><div>E-mail</div><div>Rol</div><div>Status</div><div>Actie</div></div>`+rows.map(u=>`<div class="row"><div>${escapeReport(u.display_name)}</div><div>${escapeReport(u.email)}</div><div>${escapeReport(roleLabel(u.role))}</div><div>${u.active?'Actief':'Uit'}</div><div>${u.id===me.id?'Eigen account':`<button class="btn" onclick="toggleAccount(${u.id},${u.active?0:1})">${u.active?'Deactiveer':'Activeer'}</button> <button class="btn" onclick="sendResetLink(${u.id})">Resetlink</button> <button class="btn" onclick="adminResetPassword(${u.id})">Tijdelijk ww</button>`}</div></div>`).join('')}
async function createAccount(){let r=await api('/api/accounts',{method:'POST',body:JSON.stringify({display_name:accName.value.trim(),email:accEmail.value.trim(),role:accRole.value,password:accPassword.value})});accName.value='';accEmail.value='';accPassword.value='';await loadAccounts();toast(r.created?'Account aangemaakt.':'Account bestond al.',r.created?'good':'')}
async function toggleAccount(id,active){await api(`/api/accounts/${id}`,{method:'PATCH',body:JSON.stringify({active:!!active})});await loadAccounts()}
async function sendResetLink(id){try{await api(`/api/accounts/${id}/send-reset-link`,{method:'POST',body:'{}'});toast('Herstel-link verstuurd.','good')}catch(e){toast(e.message||'Herstel-link kon niet worden verstuurd.','warn')}}
async function sendTestEmail(){try{await api('/api/test-email',{method:'POST',body:'{}'});toast('Testmail verstuurd naar je account.','good');await loadSystemStatus(true)}catch(e){toast(e.message||'Testmail mislukt.','warn');await loadSystemStatus(true)}}
async function adminResetPassword(id){let pwd=prompt('Nieuw tijdelijk wachtwoord (min. 12 tekens):');if(!pwd)return;await api(`/api/accounts/${id}/reset-password`,{method:'POST',body:JSON.stringify({new_password:pwd})});toast('Wachtwoord gereset.','good')}
async function downloadOperationalExport(){let d=await api('/api/export');let blob=new Blob([JSON.stringify(d,null,2)],{type:'application/json'});let url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`werkstuur-export-${new Date().toISOString().slice(0,10)}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
async function resetPilotData(){if(resetConfirm.value!=='RESET PILOT DATA')return alert('Bevestigingstekst is niet exact correct.');let summary=await api('/api/pilot-reset-summary');if(!confirm(`Dit verwijdert ${summary.cases} cases, ${summary.notes} notities, ${summary.attachments} bijlagen en ${summary.pilots} pilot(s). Doorgaan?`))return;await api('/api/pilot-reset',{method:'POST',body:JSON.stringify({confirm:'RESET PILOT DATA'})});alert('Pilotdata verwijderd.');resetConfirm.value='';await loadCases();render();let ob=await api('/api/onboarding-status');initOnboarding(ob);show('onboarding')}

async function loadAudit(){if(me.role==="technician")return;let a=await api("/api/audit");auditList.innerHTML=a.map(x=>`<div class="row"><div>${escapeReport(new Date(x.created_at).toLocaleString("nl-NL"))}</div><div>${escapeReport(x.display_name||"Klant")}</div><div>${escapeReport(x.action)}</div><div>${escapeReport(x.detail||"")}</div><div></div></div>`).join("")}
async function copyIntakeLink(){try{if(!navigator.clipboard?.writeText)throw new Error();await navigator.clipboard.writeText(intakeLink.textContent);toast("De intakelink is gekopieerd.","good")}catch{toast("Kopiëren is niet beschikbaar. Selecteer en kopieer de link zelf.","warn")}}

loginNow=((original)=>function(...args){return runWorkspaceAction("loginNow",original,args)})(loginNow);
createCase=((original)=>function(...args){return runWorkspaceAction("createCase",original,args)})(createCase);
saveCase=((original)=>function(...args){return runWorkspaceAction("saveCase",original,args)})(saveCase);
assignCase=((original)=>function(...args){return runWorkspaceAction("assignCase",original,args)})(assignCase);
addNote=((original)=>function(...args){return runWorkspaceAction("addNote",original,args)})(addNote);
uploadFile=((original)=>function(...args){return runWorkspaceAction("uploadFile",original,args)})(uploadFile);
saveOutcome=((original)=>function(...args){return runWorkspaceAction("saveOutcome",original,args)})(saveOutcome);
refreshWorkorders=((original)=>function(...args){return runWorkspaceAction("refreshWorkorders",original,args)})(refreshWorkorders);
createOrganization=((original)=>function(...args){return runWorkspaceAction("createOrganization",original,args)})(createOrganization);
switchOrganization=((original)=>function(...args){return runWorkspaceAction("switchOrganization",original,args)})(switchOrganization);
toggleOrganization=((original)=>function(...args){return runWorkspaceAction("toggleOrganization",original,args)})(toggleOrganization);
copyIntakeLink=((original)=>function(...args){return runWorkspaceAction("copyIntakeLink",original,args)})(copyIntakeLink);
saveEconomicAssumptions=((original)=>function(...args){return runWorkspaceAction("saveEconomicAssumptions",original,args)})(saveEconomicAssumptions);
saveBranding=((original)=>function(...args){return runWorkspaceAction("saveBranding",original,args)})(saveBranding);
createAccount=((original)=>function(...args){return runWorkspaceAction("createAccount",original,args)})(createAccount);
toggleAccount=((original)=>function(...args){return runWorkspaceAction("toggleAccount",original,args)})(toggleAccount);
sendResetLink=((original)=>function(...args){return runWorkspaceAction("sendResetLink",original,args)})(sendResetLink);
sendTestEmail=((original)=>function(...args){return runWorkspaceAction("sendTestEmail",original,args)})(sendTestEmail);
downloadOperationalExport=((original)=>function(...args){return runWorkspaceAction("downloadOperationalExport",original,args)})(downloadOperationalExport);
takePilotSnapshot=((original)=>function(...args){return runWorkspaceAction("takePilotSnapshot",original,args)})(takePilotSnapshot);
startPilot=((original)=>function(...args){return runWorkspaceAction("startPilot",original,args)})(startPilot);
closePilot=((original)=>function(...args){return runWorkspaceAction("closePilot",original,args)})(closePilot);
finishOnboarding=((original)=>function(...args){return runWorkspaceAction("finishOnboarding",original,args)})(finishOnboarding);
requestPasswordReset=((original)=>function(...args){return runWorkspaceAction("requestPasswordReset",original,args)})(requestPasswordReset);
completePasswordReset=((original)=>function(...args){return runWorkspaceAction("completePasswordReset",original,args)})(completePasswordReset);
previewCaseAnalysis=((original)=>function(...args){return runWorkspaceAction("previewCaseAnalysis",original,args)})(previewCaseAnalysis);
saveCaseAnalysis=((original)=>function(...args){return runWorkspaceAction("saveCaseAnalysis",original,args)})(saveCaseAnalysis);
tryAnalysis=((original)=>function(...args){return runWorkspaceAction("tryAnalysis",original,args)})(tryAnalysis);

let fieldsQueued=false;new MutationObserver(()=>{if(!fieldsQueued){fieldsQueued=true;queueMicrotask(()=>{fieldsQueued=false;linkFieldLabels()})}}).observe(document.body,{childList:true,subtree:true});linkFieldLabels();
window.matchMedia("(min-width: 761px)").addEventListener("change",()=>closeNavigation());

if(passwordResetToken){setAuthPanel("resetPanel");login.classList.remove("hidden");app.classList.add("hidden")}else{boot()}
