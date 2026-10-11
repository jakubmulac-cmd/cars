'use strict';
const $ = (selector, root = document) => root.querySelector(selector);
const e = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = value => new Intl.NumberFormat('cs-CZ', {maximumFractionDigits: 2}).format(value);
const money = value => `${number(value)} Kč`;
const date = value => value ? new Intl.DateTimeFormat('cs-CZ', {day:'numeric',month:'numeric',year:'numeric',timeZone:'Europe/Paris'}).format(new Date(`${value.slice(0,10)}T12:00:00Z`)) : 'Nezjištěno';
const url = value => {try {const u = new URL(value); return u.protocol === 'https:' ? e(u.href) : '';} catch {return '';}};
const state = {data: null, page: 'overview', query: '', assetState: '', owner: '', priority: '', taskState: 'open', detail: null, detailTab: 'overview', authSetup: false, stagedImport: null};
const pages = {overview:'Přehled',vehicles:'Vozidla',issues:'Úkoly',insurance:'Pojištění',sources:'Podklady',settings:'Připojení a data'};
const evidenceNames = {insurer_confirmation:'Potvrzení pojišťovny o připsání a spárování',inspection_certificate:'Doklad o technické prohlídce',registration_record:'Aktuální registrační doklad / výpis',ownership_title:'Vlastnický nebo prodejní titul',supporting_document:'Doklad potvrzující splnění úkolu'};

async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, {...options, headers:{'Content-Type':'application/json',...options.headers}, credentials:'same-origin'});
  let body;
  try {body = await response.json();} catch {throw new Error('Server nevrátil platnou odpověď.');}
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('/auth/')) await showAuth();
    throw new Error(typeof body.detail === 'string' ? body.detail : 'Zkontrolujte vyplněné údaje.');
  }
  return body;
}
function toast(text) {
  $('#toast').textContent = text;
  $('#toast').hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => {$('#toast').hidden = true;}, 4500);
}
function pill(text, type = '') {return `<span class="pill ${e(type)}">${e(text)}</span>`;}
function heading(title, description) {
  return `<div class="page-heading"><div><h1>${e(title)}</h1><p>${e(description)}</p></div><span class="snapshot"><span class="status-dot"></span>Podklady k ${date(state.data.metadata.as_of)}</span></div>`;
}
function stats() {
  const c = state.data.counts;
  return `<div class="stats-grid"><article class="stat featured"><div class="stat-top">Evidenční záznamy<span class="stat-symbol">▱</span></div><div class="stat-number">${c.vehicles}</div><div class="stat-note">Včetně prodejů, plánů a APTO</div></article><article class="stat"><div class="stat-top">Kandidáti aktuálního majetku<span class="stat-symbol">◇</span></div><div class="stat-number">${c.candidates}</div><div class="stat-note">Vlastnictví vyžaduje doložení</div></article><article class="stat"><div class="stat-top">Otevřené úkoly<span class="stat-symbol">✓</span></div><div class="stat-number">${c.open_issues}</div><div class="stat-note">${c.p0} s nejvyšší prioritou</div></article><article class="stat"><div class="stat-top">Potvrzení úhrad<span class="stat-symbol">→</span></div><div class="stat-number word">Neověřeno</div><div class="stat-note">Připsání a spárování zatím nedoloženo</div></article></div>`;
}
function urgentBanner() {
  const p0 = state.data.issues.find(i => i.priority === 'P0' && i.state !== 'Uzavřeno');
  if (!p0) return '';
  const deadline = p0.deadline ? ` Lhůta ze zdroje: ${date(p0.deadline)}.` : '';
  return `<div class="priority-banner"><div class="alert-icon">!</div><div><h3>Priorita: doložit připsání pojistného a uzavření upomínky</h3><p>Oznámení o odeslání platby nepotvrzuje její spárování u pojišťovny.${deadline}</p></div><button class="button" data-action="task" data-id="${e(p0.issue_id)}">Zobrazit úkol <span aria-hidden="true">→</span></button></div>`;
}
function vehicleRows(vehicles) {
  return vehicles.map(v => {
    const reading = v.last_reading;
    return `<tr class="vehicle-row" data-vehicle="${e(v.asset_id)}"><td><div class="vehicle-cell"><span class="vehicle-monogram">${e((v.brand || v.name).slice(0,2).toUpperCase())}</span><div><div class="vehicle-name">${e(v.name)}</div><div class="vehicle-id">${e(v.asset_id)} · ${e(v.registration_country || 'Země neověřena')}</div></div></div></td><td>${v.rz ? `<span class="plate">${e(v.rz)}</span>` : '<span class="muted">Nezjištěno</span>'}</td><td>${pill(v.asset_state, v.asset_state.startsWith('Kandidát') ? 'candidate' : '')}</td><td>${reading ? `${number(reading.km)} km<div class="vehicle-id">${date(reading.date)}${!reading.date && reading.period ? ` · ${e(reading.period)}` : ''}</div>` : '<span class="muted">Nezjištěno</span>'}</td><td>${pill(v.verification, v.verification === 'Rozpor' ? 'conflict' : '')}</td><td><button class="row-action" data-action="vehicle" data-id="${e(v.asset_id)}" aria-label="Otevřít ${e(v.name)}">→</button></td></tr>`;
  }).join('');
}
function vehicleTable(vehicles, full = false) {
  return `<div class="panel"><div class="table-wrap"><table><thead><tr><th>Vozidlo</th><th>Kandidátní RZ</th><th>Stav dle podkladů</th><th>Poslední dostupný odečet</th><th>Ověření</th><th></th></tr></thead><tbody id="vehicle-list">${vehicleRows(vehicles)}</tbody></table></div><div class="table-note">${full ? 'Otevřete vozidlo pro jeho podklady, pojištění a historii.' : 'Evidenční záznam není automaticky ověřeným vlastnictvím.'}</div></div>`;
}
function overview() {
  const vehicles = state.data.vehicles.filter(v => v.asset_state === 'Kandidát aktuálního majetku').slice(0,5);
  const tasks = state.data.issues.filter(i => i.state !== 'Uzavřeno').slice(0,3);
  return `${heading('Váš vozový park','Vozidla, povinnosti a podklady. Vše na jednom místě.')}${stats()}${urgentBanner()}<div class="dashboard-columns"><section><div class="section-heading"><h2>Co vyžaduje pozornost</h2><a href="#issues" class="text-link">Všechny úkoly →</a></div><div class="panel panel-pad">${tasks.length ? tasks.map(i => `<article class="task-preview">${pill(i.priority,i.priority.toLowerCase())}<button data-action="task" data-id="${e(i.issue_id)}"><h3>${e(i.topic)}</h3><p>${e(i.asset_id ? state.data.vehicles.find(v => v.asset_id === i.asset_id)?.name || i.asset_id : 'Celý vozový park')}${i.deadline ? ` · do ${date(i.deadline)}` : ''}</p></button></article>`).join('') : '<div class="empty">Nejsou otevřené úkoly. Nezjištěná fakta zůstávají označena na kartách.</div>'}</div></section><section><div class="section-heading"><h2>Hodnota vozového parku</h2>${pill('Bez ocenění')}</div><div class="panel valuation-empty"><span class="empty-symbol" aria-hidden="true">⌁</span><h3>Historie ocenění zatím chybí</h3><p>První cenový bod vznikne z doložených tržních podkladů. Staré ceny ani chybějící hodnoty graf nevytvářejí.</p>${pill('Čeká na podklady')}</div></section></div><section><div class="section-heading"><h2>Vozidla v přehledu</h2><a href="#vehicles" class="text-link">Všech ${state.data.counts.vehicles} záznamů →</a></div>${vehicleTable(vehicles)}</section>`;
}
function inventory() {
  const owners = [...new Set(state.data.vehicles.map(v => v.master_owner).filter(Boolean))].sort();
  const states = [...new Set(state.data.vehicles.map(v => v.asset_state))];
  return `${heading('Vozidla','Kandidátní majetek, historie prodejů i plánované pořízení.')}<div class="toolbar"><input id="vehicle-search" class="search-input" aria-label="Vyhledat vozidlo" placeholder="Hledat vozidlo, RZ nebo VIN…" value="${e(state.query)}"><select id="state-filter" class="filter-select" aria-label="Stav vozidla"><option value="">Všechny stavy</option>${states.map(s => `<option ${state.assetState === s ? 'selected' : ''}>${e(s)}</option>`).join('')}</select><select id="owner-filter" class="filter-select" aria-label="Majitel v původním přehledu"><option value="">Majitel v přehledu</option>${owners.map(s => `<option ${state.owner === s ? 'selected' : ''}>${e(s)}</option>`).join('')}</select><span id="result-count" class="result-count"></span></div>${vehicleTable([],true)}`;
}
function updateInventory() {
  if (state.page !== 'vehicles') return;
  const query = state.query.toLocaleLowerCase('cs');
  const list = state.data.vehicles.filter(v => (!state.assetState || v.asset_state === state.assetState) && (!state.owner || v.master_owner === state.owner) && [v.asset_id,v.name,v.vin,v.rz,v.source_vin,v.source_rz,...(v.registration_candidates || [])].join(' ').toLocaleLowerCase('cs').includes(query));
  $('#vehicle-list').innerHTML = list.length ? vehicleRows(list) : '<tr><td colspan="6" class="empty">Žádné vozidlo neodpovídá filtrům.</td></tr>';
  $('#result-count').textContent = `${list.length} z ${state.data.vehicles.length} záznamů`;
}
function tasksPage() {
  return `${heading('Ověřovací úkoly','Konkrétní kroky k doplnění důkazů a vyřešení rozporů.')}<div class="toolbar"><select id="priority-filter" class="filter-select" aria-label="Priorita úkolu"><option value="">Všechny priority</option>${['P0','P1','P2'].map(p => `<option ${state.priority === p ? 'selected' : ''}>${p}</option>`).join('')}</select><select id="task-state-filter" class="filter-select" aria-label="Stav úkolu"><option value="open" ${state.taskState === 'open' ? 'selected' : ''}>Otevřené úkoly</option><option value="closed" ${state.taskState === 'closed' ? 'selected' : ''}>Uzavřené úkoly</option><option value="all" ${state.taskState === 'all' ? 'selected' : ''}>Všechny úkoly</option></select><span id="task-count" class="result-count"></span></div><div id="task-list" class="task-list"></div>`;
}
function updateTasks() {
  const tasks = state.data.issues.filter(i => (!state.priority || i.priority === state.priority) && (state.taskState === 'all' || (i.state === 'Uzavřeno') === (state.taskState === 'closed')));
  $('#task-count').textContent = `${tasks.length} úkolů`;
  $('#task-list').innerHTML = tasks.length ? tasks.map(i => `<article class="task-card">${pill(i.priority,i.priority.toLowerCase())}<div class="task-card-body"><h3>${e(i.topic)}</h3><p>${e(i.action)}</p><div class="task-meta"><span>${e(i.asset_id || 'Celá flotila')}</span><span>·</span>${pill(i.state,i.state === 'Uzavřeno' ? 'closed' : '')}<span>·</span><span>${i.deadline ? `Lhůta: ${date(i.deadline)}` : 'Bez doložené lhůty'}</span><span>·</span><span>${i.assigned_to ? `Odpovídá: ${e(i.assigned_to)}` : 'Odpovědná osoba nepřiřazena'}</span></div>${i.state === 'Uzavřeno' ? `<div class="close-note">Doloženo: ${e(i.evidence_title)} · ${date(i.evidence_date)}${url(i.evidence_url) ? ` · <a href="${url(i.evidence_url)}" target="_blank" rel="noopener noreferrer">Doklad →</a>` : ''}</div>` : ''}</div><button class="button small" data-action="task" data-id="${e(i.issue_id)}">${i.state === 'Uzavřeno' ? 'Detail' : 'Doplnit'} →</button></article>`).join('') : '<div class="panel empty">Žádné úkoly v tomto výběru.</div>';
}
function insurancePage() {
  const b = state.data.metadata.billing_reconciliation;
  if (!b) return `${heading('Pojištění','Předpisy a jejich doložené souvislosti.')}<div class="panel empty">Nejprve importujte podklady.</div>`;
  return `${heading('Pojištění a předpisy','Částky, období a stav dokladů bez domýšlení aktuálního salda.')}<div class="notice orange">Potvrzení připsání a alokace plateb je <strong>neověřené</strong>. Níže uvedené částky jsou historické předpisy, nikoli potvrzený současný dluh.</div><div class="finance-grid"><article class="finance-card"><h3>ČPP · předpis Q4 2026</h3><div class="money">${money(b.cpp_q4)}</div><p>1. 10.–31. 12. 2026 · 11 vozidel</p></article><article class="finance-card"><h3>ČPP · zpětný předpis RS5 Cabrio</h3><div class="money">${money(b.cpp_retro)}</div><p>9. 7.–30. 9. 2026 · samostatná položka</p></article><article class="finance-card"><h3>ČPP · nový předpis celkem</h3><div class="money">${money(b.cpp_new_premium)}</div><p>Q4 + zpětná položka · bez násobení na rok</p></article></div><section class="panel panel-pad"><div class="section-heading"><h2>Historická rekapitulace ČPP</h2>${pill(`K ${date(b.balance_as_of)}`)}</div><dl class="field-list"><dt>Nový předpis</dt><dd>${money(b.cpp_new_premium)}</dd><dt>Starší předpisy</dt><dd>${money(b.cpp_old_prescriptions)}</dd><dt>Přeplatky</dt><dd>− ${money(b.cpp_credit)}</dd><dt>Tehdy požadováno</dt><dd><strong>${money(b.cpp_payment_requested)}</strong></dd><dt>Upomínka</dt><dd>${money(b.reminder_amount)} ke dni ${date(b.reminder_as_of)} — samostatný časový snímek, nepřičítá se</dd><dt>Lhůta z upomínky</dt><dd>${date(b.reminder_deadline)}</dd><dt>Oznámení úhrady</dt><dd>${date(b.payment_notice_date)} · neprokazuje připsání a spárování</dd></dl></section><div class="section-heading detail-section"><h2>Položky předpisů</h2><span class="muted">${state.data.premium_lines.length} položek</span></div><div class="panel table-wrap"><table><thead><tr><th>Vozidlo</th><th>Druh</th><th>Období</th><th>Částka</th><th>Splatnost</th><th>Úhrada</th></tr></thead><tbody>${state.data.premium_lines.map(p => `<tr><td><button class="text-link" data-action="vehicle" data-id="${e(p.asset_id)}">${e(p.asset_id)}</button></td><td>${e(p.kind)}</td><td>${date(p.period_from)} – ${date(p.period_to)}</td><td>${money(p.amount)}</td><td>${date(p.due_date)}</td><td>${pill(p.payment_state)}</td></tr>`).join('')}</tbody></table></div><div class="notice detail-section">Triumph: roční předpis <strong>${money(b.triumph_total)}</strong> = POV ${money(b.triumph_pov)} + HAV a ostatní ${money(b.triumph_hav_and_other)}. Druhá složka zahrnuje i další rizika. Konec Q4 u ČPP je konec fakturovaného období, nikoli doložený konec pojištění.</div>`;
}
function sourceCards(sources) {
  return sources.map(s => `<article class="source-card"><div class="source-card-top">${pill(s.source_id)}<span class="vehicle-id">${date(s.source_date)}</span></div><h3>${e(s.title)}</h3><p>${e(s.kind)}${s.notes ? ` · ${e(s.notes)}` : ''}</p>${url(s.url) ? `<a href="${url(s.url)}" target="_blank" rel="noopener noreferrer">Otevřít originální zdroj →</a>` : '<span class="vehicle-id">Odkaz na originál není k dispozici</span>'}</article>`).join('');
}
function sourcesPage() {
  return `${heading('Zdrojové podklady','Dohledatelné dokumenty, zprávy a původní tvrzení.')}<div class="notice">Odkazy na Google Drive a Gmail vyžadují přihlášení k příslušnému účtu. Importovaný snímek nenahrazuje originální doklady ani nové ověření.</div><div class="source-grid">${sourceCards(state.data.sources)}</div>`;
}
function settingsPage() {
  return `${heading('Připojení a data','Import soukromého snímku a stav externích zdrojů.')}<div class="section-heading"><h2>Externí zdroje</h2>${pill('Automatické ověřování vypnuto')}</div><section class="panel" id="connectors"><div class="empty">Načítání…</div></section><div class="section-heading detail-section"><h2>Import dat</h2></div><section class="panel import-box"><p>Vyberte JSON snímek. Nejdřív se zobrazí výsledky validace a změny. Import nevytváří potvrzení vlastnictví ani platby.</p><label for="import-file" class="form-help">Soubor fleet_context.json</label><input id="import-file" type="file" accept=".json,application/json"><div id="import-preview"></div></section><div class="section-heading detail-section"><h2>Soukromý export</h2></div><section class="panel panel-pad"><p class="form-help">Export zahrnuje importované podklady, ruční odečty, změny úkolů a auditní historii. Uchovávejte jej jako soukromý dokument.</p><button class="button" data-action="export">Stáhnout JSON export ↓</button></section>`;
}
function render() {
  if (!state.data) return;
  state.page = pages[location.hash.slice(1)] ? location.hash.slice(1) : 'overview';
  document.title = `${pages[state.page]} · Cars`;
  $('#breadcrumb-page').textContent = pages[state.page];
  document.querySelectorAll('[data-page]').forEach(a => {const active = a.dataset.page === state.page; a.classList.toggle('active',active); if (active) a.setAttribute('aria-current','page'); else a.removeAttribute('aria-current');});
  $('#nav-vehicles').textContent = state.data.counts.vehicles;
  $('#nav-issues').textContent = state.data.counts.open_issues;
  $('#snapshot-footer').textContent = `Datový snímek ${date(state.data.metadata.as_of)} · živé registry neověřeny`;
  const renderer = {overview,vehicles:inventory,issues:tasksPage,insurance:insurancePage,sources:sourcesPage,settings:settingsPage}[state.page];
  $('#page-content').innerHTML = renderer();
  if (state.page === 'vehicles') {
    updateInventory();
    $('#vehicle-search').addEventListener('input',ev => {state.query = ev.target.value; updateInventory();});
    $('#state-filter').addEventListener('change',ev => {state.assetState = ev.target.value; updateInventory();});
    $('#owner-filter').addEventListener('change',ev => {state.owner = ev.target.value; updateInventory();});
  }
  if (state.page === 'issues') {
    updateTasks();
    $('#priority-filter').addEventListener('change',ev => {state.priority = ev.target.value; updateTasks();});
    $('#task-state-filter').addEventListener('change',ev => {state.taskState = ev.target.value; updateTasks();});
  }
  if (state.page === 'settings') {
    api('/connectors').then(connectors => {if (state.page === 'settings') $('#connectors').innerHTML = connectors.map(c => `<article class="connector-row"><div><h3>${e(c.name)}</h3><p>${e(c.reason)}</p></div>${pill('Nepřipojeno')}</article>`).join('');}).catch(err => toast(err.message));
    $('#import-file').addEventListener('change',importFile);
  }
}
async function reload() {state.data = await api('/dashboard'); render();}
function fact(label, value, note = '') {return `<div class="fact"><span class="fact-label">${e(label)}</span><span class="fact-value">${e(value ?? 'Nezjištěno')}</span>${note ? `<div class="fact-note">${e(note)}</div>` : ''}</div>`;}
function fields(entries) {return `<dl class="field-list">${entries.map(([name,value]) => `<dt>${e(name)}</dt><dd>${e(value ?? 'Nezjištěno')}</dd>`).join('')}</dl>`;}
function detailOverview(d) {
  const v = d.vehicle, o = d.operations[0] || {}, a = d.acquisitions[0] || {};
  const reading = v.last_reading;
  return `<div class="notice">${e(v.verification)} · Identita, vlastnictví a provozní způsobilost vyžadují aktuální doklady.</div><div class="detail-facts">${fact('Kandidátní VIN',v.vin,'Neověřeno registrem')}${fact('Kandidátní RZ',v.rz,(v.registration_candidates || []).length ? `Značky ve zdroji: ${v.registration_candidates.join(' / ')}` : 'Historie značek v původních podkladech')}${fact('Poslední dostupný odečet',reading ? `${number(reading.km)} km` : null,reading ? `Datum: ${date(reading.date)}${!reading.date && reading.period ? ` · období ${reading.period}` : ''} · nejde o dnešní automatické měření` : 'Doplňte odečet a jeho doklad')}${fact('Majitel v původním přehledu',v.master_owner,'Zdrojové tvrzení, nikoli ověřené vlastnictví')}</div><div class="inline-actions"><button class="button small" data-action="reading" data-id="${e(v.asset_id)}">+ Doplnit odečet</button>${pill(v.asset_state)}</div><section class="detail-section"><h3>Provoz a termíny</h3>${fields([['STK ve starém zdroji',o.stk_date ? date(o.stk_date) : o.stk_raw],['Ověření STK',o.stk_verification],['Úkol k STK',o.stk_action],['Dálniční známka',o.vignette_date ? date(o.vignette_date) : o.vignette_raw],['Ověření známky',o.vignette_verification],['Servis',o.service],['Další servis',o.next_service],['Záruka / poznámky',o.warranty_or_service_notes]])}</section><section class="detail-section"><h3>Pořízení a hodnota</h3>${fields([['Původní cena',a.acquisition_amount == null ? 'Nezjištěno' : `${number(a.acquisition_amount)} · ${a.acquisition_currency || 'měna neověřena'}`],['Datum dle zdroje',date(a.acquisition_date)],['Primární doklad',a.acquisition_document],['Režim ceny',a.vat_basis],['Současné ocenění','Dosud nedoloženo']])}</section>${v.notes?.length ? `<section class="detail-section"><h3>Důležité souvislosti</h3><p>${e(Array.isArray(v.notes) ? v.notes.join('\n') : v.notes)}</p></section>` : ''}${d.issues.length ? `<section class="detail-section"><h3>Úkoly k vozidlu</h3>${d.issues.map(i => `<div class="task-preview">${pill(i.priority,i.priority.toLowerCase())}<button data-action="task" data-id="${e(i.issue_id)}"><h3>${e(i.topic)}</h3><p>${e(i.state)}</p></button></div>`).join('')}</section>` : ''}`;
}
function detailInsurance(d) {
  const i = d.insurance[0];
  if (!i) return '<div class="empty">Pojistné podklady chybí.</div>';
  return `<div class="notice orange">${e(i.evidence_state)}. Fakturované období ani historický přehled nepotvrzují současné krytí.</div>${fields([['Pojišťovna',i.insurance_company],['Nadřazená smlouva',i.policy],['Dílčí smlouva',i.child_policy],['Pojistník',i.policyholder],['Vlastník ve výkazu',i.owner],['Provozovatel',i.operator],['Zprostředkovatel',i.broker],['Význam období',i.period_semantics === 'billing_period' ? 'Fakturované období' : i.period_semantics === 'renewal_document_period' ? 'Období v oznámení o obnově' : 'Nezjištěno'],['Období v podkladu',`${date(i.period_from)} – ${date(i.period_to)}`],['Potvrzený konec smlouvy',i.contract_end_confirmed ? date(i.contract_end_confirmed) : 'Nedoložen'],['Krytí',i.coverage],['Současný závazný km limit',i.binding_km_limit == null ? `Nezjištěno · ${i.binding_km_status || 'null neznamená neomezeno'}` : i.binding_km_limit],['Úhrada',i.paid_state]])}<section class="detail-section"><h3>Historický přehled 2024</h3>${fields([['Historické krytí',i.historic_coverage_2024],['Historický nájezd',i.historic_km_text],['Závaznost dnes','Nepotvrzena']])}</section><section class="detail-section"><h3>Položky předpisu</h3>${d.premium_lines.map(p => `<div class="task-preview"><div><h3>${e(p.kind)} · ${money(p.amount)}</h3><p>${date(p.period_from)} – ${date(p.period_to)} · ${e(p.payment_state)} · zdroj ${e(p.source_id)}</p></div></div>`).join('') || '<p>Ve snímku není doložen předpis.</p>'}</section>`;
}
function detailHistory(d) {
  const readings = [...d.odometer_readings, ...d.manual_readings.map(r => ({...r,location:r.evidence,verification:'Ruční doložený odečet'}))].sort((a,b) => (b.date || b.period || '').localeCompare(a.date || a.period || ''));
  return `<div class="section-heading"><h3>Historie odečtů</h3><button class="button small" data-action="reading" data-id="${e(d.vehicle.asset_id)}">+ Doplnit odečet</button></div><div class="table-wrap"><table class="compact-table"><thead><tr><th>Datum / období</th><th>Odečet</th><th>Původ</th><th>Ověření</th></tr></thead><tbody>${readings.map(r => `<tr><td>${r.date ? date(r.date) : e(r.period || 'Nezjištěno')}</td><td>${number(r.km)} km</td><td>${e(r.source_id || 'Ruční doklad')} · ${e(r.location)}</td><td>${e(r.verification)}</td></tr>`).join('') || '<tr><td colspan="4">Žádné doložené odečty.</td></tr>'}</tbody></table></div><section class="detail-section"><h3>Knihy jízd</h3><p>${d.rides.length} historických jízd. Přiřazení podle hlavičky je kandidátní; výchozí důkazy zachovává soukromý export.</p></section><section class="detail-section"><h3>Vývoj tržní hodnoty</h3><div class="panel valuation-empty"><span class="empty-symbol">⌁</span><h3>Zatím bez cenových bodů</h3><p>Historická indikace nebo pořizovací cena nejsou měsíční tržní ocenění.</p></div></section>`;
}
function detailSources(d) {
  return `<div class="source-grid">${sourceCards(d.sources)}</div><section class="detail-section"><h3>Původní zdrojová tvrzení</h3><p class="form-help">Zachováno ${d.source_observations.length} pozorování; zde prvních ${Math.min(100,d.source_observations.length)}. Úplná historie je v soukromém exportu.</p><div class="table-wrap"><table class="compact-table"><thead><tr><th>Zdroj / buňka</th><th>Pole</th><th>Původní hodnota</th></tr></thead><tbody>${d.source_observations.slice(0,100).map(o => `<tr><td>${e(o.source_id)}<br>${e(o.sheet)} · ${e(o.cell)}</td><td>${e(o.field)}</td><td>${e(typeof o.value === 'object' ? JSON.stringify(o.value) : o.value)}</td></tr>`).join('')}</tbody></table></div></section>`;
}
function renderDetail() {
  const d = state.detail, v = d.vehicle;
  const tabs = {overview:'Přehled',insurance:'Pojištění',history:'Historie',sources:'Podklady'};
  $('#detail-content').innerHTML = `<header class="dialog-header"><div><span class="eyebrow">${e(v.asset_id)} · ${e(v.brand || 'VOZIDLO')}</span><h2>${e(v.name)}</h2>${pill(v.asset_state)}</div><button class="close-button" data-action="close-details" aria-label="Zavřít detail">×</button></header><div class="detail-tabs" role="tablist" aria-label="Informace o vozidle">${Object.entries(tabs).map(([key,label]) => `<button role="tab" aria-selected="${state.detailTab === key}" class="${state.detailTab === key ? 'active' : ''}" data-action="detail-tab" data-id="${key}">${label}</button>`).join('')}</div><div class="detail-body" role="tabpanel">${{overview:detailOverview,insurance:detailInsurance,history:detailHistory,sources:detailSources}[state.detailTab](d)}</div>`;
}
async function openVehicle(id) {
  state.detail = await api(`/vehicles/${encodeURIComponent(id)}`);
  state.detailTab = 'overview';
  renderDetail();
  if (!$('#details').open) $('#details').showModal();
}
function openTask(id) {
  const task = state.data.issues.find(i => i.issue_id === id);
  if (!task) return;
  const closed = task.state === 'Uzavřeno';
  $('#action-content').innerHTML = `<header class="dialog-header"><div><span class="eyebrow">${e(task.issue_id)} · ${e(task.priority)}</span><h2>${e(task.topic)}</h2></div><button class="close-button" data-action="close-action" aria-label="Zavřít">×</button></header><div class="action-body"><p class="form-help">${e(task.action)}</p>${task.deadline ? `<div class="notice orange">Lhůta ze zdroje: ${date(task.deadline)}</div>` : ''}${closed ? `<div class="close-note"><strong>${e(task.evidence_title)}</strong><p>${e(task.closure_note)}</p><a href="${url(task.evidence_url)}" target="_blank" rel="noopener noreferrer">Otevřít doklad →</a></div>` : ''}<form id="task-form" class="form-stack"><label>Odpovědná osoba<input name="assigned_to" maxlength="150" placeholder="Jméno nebo role" value="${e(task.assigned_to)}"></label>${!closed ? `<label class="checkbox"><input name="close" type="checkbox">Doložit splnění a uzavřít úkol</label><div class="evidence-fields" id="evidence-fields" hidden><p class="form-help">Požadovaný důkaz: <strong>${e(evidenceNames[task.required_evidence])}</strong>. Zápis potvrzuje kontrolu správcem, nikoli automatické ověření externím zdrojem.</p><label>Název dokladu<input name="evidence_title" maxlength="300"></label><label>Soukromý odkaz na doklad<input name="evidence_url" type="url" placeholder="https://…" maxlength="1000"></label><label>Datum dokladu<input name="evidence_date" type="date" max="${e(state.data.today)}"></label><label>Co doklad potvrzuje<textarea name="closure_note" maxlength="2000"></textarea></label></div>` : ''}<p class="form-error" role="alert"></p><div class="form-actions"><button type="button" class="button" data-action="close-action">Zrušit</button><button type="submit" class="button primary">Uložit</button></div></form></div>`;
  const form = $('#task-form');
  if (!closed) form.elements.close.addEventListener('change',ev => {$('#evidence-fields').hidden = !ev.target.checked; $('#evidence-fields').querySelectorAll('input,textarea').forEach(i => {i.required = ev.target.checked;});});
  form.addEventListener('submit',async ev => {
    ev.preventDefault();
    const data = Object.fromEntries(new FormData(form));
    data.close = !closed && form.elements.close.checked;
    data.evidence_type = data.close ? task.required_evidence : null;
    for (const key of ['evidence_title','evidence_url','evidence_date','closure_note']) if (!data.close) delete data[key];
    try {await api(`/issues/${encodeURIComponent(id)}`,{method:'PATCH',body:JSON.stringify(data)}); $('#action-dialog').close(); await reload(); toast('Úkol byl uložen.');} catch (err) {$('.form-error',form).textContent = err.message;}
  });
  if (!$('#action-dialog').open) $('#action-dialog').showModal();
}
function openReading(id) {
  $('#action-content').innerHTML = `<header class="dialog-header"><div><span class="eyebrow">${e(id)}</span><h2>Doplnit odečet</h2></div><button class="close-button" data-action="close-action" aria-label="Zavřít">×</button></header><div class="action-body"><form id="reading-form" class="form-stack"><label>Stav tachometru v km<input name="km" type="number" min="0" max="10000000" step="0.1" required></label><label>Datum odečtu<input name="date" type="date" max="${e(state.data.today)}" value="${e(state.data.today)}" required></label><label>Doklad nebo popis původu<textarea name="evidence" minlength="5" maxlength="1000" placeholder="Např. fotografie tachometru nebo servisní faktura s odkazem" required></textarea></label><p class="form-help">Původní odečty se zachovají. Nový záznam se uloží do auditní historie.</p><p class="form-error" role="alert"></p><div class="form-actions"><button type="button" class="button" data-action="close-action">Zrušit</button><button type="submit" class="button primary">Uložit odečet</button></div></form></div>`;
  const form = $('#reading-form');
  form.addEventListener('submit',async ev => {ev.preventDefault(); try {await api(`/vehicles/${encodeURIComponent(id)}/readings`,{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(form)))}); $('#action-dialog').close(); await reload(); state.detail = await api(`/vehicles/${encodeURIComponent(id)}`); renderDetail(); toast('Odečet byl uložen.');} catch(err) {$('.form-error',form).textContent = err.message;}});
  if (!$('#action-dialog').open) $('#action-dialog').showModal();
}
async function importFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  state.stagedImport = null;
  const box = $('#import-preview');
  box.textContent = 'Ověřování souboru…';
  try {
    if (file.size > 5_000_000) throw new Error('Soubor je příliš velký. Maximum je 5 MB.');
    const payload = JSON.parse(await file.text());
    const result = await api('/imports/preview',{method:'POST',body:JSON.stringify(payload)});
    state.stagedImport = result.id;
    box.innerHTML = `<div class="import-report"><strong>Validace prošla · snímek ${date(result.as_of)}</strong><p>${result.counts.vehicles} vozidel · ${result.counts.issues} úkolů · ${result.counts.premium_lines} pojistných položek</p><p>Nové záznamy: ${result.new_vehicles}. Změněné: ${result.changed_vehicles}. Rozpory: ${result.conflicts.length}.</p><p>${result.already_imported ? 'Tento snímek už je importovaný. Opakování nevytvoří duplicity.' : 'Ruční odečty a doplněné úkoly zůstanou zachovány.'}</p></div><button class="button primary" data-action="commit-import">Potvrdit import</button>`;
  } catch(err) {box.innerHTML = `<p class="form-error" role="alert">${e(err.message)}</p>`;}
}
async function showAuth() {
  const status = await api('/auth/status');
  state.authSetup = !status.configured;
  state.data = null;
  $('#loading').hidden = true;
  $('#application').hidden = true;
  $('#auth-screen').hidden = false;
  $('#auth-title').textContent = state.authSetup ? 'Váš soukromý prostor' : 'Vítejte zpět';
  $('#auth-description').textContent = state.authSetup ? 'Zvolte si přístupové heslo. Stačí alespoň 12 znaků.' : 'Přihlaste se ke svému přehledu vozidel.';
  $('#auth-submit').innerHTML = state.authSetup ? 'Vytvořit přístup <span aria-hidden="true">→</span>' : 'Přihlásit se <span aria-hidden="true">→</span>';
  $('#password').minLength = state.authSetup ? 12 : 1;
  $('#password').autocomplete = state.authSetup ? 'new-password' : 'current-password';
  $('#password').value = '';
  if ($('#details').open) $('#details').close();
  if ($('#action-dialog').open) $('#action-dialog').close();
}
async function showApp() {
  await reload();
  $('#loading').hidden = true;
  $('#auth-screen').hidden = true;
  $('#application').hidden = false;
}
$('#auth-form').addEventListener('submit',async event => {
  event.preventDefault();
  $('#auth-submit').disabled = true;
  $('#auth-error').textContent = '';
  try {await api(`/auth/${state.authSetup ? 'setup' : 'login'}`,{method:'POST',body:JSON.stringify({password:$('#password').value})}); $('#password').value = ''; await showApp();} catch(err) {$('#auth-error').textContent = err.message;} finally {$('#auth-submit').disabled = false;}
});
$('#logout').addEventListener('click',async () => {try {await api('/auth/logout',{method:'POST',body:'{}'}); await showAuth();} catch(err) {toast(err.message);}});
window.addEventListener('hashchange',render);
document.addEventListener('click',async event => {
  const button = event.target.closest('[data-action]');
  if (button) {
    const {action,id} = button.dataset;
    try {
      if (action === 'vehicle') await openVehicle(id);
      if (action === 'close-details') $('#details').close();
      if (action === 'close-action') $('#action-dialog').close();
      if (action === 'detail-tab') {state.detailTab = id; renderDetail();}
      if (action === 'task') openTask(id);
      if (action === 'reading') openReading(id);
      if (action === 'commit-import' && state.stagedImport) {button.disabled = true; await api(`/imports/${state.stagedImport}/commit`,{method:'POST',body:'{}'}); state.stagedImport = null; await reload(); toast('Import dokončen bez duplicit.');}
      if (action === 'export') {const data = await api('/export'); const blob = new Blob([JSON.stringify(data,null,2)],{type:'application/json'}); const href = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = href; a.download = `cars-soukromy-export-${state.data.today}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(href),1000);}
    } catch(err) {button.disabled = false; toast(err.message);}
    return;
  }
  const row = event.target.closest('[data-vehicle]');
  if (row) {try {await openVehicle(row.dataset.vehicle);} catch(err) {toast(err.message);}}
});
(async () => {try {const status = await api('/auth/status'); if (status.authenticated) await showApp(); else await showAuth();} catch(err) {$('#loading').textContent = `Přehled nelze načíst: ${err.message}`;}})();
