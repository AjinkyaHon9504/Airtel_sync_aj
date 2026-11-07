const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
const api = async (path, body, method) => {
  const r = await fetch(path, { method: method || (body ? "POST" : "GET"), headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
};
const inr = n => "₹" + Number(n || 0).toLocaleString("en-IN");
const md = t => String(t).replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
let S = { sid: null, data: null, term: 12, orderId: null };

/* ---------- navigation ---------- */
$$("nav button").forEach(b => b.onclick = () => { $$("nav button").forEach(x => x.classList.toggle("on", x === b)); $$(".view").forEach(v => v.classList.toggle("on", v.id === b.dataset.view)); if (b.dataset.view === "office") loadOffice(); });
const go = step => { $$("#steps button").forEach(x => x.classList.toggle("on", x.dataset.step === step)); $$(".step").forEach(v => v.classList.toggle("on", v.id === step)); if (step === "quote") renderQuote(); if (step === "kyc") renderConsent(); };
$$("#steps button").forEach(b => b.onclick = () => go(b.dataset.step));

/* ---------- advisor ---------- */
const bubble = (text, who = "bot", cls = "") => { const d = document.createElement("div"); d.className = `b ${who} ${cls}`; d.innerHTML = md(text); $("#log").appendChild(d); $("#log").scrollTop = 1e9; };
async function start() {
  $("#log").innerHTML = ""; S.data = null;
  const r = await api("/api/advisor/start", { lang: $("#lang").value });
  S.sid = r.session_id; show(r);
}
function show(r) {
  S.data = r;
  r.replies.forEach(t => bubble(t));
  $("#aiBadge").textContent = r.llm ? "Gemini + rules" : "rules (offline)"; $("#aiBadge").classList.toggle("ai", r.llm);
  const chips = $("#chips"); chips.innerHTML = "";
  if (r.handoff) bubble("📞 A callback has been booked. Reference: **" + r.lead_id + "**", "bot", "cta");
  if (r.quote_ready && r.recommendation) {
    const c = document.createElement("button"); c.textContent = "See my quote →"; c.className = "primary"; c.onclick = () => go("quote"); chips.appendChild(c);
    ["Too expensive", "Add CCTV", "No security", "How long to install?", "Talk to a person"].forEach(t => { const b = document.createElement("button"); b.textContent = t; b.onclick = () => say(t); chips.appendChild(b); });
  } else if (!r.handoff) {
    ["Internet + UPI billing", "WhatsApp for customers", "CCTV", "Backup internet", "GST: yes", "GST: no"].forEach(t => { const b = document.createElement("button"); b.textContent = t; b.onclick = () => say(t.replace("GST: yes", "yes we have GST").replace("GST: no", "no GST")); chips.appendChild(b); });
  }
  renderWhy(r);
}
async function say(text) {
  if (!text.trim()) return;
  bubble(text, "me");
  try { show(await api("/api/advisor/message", { session_id: S.sid, text })); } catch (e) { bubble("⚠️ " + e.message); }
}
$("#send").onsubmit = e => { e.preventDefault(); const t = $("#msg").value; $("#msg").value = ""; say(t); };
$("#restart").onclick = start; $("#lang").onchange = start;
$$(".eg").forEach(b => b.onclick = () => { go("chat"); say(b.textContent); });

// voice input (Web Speech API, works in Chrome/Edge; Indian locales)
const LOC = { en: "en-IN", hi: "hi-IN", hinglish: "hi-IN", mr: "mr-IN", ta: "ta-IN", te: "te-IN", bn: "bn-IN", gu: "gu-IN", kn: "kn-IN" };
$("#mic").onclick = () => {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return bubble("Voice input needs Chrome or Edge.");
  const r = new SR(); r.lang = LOC[$("#lang").value] || "en-IN"; r.interimResults = false;
  $("#mic").classList.add("rec"); r.onresult = e => say(e.results[0][0].transcript); r.onend = () => $("#mic").classList.remove("rec"); r.start();
};

function renderWhy(r) {
  const p = r.profile || {}, seg = { micro: "Micro retail & services", prof: "Professional office", multi: "Multi-site", mfg: "Small manufacturer" };
  const kv = [["Business", p.business_type], ["Segment", seg[p.segment]], ["City", p.city ? `${p.city} (tier ${p.city_tier ?? "?"})` : null], ["Staff", p.employees], ["Sites", p.sites],
    ["GST", p.gstin ? `${p.gstin.slice(0, 2)}••••••••${p.gstin.slice(-3)} · ${p.gstin_status}` : p.has_gst === true ? "yes" : p.has_gst === false ? "no" : null], ["Needs", (p.needs || []).join(", ")], ["Declined", (p.removed || []).join(", ")]];
  let h = "<h4>Behind the screen</h4>" + kv.filter(x => x[1] || x[1] === 0).map(([k, v]) => `<div class="kv"><span class="muted">${k}</span><b>${md(v)}</b></div>`).join("");
  const rec = r.recommendation;
  if (rec) {
    h += `<p class="small muted" style="margin-top:8px">Rules applied: city tier, min staff/sites, GST requirement and product dependencies from <code>product_catalogue.csv</code>. Prices = catalogue midpoint.</p>`;
    if (rec.blocked.length) h += rec.blocked.map(b => `<div class="small">⛔ ${md(b.name)}: ${md(b.reason)}</div>`).join("");
  }
  $("#why").innerHTML = h;
}

/* ---------- quote ---------- */
function renderQuote() {
  const r = S.data, el = $("#quoteBody");
  if (!r || !r.recommendation) { el.innerHTML = '<p class="muted">Chat with the advisor first — your bundle appears here.</p>'; return; }
  const rec = r.recommendation, tier = r.selected_tier, q = rec.tiers[tier];
  const names = { essential: "Essential", recommended: "Recommended", complete: "Complete" };
  let h = `<div class="tiers">${Object.entries(rec.tiers).map(([k, t]) => `<button data-tier="${k}" class="${k === tier ? "on" : ""}">${names[k]}<b>${inr(t.monthly)}</b></button>`).join("")}</div>`;
  h += `<div class="card"><div class="muted small">One monthly bill · ${q.contract_months}-month contract</div><div class="total">${inr(q.monthly)}<small> /month + ${inr(q.gst)} GST</small></div>
  <div class="small muted">One-time setup ${inr(q.setup)}${q.setup_waived ? ` — <b style="color:var(--ok)">waived on 24 months</b>` : ""} · First bill ${inr(q.first_bill)} · Live in ~${q.install_days} days</div>
  <div class="term">${[12, 24].map(t => `<button data-term="${t}" class="${q.contract_months == t || (t == 12 && q.contract_months < 24 && S.term == 12) ? "on" : ""}">${t} months${t == 24 ? " · no setup fee" : ""}</button>`).join("")}</div></div>`;
  h += `<div class="card"><h3>What's in it — switch add-ons on/off</h3>` + q.lines.map((l, i) => `<div class="line"><div class="tog"><input type="checkbox" checked data-pid="${l.product_id}" ${i === 0 ? "disabled" : ""}><div><div class="n">${md(l.name)} ${l.qty > 1 ? "× " + l.qty : ""}</div><div class="d">${md((q.why[i] || "").split(": ").slice(1).join(": "))}</div></div></div><div class="p">${inr(l.monthly)}</div></div>`).join("");
  const all = new Set(Object.values(rec.tiers).flatMap(t => t.lines.map(l => l.product_id)));
  const extra = [...all].filter(p => !q.lines.find(l => l.product_id === p));
  if (extra.length) {
    const lines = Object.values(rec.tiers).flatMap(t => t.lines);
    h += `<div class="muted small" style="margin-top:10px">Add more:</div>` + extra.map(p => { const l = lines.find(x => x.product_id === p); return `<div class="line"><div class="tog"><input type="checkbox" data-pid="${p}"><div class="n">${md(l.name)}</div></div><div class="p muted">+${inr(l.unit_price)}/${l.unit.replace("per ", "")}</div></div>`; }).join("");
  }
  h += `</div>`;
  if (rec.blocked.length) h += `<div class="blocked"><b>Not available yet</b>${rec.blocked.map(b => `<div>• ${md(b.name)} — ${md(b.reason)}</div>`).join("")}${rec.fixes.map(f => `<div style="margin-top:6px">💡 ${md(f)}</div>`).join("")}</div>`;
  h += `<button id="toKyc" class="primary wide">Looks good — continue to KYC</button><p class="muted small">Prices exclude 18% GST, shown separately. No hidden charges: what you see is your monthly bill.</p>`;
  el.innerHTML = h;
  el.querySelectorAll("[data-tier]").forEach(b => b.onclick = async () => { S.data = await api("/api/advisor/select", { session_id: S.sid, tier: b.dataset.tier }); renderQuote(); });
  el.querySelectorAll("[data-term]").forEach(b => b.onclick = async () => { S.term = +b.dataset.term; S.data = await api("/api/advisor/select", { session_id: S.sid, term: S.term, tier }); renderQuote(); });
  el.querySelectorAll("[data-pid]").forEach(c => c.onchange = async () => { S.data = await api("/api/advisor/select", { session_id: S.sid, toggles: { [c.dataset.pid]: c.checked }, tier, term: S.term }); renderQuote(); });
  $("#toKyc").onclick = () => go("kyc");
}

/* ---------- KYC ---------- */
let NOTICE = null;
async function renderConsent() {
  if (!NOTICE) NOTICE = await api("/api/kyc/notice");
  $("#purposes").innerHTML = `<div class="purp">${Object.entries(NOTICE.purposes).map(([k, v]) => `<label><input type="checkbox" value="${k}" ${k !== "marketing" ? "checked" : ""} ${k === "kyc" ? "disabled" : ""}> <span>${md(v)}${k === "kyc" ? " <b>(required)</b>" : ""}</span></label>`).join("")}</div><p class="small muted">Notice ${NOTICE.version} · retention ${NOTICE.retention_days} days · grievance: ${NOTICE.grievance}</p>`;
  const sp = $("#specimen"); if (sp.options.length < 3) for (let i = 1; i <= 12; i++) sp.add(new Option("Specimen K" + String(i).padStart(2, "0"), "K" + String(i).padStart(2, "0")));
}
$("#giveConsent").onclick = async () => {
  if (!S.sid) await start();
  const purposes = ["kyc", ...$$("#purposes input:checked").map(i => i.value).filter(v => v !== "kyc")];
  const r = await api("/api/kyc/consent", { session_id: S.sid, purposes });
  $("#consentBox").classList.add("hidden"); $("#uploadBox").classList.remove("hidden");
  $("#kycResult").innerHTML = `<p class="small muted">✔ Consent recorded · receipt ${r.receipt}</p>`;
};
$("#withdraw").onclick = async () => { await api("/api/kyc/withdraw", { session_id: S.sid, purposes: [] }); $("#uploadBox").classList.add("hidden"); $("#consentBox").classList.remove("hidden"); $("#kycResult").innerHTML = '<p class="small">Consent withdrawn and KYC data erased.</p>'; };
$("#verifyBtn").onclick = async () => {
  const fd = new FormData(); fd.append("session_id", S.sid);
  $$(".uploads input").forEach(i => i.files[0] && fd.append(i.dataset.doc, i.files[0]));
  $("#kycResult").innerHTML = '<p class="muted">Reading documents on our server…</p>';
  const r = await fetch("/api/kyc/verify", { method: "POST", body: fd }); renderKyc(await r.json());
};
$("#specimen").onchange = async e => { if (!e.target.value) return; $("#kycResult").innerHTML = '<p class="muted">Reading ' + e.target.value + ' on our server…</p>'; renderKyc(await api(`/api/kyc/specimen/${e.target.value}?session_id=${S.sid}`, {})); };
function renderKyc(r) {
  const V = { verified: ["✅ Verified", "All checks passed — you can place the order."], needs_action: ["⚠️ Needs a quick fix", "Fix the items below and re-upload — no visit needed."], manual_review: ["🔍 Sent for review", "Something doesn't match; an Accel specialist will check with you within 4 working hours."], rejected: ["⛔ Can't proceed", "A registration problem blocks activation — see below."] }[r.verdict];
  const ic = { pass: "✅", warn: "ℹ️", fail: "❌" };
  let h = `<div class="verdict v-${r.verdict}"><b>${V[0]}</b>${V[1]}</div>`;
  h += r.checks.sort((a, b) => ({ fail: 0, warn: 1, pass: 2 }[a.status] - { fail: 0, warn: 1, pass: 2 }[b.status])).map(c => `<div class="chk"><span class="ic">${ic[c.status]}</span><div><b>${md(c.title)}</b><div class="muted small">${md(c.detail)}</div>${c.fix ? `<div class="fix">👉 ${md(c.fix)}</div>` : ""}</div></div>`).join("");
  h += `<button id="placeOrder" class="primary wide" style="margin-top:12px">${r.verdict === "verified" ? "E-sign & place order" : "Place order (KYC will complete in tracker)"}</button>`;
  $("#kycResult").innerHTML = h;
  $("#placeOrder").onclick = placeOrder;
}
async function placeOrder() {
  if (!S.data || !S.data.recommendation) { go("chat"); return bubble("Let's build your bundle first."); }
  const o = await api("/api/orders", { session_id: S.sid, name: "Owner", phone: "9800000000" });
  S.orderId = o.id; $("#orderId").value = o.id; go("track"); renderTrack(o);
}

/* ---------- tracker ---------- */
$("#trackForm").onsubmit = async e => { e.preventDefault(); try { renderTrack(await api("/api/orders/" + $("#orderId").value.trim())); } catch (err) { $("#trackBody").innerHTML = `<p>${err.message}</p>`; } };
function renderTrack(o) {
  let h = `<div class="card"><div class="muted small">Order ${o.id} · placed ${o.created}</div><div class="total" style="font-size:24px">${inr(o.monthly)}<small>/month</small></div><div class="small">Everything live by <b>${o.eta}</b>${o.sla_risk ? ' · <span class="pill">leased line: site survey</span>' : ""}</div>
  <ul class="tl">${o.stages.map(s => `<li class="${s.done ? "done" : ""} ${s.current ? "cur" : ""}">${s.name}</li>`).join("")}</ul></div>
  <div class="card"><h3>Each service</h3>${o.lines.map(l => `<div class="line"><div class="n">${md(l.name)} ${l.qty > 1 ? "× " + l.qty : ""}</div><div class="p">by ${l.eta}</div></div>`).join("")}</div>
  <div class="card"><h3>Updates</h3>${o.events.map(e => `<div class="small">• ${e.at} — ${md(e.text)}</div>`).join("")}<p class="small muted">You'll also get each update on WhatsApp — no need to call.</p></div>
  <button id="adv" class="ghost small">Demo: advance to next stage</button>`;
  $("#trackBody").innerHTML = h;
  $("#adv").onclick = async () => renderTrack(await api(`/api/orders/${o.id}/advance`, {}));
}

/* ---------- back office ---------- */
async function loadOffice() {
  const [f, L, O] = await Promise.all([api("/api/backoffice/funnel"), api("/api/backoffice/leads?segment=" + encodeURIComponent($("#segFilter").value)), api("/api/backoffice/orders")]);
  $("#kpis").innerHTML = [["Lead → activation", f.activation_rate + "%"], ["Days to activate", f.days_to_activate], ["Status chases / customer", f.follow_up_calls], ["Cost per activation", inr(f.cac)], ["6-month churn", f.churn_6m + "%"]].map(([k, v]) => `<div class="kpi"><small>${k} (baseline)</small><b>${v}</b></div>`).join("");
  $("#handoffs").innerHTML = L.advisor_handoffs.length ? `<table><tr><th>Ref</th><th>Why</th><th>Summary</th></tr>${L.advisor_handoffs.map(l => `<tr><td>${l.id}</td><td>${md(l.reason)}</td><td>${md(l.summary)}</td></tr>`).join("")}</table>` : '<p class="muted small">None yet — try "kirana hai gaon mein" or "call me" in the advisor.</p>';
  $("#orders").innerHTML = O.length ? `<table><tr><th>Order</th><th>Monthly</th><th>KYC</th><th>Stage</th></tr>${O.map(o => `<tr><td>${o.id}</td><td>${inr(o.monthly)}</td><td>${o.kyc_verdict}</td><td>${o.stages.find(s => s.current).name}</td></tr>`).join("")}</table>` : '<p class="muted small">Orders placed in the owner app appear here.</p>';
  const m = L.model; $("#modelInfo").textContent = `(propensity model · AUC ${m.auc} on June hold-out · top 10% activate at ${m.top_decile_rate}% vs ${m.base_rate}%)`;
  $("#winback").innerHTML = `<table><tr><th>Lead</th><th>Business</th><th>City</th><th>Dropped because</th><th>Score</th><th>Win-back</th><th>Next best action</th></tr>${L.leads.map(l => `<tr><td>${l.lead_id}</td><td>${md(l.business)}<div class="muted small">${md(l.type)}</div></td><td>${l.city}</td><td>${md(l.drop_reason)}</td><td>${l.score}%</td><td><span class="pill hi">${l.winback}</span></td><td>${md(l.action)}</td></tr>`).join("")}</table>`;
  const mx = f.stages[0].leads;
  $("#funnel").innerHTML = f.stages.map(s => `<div class="bar" style="width:${Math.max(36, s.leads / mx * 100)}%">${s.stage} · ${s.leads.toLocaleString("en-IN")}</div>`).join("");
  $("#drops").innerHTML = `<table><tr><th>Reason</th><th>Leads</th><th>Recoverable</th></tr>${f.drop_reasons.slice(0, 10).map(d => `<tr><td>${md(d.reason)}</td><td>${d.leads}</td><td>${Math.round(d.recoverable * 100)}%</td></tr>`).join("")}</table>`;
}
$("#segFilter").onchange = loadOffice;

start();
