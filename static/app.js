'use strict';
const fmt = new Intl.NumberFormat('en-IN');
const rupees = paise => '₹' + fmt.format((paise/100).toFixed(0));
const esc = v => String(v ?? '').replace(/[&<>"']/g, s=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]));
const $ = id => document.getElementById(id);
const headings = {
 overview:['Command center','Payment risk, member friction, and review performance.','OVERVIEW'],
 support:['Member intake','Capture the member statement and link it to the correct payment.','SUPPORT'],
 cases:['Case operations','Review payment evidence and record an analyst disposition.','OPERATIONS'],
 analysis:['Investigations','Compare complaints, exposure, posting delays and mature cohorts.','ANALYTICS'],
 rules:['Detection strategy','Compare protection coverage and operational review cost.','STRATEGY']
};
function message(text=''){ $('message').textContent=text; }
async function api(url,options){
  let response;
  try { response=await fetch(url,options); }
  catch { throw Error('Cannot reach the local API. Check that FastAPI is running.'); }
  let json;
  try { json=await response.json(); }
  catch { throw Error(`Unexpected response from server (HTTP ${response.status}).`); }
  if(!response.ok)throw Error(typeof json.detail==='string'?json.detail:JSON.stringify(json.detail));
  return json;
}
let demoReadOnly=false;
async function loadMode(){
  try {
    const m=await api('/api/meta');
    demoReadOnly=Boolean(m.read_only);
    document.querySelectorAll('[data-write-action]').forEach(el=>{el.disabled=demoReadOnly;el.title=demoReadOnly?'Public preview is read-only':'';});
    if(demoReadOnly){$('complaintResult').textContent='Public preview: new case creation and analyst decisions are disabled. Run locally to try the write workflow.';}
  }catch(e){message(e.message);}
}
function tab(name){document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('active',p.id===name));document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b.dataset.tab===name));$('heading').textContent=headings[name][0];$('subheading').textContent=headings[name][1];$('sectionLabel').textContent=headings[name][2];$('breadcrumb').textContent=headings[name][0];message('');if(name==='cases')loadCases();if(name==='analysis')loadAnalysis();if(name==='rules')loadRules();}
document.querySelectorAll('nav button').forEach(b=>b.addEventListener('click',()=>tab(b.dataset.tab)));
function stat(label,value,note){return `<div class="stat"><span>${label}</span><strong>${value}</strong><small>${note}</small></div>`;}
async function loadOverview(){try{const d=await api('/api/overview');$('kpis').innerHTML=stat('PAYMENTS',fmt.format(d.counts.payments),'Synthetic three-month cohort')+stat('SUPPORT CONTACTS',fmt.format(d.counts.contacts),'Includes repeat contacts')+stat('UNIQUE DISPUTED',fmt.format(d.counts.disputed_payments),'Distinct payment IDs')+stat('CONFIRMED FRAUD',fmt.format(d.counts.confirmed_fraud),'Synthetic follow-up outcomes');if(d.example)$('memberId').value=d.example.member_id;loadOverviewTrend();}catch(e){message(e.message);}}
async function loadOverviewTrend(){
  try {
    const d=await api('/api/investigation');
    const rows=d.monthly || [];
    if(!rows.length){$('overviewTrend').textContent='No monthly trends available';return;}
    const peak=Math.max(1,...rows.map(r=>Number(r.contacts_per_1k_successes)||0));
    $('overviewTrend').innerHTML=`<div class="trend">${rows.map(r=>`<div class="trend-row"><b>${esc(r.period)}</b><div class="trend-track"><div class="trend-fill" style="width:${Math.max(0,Math.min(100,100*(Number(r.contacts_per_1k_successes)||0)/peak))}%"></div></div><strong>${esc(r.contacts_per_1k_successes)}</strong></div>`).join('')}</div><div class="chart-caption">Support contacts per 1,000 successful payments. Compare alongside unique disputed payments and affected members in Investigations.</div>`;
  }catch(e){$('overviewTrend').textContent='Unable to load cohort trends: '+e.message;}
}

async function loadPayments(){try{const d=await api('/api/members/'+encodeURIComponent($('memberId').value.trim())+'/payments');$('paymentSelect').innerHTML='<option value="">Select payment…</option>'+d.payments.map(p=>`<option value="${esc(p.payment_id)}">${esc(p.payment_id)} · ${rupees(p.amount_paise)} · ${esc(p.created_at.slice(0,10))} · ${esc(p.product_flow)}</option>`).join('');if(!d.payments.length)message('No synthetic payments found for this member.');else message('');}catch(e){message(e.message);}}
async function submitComplaint(){
  try {
    if(demoReadOnly)throw Error('This preview is read-only.');
    const body={member_id:$('memberId').value.trim(),payment_id:$('paymentSelect').value||null,note:$('complaintNote').value};
    const d=await api('/api/complaints',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    $('complaintResult').innerHTML=`Created <strong>${esc(d.complaint_id)}</strong> as unresolved. <button class="quiet" onclick="openCase('${esc(d.complaint_id)}','${esc(d.payment_id)}')">Open investigation →</button>`;
    message('Member report saved. No fraud conclusion has been made.');
  }catch(e){message(e.message);}
}
async function openCase(caseId,paymentId){
  tab('cases');
  activeCaseId=caseId;
  await loadCases();
  renderCases(cachedCases.filter(filterCase));
  await loadPayment(paymentId,caseId);
}
let activeCaseId=null;
let cachedCases=[];
function renderCases(items){
  $('queueCount').textContent=`${items.length} SHOWN`;
  $('caseList').innerHTML=items.length?items.map(c=>`<button class="case-item ${activeCaseId===c.complaint_id?'selected':''}" onclick="activeCaseId='${esc(c.complaint_id)}';renderCases(cachedCases.filter(filterCase));loadPayment('${esc(c.payment_id)}','${esc(c.complaint_id)}')"><strong>${esc(c.complaint_id)}</strong> <span class="tag ${esc(c.analyst_disposition||'unresolved')}">${esc(c.analyst_disposition||'unresolved')}</span><small>${esc(c.member_id)} &nbsp;·&nbsp; ${rupees(c.amount_paise)} &nbsp;·&nbsp; ${esc(c.payment_id)}</small><small>${esc(c.created_at.slice(0,16))} &nbsp;·&nbsp; ${c.contact_count} contact(s)</small></button>`).join(''):'<div class="empty-state" style="margin:60px auto"><p>No matching cases</p></div>';
}
function filterCase(c){let q=($('caseSearch')?.value||'').trim().toLowerCase();return !q||[c.complaint_id,c.member_id,c.payment_id].some(v=>String(v).toLowerCase().includes(q));}
async function loadCases(){try{const d=await api('/api/cases?limit=60');cachedCases=d.cases;renderCases(cachedCases.filter(filterCase));}catch(e){message(e.message);}}
$('caseSearch').addEventListener('input',()=>renderCases(cachedCases.filter(filterCase)));

async function loadPayment(paymentId,complaintId){
  try {
    const [d,cDetail]=await Promise.all([
      api('/api/payments/'+encodeURIComponent(paymentId)),
      api('/api/cases/'+encodeURIComponent(complaintId))
    ]);
    const p=d.payment;
    const outcome=d.synthetic_outcome;
    const evidence=d.events.map(ev=>`<div class="timeline-item"><strong>${esc(ev.event_type)}</strong> — ${esc(ev.detail)} <small>${esc(ev.event_id)} · ${esc(ev.occurred_at)}</small></div>`).join('');
    const contacts=d.complaints.map(c=>`<div class="kv"><span>${esc(c.complaint_id)}</span><div>${esc(c.reason)} <span class="tag ${esc(c.analyst_disposition||'unresolved')}">${esc(c.analyst_disposition||'unresolved')}</span><br/><span class="subtle">${esc(c.created_at)}</span></div></div>`).join('');
    const dispositions=cDetail.dispositions.map(item=>`<div class="timeline-item"><strong>${esc(item.status)}</strong><small>${esc(item.decided_at)} · Decision ${esc(item.disposition_id)}</small><p>${esc(item.rationale)}</p></div>`).join('');
    $('paymentDetail').innerHTML=`
      <div class="kv"><span>Payment</span><strong>${esc(p.payment_id)}</strong></div>
      <div class="kv"><span>Member</span><strong>${esc(p.member_id)}</strong></div>
      <div class="kv"><span>Amount</span><strong>${rupees(p.amount_paise)}</strong></div>
      <div class="kv"><span>Payment status</span><strong>${esc(p.status)}</strong></div>
      <div class="kv"><span>Product flow</span>${esc(p.product_flow)}</div>
      <div class="divider"></div>
      <h2>Member statement</h2><p class="muted">${esc(cDetail.case.note)}</p>
      <h2>Payment event timeline</h2><div class="timeline">${evidence}</div>
      <h2>Related contacts (${d.complaints.length})</h2>${contacts}
      <h2>Analyst decision history (${cDetail.dispositions.length})</h2><div class="timeline">${dispositions||'<p class="muted">No analyst finding yet. The member allegation remains unresolved.</p>'}</div>
      <details class="evidence-note"><summary>Retrospective synthetic outcome (evaluation only)</summary>
        <p>${esc(outcome?.outcome||'not available')} · available ${esc(outcome?.available_at||'not yet')}</p>
        <p class="subtle">This independent label is only used for retrospective rule evaluation. It is not a payment-time feature and does not automatically set the case decision.</p>
      </details>
      <div class="divider"></div>
      <h2>Record finding — ${esc(complaintId)}</h2>
      <select id="decision" ${demoReadOnly?'disabled':''}><option value="genuine">Genuine payment</option><option value="confirmed_fraud">Confirmed fraud</option></select>
      <textarea id="rationale" rows="3" placeholder="Cite verified evidence, event IDs or member confirmation (10+ characters)" ${demoReadOnly?'disabled':''}></textarea>
      <button class="primary" data-write-action ${demoReadOnly?'disabled title="Read-only demo"':''} onclick="saveDisposition('${esc(complaintId)}','${esc(paymentId)}')">Record analyst decision</button>`;
  }catch(e){message(e.message);}
}
async function saveDisposition(complaintId,paymentId){
  try {
    if(demoReadOnly)throw Error('This preview is read-only.');
    const body={status:$('decision').value,rationale:$('rationale').value};
    await api('/api/cases/'+encodeURIComponent(complaintId)+'/disposition',{
      method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)
    });
    await loadCases();
    await loadPayment(paymentId,complaintId);
    message('Decision saved in append-only history. Seeded outcome labels and historical evaluation metrics remain unchanged.');
  }catch(e){message(e.message);}
}
function table(rows,columns){if(!rows.length)return '<p class="subtle">No records.</p>';return `<div class="tablewrap"><table><thead><tr>${columns.map(c=>`<th>${esc(c[1])}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${columns.map(c=>`<td class="${typeof r[c[0]]==='number'?'num':''}">${esc(r[c[0]]??'—')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;}
async function loadAnalysis(){try{const d=await api('/api/investigation');$('monthly').innerHTML=table(d.monthly,[['period','Month'],['successful_payments','Successful'],['tickets','Contacts'],['disputed_payments','Disputed payments'],['affected_members','Members'],['contacts_per_1k_successes','Contacts/1k'],['confirmed_fraud_payments','Confirmed fraud'],['confirmed_net_loss_inr','Net loss ₹'],['confirmed_loss_bps','Loss bps']]);$('flowTable').innerHTML=table(d.flows,[['period','Month'],['product_flow','Flow'],['successes','Successes'],['tickets','Contacts'],['contacts_per_1k_successes','Per 1k']]);$('postingTable').innerHTML=table(d.posting,[['period','Month'],['successful_payments','Successes'],['posted_after_24h','Delay >24h'],['delayed_payment_contacts','Contacts linked']]);message('');}catch(e){message(e.message);}}
async function loadRules(){try{const d=await api('/api/rules');$('ruleIntro').textContent=`${d.population}. ${d.known_outcomes}/${d.total_successful} outcomes resolved by ${d.as_of}. Daily budget: ${d.baseline.daily_budget}.`;$('ruleCards').innerHTML=[['baseline','Baseline',d.rules.baseline],['combined','Baseline + proposed',d.rules.proposed]].map(([key,title,desc])=>{const r=d[key];return `<div class="rule-card"><h3>${title}</h3><p>${esc(desc)}</p><div class="rule-metrics"><div><span>REVIEWS</span><strong>${r.reviews}</strong></div><div><span>CONFIRMED FRAUD</span><strong>${r.confirmed_fraud}</strong></div><div><span>PRECISION (RESOLVED)</span><strong>${(r.precision*100).toFixed(1)}%</strong></div><div><span>RECALL (KNOWN)</span><strong>${(r.recall*100).toFixed(1)}%</strong></div><div><span>GENUINE REVIEWS</span><strong>${r.genuine_reviews}</strong></div><div><span>UNRESOLVED</span><strong>${r.unresolved_reviews}</strong></div><div><span>BUSIEST DAY</span><strong>${r.busiest_day_reviews}</strong></div><div><span>DAYS OVER BUDGET</span><strong>${r.days_over_budget}</strong></div></div><div class="warning">Historical covered loss: ₹${fmt.format(r.historical_loss_covered_inr)}</div></div>`;}).join('');$('incremental').innerHTML=table([d.incremental],[['reviews','Extra reviews'],['confirmed_fraud','Extra fraud'],['genuine_reviews','Extra genuine reviews'],['unresolved_reviews','Extra unresolved'],['historical_loss_covered_inr','Extra covered loss ₹']]);$('ruleCaveat').textContent=d.caveat+' Precision: '+d.precision_denominator+'. Recall: '+d.recall_denominator+'.';message('');}catch(e){message(e.message);}}
loadMode();
loadOverview();
