'use strict';
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safeUrl = value => { try { const u = new URL(value); return ['https:', 'http:'].includes(u.protocol) && !u.username && !u.password ? esc(u.href) : '#'; } catch { return '#'; } };
const date = value => value ? new Date(value).toLocaleDateString(ui === 'hi' ? 'hi-IN' : 'en-IN', {day:'numeric', month:'short', year:'numeric'}) : '—';
let ui = localStorage.getItem('scamserp-language') || 'en';
let meta, geometry, adminToken = '', currentRoute = 0, googleMapsPromise;
let mapFilters = { category:'all', language:'all', window:'30' };
let queryFilters = { search:'', category:'all', language:'all', offset:0 };
const hindi = {
  'Check before you trust.':'भरोसा करने से पहले जांचें।',
  'A number. A website. A second opinion.':'एक नंबर। एक वेबसाइट। एक भरोसेमंद जांच।',
  'Check a contact':'संपर्क जांचें', 'Search risk map':'खोज जोखिम मानचित्र', 'Open research':'खुला शोध', 'Official registry':'आधिकारिक रिकॉर्ड',
  'Audit dashboard':'ऑडिट डैशबोर्ड', 'Risk map':'मानचित्र', 'Audits':'ऑडिट',
  'Paste a number, website or message':'नंबर, वेबसाइट या संदेश पेस्ट करें', 'Check contact':'संपर्क जांचें', 'Your message stays private. We don’t save lookup inputs.':'आपका संदेश निजी है। हम जांच का इनपुट सेव नहीं करते।',
  'Verified Official':'सत्यापित आधिकारिक', 'No Issue Found':'कोई समस्या नहीं मिली', 'Unverified':'असत्यापित', 'Suspicious':'संदिग्ध', 'Likely Fraud':'धोखाधड़ी के प्रबल संकेत', 'No data':'डेटा उपलब्ध नहीं',
  'Current official alternative':'वर्तमान आधिकारिक संपर्क', 'What to do now':'अब क्या करें', 'View the evidence':'प्रमाण देखें',
  'Don’t share an OTP, PIN or password.':'OTP, PIN या पासवर्ड साझा न करें।', 'Financial cybercrime? Act quickly.':'वित्तीय साइबर अपराध? जल्दी कार्रवाई करें।',
  'Call 1930 and report at the national cybercrime portal. Report suspicious calls and messages through Chakshu.':'1930 पर कॉल करें और राष्ट्रीय साइबर अपराध पोर्टल पर शिकायत करें। संदिग्ध कॉल और संदेश चक्षु पर रिपोर्ट करें।',
  'Independent public-interest project. Not an official government service. Not legal or financial advice.':'स्वतंत्र जनहित परियोजना। यह सरकारी सेवा, कानूनी या वित्तीय सलाह नहीं है।',
  'Findings':'निष्कर्ष', 'No published evidence for this query yet.':'इस खोज का प्रकाशित प्रमाण अभी उपलब्ध नहीं है।', 'Share verdict':'परिणाम साझा करें',
  'How we score':'स्कोर कैसे बनता है', 'Dispute this finding':'इस निष्कर्ष पर आपत्ति करें', 'Prepare report':'रिपोर्ट तैयार करें',
};
const t = x => ui === 'hi' ? (hindi[x] || x) : x;
const num = x => Number(x || 0).toLocaleString(ui === 'hi' ? 'hi-IN' : 'en-IN');
const percent = x => x == null ? '—' : `${x.toFixed(1)}%`;
const badge = value => `<span class="badge ${({'Verified Official':'verified','Suspicious':'suspicious','Likely Fraud':'fraud','Unverified':'unverified','No Issue Found':'clear'})[value] || ''}">${value === 'Verified Official' ? '✓' : value === 'No data' ? '○' : '◈'} ${esc(t(value))}</span>`;
const loading = () => { $('#main').innerHTML = '<div class="loading" role="status">Loading evidence…</div>'; };
const empty = (title, detail='') => `<div class="empty"><strong>${esc(t(title))}</strong>${esc(detail)}</div>`;
async function api(path, options={}) {
  const response = await fetch(path, { ...options, headers:{ 'Content-Type':'application/json', ...(options.headers || {}) } });
  if (!response.ok) { let e; try { e = await response.json(); } catch {} throw new Error(typeof e?.detail === 'string' ? e.detail : `Request failed (${response.status})`); }
  return response.json();
}
function toast(message) { $('#toast').textContent = message; $('#toast').classList.add('visible'); setTimeout(() => $('#toast').classList.remove('visible'), 3500); }
function showError(error, target='#main') { $(target).innerHTML = `<div class="error" role="alert">${esc(error.message)} <button class="text-button" data-action="reload">Try again</button></div>`; }
function updateShell() {
  document.documentElement.lang = ui;
  $('#language').textContent = ui === 'hi' ? 'हिन्दी / EN' : 'EN / हिन्दी';
  $('#language').setAttribute('aria-label', ui === 'hi' ? 'Switch to English' : 'Switch to Hindi');
  $$('[data-nav]').forEach(a => { a.textContent = t({'lookup':'Check contact', 'map':'Risk map', 'audits':'Audits', 'research':'Open research', 'registry':'Official registry'}[a.dataset.nav]); a.classList.toggle('active', (location.hash || '#lookup').startsWith('#'+a.dataset.nav)); });
  $('[data-i18n="notice"]').textContent = t('Independent public-interest project. Not an official government service. Not legal or financial advice.');
}
function safety() { return `<aside class="safety-banner"><div><h3>${esc(t('Financial cybercrime? Act quickly.'))}</h3><p>${esc(t('Call 1930 and report at the national cybercrime portal. Report suspicious calls and messages through Chakshu.'))}</p></div><div class="safety-actions"><a href="tel:1930" aria-label="Call national cybercrime helpline 1930"><strong>1930</strong>National helpline</a><div><a href="https://cybercrime.gov.in/" target="_blank" rel="noopener noreferrer">Cybercrime portal ↗</a><br><a href="https://sancharsaathi.gov.in/sfc/" target="_blank" rel="noopener noreferrer">Chakshu ↗</a></div></div></aside>`; }
function head(eyebrow,title,description,action='') { return `<div class="page-head"><div><div class="eyebrow">${esc(eyebrow)}</div><h1>${esc(t(title))}</h1><p class="sub">${esc(description)}</p></div>${action}</div>`; }
function lookupPage() {
  const english=ui!=='hi';
  $('#main').innerHTML = `<section class="lookup-hero"><div class="lookup-intro"><h1>${english?'Check before you trust.':'भरोसा करने से पहले जांचें।'}</h1><p>${english?'Check a number, website or message against official sources.':'नंबर, वेबसाइट या संदेश को आधिकारिक स्रोतों से जांचें।'}</p></div><div class="lookup-box"><form id="lookup-form"><label for="lookup-input">${esc(t('Paste a number, website or message'))}</label><textarea id="lookup-input" name="text" maxlength="4000" required placeholder="${english?'e.g. 1800 1234, sbi.bank.in, or a message you received…':'जैसे 1800 1234, sbi.bank.in, या मिला हुआ संदेश…'}"></textarea><div class="lookup-bottom"><span class="privacy">${esc(t('Your message stays private. We don’t save lookup inputs.'))}</span><button class="btn" type="submit">${esc(t('Check contact'))} <span aria-hidden="true">→</span></button></div></form><details class="lookup-examples"><summary>${english?'Try an example':'उदाहरण देखें'}</summary><div class="examples"><button class="chip" data-example="1800 1234">SBI number</button><button class="chip" data-example="sbi.bank.in">Official website</button><button class="chip" data-example="SBI support: https://sbi-care-3.example/ . Fictional demo only; do not call 1800 000 0000.">Demo message</button></div></details></div></section><section id="lookup-results" class="lookup-results" aria-live="polite"></section><details class="coverage-details"><summary>${english?'Coverage and limitations':'कवरेज और सीमाएं'}<span>${num(meta.registry_current)} / ${meta.entities.length} ${english?'entities source-checked':'संस्थाओं के स्रोत जांचे गए'}</span></summary><section class="evidence-strip" aria-label="Project coverage"><div class="stat"><strong>${num(meta.registry_current)} / ${meta.entities.length}</strong><span>Entities with current source checks</span></div><div class="stat"><strong>${num(meta.queries)}</strong><span>Active query variants · 7 language forms</span></div><div class="stat"><strong>${num(meta.observations)}</strong><span>${meta.mode==='demo'?'Synthetic':'Published'} observations</span></div><div class="stat"><strong>Source-led</strong><span>Every verdict includes evidence</span></div></section><p class="hint">${english?'Missing evidence is not a safety guarantee. Official contacts and translations still require review.':'प्रमाण न होना सुरक्षा की गारंटी नहीं है। आधिकारिक संपर्कों और अनुवादों की समीक्षा जरूरी है।'} <a href="#methodology">${esc(t('How we score'))} →</a></p></details><nav class="lookup-secondary" aria-label="Explore evidence"><a href="#map">${english?'Explore the risk map':'जोखिम मानचित्र देखें'} →</a><a href="#registry">${english?'Official contacts':'आधिकारिक संपर्क'} →</a><a href="#research">${english?'Browse research':'शोध देखें'} →</a></nav>${safety()}`;
}

function officialPanel(alt) {
  if(!alt.domains.length && !alt.phones.length)return `<p class="hint">${ui==='hi'?'इस संस्था का वर्तमान सत्यापित संपर्क उपलब्ध नहीं है।':'No current verified alternative is available for this entity.'}</p>`;
  const primary=alt.domains[0] || alt.phones[0];
  const phoneLink=r=>`<a href="tel:${esc(r.value.replace(/^(toll|short|service):/,''))}">${esc(r.display)}</a>`;
  return `<div class="official-panel"><h3>✓ ${esc(t('Current official alternative'))}</h3><div class="official-primary">${alt.domains.map(r=>`<a href="https://${esc(r.value)}" target="_blank" rel="noopener noreferrer">${esc(r.display)} ↗</a>`).join('')}${alt.phones.slice(0,1).map(phoneLink).join('')}</div>${alt.phones.length>1?`<details class="more-contacts"><summary>${ui==='hi'?'अन्य सत्यापित नंबर':'Other verified numbers'} (${alt.phones.length-1})</summary>${alt.phones.slice(1).map(phoneLink).join('')}</details>`:''}<small class="source-note">Source checked ${date(primary.verified_at)} · Recheck by ${date(primary.expires_at)} · <a class="hint" href="${safeUrl(primary.source_url)}" target="_blank" rel="noopener noreferrer">Primary source ↗</a></small></div>`;
}

function advertiserPanel(r) {
  if(r.kind!=='ad')return '';
  const a=r.advertiser_evidence;
  const candidates=r.advertiser_candidates || [];
  return `<details class="evidence"><summary>Advertiser evidence</summary>${a?`<p class="hint">${esc(a.name || 'Name unavailable')} · ${esc(a.attribution)} · Verification: ${esc(a.verification_status || 'unknown')}</p><a class="hint" href="${safeUrl(a.source_url)}" target="_blank" rel="noopener noreferrer">Ads Transparency source ↗</a><p class="hint">${esc(a.note)} Search ID: ${esc(a.search_id || 'unavailable')}. Account creation: ${esc(a.account_created_at || 'unknown')}.</p>`:'<p class="hint">No attributed advertiser record. Missing evidence is not an adverse signal.</p>'}${candidates.length?`<p class="hint">Domain-search candidates: ${candidates.map(c=>esc(c.name || c.id)).join(', ')}. These do not establish ownership of this ad.</p>`:''}${r.advertiser_relationship_review?`<p class="hint">Reviewed relationship: ${esc(r.advertiser_relationship_review.relationship)} · <a href="${safeUrl(r.advertiser_relationship_review.source_url)}" target="_blank" rel="noopener noreferrer">Review source ↗</a></p>`:''}</details>`;
}
function evidenceCard(r, actions=true) {
  return `<article class="evidence-item"><div class="result-top">${badge(r.verdict)}<span class="hint">${esc(r.kind)} · #${r.position} · ${r.risk}/100</span></div><h3>${esc(r.title)}</h3><span class="hint">${esc(r.domain || 'No website supplied')}</span><blockquote>${esc(r.snippet || 'No snippet provided')}</blockquote><div class="evidence-meta"><span>${esc(r.query_text || 'Targeted search')}</span><span>${esc(r.location)}</span><span>${date(r.fetched_at)}</span><span>Search ID: ${esc(r.search_id || 'unavailable')}</span><span>${esc(r.rule_version)}</span></div>${advertiserPanel(r)}${r.signals.map(s=>`<div class="signal"><b>${s.points > 0 ? '+' : ''}${s.points}</b><span>${esc(ui === 'hi' ? s.reason_hi : s.reason)} <small>(${esc(s.family)})</small></span></div>`).join('')}${r.signals.length === 0 ? '<p class="hint">Registry match or no adverse rule signals. Absence of signals is not a safety guarantee.</p>' : ''}${actions ? `<div class="action-row"><button class="text-button" data-report="${esc(r.id)}">${esc(t('Prepare report'))}</button><button class="text-button" data-dispute="${esc(r.id)}">${esc(t('Dispute this finding'))}</button>${r.query_id ? `<a class="hint" href="#query/${encodeURIComponent(r.query_id)}?state=${encodeURIComponent(r.state)}">Full search evidence →</a>` : ''}</div>` : ''}</article>`;
}
function verdictCard(r) {
  const cleanNumber=r.normalized.replace(/^(toll|short|service):/,'');
  return `<article class="result-card"><div class="result-top"><div>${badge(r.verdict)}<h2>${esc(r.entity_name || cleanNumber)}</h2><div class="result-number">${esc(cleanNumber)} · ${esc(r.type)}</div></div><div class="result-score"><strong>${r.risk ?? '—'}</strong><span>risk / 100</span></div></div><p>${esc(ui==='hi'?r.explanation_hi:r.explanation)}</p>${officialPanel(r.official_alternative)}<details class="observation-details"><summary>${ui==='hi'?'ऑडिट इतिहास':'Audit history'}<span>${num(r.seen_count)} ${r.demo?'synthetic':'published'} sightings</span></summary><div class="evidence-meta"><span>${esc(r.confidence)}</span><span>${r.locations.map(esc).join(', ')}</span>${r.first_seen?`<span>First ${date(r.first_seen)} · Latest ${date(r.last_seen)}</span>`:''}</div>${r.registry_source?`<a class="hint" href="${safeUrl(r.registry_source.source_url)}" target="_blank" rel="noopener noreferrer">Registry evidence ↗</a>`:''}<p class="hint">${esc(r.confidence_note || 'Evidence strength, not a probability of fraud.')}</p></details>${r.evidence.length?`<details class="evidence"><summary>${esc(t('View the evidence'))} (${r.evidence.length} examples)</summary>${r.evidence.map(x=>evidenceCard(x)).join('')}</details>`:''}<div class="action-row"><button class="text-button" data-share="${esc(cleanNumber)}" data-verdict="${esc(r.verdict)}">${esc(t('Share verdict'))} ↗</button>${r.live_available && r.verdict==='No data'?`<button class="btn secondary small" data-live="${esc(cleanNumber)}">Run live search (uses credits)</button>`:''}</div></article>`;
}

async function performLookup(text) {
  const target = $('#lookup-results'); if (!target) return;
  target.innerHTML = '<p role="status" class="hint">Checking current registry and published evidence…</p>';
  const button = $('#lookup-form button[type="submit"]'); button.disabled = true;
  try { const data = await api('/api/lookup/text',{method:'POST',body:JSON.stringify({text})}); target.innerHTML = data.items.length ? `<h2>${esc(t('Findings'))}</h2>${data.items.map(verdictCard).join('')}<div class="official-panel"><h3>${esc(t('What to do now'))}</h3><p>${esc(t('Don’t share an OTP, PIN or password.'))} ${ui === 'hi' ? 'संस्था की मूल वेबसाइट पर दिए संपर्क का उपयोग करें।' : 'Use the contact on the institution’s own website. A verified number does not authenticate an incoming caller.'}</p></div>` : empty('No number or website found','Try a complete Indian phone number, URL or a message containing a link.'); target.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'}); } catch(e) { showError(e,'#lookup-results'); } finally { button.disabled=false; }
}
function selectOptions(items,selected) { return items.map(([v,label])=>`<option value="${esc(v)}" ${String(v)===String(selected) ? 'selected' : ''}>${esc(label)}</option>`).join(''); }
function filters() { return `<form id="map-filters" class="filters"><label>Query category<select name="category">${selectOptions([['all','All categories'],...meta.categories.map(c=>[c,c.charAt(0).toUpperCase()+c.slice(1)])],mapFilters.category)}</select></label><label>Search language<select name="language">${selectOptions([['all','All languages'],...Object.entries(meta.languages).filter(([l])=>l!=='hinglish')],mapFilters.language)}</select></label><label>Time window<select name="window">${selectOptions([['7','Last 7 days'],['30','Last 30 days'],['90','Last 90 days']],mapFilters.window)}</select></label><span class="filter-note">Fixed city proxies · sample size on every state</span></form>`; }
const mapColor = value => value == null ? '#e7e9e0' : value < 20 ? '#d9e7c9' : value < 40 ? '#abc989' : value < 60 ? '#75965e' : '#365d43';
const geoAliases = {'NCT of Delhi':'Delhi','National Capital Territory of Delhi':'Delhi','Uttaranchal':'Uttarakhand','Orissa':'Odisha','Jammu & Kashmir':'Jammu and Kashmir'};
function indiaSvg(states) {
  if (!geometry) return empty('Map geometry unavailable','Location data is available in the table.');
  const byName = Object.fromEntries(states.map(s=>[s.state,s]));
  const project = ([lon,lat]) => [20+(lon-67)*13.8, 15+(38-lat)*12.0];
  const ringPath = ring => ring.map((p,i)=>`${i?'L':'M'}${project(p).map(v=>v.toFixed(2)).join(',')}`).join(' ')+'Z';
  const shapePath = g => (g.type === 'Polygon' ? [g.coordinates] : g.coordinates).map(poly=>poly.map(ringPath).join(' ')).join(' ');
  return `<svg class="map-svg" viewBox="0 0 480 410" role="group" aria-label="India state choropleth; six locations sampled">${geometry.features.filter(f=>['Polygon','MultiPolygon'].includes(f.geometry.type)).map(f=>{const raw=(f.properties.shapeName || f.properties.NAME_1 || f.properties.name).normalize('NFD').replace(/[\u0300-\u036f]/g,''); const name=geoAliases[raw] || raw; const s=byName[name]; const description=`${name}: ${s?.exposure == null ? 'insufficient or no data' : s.exposure+' percent exposure'}, ${s?.n_runs || 0} runs, ${s?.n || 0} observations`; return `<path d="${shapePath(f.geometry)}" fill="${mapColor(s?.exposure)}" class="state-shape" tabindex="0" role="button" data-state="${esc(name)}" aria-label="${esc(description)}"><title>${esc(description)}</title></path>`;}).join('')}</svg>`;
}
const mapCoordinates = {
  Maharashtra: {lat: 19.076, lng: 72.8777},
  'Uttar Pradesh': {lat: 26.8467, lng: 80.9462},
  'Tamil Nadu': {lat: 13.0827, lng: 80.2707},
  Telangana: {lat: 17.385, lng: 78.4867},
  'West Bengal': {lat: 22.5726, lng: 88.3639},
  Delhi: {lat: 28.6139, lng: 77.209}
};
function loadGoogleMaps() {
  if (!meta.google_maps_api_key) return Promise.reject(new Error('Google Maps is not configured. Add GOOGLE_MAPS_API_KEY to .env.'));
  if (googleMapsPromise) return googleMapsPromise;
  googleMapsPromise = new Promise((resolve, reject) => {
    const callback = `__scamserpMapsReady${Date.now()}`;
    window[callback] = () => { delete window[callback]; resolve(window.google.maps); };
    const script = document.createElement('script');
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(meta.google_maps_api_key)}&callback=${callback}&v=weekly&loading=async`;
    script.async = true;
    script.onerror = () => { delete window[callback]; reject(new Error('Google Maps could not be loaded. Check the API key restrictions and enabled Maps JavaScript API.')); };
    document.head.appendChild(script);
  });
  return googleMapsPromise;
}
async function renderGoogleMap(states) {
  const target = $('#google-map');
  if (!target) return;
  try {
    const maps = await loadGoogleMaps();
    const map = new maps.Map(target, {center: {lat: 21.5, lng: 79}, zoom: 5, streetViewControl: false, mapTypeControl: false, fullscreenControl: true});
    states.filter(s => mapCoordinates[s.state]).forEach(s => {
      const marker = new maps.Marker({map, position: mapCoordinates[s.state], title: `${s.state}: ${s.exposure == null ? 'No data' : `${s.exposure}% exposure`}`});
      const info = new maps.InfoWindow({content: `<strong>${esc(s.state)}</strong><br>${s.exposure == null ? 'No eligible data' : `${esc(String(s.exposure))}% weighted exposure`}<br>${esc(String(s.n_runs))} eligible runs`});
      marker.addListener('click', () => { info.open({map, anchor: marker}); selectState(s.state).catch(error => toast(error.message)); });
    });
  } catch (error) {
    target.innerHTML = `<div class="map-error" role="alert">${esc(error.message)}</div>`;
  }
}
function miniTrend(data) {
  const rows=data.filter(d=>d.exposure!=null); if(!rows.length) return empty('Insufficient trend data');
  const p = rows.map((r,i)=>[40+i*(500/Math.max(1,rows.length-1)),130-r.exposure]);
  return `<svg class="chart-svg" viewBox="0 0 580 165" role="img" aria-label="Exposure over collection dates"><path d="M40 30H540 M40 80H540 M40 130H540" stroke="#e4e8dc" fill="none"/><text x="4" y="34">100%</text><text x="7" y="84">50%</text><text x="15" y="134">0%</text><path d="${p.map((x,i)=>(i?'L':'M')+x.join(',')).join(' ')}" stroke="#60814d" stroke-width="2.5" fill="none"/>${p.map((x,i)=>`<circle cx="${x[0]}" cy="${x[1]}" r="4" fill="#60814d"><title>${rows[i].date}: ${rows[i].exposure}% (${rows[i].n_runs} runs)</title></circle><text x="${x[0]}" y="156" text-anchor="middle">${esc(rows[i].date.slice(5))}</text>`).join('')}</svg>`;
}
async function mapPage(id) { return RiskMap.render(id); }
async function selectState(state) {
  const path=$$('[data-state]').find(p=>p.tagName.toLowerCase()==='path' && p.dataset.state===state);
  $$('.state-shape').forEach(p=>p.classList.toggle('selected',p.dataset.state===state));
  if($('#map-tooltip')) $('#map-tooltip').textContent = path?.getAttribute('aria-label') || state;
  const data=await api(`/api/states/${encodeURIComponent(state)}/queries?${new URLSearchParams(mapFilters)}`);
  if(!$('#state-detail')) return;
  $('#state-detail').innerHTML=`<section class="card"><div class="section-line"><div><div class="eyebrow">As seen from ${esc(meta.states[state] || state)}</div><h2>${esc(state)} · query evidence</h2></div><span class="pill">${data.items.length} top queries</span></div>${data.items.length ? data.items.map(q=>`<div class="query-row"><div><a href="#query/${encodeURIComponent(q.id)}?state=${encodeURIComponent(state)}">${esc(q.text)} ↗</a><small>${esc(meta.languages[q.language] || q.language)} · ${q.n_runs} eligible runs</small></div><span class="badge">${percent(q.exposure)} exposure</span></div>`).join('') : empty('No eligible published runs for this state',data.note || 'Try another filter or location.')}</section>`;
}
async function researchPage(id) {
  const [queries, watch, campaigns, evaluation]=await Promise.all([api('/api/queries?'+new URLSearchParams(queryFilters)),api('/api/autocomplete/watchlist'),api('/api/campaigns'),api('/api/evaluation')]);
  if(id!==currentRoute) return;
  $('#main').innerHTML=`${head('Evidence library','Research you can inspect.', 'Trace a finding back to the query, position, source snippet and rules that produced it.')}<div class="action-row"><a class="btn secondary" href="/api/export?format=csv">CSV dataset ↓</a><a class="btn secondary" href="/api/export?format=json">JSON dataset ↓</a><a class="btn secondary" href="/api/digest?format=html" target="_blank" rel="noopener">Weekly digest ↗</a><a class="btn secondary" href="/api/data-dictionary" target="_blank" rel="noopener">Data dictionary ↗</a></div><div class="tab-links"><button class="active" data-research-tab="queries">Query library</button><button data-research-tab="autocomplete">Autocomplete watch</button><button data-research-tab="campaigns">Campaign clusters</button><button data-research-tab="evaluation">Quality & limitations</button></div><div id="research-content"><section class="card"><form id="query-search" class="filters"><label>Search query<input name="search" type="search" value="${esc(queryFilters.search)}" placeholder="Search entity or phrase…"></label><label>Language<select name="language">${selectOptions([['all','All languages'],...Object.entries(meta.languages)],queryFilters.language)}</select></label><label>Category<select name="category">${selectOptions([['all','All categories'],...meta.categories.map(c=>[c,c])],queryFilters.category)}</select></label><button class="btn small">Apply</button></form><div class="section-line"><h3>Versioned query library</h3><span class="count-label">${num(queries.total)} matching seed queries</span></div>${queries.items.length ? queries.items.map(q=>`<div class="query-row"><div><a href="#query/${encodeURIComponent(q.id)}">${esc(q.text)} ↗</a><small>${esc(q.entity_name)} · ${esc(meta.languages[q.language])} · Tier ${q.tier} · ${esc(q.origin)}</small></div><span class="badge">${q.runs} runs</span></div>`).join('') : empty('No queries match your filters')}<div class="action-row">${queryFilters.offset > 0 ? '<button class="btn secondary small" data-page="prev">← Previous</button>' : ''}${queryFilters.offset+queries.items.length < queries.total ? '<button class="btn secondary small" data-page="next">Next queries →</button>' : ''}</div><p class="hint">Native-speaker review of seed translations remains a launch requirement. Autocomplete expansions enter the inactive review queue.</p></section></div>`;
  const queryHtml=$('#research-content').innerHTML;
  const bindQuery=()=>{const form=$('#query-search'); if(form)form.addEventListener('submit',e=>{e.preventDefault(); queryFilters={...Object.fromEntries(new FormData(form)),offset:0};navigate();});};
  bindQuery();
  $$('[data-research-tab]').forEach(button=>button.addEventListener('click',()=>{
    $$('[data-research-tab]').forEach(b=>b.classList.toggle('active',b===button));
    const tab=button.dataset.researchTab;
    if(tab==='queries'){ $('#research-content').innerHTML=queryHtml;bindQuery(); }
    if(tab==='autocomplete') $('#research-content').innerHTML=`<section class="card"><h2>Autocomplete watch</h2><p>Wording to monitor, never an accusation. Suggestions are not included in ranked exposure.</p>${watch.items.length ? watch.items.slice(0,60).map(w=>`<div class="query-row"><div><strong>${esc(w.text)}</strong><small>${esc(w.entity)} · ${esc(meta.languages[w.language])} · First ${date(w.first_seen)} · Last ${date(w.last_seen)}</small></div><span class="badge">${w.seen} sightings</span></div>`).join('') : empty('No autocomplete observations yet')}</section>`;
    if(tab==='campaigns') $('#research-content').innerHTML=`<section class="card"><h2>Reviewed infrastructure clusters</h2><p>Observations connected by shared domains, phones or advertiser identifiers. Personal advertiser identities are omitted.</p>${campaigns.items.length ? campaigns.items.map(c=>`<div class="query-row"><div><a href="#campaign/${encodeURIComponent(c.id)}">${esc(c.id)} ↗</a><small>First ${date(c.first_seen)} · Latest ${date(c.last_seen)} · ${esc(c.review_state)}</small></div><span class="badge">${num(c.size)} observations</span></div>`).join('') : empty('No reviewed campaigns published')}</section>`;
    if(tab==='evaluation') $('#research-content').innerHTML=evaluationHtml(evaluation);
  }));
}
function evaluationHtml(e) { return `<section class="card"><div class="eyebrow">Honest quality reporting</div><h2>Real-world evaluation is pending.</h2><p>Measured precision and recall require independent labels. Regression tests verify rule behavior; they do not establish real-world accuracy.</p><div class="evidence-strip"><div class="stat"><strong>${e.real.n}</strong><span>Independent real observation labels</span></div><div class="stat"><strong>${e.real.precision == null ? 'Not measured' : e.real.precision*100+'%'}</strong><span>Likely Fraud precision</span></div><div class="stat"><strong>${e.real.recall == null ? 'Not measured' : e.real.recall*100+'%'}</strong><span>Likely Fraud recall</span></div><div class="stat"><strong>300</strong><span>Target human-labelled observations</span></div></div><h3>Before public launch</h3><ul>${e.limitations.map(x=>`<li class="hint">${esc(x)}</li>`).join('')}</ul><p class="hint">Rule version: ${esc(e.rule_version)}. Targets of 90% precision and 70% recall are goals, not results.</p><a href="#methodology">Read the trust model →</a></section>`; }
async function registryPage(id) {
  const data=await api('/api/registry'); if(id!==currentRoute)return;
  const entities=meta.entities;
  $('#main').innerHTML=`${head('Registry first','The source matters.', 'Official contacts need primary-source evidence, a verification date and a future recheck date. Pending entries never confer official status.')}<form class="filters" id="registry-filter"><label>Entity<select name="entity">${selectOptions([['all','All entities'],...entities.map(e=>[e.id,e.name])],'all')}</select></label><label>Review state<select name="status">${selectOptions([['all','All entries'],['current','Current source checks'],['pending','Needs review']],'all')}</select></label><button class="btn secondary small" type="button" data-action="suggest">Suggest a correction</button></form><section class="card"><div id="registry-records"></div></section><p class="hint">Four entities have assistant primary-source checks dated 9 Oct 2026; all 40 need independent human verification before launch. Source checks expire after 30 days.</p>`;
  const render=()=>{const form=new FormData($('#registry-filter')); const rows=data.records.filter(r=>(form.get('entity')==='all'||r.entity_id===form.get('entity'))&&(form.get('status')==='all'||(form.get('status')==='current'?r.current:!r.current))); $('#registry-records').innerHTML=rows.length ? rows.map(r=>`<div class="source-record"><div><a href="#entity/${encodeURIComponent(r.entity_id)}"><strong>${esc(r.entity_name)} ↗</strong></a><div>${esc(r.kind)} · ${esc(r.display)}</div><a href="${safeUrl(r.source_url)}" target="_blank" rel="noopener noreferrer">Primary-source reference ↗</a><small>Verified ${date(r.verified_at)} · Recheck ${date(r.expires_at)} · ${esc(r.verifier)}</small></div><div>${r.current ? badge('Verified Official') : badge('Unverified')}</div></div>`).join('') : empty('No registry entries match');}; render(); $('#registry-filter').addEventListener('change',render);
}
async function queryPage(qid,state,id) {
  const data=await api('/api/queries/'+encodeURIComponent(qid)+(state?'?state='+encodeURIComponent(state):'')); if(id!==currentRoute)return;
  $('#main').innerHTML=`<div class="breadcrumbs"><a href="#research">Research</a> / Query evidence</div>${head('Annotated search results',data.query.text,`${data.query.entity_name} · ${meta.languages[data.query.language]} · Tier ${data.query.tier}`)}${data.run ? `<section class="card"><div class="evidence-meta"><span>As seen from ${esc(data.run.location)}</span><span>${date(data.run.fetched_at)}</span><span>Engine: ${esc(data.run.engine)}</span><span>Search ID: ${esc(data.run.search_id)}</span></div><p class="hint">${data.run.demo ? 'All displayed results are synthetic fixtures, not captured Google results.' : 'Collected through SerpApi. Results may differ for other users.'} ${data.withheld ? data.withheld+' findings withheld pending review.' : ''}</p>${data.results.map(r=>evidenceCard(r)).join('')}</section>` : empty('No published evidence for this query yet.','Run a budgeted collection from the review workspace in live mode.')}<section class="card wide-card"><h3>Recent collection history</h3><div class="table-scroll"><table><thead><tr><th>Time</th><th>Location</th><th>Engine</th><th>Status</th></tr></thead><tbody>${data.runs.map(r=>`<tr><td>${date(r.fetched_at)}</td><td>${esc(r.state)}</td><td>${esc(r.engine)}</td><td>${esc(r.status)}</td></tr>`).join('') || '<tr><td colspan="4">No runs yet</td></tr>'}</tbody></table></div></section>`;
}
async function entityPage(eid,id) {
  const data=await api('/api/entities/'+encodeURIComponent(eid)+'/report'); if(id!==currentRoute)return;
  $('#main').innerHTML=`<div class="breadcrumbs"><a href="#registry">Registry</a> / Entity report</div>${head('Entity report',data.entity.name,`${data.entity.category} · Current 30-day collected sample`)}<section class="card"><h2>${percent(data.summary.exposure)} weighted exposure</h2><p>${data.summary.n_runs} eligible runs · ${data.summary.n} ranked observations.</p>${officialPanel({domains:data.registry.filter(r=>r.current&&r.kind==='domain'),phones:data.registry.filter(r=>r.current&&r.kind==='phone')})}</section><section class="card wide-card"><h3>Published evidence</h3>${data.findings.map(r=>evidenceCard(r)).join('') || empty('No published findings')}</section>`;
}
async function campaignPage(cid,id) {
  const data=await api('/api/campaigns/'+encodeURIComponent(cid)); if(id!==currentRoute)return;
  $('#main').innerHTML=`<div class="breadcrumbs"><a href="#research">Research</a> / Campaign cluster</div>${head('Reviewed evidence cluster',cid,`${data.campaign.size} linked observations · first ${date(data.campaign.first_seen)} · last ${date(data.campaign.last_seen)}`)}<section class="card"><p>Connected by shared infrastructure. This does not identify an individual or prove that every result has the same operator.</p>${data.findings.map(r=>evidenceCard(r)).join('')}</section>`;
}
function methodologyPage() {
  $('#main').innerHTML=`${head('Transparent by design','Signals, not guesswork.', 'Every verdict comes from a versioned rule model. No language model decides whether a result is fraudulent.')}<section class="card"><div class="method-step"><h3><span class="number">1</span>Start with current official records</h3><p>A source-checked domain with matching contact numbers is Verified Official. Phone-only lookups can match a current phone record. Expired and pending entries remain Unverified.</p></div><div class="method-step"><h3><span class="number">2</span>Show the reasons behind the score</h3><div class="table-scroll"><table><thead><tr><th>Signal family</th><th>Evidence</th><th>Points</th></tr></thead><tbody><tr><td>Identity</td><td>Unlisted domain · lookalike · brand token</td><td>25 · 30 · 15</td></tr><tr><td>Contact</td><td>Unmatched contact · reused across unrelated domains</td><td>35 · 20</td></tr><tr><td>Infrastructure</td><td>Under 90 days old · free hosting</td><td>20 · 15</td></tr><tr><td>Ad behavior</td><td>Explicitly unverified / unlinked advertiser · new account</td><td>20 · 15</td></tr><tr><td>Local</td><td>Listing contact conflicts with verified entity registry</td><td>25</td></tr><tr><td>Mitigators</td><td>Government domain · reputable / authorized intermediary</td><td>−40 · −20</td></tr></tbody></table></div><p class="hint">Scores clamp to 0–100. Missing advertiser, domain-age or phone-registry data is a gap and never a negative signal.</p></div><div class="method-step"><h3><span class="number">3</span>Use conservative verdicts</h3><p>${badge('No Issue Found')} below 20, with no unexplained contact. ${badge('Unverified')} 20–49, unresolved entity or sparse contact evidence. ${badge('Suspicious')} 50–74, or a high score from one family. ${badge('Likely Fraud')} 75+ with at least two independent families and campaign review.</p><p>No Issue Found means no adverse signals in this observation. It is not a guarantee of safety. Unknown items return No data.</p></div><div class="method-step"><h3><span class="number">4</span>Measure what a searcher could see</h3><p>Ads receive weight 1.5. Organic and local result rank r receive weight 1/r. Exposure is the weighted share of Suspicious or Likely Fraud results in a complete eligible run, then averaged over runs. Autocomplete and other unranked surfaces are excluded.</p><p>States with fewer than ${meta.min_runs} runs are grey. Confidence intervals use a query-cluster bootstrap and describe the sampled query library. They do not estimate national fraud prevalence. Disputed and unreviewed results withhold the whole ranked run.</p></div><div class="method-step"><h3><span class="number">5</span>Make correction possible</h3><p>Public suggestions require review. New Likely Fraud campaigns remain private until reviewed. Disputing a finding hides it immediately. Source history, raw response archives and rule revisions remain available to administrators.</p></div></section>${safety()}`;
}
async function adminPage(id) {
  $('#main').innerHTML=`${head('Protected operations','Review workspace.', 'Manage source checks, review findings and keep live collection within its budget.')}<section class="card"><form id="admin-login" class="filters"><label>Admin token<input id="admin-token" type="password" autocomplete="off" required placeholder="SCAMSERP_ADMIN_TOKEN"></label><button class="btn">Unlock workspace</button><button class="btn secondary" type="button" data-action="admin-lock">Lock</button></form><p class="hint">Token stays in this tab’s memory and is sent only to this server. Configure it in the server environment. Admin access is disabled when no token is configured.</p><div id="admin-content"></div></section>`;
  $('#admin-login').addEventListener('submit',async e=>{e.preventDefault();adminToken=$('#admin-token').value;$('#admin-token').value=''; await loadAdmin();});
  if(adminToken) await loadAdmin();
}
async function adminApi(path,body) { return api(path,{method:body?'POST':'GET',headers:{Authorization:'Bearer '+adminToken},...(body?{body:JSON.stringify(body)}:{})}); }
async function loadAdmin() {
  try {
    const data=await adminApi('/api/admin/overview');
    $('#admin-content').innerHTML=`<div class="evidence-strip"><div class="stat"><strong>${data.mode}</strong><span>Dataset isolation mode</span></div><div class="stat"><strong>${data.budget.daily_used} / ${data.budget.daily_cap}</strong><span>Today's reserved requests (UTC)</span></div><div class="stat"><strong>${data.budget.monthly_used} / ${data.budget.monthly_cap}</strong><span>Month's reserved requests (UTC)</span></div><div class="stat"><strong>${data.api_configured?'Ready':'No key'}</strong><span>SerpApi integration</span></div></div><h3>Registry editor</h3><form id="registry-editor" class="admin-grid"><label>Entity<select name="entity_id">${selectOptions(meta.entities.map(e=>[e.id,e.name]),'sbi')}</select></label><label>Kind<select name="kind">${selectOptions(['domain','phone','social','email','intermediary'].map(v=>[v,v]),'domain')}</select></label><label>Value<input name="value" required placeholder="sbi.bank.in"></label><label>Display label<input name="display" required placeholder="sbi.bank.in"></label><label class="full">Primary source URL<input name="source_url" type="url" required placeholder="https://…"></label><label>Verifier<input name="verifier" required minlength="2" placeholder="Reviewer name / role"></label><label>Status<select name="status">${selectOptions(['pending','verified','rejected'].map(v=>[v,v]),'pending')}</select></label><label>Verified at (ISO timestamp)<input name="verified_at" placeholder="2026-10-09T00:00:00+00:00"></label><label>Expires at (ISO timestamp)<input name="expires_at" placeholder="2026-11-08T00:00:00+00:00"></label><div class="full"><button class="btn small">Save and rescore</button></div></form><p class="hint">Verification requires your source review. Shared platform roots cannot be authorized as an entity domain.</p><div class="method-step"><h3>Collect a query</h3><form id="collect-form" class="filters"><label>Query ID<input name="query_id" value="sbi-en-1" required></label><label>Location<select name="state">${selectOptions(Object.keys(meta.states).map(v=>[v,v]),'Delhi')}</select></label><label>Engine<select name="engine">${selectOptions(['google','google_autocomplete','google_local'].map(v=>[v,v]),'google')}</select></label><button class="btn small">Collect with budget</button></form><p class="hint">Live mode and a SerpApi key are required. Each retry reserves a request; the cap cannot be bypassed by concurrency.</p></div><div class="method-step"><h3>Campaign review queue</h3>${data.campaigns.length ? data.campaigns.slice(0,20).map(c=>`<div class="query-row"><div><strong>${esc(c.id)}</strong><small>${c.size} observations · ${esc(c.review_state)}</small><button class="text-button" data-admin-evidence="${esc(c.id)}">Inspect private evidence</button></div><div class="action-row"><button class="btn secondary small" data-admin-review="${esc(c.id)}" data-decision="approved">Approve</button><button class="btn secondary small" data-admin-review="${esc(c.id)}" data-decision="rejected">Reject</button></div></div>`).join('') : empty('No campaigns awaiting review')}</div><div class="method-step"><h3>Pending disputes</h3>${data.disputes.length ? data.disputes.map(d=>`<div class="query-row"><div><strong>${esc(d.id)}</strong><p>${esc(d.message)}</p><small>Finding ${esc(d.target_id)}</small></div><div class="action-row"><button class="btn secondary small" data-dispute-review="${esc(d.id)}" data-decision="approved">Uphold</button><button class="btn secondary small" data-dispute-review="${esc(d.id)}" data-decision="rejected">Reject dispute</button></div></div>`).join('') : '<p class="hint">No pending disputes.</p>'}</div><div class="method-step"><h3>Registry suggestions & query candidates</h3><p class="hint">${data.suggestions.length} suggestions · ${data.query_candidates.length} inactive autocomplete candidates. Use the API docs for full review operations.</p>${data.suggestions.map(s=>`<div class="query-row"><div><strong>${esc(s.entity_id)} · ${esc(s.value)}</strong><small>${esc(s.source_url)}</small></div><button class="btn secondary small" data-suggestion-review="${esc(s.id)}">Review suggestion</button></div>`).join('')}${data.query_candidates.slice(0,10).map(q=>`<div class="query-row"><div><strong>${esc(q.text)}</strong><small>${esc(q.id)} · ${esc(q.language)}</small></div><button class="btn secondary small" data-query-activate="${esc(q.id)}">Activate</button></div>`).join('')}</div><div class="method-step"><h3>Collection gaps</h3>${data.failures.slice(0,10).map(f=>`<div class="query-row"><div><strong>${esc(f.engine)} · ${esc(f.state)}</strong><small>${date(f.fetched_at)} · ${esc(f.status)} · ${esc(f.error || 'No structured results returned')}</small></div></div>`).join('') || '<p class="hint">No collection gaps recorded.</p>'}</div>`;
    renderAdminTools(data);
    $('#registry-editor').addEventListener('submit',async e=>{e.preventDefault();const body=Object.fromEntries(new FormData(e.target));for(const key of ['verified_at','expires_at'])if(!body[key])body[key]=null;await adminAction('/api/admin/registry',body,'Registry saved; historical scores updated.');});
    $('#collect-form').addEventListener('submit',async e=>{e.preventDefault();await adminAction('/api/admin/collect',Object.fromEntries(new FormData(e.target)),'Collection complete.');});
  } catch(e) { showError(e,'#admin-content'); }
}
async function adminAction(path,body,message) { try { await adminApi(path,body);toast(message);await loadAdmin(); } catch(e) { toast(e.message); } }
function modal(content) { $('#modal-content').innerHTML=content;$('#modal').showModal(); }
async function reportModal(oid) { const data=await api('/api/report/'+encodeURIComponent(oid));modal(`<h2>Review your report summary</h2><p class="hint">${data.demo?'Synthetic fixtures must not be reported to authorities.':'Review the evidence and submit it yourself using the official channels.'}</p><textarea id="report-copy" class="modal-textarea" readonly aria-label="Generated report summary">${esc(data.text)}</textarea><button class="btn small" data-copy="report-copy">Copy summary</button>${data.demo?'':data.channels.map(c=>`<a class="btn secondary small" href="${safeUrl(c.url)}" target="_blank" rel="noopener noreferrer">${esc(c.name)} ↗</a>`).join('')}`); }
function disputeModal(oid) { modal(`<h2>Request a finding review</h2><p class="hint">The finding will be hidden while it is reviewed. Include the official source and explain the correction. Your message is stored for review; avoid personal details.</p><form id="dispute-form"><label for="dispute-message">Reason for review</label><textarea id="dispute-message" class="modal-textarea" required minlength="10" maxlength="2000"></textarea><button class="btn small">Submit for review</button></form>`);$('#dispute-form').addEventListener('submit',async e=>{e.preventDefault();try{await api('/api/disputes',{method:'POST',body:JSON.stringify({target_id:oid,message:$('#dispute-message').value})});$('#modal').close();toast('Finding hidden pending review.');navigate();}catch(e){toast(e.message);}}); }
function suggestionModal() { modal(`<h2>Suggest an official contact</h2><p class="hint">Suggestions enter a private review queue and never change verdicts automatically.</p><form id="suggestion-form" class="admin-grid"><label>Entity<select name="entity_id">${selectOptions(meta.entities.map(e=>[e.id,e.name]),'sbi')}</select></label><label>Kind<select name="kind"><option>domain</option><option>phone</option></select></label><label class="full">Contact value<input name="value" required></label><label class="full">Official source URL<input name="source_url" type="url" required></label><div class="full"><button class="btn small">Send for review</button></div></form>`);$('#suggestion-form').addEventListener('submit',async e=>{e.preventDefault();const body=Object.fromEntries(new FormData(e.target));try{await api('/api/registry/suggestions',{method:'POST',body:JSON.stringify({...body,display:body.value,verifier:'Public suggestion',status:'pending'})});$('#modal').close();toast('Suggestion queued for review.');}catch(e){toast(e.message);}}); }
function reviewerModal(callback) { modal('<h2>Record your review</h2><p class="hint">Confirm your decision after inspecting the evidence. Your reviewer label is saved in the audit log.</p><form id="reviewer-form"><label for="reviewer-name">Reviewer name or role</label><input id="reviewer-name" required minlength="2" maxlength="100"><div class="action-row"><button class="btn small">Save review</button></div></form>');$('#reviewer-form').addEventListener('submit',e=>{e.preventDefault();const name=$('#reviewer-name').value;$('#modal').close();callback(name);}); }
async function campaignReviewModal(cid,decision) {
  const data=await adminApi('/api/admin/campaigns/'+encodeURIComponent(cid));
  const findings=[...data.findings];
  while(findings.length<data.campaign.size){
    const page=await adminApi('/api/admin/campaigns/'+encodeURIComponent(cid)+'?offset='+findings.length);
    if(page.campaign.evidence_hash!==data.campaign.evidence_hash || !page.findings.length)throw new Error('Campaign evidence changed. Reload the review queue.');
    findings.push(...page.findings);
  }
  modal(`<h2>Review ${esc(cid)}</h2><p class="hint">Inspect all ${num(findings.length)} findings. This decision applies to this evidence version; changes require a new review.</p>${findings.map(r=>evidenceCard(r,false)).join('')}<button id="campaign-decision" class="btn small">${decision==='approved'?'Approve reviewed evidence':'Reject campaign'}</button>`);
  $('#campaign-decision').addEventListener('click',()=>reviewerModal(name=>adminAction('/api/admin/campaigns/'+encodeURIComponent(cid)+'/review',{decision,reviewer:name,evidence_hash:data.campaign.evidence_hash},'Campaign review saved.')));
}
document.addEventListener('submit',e=>{if(e.target.id==='lookup-form'){e.preventDefault();performLookup($('#lookup-input').value);}});
document.addEventListener('click',async e=>{
  const b=e.target.closest('button,[data-state]'); if(!b)return;
  try {
    if(b.dataset.example){$('#lookup-input').value=b.dataset.example;$('#lookup-input').focus();const examples=b.closest('details');if(examples)examples.open=false;}
    if(b.dataset.state)await selectState(b.dataset.state);
    if(b.dataset.report)await reportModal(b.dataset.report);
    if(b.dataset.dispute)disputeModal(b.dataset.dispute);
    if(b.dataset.copy){const input=$('#'+b.dataset.copy);try{await navigator.clipboard.writeText(input.value);toast('Copied.');}catch{input.select();toast('Select and copy the highlighted text.');}}
    if(b.dataset.share){const text=`ScamSERP ${meta.mode==='demo'?'illustrative demo':''}: ${b.dataset.share} — ${b.dataset.verdict}. Check date and source before using this contact. This is an evidence-based check, not a guarantee. ${location.origin}`;if(navigator.share)await navigator.share({title:'ScamSERP contact check',text});else{try{await navigator.clipboard.writeText(text);toast('Verdict copied.');}catch{modal(`<h2>Share this verdict</h2><textarea class="modal-textarea" readonly>${esc(text)}</textarea>`);}}}
    if(b.dataset.live){modal(`<h2>Run a live check</h2><p>This sends the number or domain to SerpApi and uses the server’s credit budget. The raw search metadata is retained for reproducibility. Continue only if you want this item searched.</p><button id="confirm-live" class="btn small">Search with SerpApi</button>`);$('#confirm-live').addEventListener('click',async()=>{try{b.disabled=true;const data=await api('/api/lookup/live',{method:'POST',body:JSON.stringify({text:b.dataset.live})});$('#modal').close();$('#lookup-results').innerHTML=verdictCard(data.result);}catch(e){toast(e.message);}finally{b.disabled=false;}});}
    if(b.dataset.page){queryFilters.offset=Math.max(0,queryFilters.offset+(b.dataset.page==='next'?60:-60));navigate();}
    if(b.dataset.adminReview)await campaignReviewModal(b.dataset.adminReview,b.dataset.decision);
    if(b.dataset.disputeReview)reviewerModal(name=>adminAction(`/api/admin/disputes/${encodeURIComponent(b.dataset.disputeReview)}/review`,{decision:b.dataset.decision,reviewer:name},'Dispute review saved.'));
    if(b.dataset.adminEvidence){const data=await adminApi('/api/admin/campaigns/'+encodeURIComponent(b.dataset.adminEvidence));modal(`<h2>${esc(data.campaign.id)}</h2>${data.findings.map(r=>evidenceCard(r,false)).join('')}`);}
    if(b.dataset.suggestionReview)reviewerModal(name=>adminAction(`/api/admin/suggestions/${encodeURIComponent(b.dataset.suggestionReview)}/review`,{decision:'approved',reviewer:name},'Suggestion marked reviewed; verify using the registry editor.'));
    if(b.dataset.queryActivate)reviewerModal(name=>adminAction(`/api/admin/queries/${encodeURIComponent(b.dataset.queryActivate)}/review`,{decision:'approved',reviewer:name},'Query activated.'));
    if(b.dataset.action==='reload')navigate();
    if(b.dataset.action==='suggest')suggestionModal();
    if(b.dataset.action==='admin-lock'){adminToken='';$('#admin-content').innerHTML='';toast('Workspace locked.');}
  } catch(error){if(error.name!=='AbortError')toast(error.message);}
});
document.addEventListener('keydown',e=>{if(e.target.matches('.state-shape')&&['Enter',' '].includes(e.key)){e.preventDefault();selectState(e.target.dataset.state).catch(x=>toast(x.message));}});
$('#language').addEventListener('click',()=>{ui=ui==='en'?'hi':'en';localStorage.setItem('scamserp-language',ui);navigate();});
$('.modal-close').addEventListener('click',()=>$('#modal').close());
$('#modal').addEventListener('click',e=>{if(e.target===$('#modal')){const r=$('#modal').getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)$('#modal').close();}});
async function navigate() {
  AuditDashboard.leave();
  RiskMap.leave();
  document.body.classList.remove('map-mode');
  const id=++currentRoute;updateShell();loading();
  const raw=(location.hash || '#lookup').slice(1);const [path,qs]=raw.split('?');const [page,value]=path.split('/');const state=new URLSearchParams(qs || '').get('state');
  document.body.dataset.page=page;
  $$('.nav-more[open]').forEach(menu=>menu.open=false);
  try {
    if(page==='lookup')lookupPage();
    else if(page==='map')await mapPage(id);
    else if(page==='audits')await AuditDashboard.render(id);
    else if(page==='research')await researchPage(id);
    else if(page==='registry')await registryPage(id);
    else if(page==='query')await queryPage(decodeURIComponent(value),state,id);
    else if(page==='entity')await entityPage(decodeURIComponent(value),id);
    else if(page==='campaign')await campaignPage(decodeURIComponent(value),id);
    else if(page==='methodology')methodologyPage();
    else if(page==='admin')await adminPage(id);
    else $('#main').innerHTML=empty('Page not found','Use the navigation to continue.');
    document.title=`${page==='lookup'?'Check before you trust':page.charAt(0).toUpperCase()+page.slice(1)} — ScamSERP`;
  } catch(e){if(id===currentRoute)showError(e);}
}
window.addEventListener('hashchange',()=>{navigate();window.scrollTo({top:0,behavior:'instant'});});
(async()=>{try{meta=await api('/api/meta');await navigate();}catch(e){showError(e);}})();

document.addEventListener('click',e=>{if(!e.target.closest('.nav-more') || e.target.closest('.nav-more-menu a'))$$('.nav-more[open]').forEach(menu=>menu.open=false);});
document.addEventListener('keydown',e=>{if(e.key==='Escape')$$('.nav-more[open],.map-extra-categories[open]').forEach(menu=>{menu.open=false;menu.querySelector('summary').focus();});});
$('.skip').addEventListener('click',e=>{e.preventDefault();$('#main').focus({preventScroll:true});$('#main').scrollIntoView({behavior:'instant',block:'start'});});
