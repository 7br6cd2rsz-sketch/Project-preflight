"use strict";
// Drafts stay in memory only: no customer information or credentials in browser storage.
const wsEditBaselines=new Map();
const wsProtectedScopes=["caseView","newModal"];
function wsControlState(control){
 if(control.type==="file")return [...(control.files||[])].map(file=>[file.name,file.size,file.lastModified]);
 if(["checkbox","radio"].includes(control.type))return !!control.checked;
 return control.value;
}
function wsScopeControls(id){return [...($(id)?.querySelectorAll("input,select,textarea")||[])].filter(control=>control.id&&control.type!=="password"&&control.type!=="hidden")}
function wsResetScope(id){wsEditBaselines.set(id,new Map(wsScopeControls(id).map(control=>[control.id,JSON.stringify(wsControlState(control))])));wsUpdateDraftState()}
function wsAreaFor(id){return id.startsWith("analysis")?"analysis":id==="caseStatus"?"status":id==="assignedTo"?"assignment":id==="noteText"?"note":id==="fileInput"?"file":"outcome"}
function wsCommitArea(id,area){const baseline=wsEditBaselines.get(id);if(!baseline)return;for(const control of wsScopeControls(id))if(wsAreaFor(control.id)===area)baseline.set(control.id,JSON.stringify(wsControlState(control)));wsUpdateDraftState()}
function wsScopeDirty(id){const baseline=wsEditBaselines.get(id);return !!baseline&&wsScopeControls(id).some(control=>baseline.has(control.id)&&baseline.get(control.id)!==JSON.stringify(wsControlState(control)))}
function wsDiscardScope(id){const baseline=wsEditBaselines.get(id);if(!baseline)return;for(const control of wsScopeControls(id)){if(!baseline.has(control.id))continue;const value=JSON.parse(baseline.get(control.id));if(control.type==="file")control.value="";else if(["checkbox","radio"].includes(control.type))control.checked=value;else control.value=value;if(id==="newModal"&&control.id==="nType")plannerBrands()}wsUpdateDraftState()}
function wsVisibleDirtyScopes(){return wsProtectedScopes.filter(id=>{const root=$(id);return root&&!root.classList.contains("hidden")&&wsScopeDirty(id)})}
function wsConfirmLeave(){
 const writes=["createCase","saveCase","assignCase","saveCaseAnalysis","addNote","uploadFile","saveOutcome","saveCustomer","archiveCustomer","createTeamMember","saveTeamMember","toggleTeamMember","submitSupport","updateSupport"];
 if(typeof runWorkspaceAction==="function"&&writes.some(name=>runWorkspaceAction.pending.has(name))){toast("Wacht even tot het opslaan is bevestigd.","warn");return false}
 const dirty=wsVisibleDirtyScopes();if(!dirty.length)return true;
 if(!confirm("Je hebt invoer die nog niet is opgeslagen. Wil je deze invoer verlaten?"))return false;
 dirty.forEach(wsDiscardScope);return true;
}
function wsLockAction(name){
 const selectors={createCase:"#newModal input,#newModal select,#newModal textarea",saveCase:"#caseStatus",assignCase:"#assignedTo",saveCaseAnalysis:"#caseAnalysisForm input,#caseAnalysisForm select,#caseAnalysisForm textarea",addNote:"#noteText",uploadFile:"#fileInput",saveOutcome:"#casePane-outcome input,#casePane-outcome select,#casePane-outcome textarea"};
 const controls=selectors[name]?[...document.querySelectorAll(selectors[name])]:[],previous=controls.map(control=>control.disabled);
 controls.forEach(control=>control.disabled=true);
 return ()=>controls.forEach((control,index)=>{if(control.isConnected)control.disabled=control.closest("#caseView")&&!caseWriteAllowed()?true:previous[index]});
}
function wsCaseDrafts(savedAreas=[]){
 const baseline=wsEditBaselines.get("caseView"),result=[];if(!baseline)return result;
 for(const control of wsScopeControls("caseView"))if(!savedAreas.includes(wsAreaFor(control.id))&&baseline.has(control.id)&&baseline.get(control.id)!==JSON.stringify(wsControlState(control)))result.push({id:control.id,type:control.type,value:wsControlState(control)});
 return result;
}
function wsRestoreCaseDrafts(drafts){
 for(const draft of drafts){const control=$(draft.id);if(!control)continue;if(draft.type==="file"){wsEditBaselines.get("caseView")?.set(draft.id,"[]");continue}
  if(["checkbox","radio"].includes(draft.type))control.checked=draft.value;else control.value=draft.value;
  if(draft.id.startsWith("analysis"))control.closest("details")?.setAttribute("open","");
 }
 wsUpdateDraftState();
}
function wsUpdateDraftState(){
 const indicator=$("wsDraftState"),dirty=wsVisibleDirtyScopes().length>0;
 if(indicator){indicator.textContent=dirty?"Nog niet opgeslagen":"Alles opgeslagen";indicator.classList.toggle("pending",dirty)}
}
function wsFieldError(id,message,messageId){
 const control=$(id);if(control){control.setAttribute("aria-invalid",String(!!message));if(messageId)control.setAttribute("aria-describedby",messageId);if(message)control.focus()}
 if(messageId&&$(messageId))$(messageId).textContent=message;
}
function wsNextStep(a){
 if(a?.triage_level==="veiligheidsreview")return "Laat eerst de veiligheid beoordelen. Gebruik de installatie niet bij een actieve veiligheidsmelding.";
 if(a?.warnings?.length||a?.fault_confidence==="laag")return "Laat de planner of vakbekwame monteur deze melding technisch beoordelen.";
 if(a?.missing?.length)return "Vul eerst de ontbrekende informatie aan of vraag deze bij de klant op.";
 if(a?.remote_checks?.length)return "Beoordeel de genoemde controles op afstand voordat je een locatiebezoek plant.";
 return "Laat de planner en monteur de voorbereiding controleren en de passende vervolgstap bepalen.";
}
document.addEventListener("input",event=>{if(event.target?.hasAttribute?.("aria-invalid"))event.target.removeAttribute("aria-invalid");wsUpdateDraftState()});
document.addEventListener("change",()=>wsUpdateDraftState());
window.addEventListener("beforeunload",event=>{if(wsVisibleDirtyScopes().length){event.preventDefault();event.returnValue=""}});
document.addEventListener("keydown",event=>{
 if(event.key!=="Enter"||event.isComposing||event.target?.tagName!=="INPUT")return;
 if(event.target.closest("#loginPanel")){event.preventDefault();loginNow()}
 else if(event.target.closest("#forgotPanel")){event.preventDefault();requestPasswordReset()}
 else if(event.target.closest("#resetPanel")){event.preventDefault();completePasswordReset()}
});
window.addEventListener("offline",()=>markConnection("offline"));
window.addEventListener("online",()=>{markConnection("online");if(me)toast("Je verbinding is terug. Controleer je overzicht voordat je een onbevestigde actie opnieuw uitvoert.","good")});
wsProtectedScopes.forEach(wsResetScope);
setTimeout(()=>{const splash=$("sessionSplash");if(splash&&!splash.classList.contains("hidden")){const message=splash.querySelector("span");if(message)message.textContent="Het opstarten duurt wat langer. Je werkomgeving wordt geladen…"}},8000);
