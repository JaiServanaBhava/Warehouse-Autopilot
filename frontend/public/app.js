/* ==========================================================================
   WAREHOUSE AUTOPILOT — Frontend Application Logic
   Vanilla JS. Real-time SSE, live Autopilot Action Queue, Heatmap,
   Product QR Intelligence Passport, Dark/Light Theme & Responsive Design.
   ========================================================================== */

(() => {
"use strict";

/* --------------------------------------------------------------------- *
 * 0. API CONFIG
 * --------------------------------------------------------------------- */
function guessApiBase() {
  const saved = localStorage.getItem("wa_api_base");
  if (saved) return saved;
  if (location.protocol === "file:") return "http://localhost:8001/api";
  if (location.port === "8001") return `${location.protocol}//${location.hostname}:8001/api`;
  if (location.port === "8000") return `${location.protocol}//${location.hostname}:8000/api`;
  return "/api";
}

let API_BASE = guessApiBase();

async function api(path, opts = {}) {
  const url = `${API_BASE}${path}`;
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  let res;
  try {
    res = await fetch(url, { ...opts, headers });
  } catch (e) {
    setConn(false);
    throw e;
  }
  setConn(true);
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = j.detail || JSON.stringify(j); } catch (_) {}
    throw new Error(msg || `HTTP ${res.status}`);
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res.text();
}
const GET = (p) => api(p);
const POST = (p, body) => api(p, { method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined });
const PUT = (p, body) => api(p, { method: "PUT", body: body !== undefined ? JSON.stringify(body) : undefined });
const DEL = (p) => api(p, { method: "DELETE" });

function setConn(ok) {
  const dot = $("#connDot"), txt = $("#connText");
  if (!dot) return;
  dot.classList.toggle("on", ok);
  dot.classList.toggle("off", !ok);
  txt.textContent = ok ? "Connected" : "Offline — check API URL / backend";
}

/* --------------------------------------------------------------------- *
 * 1. DOM HELPERS & FORMATTERS
 * --------------------------------------------------------------------- */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtMoney = (n) => "₹" + Math.round(n || 0).toLocaleString("en-IN");
const fmtTime = (iso) => { try { return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); } catch { return ""; } };
const fmtDateTime = (iso) => { try { return new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }); } catch { return iso || ""; } };
const timeAgo = (iso) => {
  try {
    const s = (Date.now() - new Date(iso).getTime()) / 1000;
    if (s < 60) return "just now";
    if (s < 3600) return Math.floor(s / 60) + "m ago";
    if (s < 86400) return Math.floor(s / 3600) + "h ago";
    return Math.floor(s / 86400) + "d ago";
  } catch { return ""; }
};
function animateCount(el, to, prefix = "", suffix = "") {
  if (!el) return;
  const from = Number(el.dataset.val || 0);
  to = Number(to) || 0;
  if (from === to) {
    el.textContent = prefix + to.toLocaleString("en-IN") + suffix;
    return;
  }
  const dur = 120, start = performance.now();
  function step(t) {
    const p = Math.min(1, (t - start) / dur);
    const eased = 1 - Math.pow(1 - p, 2);
    const val = Math.round(from + (to - from) * eased);
    el.textContent = prefix + val.toLocaleString("en-IN") + suffix;
    if (p < 1) requestAnimationFrame(step); else el.dataset.val = to;
  }
  requestAnimationFrame(step);
}
function debounce(fn, ms = 250) {
  let timer;
  return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
}

/* --------------------------------------------------------------------- *
 * 2. THEME SWITCHER (DARK / LIGHT MODE)
 * --------------------------------------------------------------------- */
function initTheme() {
  const saved = localStorage.getItem("wa_theme") || "dark";
  document.documentElement.setAttribute("data-theme", saved);
  updateThemeButton(saved);
}
function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "dark";
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("wa_theme", next);
  updateThemeButton(next);
}
function updateThemeButton(theme) {
  const btn = $("#themeToggleBtn");
  if (btn) {
    btn.textContent = theme === "light" ? "🌙" : "☀️";
    btn.title = theme === "light" ? "Switch to Dark Mode" : "Switch to Light Mode";
  }
}
const themeToggleBtn = $("#themeToggleBtn");
if (themeToggleBtn) themeToggleBtn.addEventListener("click", toggleTheme);

/* --------------------------------------------------------------------- *
 * 3. TOASTS & IN-APP HTML NOTIFICATION POP-UPS (MAX 2, 3s AUTO-DISMISS)
 * --------------------------------------------------------------------- */
function toast(title, body, severity = "MEDIUM", channel = "") {
  const stack = $("#toastStack");
  if (!stack) return;

  // Cap at max 2 visible notifications to prevent user clutter
  const MAX_TOASTS = 2;
  while (stack.children.length >= MAX_TOASTS) {
    stack.firstElementChild.remove();
  }

  const tLow = (title + " " + channel + " " + severity).toLowerCase();
  let icon = "🤖";
  if (tLow.includes("email")) icon = "📧";
  else if (tLow.includes("whatsapp") || tLow.includes("wa")) icon = "💬";
  else if (tLow.includes("po") || tLow.includes("reorder") || tLow.includes("supplier") || tLow.includes("qr")) icon = "📦";
  else if (severity === "CRITICAL" || tLow.includes("critical") || tLow.includes("shortage")) icon = "🚨";
  else if (severity === "HIGH" || tLow.includes("warn")) icon = "⚠️";
  else if (tLow.includes("done") || tLow.includes("success") || tLow.includes("applied")) icon = "✅";

  let shortBody = String(body || "").trim();
  if (shortBody.length > 90) shortBody = shortBody.slice(0, 87) + "…";

  const el = document.createElement("div");
  el.className = `toast toast-card ${severity.toLowerCase()}`;
  el.innerHTML = `
    <div class="toast-head">
      <div class="toast-title-wrap">
        <span class="toast-icon">${icon}</span>
        <b class="toast-title">${esc(title)}</b>
      </div>
      <button class="toast-close-btn" title="Close">✕</button>
    </div>
    ${shortBody ? `<div class="toast-body">${esc(shortBody)}</div>` : ''}
    <div class="toast-progress-track">
      <div class="toast-progress-bar"></div>
    </div>
  `;

  stack.appendChild(el);

  let isClosed = false;
  function dismiss() {
    if (isClosed) return;
    isClosed = true;
    el.style.animation = "toastSlideOut 0.2s ease forwards";
    setTimeout(() => el.remove(), 200);
  }

  const closeBtn = el.querySelector(".toast-close-btn");
  if (closeBtn) closeBtn.onclick = dismiss;

  // Auto dismiss after 3 seconds
  setTimeout(dismiss, 3000);
}

/* --------------------------------------------------------------------- *
 * 4. MODAL SYSTEM & MOBILE DRAWER
 * --------------------------------------------------------------------- */
const modalRoot = $("#modalRoot"), modalPanel = $("#modalPanel"), modalBackdrop = $("#modalBackdrop");
function openModal(html) {
  if (!modalPanel || !modalRoot) return;
  modalPanel.innerHTML = `<button class="modal-close" id="modalCloseBtn">✕</button>${html}`;
  modalRoot.classList.remove("hidden");
  $("#modalCloseBtn").onclick = closeModal;
}
function closeModal() {
  if (!modalRoot || !modalPanel) return;
  modalRoot.classList.add("hidden");
  modalPanel.innerHTML = "";
}
if (modalBackdrop) modalBackdrop.addEventListener("click", closeModal);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

// Mobile Hamburger & Scrim Toggle
const menuBtn = $("#menuBtn"), sidebar = $("#sidebar"), sidebarScrim = $("#sidebarScrim");
if (menuBtn && sidebar) {
  menuBtn.addEventListener("click", () => {
    sidebar.classList.toggle("open");
    if (sidebarScrim) sidebarScrim.classList.toggle("open");
  });
}
if (sidebarScrim) {
  sidebarScrim.addEventListener("click", () => {
    sidebar?.classList.remove("open");
    sidebarScrim.classList.remove("open");
  });
}

/* Topbar Notification Bell Click Handler */
const topbarNotifBtn = $("#topbarNotifBtn");
if (topbarNotifBtn) {
  topbarNotifBtn.addEventListener("click", () => showView("alerts"));
}

/* --------------------------------------------------------------------- *
 * 5. RUNTIME COMPANY EMAIL & RESET DEMO
 * --------------------------------------------------------------------- */
let activeCompanyEmail = "manager@warehouse.com";

async function fetchActiveEmail() {
  try {
    const res = await GET("/notifications/active-email");
    if (res && res.company_email) {
      activeCompanyEmail = res.company_email;
    }
  } catch (e) { /* ignore */ }
}

function showResetDemoModal() {
  openModal(`
    <div class="modal-title">🔄 Reset Demo &amp; Dispatch Real-Time Digest</div>
    <div class="modal-sub">This regenerates inventory, orders, and queues while preserving your configured email and WhatsApp settings.</div>
    <div class="form-group" style="margin-top:14px;">
      <label class="form-label">Alert Recipient (Company / Judge Email)</label>
      <input id="demoResetEmailInput" class="input" type="email" value="${esc(activeCompanyEmail)}" style="width:100%;font-size:14px;padding:10px 14px;" />
    </div>
    <p class="muted" style="margin:8px 0 16px;font-size:12px;color:var(--text-dim);">
      ⚡ On reset, Warehouse Autopilot detects the KB-303 shortage and dispatches an instant operational email digest and WhatsApp alert.
    </p>
    <div class="form-actions">
      <button class="btn btn-ghost" id="resetModalCancel">Cancel</button>
      <button class="btn btn-danger" id="resetModalConfirm">Reset Demo &amp; Send Real-Time Alert</button>
    </div>
  `);
  $("#resetModalCancel").onclick = closeModal;
  $("#resetModalConfirm").onclick = async () => {
    const emailVal = $("#demoResetEmailInput").value.trim();
    if (emailVal && emailVal.includes("@")) {
      activeCompanyEmail = emailVal;
    }
    closeModal();
    try {
      toast("Resetting Warehouse…", "Regenerating state and evaluating shortages", "MEDIUM");
      const r = await POST("/demo/reset", { company_email: activeCompanyEmail });
      toast("Demo Reset Complete", `Real-time operational alert dispatched to ${r.recipient || activeCompanyEmail}`, "MEDIUM");
      loadDashboard();
      if (currentView !== "dashboard") loadView(currentView);
    } catch (e) {
      toast("Reset Failed", e.message, "HIGH");
    }
  };
}

const resetDemoBtn = $("#resetDemoBtn");
if (resetDemoBtn) resetDemoBtn.addEventListener("click", showResetDemoModal);
const resetDemoBtn2 = $("#resetDemoBtn2");
if (resetDemoBtn2) resetDemoBtn2.addEventListener("click", showResetDemoModal);

/* --------------------------------------------------------------------- *
 * 6. NAVIGATION
 * --------------------------------------------------------------------- */
const VIEW_TITLES = {
  dashboard: ["Command Center", "Live warehouse state, autopilot actions & risk"],
  inventory: ["Inventory", "Products, stock levels, reorder signals & QR Passport"],
  orders: ["Orders", "Priority, allocation & risk per order"],
  picking: ["Picking", "Active picking tasks & routes"],
  packing: ["Packing", "Packing queue & worker load"],
  qc: ["Quality Control", "Pass / fail checks before dispatch"],
  dispatch: ["Dispatch", "Ready-for-dispatch & final handoff"],
  exceptions: ["Exceptions", "Detection → Analysis → Decision → Resolution"],
  decisions: ["Decision Engine", "Recommendations with reasons & confidence"],
  alerts: ["Alerts & Notifications", "Severity-based escalation across channels"],
  analytics: ["Analytics", "Health, impact, risk radar & dependencies"],
  map: ["Warehouse Map", "Digital twin of zones & stock status"],
  audit: ["Audit Log", "Every important action, tracked"],
  settings: ["Settings", "Notifications, automation & demo data"],
  copilot: ["Warehouse AI Copilot", "Autonomous conversational intelligence with live database context"],
};

let currentView = "dashboard";
function showView(name) {
  currentView = name;
  $$(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  $$(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${name}`));
  const [title, sub] = VIEW_TITLES[name] || [name, ""];
  const vt = $("#viewTitle"), vs = $("#viewSubtitle");
  if (vt) vt.textContent = title;
  if (vs) vs.textContent = sub;
  sidebar?.classList.remove("open");
  sidebarScrim?.classList.remove("open");
  loadView(name);
}
$$(".nav-item").forEach((btn) => btn.addEventListener("click", () => showView(btn.dataset.view)));

function loadView(name) {
  switch (name) {
    case "dashboard": loadDashboard(); break;
    case "copilot": loadCopilotView(); break;
    case "inventory": loadInventory(); break;
    case "orders": loadOrders(); break;
    case "picking": loadQueue("PICKING"); break;
    case "packing": loadQueue("PACKING"); break;
    case "qc": loadQueue("QC"); break;
    case "dispatch": loadQueue("DISPATCH"); break;
    case "exceptions": loadExceptions(); break;
    case "decisions": loadDecisions(); break;
    case "alerts": loadAlerts(); loadOutbox(); break;
    case "analytics": loadAnalytics(); break;
    case "map": loadWarehouseMap(); break;
    case "audit": loadAudit(); break;
    case "settings": loadSettings(); break;
  }
}

/* --------------------------------------------------------------------- *
 * 7. DASHBOARD
 * --------------------------------------------------------------------- */
const KPI_DEFS = [
  ["products_total", "Total products", "📦", ""],
  ["total_stock", "Total inventory", "🧮", ""],
  ["available_stock", "Available stock", "✅", "ok"],
  ["reserved_stock", "Reserved stock", "🔒", ""],
  ["damaged_stock", "Damaged stock", "⚠", "warn"],
  ["low_stock_products", "Low-stock products", "📉", "warn"],
  ["out_of_stock_products", "Out-of-stock products", "⛔", "danger"],
  ["open_exceptions", "Active exceptions", "🧩", "danger"],
];

let activeDashboardCatFilter = "";

async function loadDashboard() {
  fetchActiveEmail();
  let d;
  try { d = await GET("/dashboard"); } catch (e) { return; }

  const wn = $("#warehouseName");
  if (wn) wn.textContent = d.warehouse_name || "Central DC";

  if (activeDashboardCatFilter) {
    try {
      const prods = await GET("/products");
      let filtered = prods;
      if (activeDashboardCatFilter === "Critical") {
        filtered = prods.filter((p) => (p.computed_usable_stock || 0) <= 0 || p.stock_status === "CRITICAL");
      } else {
        filtered = prods.filter((p) => (p.category || "").toLowerCase() === activeDashboardCatFilter.toLowerCase());
      }
      d.total_skus = filtered.length;
      d.physical_stock = filtered.reduce((s, p) => s + (p.physical_stock || 0), 0);
      d.available_stock = filtered.reduce((s, p) => s + (p.computed_usable_stock || 0), 0);
      d.reserved_stock = filtered.reduce((s, p) => s + (p.reserved_stock || 0), 0);
      d.damaged_stock = filtered.reduce((s, p) => s + (p.damaged_stock || 0), 0);
      d.low_stock_products = filtered.filter((p) => p.stock_status === "LOW_STOCK").length;
      d.out_of_stock_products = filtered.filter((p) => p.stock_status === "OUT_OF_STOCK" || (p.computed_usable_stock || 0) <= 0).length;
    } catch (e) {}
  }

  const grid = $("#kpiGrid");
  if (grid && !grid.dataset.built) {
    grid.innerHTML = KPI_DEFS.map(([key, label, icon, cls]) => `
      <div class="kpi-card ${cls}" data-key="${key}">
        <div class="kpi-icon">${icon}</div>
        <div class="kpi-val" data-val="0">0</div>
        <div class="kpi-label">${label}</div>
      </div>`).join("") + `
      <div class="kpi-card ok" data-key="__critical_orders">
        <div class="kpi-icon">🚨</div><div class="kpi-val" data-val="0">0</div><div class="kpi-label">Critical orders</div>
      </div>
      <div class="kpi-card warn" data-key="__at_risk">
        <div class="kpi-icon">⏱</div><div class="kpi-val" data-val="0">0</div><div class="kpi-label">Orders at risk</div>
      </div>
      <div class="kpi-card" data-key="__health">
        <div class="kpi-icon">💠</div><div class="kpi-val" data-val="0">0</div><div class="kpi-label">Warehouse health</div>
      </div>
      <div class="kpi-card ok" data-key="__autopilot">
        <div class="kpi-icon">🤖</div><div class="kpi-val" data-val="0">0</div><div class="kpi-label">Autopilot score</div>
      </div>`;
    grid.dataset.built = "1";
  }

  if (grid) {
    KPI_DEFS.forEach(([key]) => {
      const card = grid.querySelector(`[data-key="${key}"] .kpi-val`);
      if (card) animateCount(card, d[key] || 0);
    });
    const critical = d.priority_stats?.CRITICAL || 0;
    const impact = d.impact || {};
    animateCount(grid.querySelector('[data-key="__critical_orders"] .kpi-val'), critical);
    animateCount(grid.querySelector('[data-key="__at_risk"] .kpi-val'), impact.orders_at_risk || 0);
    animateCount(grid.querySelector('[data-key="__health"] .kpi-val'), d.health?.overall || 0);
    animateCount(grid.querySelector('[data-key="__autopilot"] .kpi-val'), d.autopilot?.score || 0);
  }

  // 1. Load Autopilot Action Queue
  loadAutopilotActions();

  // 2. Load Bottleneck Heatmap & Zones
  loadWarehouseHeatmap();

  // 3. Load Queues & Bottleneck
  const queues = d.queues || {};
  const qr = $("#queueRow");
  if (qr) {
    qr.innerHTML = ["PICKING", "PACKING", "QC", "DISPATCH"].map((s) => `
      <div class="queue-cell"><div class="qv">${queues[s] || 0}</div><div class="ql">${s}</div></div>`).join("");
  }
  renderBottleneck(d);

  // 4. Health & Impact
  renderHealth($("#healthBreakdown"), d.health);
  const htag = $("#healthOverallTag");
  if (htag) htag.textContent = `${d.health?.overall ?? "--"}/100`;
  renderImpact($("#impactPanel"), d.impact);

  // 5. Real-Time Outbox Stream on Dashboard
  loadDashOutbox();

  // 6. Recent Activity
  renderActivity($("#activityFeed"), d.recent_activity || []);

  // 7. Sync autopilot mini score in sidebar foot
  updateAutopilotRing(d.autopilot?.score ?? 0, d.health?.overall ?? 0);
}

/* Category Filter Pills on Dashboard */
$$("#dashCatFilters .filter-pill").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$("#dashCatFilters .filter-pill").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    activeDashboardCatFilter = btn.dataset.cat;
    loadDashboard();
  });
});

const refreshAutopilotBtn = $("#refreshAutopilotBtn");
if (refreshAutopilotBtn) refreshAutopilotBtn.addEventListener("click", () => {
  toast("Refreshing Autopilot…", "Recalculating ranked actions and zone loads", "MEDIUM");
  loadAutopilotActions();
  loadWarehouseHeatmap();
});

/* --------------------------------------------------------------------- *
 * 7b. 🧠 “WHAT SHOULD I DO NOW?” AUTOPILOT LIVE RANKED ACTION QUEUE
 * --------------------------------------------------------------------- */
async function loadAutopilotActions() {
  const container = $("#autopilotActionList");
  if (!container) return;
  try {
    const actions = await GET("/autopilot/actions");
    if (!actions || !actions.length) {
      container.innerHTML = `<div class="empty-state"><div class="es-icon">✨</div>All operations optimized · No urgent actions needed</div>`;
      return;
    }
    container.innerHTML = actions.map((act) => `
      <div class="action-card ${act.urgency ? act.urgency.toLowerCase() : ''}" data-act-id="${esc(act.id)}">
        <div class="act-card-header">
          <div class="act-card-title-wrap">
            <span class="act-icon">${act.icon || '⚡'}</span>
            <b class="act-title">${esc(act.title)}</b>
          </div>
          <div class="act-badge-row">
            <span class="act-urgency-chip ${act.urgency || 'MEDIUM'}">${act.urgency || 'MEDIUM'}</span>
            <span class="act-conf-pill">${act.confidence}% confidence</span>
          </div>
        </div>
        <div class="act-card-body">
          <div class="act-impact-pill">✨ <b>Impact:</b> ${esc(act.impact)}</div>
          <div class="act-reason-text"><b>Reason:</b> ${esc(act.reason)}</div>
        </div>
        <div class="act-card-foot">
          <button class="btn btn-accent btn-sm btn-exec-action"
                  data-action-type="${esc(act.type)}"
                  data-action-params='${esc(JSON.stringify(act.params || {}))}'>
            <span>⚡ Execute Action</span>
          </button>
        </div>
      </div>`).join("");

    $$(".btn-exec-action", container).forEach((btn) => {
      btn.addEventListener("click", async () => {
        const actionType = btn.dataset.actionType;
        let params = {};
        try { params = JSON.parse(btn.dataset.actionParams || "{}"); } catch (_) {}
        btn.disabled = true;
        btn.innerHTML = `<span>⏳ Executing…</span>`;
        try {
          const res = await POST("/autopilot/actions/execute", { type: actionType, params });
          btn.innerHTML = `<span>✅ Done!</span>`;
          toast("Action Executed Successfully", res.result || "Autopilot optimization applied", "MEDIUM");
          setTimeout(() => { loadDashboard(); }, 400);
        } catch (err) {
          btn.disabled = false;
          btn.innerHTML = `<span>⚡ Execute Action</span>`;
          toast("Execution Failed", err.message, "HIGH");
        }
      });
    });
  } catch (e) {
    container.innerHTML = `<div class="empty-state">Failed to load Autopilot actions: ${esc(e.message)}</div>`;
  }
}

/* --------------------------------------------------------------------- *
 * 7c. 🗺️ BOTTLENECK HEATMAP + WORKER LOAD BALANCING
 * --------------------------------------------------------------------- */
async function loadWarehouseHeatmap() {
  const grid = $("#zoneHeatmapGrid");
  if (!grid) return;
  try {
    const data = await GET("/warehouse/heatmap");
    const zones = data.zones || [];
    grid.innerHTML = zones.map((z) => {
      const color = z.status === "OVERLOADED" ? "var(--critical)" : (z.status === "CONGESTED" ? "var(--warn)" : "var(--ok)");
      const bgGlow = z.status === "OVERLOADED" ? "rgba(239,68,68,0.08)" : (z.status === "CONGESTED" ? "rgba(251,146,60,0.08)" : "rgba(47,224,165,0.06)");
      return `
        <div class="zone-heat-card ${z.status.toLowerCase()}" style="background:${bgGlow};border-color:${color}44;">
          <div class="zhc-top">
            <div>
              <div class="zhc-name">${esc(z.name)}</div>
              <div class="zhc-locs">${esc(z.locations.join(", "))}</div>
            </div>
            <span class="zhc-status-chip ${z.status}">${z.status}</span>
          </div>
          <div class="zhc-meter-row">
            <div class="zhc-meter-label"><span>Congestion</span><b>${z.workload_pct}%</b></div>
            <div class="zhc-meter-bar"><div class="zhc-meter-fill" style="width:${z.workload_pct}%;background:${color};"></div></div>
          </div>
          <div class="zhc-stats-grid">
            <div class="zhc-stat"><span>Orders waiting</span><b>${z.orders_waiting}</b></div>
            <div class="zhc-stat"><span>Active tasks</span><b>${z.active_tasks}</b></div>
            <div class="zhc-stat"><span>SKU count</span><b>${z.sku_count}</b></div>
            <div class="zhc-stat"><span>Workers</span><b>${z.workers_assigned}</b></div>
          </div>
        </div>`;
    }).join("");

    const rec = data.recommendation;
    const rtitle = $("#rebalanceTitle"), rdetail = $("#rebalanceDetail");
    if (rec && rtitle && rdetail) {
      rtitle.textContent = `🚨 ${rec.overloaded_zone} Overloaded (${rec.overloaded_pct}%)`;
      rdetail.textContent = `${rec.detail} Recommendation: ${rec.action}`;
    }
  } catch (e) {
    grid.innerHTML = `<div class="empty-state">Failed to load heatmap: ${esc(e.message)}</div>`;
  }
}

const execRebalanceBtn = $("#execRebalanceBtn");
if (execRebalanceBtn) {
  execRebalanceBtn.addEventListener("click", async () => {
    execRebalanceBtn.disabled = true;
    execRebalanceBtn.textContent = "⏳ Rebalancing…";
    try {
      const res = await POST("/warehouse/rebalance-workers");
      toast("Workers Rebalanced", `Shifted workers to relieve Zone C congestion`, "MEDIUM");
      loadWarehouseHeatmap();
      loadDashboard();
    } catch (e) {
      toast("Rebalance Failed", e.message, "HIGH");
    } finally {
      execRebalanceBtn.disabled = false;
      execRebalanceBtn.textContent = "⚡ Rebalance Workers Now";
    }
  });
}

/* --------------------------------------------------------------------- *
 * 7d. REAL-TIME OUTBOX STREAM ON DASHBOARD & MODAL PREVIEW
 * --------------------------------------------------------------------- */
async function loadDashOutbox() {
  const container = $("#dashOutboxList");
  if (!container) return;
  try {
    const items = await GET("/outbox?limit=5");
    if (!items || !items.length) {
      container.innerHTML = `<div class="empty-state">No real-time emails dispatched yet</div>`;
      return;
    }
    container.innerHTML = items.map((o) => `
      <div class="outbox-stream-row" data-outbox-id="${esc(o.id)}">
        <div class="os-left">
          <span class="os-ch ${esc(o.channel).toLowerCase()}">${o.channel.includes("EMAIL") ? "📧 EMAIL" : (o.channel.includes("WHATSAPP") ? "💬 WA" : "📦 PO")}</span>
          <div class="os-text">
            <b class="os-sub">${esc(o.subject || o.body?.slice(0, 45) || 'Notification')}</b>
            <span class="os-meta">${esc(o.recipient || 'Broadcast')} · ${timeAgo(o.created_at)}</span>
          </div>
        </div>
        <div class="os-right">
          <span class="outbox-status ${esc(o.status)}">${esc(o.status)}</span>
          <button class="btn btn-ghost btn-xs btn-view-email" data-id="${esc(o.id)}">View</button>
        </div>
      </div>`).join("");

    $$(".btn-view-email", container).forEach((btn) => {
      btn.addEventListener("click", () => {
        const item = items.find((x) => x.id === btn.dataset.id);
        if (item) showEmailDetailModal(item);
      });
    });
  } catch (e) {
    container.innerHTML = `<div class="empty-state">${esc(e.message)}</div>`;
  }
}

function showEmailDetailModal(item) {
  openModal(`
    <div class="modal-title">📧 Dispatched Email / Notification Preview</div>
    <div class="modal-sub">Channel: ${esc(item.channel)} · Status: <span class="outbox-status ${esc(item.status)}">${esc(item.status)}</span> · Sent: ${fmtDateTime(item.created_at)}</div>
    <div class="email-preview-meta">
      <div><b>Recipient:</b> <span>${esc(item.recipient || 'N/A')}</span></div>
      <div><b>Subject:</b> <span>${esc(item.subject || 'Warehouse Alert')}</span></div>
      <div><b>Provider Message ID:</b> <code>${esc(item.provider_message_id || 'sim-smtp-dispatch')}</code></div>
    </div>
    <div class="email-preview-box">
      <pre style="white-space:pre-wrap;font-family:var(--font);font-size:13px;line-height:1.6;color:#e2e8f0;margin:0;">${esc(item.body || '')}</pre>
    </div>
    <div class="form-actions">
      <button class="btn btn-ghost" id="closeEmailPreview">Close</button>
      <button class="btn btn-accent" id="resendEmailPreview">Resend Notification</button>
    </div>
  `);
  $("#closeEmailPreview").onclick = closeModal;
  $("#resendEmailPreview").onclick = async () => {
    try {
      await POST(`/outbox/${item.id}/resend`);
      toast("Notification Resent", `Dispatched again to ${item.recipient}`, "MEDIUM");
      closeModal();
      loadDashOutbox();
    } catch (err) { alert(err.message); }
  };
}

const viewAllOutboxBtn = $("#viewAllOutboxBtn");
if (viewAllOutboxBtn) {
  viewAllOutboxBtn.addEventListener("click", () => {
    showView("alerts");
    const tab = $(`#alertCenterTabs [data-sub="history"]`);
    if (tab) tab.click();
  });
}

function renderHealth(container, health) {
  if (!container) return;
  if (!health) { container.innerHTML = `<div class="empty-state">No health data yet</div>`; return; }
  const rows = Object.entries(health.breakdown || {});
  container.innerHTML = rows.map(([k, v]) => `
    <div class="health-row">
      <div class="hr-label">${esc(k)}</div>
      <div class="health-bar"><div class="health-bar-fill" style="width:${Math.max(0, Math.min(100, v))}%"></div></div>
      <div class="hr-val">${v}</div>
    </div>`).join("") || `<div class="empty-state">No breakdown available</div>`;
}

function renderImpact(container, impact) {
  if (!container) return;
  if (!impact) { container.innerHTML = `<div class="empty-state">No impact data</div>`; return; }
  container.innerHTML = `
    <div class="impact-col nothing">
      <div class="impact-col-title">If we do nothing</div>
      <div class="impact-stat"><span>Delayed orders</span><b>${impact.orders_at_risk ?? "--"}</b></div>
      <div class="impact-stat"><span>Potential loss</span><b>${fmtMoney(impact.potential_loss)}</b></div>
    </div>
    <div class="impact-col act">
      <div class="impact-col-title">If we act on recommendations</div>
      <div class="impact-stat"><span>Loss avoided</span><b>${fmtMoney(impact.loss_avoided ?? (impact.potential_loss || 0) * 0.7)}</b></div>
      <div class="impact-stat"><span>Orders protected</span><b>${impact.orders_protected ?? "--"}</b></div>
    </div>
    <div class="impact-note" style="grid-column:1/-1;">Estimates derived from real orders, inventory runway and deadline risk.</div>`;
}

function renderBottleneck(d) {
  const panel = $("#bottleneckPanel");
  if (!panel) return;
  const q = d.queues || {};
  let stage = "None detected", icon = "✅";
  let max = 0;
  Object.entries(q).forEach(([k, v]) => { if (v > max) { max = v; stage = k; } });
  if (max === 0) { panel.innerHTML = `<div class="bottleneck-badge">✅</div><div class="bottleneck-text"><b>No bottleneck</b><span>All queues are balanced</span></div>`; return; }
  icon = { PICKING: "🎯", PACKING: "📦", QC: "🔍", DISPATCH: "🚚" }[stage] || "⚠";
  panel.innerHTML = `<div class="bottleneck-badge">${icon}</div><div class="bottleneck-text"><b>${stage} queue</b><span>${max} order${max === 1 ? "" : "s"} waiting — largest queue right now</span></div>`;
}

function renderActivity(container, items) {
  if (!container) return;
  if (!items.length) { container.innerHTML = `<div class="empty-state">No recent activity</div>`; return; }
  container.innerHTML = items.map((a) => `
    <div class="act-row"><span class="act-dot"></span>
      <span class="act-msg">${esc(a.message)}</span>
      <span class="act-time">${timeAgo(a.at)}</span>
    </div>`).join("");
}

function updateAutopilotRing(score, health) {
  const ring = $("#autopilotRing");
  if (!ring) return;
  const circumference = 100;
  const offset = circumference - Math.max(0, Math.min(100, score));
  ring.style.strokeDashoffset = offset;
  const ms = $("#autopilotMiniScore"), mst = $("#autopilotMiniStatus");
  if (ms) ms.textContent = score;
  if (mst) mst.textContent = health >= 80 ? "Nominal" : health >= 55 ? "Monitoring" : "Attention needed";
}

/* --------------------------------------------------------------------- *
 * 8. INVENTORY & PRODUCT QR INTELLIGENCE PASSPORT
 * --------------------------------------------------------------------- */
let inventoryCache = [];
async function loadInventory() {
  const search = $("#invSearch")?.value.trim() || "";
  const category = $("#invCategory")?.value || "";
  const status = $("#invStatus")?.value || "";
  let products;
  try { products = await GET(`/products?search=${encodeURIComponent(search)}&category=${encodeURIComponent(category)}&status=${encodeURIComponent(status)}`); }
  catch (e) { $("#inventoryBody").innerHTML = `<tr><td colspan="12" class="empty-state">${esc(e.message)}</td></tr>`; return; }
  inventoryCache = products;

  if ($("#invCategory") && !$("#invCategory").dataset.built) {
    const cats = [...new Set(products.map((p) => p.category).filter(Boolean))];
    $("#invCategory").insertAdjacentHTML("beforeend", cats.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join(""));
    $("#invCategory").dataset.built = "1";
  }

  const sortKey = $("#invSort")?.value || "name";
  const sorters = {
    name: (a, b) => a.name.localeCompare(b.name),
    stock: (a, b) => b.available_stock - a.available_stock,
    status: (a, b) => a.status.localeCompare(b.status),
    stockout: (a, b) => (a.days_until_stockout ?? 999) - (b.days_until_stockout ?? 999),
  };
  products.sort(sorters[sortKey] || sorters.name);

  $("#inventoryBody").innerHTML = products.length ? products.map((p) => `
    <tr data-pid="${p.id}">
      <td class="mono font-semibold">${esc(p.sku)}</td>
      <td>${esc(p.name)}</td>
      <td><span class="tag">${esc(p.category || '-')}</span></td>
      <td class="mono">${esc(p.location || '-')}</td>
      <td class="mono">${p.physical_stock}</td>
      <td class="mono">${p.reserved_stock}</td>
      <td class="mono">${p.damaged_stock}</td>
      <td class="mono font-bold">${p.available_stock}</td>
      <td><span class="status-pill ${p.status}">${p.status.replace(/_/g, ' ')}</span></td>
      <td class="mono">${p.days_until_stockout !== undefined ? p.days_until_stockout + 'd' : '-'}</td>
      <td class="mono">${p.recommended_reorder || 0}</td>
      <td class="tbl-actions">
        <button class="btn btn-accent btn-xs" data-act="qr" title="Product QR Intelligence Passport">📱 QR Passport</button>
        <button class="btn btn-ghost btn-xs" data-act="adjust" title="Adjust stock">Adjust</button>
        <button class="btn btn-ghost btn-xs" data-act="details" title="Details">Details</button>
      </td>
    </tr>`).join("") : `<tr><td colspan="12" class="empty-state">No products found</td></tr>`;
}

$("#invSearch")?.addEventListener("input", debounce(loadInventory, 300));
$("#invCategory")?.addEventListener("change", loadInventory);
$("#invStatus")?.addEventListener("change", loadInventory);
$("#invSort")?.addEventListener("change", loadInventory);

$("#inventoryBody")?.addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-act]");
  if (!btn) return;
  const tr = btn.closest("tr");
  const pid = tr?.dataset.pid;
  const p = inventoryCache.find((x) => x.id === pid);
  if (!p) return;

  if (btn.dataset.act === "qr") {
    openQRPassportModal(pid);
  }

  if (btn.dataset.act === "adjust") {
    openModal(`
      <div class="modal-title">Adjust Stock — ${esc(p.sku)}</div>
      <div class="modal-sub">${esc(p.name)} · Current Physical: ${p.physical_stock}</div>
      <div class="form-group" style="margin-top:12px;">
        <label class="form-label">New Physical Stock Count</label>
        <input id="adjQty" class="input" type="number" value="${p.physical_stock}" style="width:100%;" />
      </div>
      <div class="form-group">
        <label class="form-label">Reason</label>
        <input id="adjReason" class="input" type="text" placeholder="Physical cycle count" style="width:100%;" />
      </div>
      <div class="form-actions">
        <button class="btn btn-ghost" id="adjCancel">Cancel</button>
        <button class="btn btn-accent" id="adjSave">Save Adjustment</button>
      </div>`);
    $("#adjCancel").onclick = closeModal;
    $("#adjSave").onclick = async () => {
      const q = Number($("#adjQty").value);
      const reason = $("#adjReason").value.trim() || "Cycle count";
      await POST("/inventory/adjust", { product_id: pid, quantity: q, reason });
      toast("Stock adjusted", `${p.sku} set to ${q}`);
      closeModal(); loadInventory(); loadDashboard();
    };
  }

  if (btn.dataset.act === "details") {
    const data = await GET(`/products/${pid}`);
    openModal(`
      <div class="modal-title">${esc(p.sku)} — ${esc(p.name)}</div>
      <div class="modal-sub">${esc(p.category)} · Supplier: ${esc(p.supplier || 'N/A')} · Unit Price: ${fmtMoney(p.unit_price)}</div>
      <div class="why-reasons" style="margin:14px 0;">
        <div class="why-reason"><span>Physical Stock</span><b>${p.physical_stock}</b></div>
        <div class="why-reason"><span>Reserved</span><b>${p.reserved_stock}</b></div>
        <div class="why-reason"><span>Damaged</span><b>${p.damaged_stock}</b></div>
        <div class="why-reason"><span>Available</span><b style="color:var(--ok);">${p.available_stock}</b></div>
      </div>
      <p class="muted" style="margin-bottom:14px;">${esc(data.forecast?.explanation || '')}</p>
      <div class="form-actions" style="margin-top:16px;">
        <button class="btn btn-accent" id="openQRFromDetails">📱 View QR Intelligence Passport</button>
      </div>
    `);
    const qbtn = $("#openQRFromDetails");
    if (qbtn) qbtn.onclick = () => openQRPassportModal(pid);
  }
});

/* --------------------------------------------------------------------- *
 * 8b. QR INTELLIGENCE PASSPORT MODAL & REALITY CHECK
 * --------------------------------------------------------------------- */
async function openQRPassportModal(pid) {
  openModal(`<div class="loading-shimmer" style="padding:40px;text-align:center;">Generating QR Intelligence Passport…</div>`);
  try {
    const passport = await GET(`/products/${pid}/qr-passport`);
    renderQRPassportModalContent(passport);
  } catch (err) {
    openModal(`<div class="modal-title">QR Passport Error</div><div class="modal-sub">${esc(err.message)}</div>`);
  }
}

function renderQRPassportModalContent(passport) {
  const live = passport.live_state || {};
  const isStale = passport.is_stale;
  
  openModal(`
    <div class="qr-passport-modal-shell">
      <div class="qr-passport-header">
        <div>
          <div class="modal-title" style="display:flex;align-items:center;gap:8px;">
            <span>📱 QR Intelligence Passport</span>
            <span class="status-chip st-${esc(passport.snapshot_status)}">${esc(passport.snapshot_status)}</span>
          </div>
          <div class="modal-sub">${esc(passport.sku)} — ${esc(passport.name)} · Zone ${esc(passport.location || 'N/A')}</div>
        </div>
        <div class="qr-version-pill">
          <span>Snapshot v${passport.snapshot_version}</span>
        </div>
      </div>

      <!-- Reality Check Status Banner -->
      <div class="qr-reality-banner ${isStale ? 'stale' : 'fresh'}">
        <div class="qrb-icon">${isStale ? '⚠️' : '✓'}</div>
        <div class="qrb-text">
          <b>${isStale ? 'QR SNAPSHOT IS OUTDATED' : 'QR SNAPSHOT IS SYNCHRONIZED'}</b>
          <span>${isStale 
            ? `Live usable stock is <b>${live.usable_stock}</b> (QR payload shows <b>${passport.snapshot_usable_stock}</b>). Regenerate QR recommended.`
            : `QR operational snapshot matches live warehouse state perfectly.`}</span>
        </div>
        ${isStale ? `<button class="btn btn-accent btn-xs" id="quickRegenQRBtn">🔄 Regenerate Now</button>` : ''}
      </div>

      <!-- Main Passport Identity Card Layout -->
      <div class="qr-passport-card-grid">
        <!-- Left: Physical QR Identity Card -->
        <div class="qr-card-col">
          <div class="qr-image-frame">
            <img src="${passport.qr_image_url}" alt="QR Intelligence Passport" class="qr-actual-img" />
            <div class="qr-scan-hint">Scan with generic phone camera</div>
          </div>
          <div class="qr-download-actions">
            <button class="btn btn-ghost btn-sm" id="downloadQRBtn">📥 Download QR</button>
            <button class="btn btn-accent btn-sm" id="printLabelBtn">🖨️ Print Bin Label</button>
          </div>
        </div>

        <!-- Right: Operational Snapshot Data -->
        <div class="qr-data-col">
          <div class="qr-data-card">
            <div class="qr-data-header">OPERATIONAL SNAPSHOT DATA</div>
            <div class="qr-kv-table">
              <div class="qr-kv-row"><span>SKU</span><b>${esc(passport.sku)}</b></div>
              <div class="qr-kv-row"><span>Product</span><b>${esc(passport.name)}</b></div>
              <div class="qr-kv-row"><span>Location</span><b>${esc(passport.location)}</b></div>
              <div class="qr-kv-row"><span>Snapshot Usable Stock</span><b style="color:var(--ok);font-size:14px;">${passport.snapshot_usable_stock} units</b></div>
              <div class="qr-kv-row"><span>Live Current Usable</span><b>${live.usable_stock} units</b></div>
              <div class="qr-kv-row"><span>Action Directive</span><b style="color:#38bdf8;">${esc(passport.snapshot_action)}</b></div>
              <div class="qr-kv-row"><span>Snapshot Generated</span><b>${fmtDateTime(passport.generated_at)}</b></div>
            </div>
          </div>

          <!-- Reality Verification Tool -->
          <div class="qr-verify-shell">
            <div class="qr-verify-head">
              <b>🔍 Verify Scanned QR Payload</b>
              <span class="panel-hint">Paste scanned text to test reality check</span>
            </div>
            <div class="qr-verify-input-row">
              <textarea id="qrVerifyTextarea" class="input" rows="2" style="width:100%;font-size:11px;font-family:var(--mono);resize:vertical;" placeholder="Paste scanned QR text here...">${esc(passport.snapshot_payload)}</textarea>
            </div>
            <button class="btn btn-ghost btn-xs" id="runVerifyBtn" style="margin-top:6px;">Run Reality Verification</button>
            <div id="verifyResultBox" class="verify-result-box hidden"></div>
          </div>
        </div>
      </div>

      <div class="form-actions" style="margin-top:18px;">
        <button class="btn btn-ghost" id="closeQRModalBtn">Close</button>
        <button class="btn btn-accent" id="regenQRModalBtn">🔄 Regenerate Snapshot</button>
      </div>
    </div>
  `);

  // Bind buttons
  $("#closeQRModalBtn").onclick = closeModal;
  
  $("#regenQRModalBtn").onclick = async () => {
    $("#regenQRModalBtn").disabled = true;
    $("#regenQRModalBtn").textContent = "⏳ Regenerating…";
    try {
      const updated = await POST(`/products/${passport.product_id}/qr-passport/regenerate`);
      toast("QR Passport Regenerated", `Snapshot updated to v${updated.snapshot_version}`, "MEDIUM", "qr");
      renderQRPassportModalContent(updated);
      loadInventory();
    } catch (e) {
      toast("Regeneration Failed", e.message, "HIGH");
      $("#regenQRModalBtn").disabled = false;
      $("#regenQRModalBtn").textContent = "🔄 Regenerate Snapshot";
    }
  };

  const quickRegen = $("#quickRegenQRBtn");
  if (quickRegen) {
    quickRegen.onclick = () => $("#regenQRModalBtn").click();
  }

  $("#downloadQRBtn").onclick = () => {
    const a = document.createElement("a");
    a.href = passport.qr_image_url;
    a.download = `QR_Passport_${passport.sku}.png`;
    a.click();
  };

  $("#printLabelBtn").onclick = () => {
    printBinLabel(passport);
  };

  $("#runVerifyBtn").onclick = async () => {
    const text = $("#qrVerifyTextarea").value.trim();
    const resBox = $("#verifyResultBox");
    resBox.classList.remove("hidden");
    resBox.innerHTML = `<span>⏳ Comparing snapshot with database…</span>`;
    try {
      const v = await POST("/products/qr-passport/verify", { payload: text, product_id: passport.product_id });
      if (v.matched) {
        resBox.className = "verify-result-box fresh";
        resBox.innerHTML = `<b>✓ PERFECT MATCH:</b> ${esc(v.message)}`;
      } else {
        resBox.className = "verify-result-box stale";
        resBox.innerHTML = `<b>⚠️ REALITY CHECK MISMATCH:</b> ${esc(v.message)}`;
      }
    } catch (err) {
      resBox.className = "verify-result-box stale";
      resBox.innerHTML = `<b>Error:</b> ${esc(err.message)}`;
    }
  };
}

function printBinLabel(passport) {
  const printWin = window.open("", "_blank", "width=600,height=600");
  if (!printWin) {
    alert("Please allow popups to print bin labels.");
    return;
  }
  printWin.document.write(`
    <!DOCTYPE html>
    <html>
    <head>
      <title>Bin Label — ${passport.sku}</title>
      <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 20px; display: flex; justify-content: center; align-items: center; min-height: 90vh; background: #f8fafc; }
        .bin-label { width: 340px; border: 3px solid #0f172a; border-radius: 12px; padding: 18px; background: #fff; box-shadow: 0 4px 12px rgba(0,0,0,0.1); text-align: center; }
        .label-header { font-size: 11px; font-weight: 800; letter-spacing: 0.1em; color: #64748b; text-transform: uppercase; border-bottom: 2px solid #e2e8f0; padding-bottom: 6px; margin-bottom: 12px; }
        .label-qr { width: 180px; height: 180px; margin: 0 auto 10px; }
        .label-sku { font-size: 24px; font-weight: 900; font-family: monospace; color: #0f172a; margin-bottom: 4px; }
        .label-name { font-size: 14px; font-weight: 700; color: #334155; margin-bottom: 10px; }
        .label-meta-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 12px; background: #f1f5f9; padding: 8px; border-radius: 6px; text-align: left; margin-bottom: 10px; }
        .label-meta-grid span { color: #64748b; }
        .label-meta-grid b { color: #0f172a; }
        .label-action { font-size: 11px; font-weight: 700; padding: 6px; border-radius: 6px; background: #0f172a; color: #fff; }
        @media print { body { background: #fff; padding: 0; } .bin-label { box-shadow: none; } }
      </style>
    </head>
    <body>
      <div class="bin-label">
        <div class="label-header">WAREHOUSE PRODUCT PASSPORT</div>
        <img class="label-qr" src="${passport.qr_image_url}" alt="QR" />
        <div class="label-sku">${esc(passport.sku)}</div>
        <div class="label-name">${esc(passport.name)}</div>
        <div class="label-meta-grid">
          <div><span>Location:</span> <b>${esc(passport.location)}</b></div>
          <div><span>Status:</span> <b>${esc(passport.snapshot_status)}</b></div>
          <div><span>Usable:</span> <b>${passport.snapshot_usable_stock} units</b></div>
          <div><span>Version:</span> <b>v${passport.snapshot_version}</b></div>
        </div>
        <div class="label-action">${esc(passport.snapshot_action)}</div>
      </div>
      <script>window.onload = () => { window.print(); };</script>
    </body>
    </html>
  `);
  printWin.document.close();
}

/* --------------------------------------------------------------------- *
 * 9. ORDERS
 * --------------------------------------------------------------------- */
async function loadOrders() {
  const status = $("#orderStatusFilter")?.value || "";
  const priority = $("#orderPriorityFilter")?.value || "";
  let orders;
  try { orders = await GET(`/orders?status=${encodeURIComponent(status)}&priority=${encodeURIComponent(priority)}`); }
  catch (e) { $("#orderList").innerHTML = `<div class="empty-state">${esc(e.message)}</div>`; return; }

  $("#orderList").innerHTML = orders.length ? orders.map((o) => `
    <div class="order-card" data-id="${o.id}">
      <div class="order-head">
        <div>
          <b class="order-no">${esc(o.order_no)}</b>
          <span class="order-cust">${esc(o.customer_name)} (${esc(o.customer_priority || 'NORMAL')})</span>
          ${o.customer_email ? `<span class="order-email" style="font-size:11px;color:var(--text-mute);margin-left:8px;">📧 ${esc(o.customer_email)}</span>` : ''}
        </div>
        <div class="order-badges">
          <span class="status-chip st-${o.status}">${o.status}</span>
          <span class="prio-chip prio-${o.priority}">${o.priority}</span>
        </div>
      </div>
      <div class="order-meta-row">
        <div><span>Value:</span> <b>${fmtMoney(o.order_value)}</b></div>
        <div><span>Required By:</span> <b>${fmtDateTime(o.required_by)}</b></div>
        <div><span>Risk Score:</span> <b class="${o.risk_level === 'CRITICAL' ? 'text-critical' : ''}">${o.risk_score || 0} (${o.risk_level || 'LOW'})</b></div>
      </div>
      <div class="order-items-list">
        ${(o.items || []).map((it) => `
          <div class="order-item-pill">
            <span>${esc(it.sku)}</span>
            <b>Qty: ${it.quantity} (Allocated: ${it.allocated})</b>
          </div>`).join("")}
      </div>
      <div class="order-actions">
        <button class="btn btn-ghost btn-xs" data-act="explain">Explain Risk</button>
        <button class="btn btn-ghost btn-xs" data-act="allocate">Re-Allocate</button>
        <button class="btn btn-ghost btn-xs" data-act="email">Set Customer Email</button>
      </div>
    </div>`).join("") : `<div class="empty-state">No orders found</div>`;

  $("#orderList").onclick = async (e) => {
    const btn = e.target.closest("button[data-act]");
    if (!btn) return;
    const card = btn.closest(".order-card");
    const oid = card?.dataset.id;
    const order = orders.find((x) => x.id === oid);
    if (!order) return;

    if (btn.dataset.act === "explain") {
      const exp = await GET(`/orders/${oid}/explain`);
      openModal(`
        <div class="modal-title">Order Risk Explanation — ${esc(order.order_no)}</div>
        <div class="modal-sub">${esc(order.customer_name)} · Value: ${fmtMoney(order.order_value)}</div>
        <div class="why-reasons" style="margin:14px 0;">
          ${(exp.reasons || []).map((r) => `<div class="why-reason"><span>⚠</span><span>${esc(r)}</span></div>`).join("")}
        </div>
        <div class="modal-sub">Recommendations</div>
        <div class="why-reasons">
          ${(exp.recommendations || []).map((rc) => `<div class="why-reason" style="color:var(--ok);"><span>👉</span><span>${esc(rc)}</span></div>`).join("")}
        </div>
      `);
    }

    if (btn.dataset.act === "allocate") {
      await POST(`/orders/${oid}/allocate`);
      toast("Allocated", `Re-allocated stock for ${order.order_no}`);
      loadOrders(); loadDashboard();
    }

    if (btn.dataset.act === "email") {
      const currentEmail = order.customer_email || "";
      openModal(`
        <div class="modal-title">Set Customer Email — ${esc(order.order_no)}</div>
        <div class="modal-sub">Customer: ${esc(order.customer_name)}</div>
        <div class="form-group" style="margin-top:12px;">
          <label class="form-label">Customer Contact Email</label>
          <input id="custEmailInput" class="input" type="email" value="${esc(currentEmail)}" style="width:100%;" placeholder="e.g. buyer@customer.com" />
        </div>
        <div class="form-actions">
          <button class="btn btn-ghost" id="custEmailCancel">Cancel</button>
          <button class="btn btn-accent" id="custEmailSave">Save Email</button>
        </div>
      `);
      $("#custEmailCancel").onclick = closeModal;
      $("#custEmailSave").onclick = async () => {
        const val = $("#custEmailInput").value.trim();
        await PUT(`/orders/${oid}/customer-email?email=${encodeURIComponent(val)}`);
        toast("Customer Email Saved", `${order.order_no} -> ${val}`);
        closeModal(); loadOrders();
      };
    }
  };
}

$("#orderStatusFilter")?.addEventListener("change", loadOrders);
$("#orderPriorityFilter")?.addEventListener("change", loadOrders);

/* --------------------------------------------------------------------- *
 * 10. PIPELINE QUEUES (Picking, Packing, QC, Dispatch)
 * --------------------------------------------------------------------- */
async function loadQueue(stage) {
  let tasks;
  try { tasks = await GET(`/tasks?stage=${encodeURIComponent(stage)}&status=`); } catch (e) { return; }
  const container = $(`#${stage.toLowerCase()}Queue`);
  if (!container) return;

  const countTag = $(`#${stage.toLowerCase().slice(0, 4)}Count`);
  if (countTag) countTag.textContent = tasks.filter((t) => t.status !== "DONE").length;

  container.innerHTML = tasks.length ? tasks.map((t, idx) => {
    const isDone = t.status === "DONE";
    let extraHtml = "";

    if (stage === "PICKING") {
      const routes = ["A07 → B02 → C01", "B03 → A01 → A05", "C02 → C08 → D01", "A04 → B06"][idx % 4];
      extraHtml = `
        <div class="task-extra-grid">
          <div class="task-extra-chip"><span>🎯 Pick Route:</span> <b>${routes}</b></div>
          <div class="task-extra-chip"><span>📍 Items:</span> <b>${1 + (idx % 3)} SKU(s) allocated</b></div>
        </div>`;
    } else if (stage === "PACKING") {
      const cartons = ["Box M (2.4 kg) · Bubble Wrap", "Heavy Duty L (5.1 kg)", "Standard Pouch S (0.8 kg)"][idx % 3];
      extraHtml = `
        <div class="task-extra-grid">
          <div class="task-extra-chip"><span>📦 Packaging:</span> <b>${cartons}</b></div>
          <div class="task-extra-chip"><span>🏷️ Barcode:</span> <b style="color:var(--ok);">✓ Scanned & Verified</b></div>
        </div>`;
    } else if (stage === "QC") {
      extraHtml = `
        <div class="task-extra-grid">
          <div class="task-extra-chip"><span>🔍 Check:</span> <b>Damage & Serial Integrity</b></div>
          <div class="task-extra-chip"><span>📋 Inspection:</span> <b>Pending Sign-off</b></div>
        </div>`;
    } else if (stage === "DISPATCH") {
      const carriers = ["Delhivery Express", "BlueDart Priority Air", "Bluedart Cargo"][idx % 3];
      const awb = `AWB-${8921000 + idx * 37}`;
      const bay = `Dock Bay #${(idx % 4) + 1}`;
      extraHtml = `
        <div class="task-extra-grid">
          <div class="task-extra-chip"><span>🚚 Carrier:</span> <b>${carriers}</b></div>
          <div class="task-extra-chip"><span>🧾 Tracking:</span> <code>${awb}</code></div>
          <div class="task-extra-chip"><span>🚪 Loading:</span> <b>${bay}</b></div>
        </div>`;
    }

    return `
      <div class="task-card ${isDone ? 'done' : ''}" data-tid="${t.id}">
        <div class="task-head">
          <div style="display:flex;align-items:center;gap:8px;">
            <b class="task-order-no">${esc(t.order_no || 'Task')}</b>
            <span class="status-chip st-${t.status}">${t.status}</span>
          </div>
          <span class="prio-chip prio-${esc(t.priority || 'MEDIUM')}">${esc(t.priority || 'MEDIUM')}</span>
        </div>
        <div class="task-meta">Customer: <b>${esc(t.customer_name || 'N/A')}</b> · Assigned: <b>${esc(t.worker_name || 'Autonomous Pool')}</b></div>
        ${extraHtml}
        <div class="task-actions" style="margin-top:12px;">
          ${stage === "QC" ? `
            <button class="btn btn-accent btn-xs" data-qc="pass">✓ Pass QC Inspection</button>
            <button class="btn btn-danger btn-xs" data-qc="fail">✕ Flag Defect / Fail</button>
          ` : stage === "DISPATCH" ? `
            <button class="btn btn-accent btn-xs" data-act="complete">🚚 Dispatch Shipment</button>
          ` : `
            <button class="btn btn-accent btn-xs" data-act="complete">✓ Complete ${stage}</button>
          `}
        </div>
      </div>
    `;
  }).join("") : `<div class="empty-state">No tasks in ${stage} queue right now</div>`;

  container.onclick = async (e) => {
    const btn = e.target.closest("button[data-act], button[data-qc]");
    if (!btn) return;
    const card = btn.closest(".task-card");
    const tid = card?.dataset.tid;

    if (btn.dataset.act === "complete") {
      await POST(`/tasks/${tid}/complete`);
      toast("Task Completed", `Advanced from ${stage}`, "MEDIUM");
      loadQueue(stage); loadDashboard();
    }
    if (btn.dataset.qc === "pass") {
      await POST(`/tasks/${tid}/qc`, { passed: true });
      toast("QC Passed", "Order verified and moved to Dispatch", "MEDIUM");
      loadQueue("QC"); loadDashboard();
    }
    if (btn.dataset.qc === "fail") {
      const notes = prompt("Reason for QC failure:", "Damaged packaging or defective item") || "Quality check failed";
      await POST(`/tasks/${tid}/qc`, { passed: false, notes });
      toast("QC Failed", "Exception created and alert dispatched", "HIGH");
      loadQueue("QC"); loadDashboard();
    }
  };
}

/* --------------------------------------------------------------------- *
 * 11. EXCEPTIONS & DECISIONS
 * --------------------------------------------------------------------- */
async function loadExceptions() {
  const status = $("#excStatus")?.value || "";
  let excs;
  try { excs = await GET(`/exceptions?status=${encodeURIComponent(status)}`); } catch (e) { return; }
  const container = $("#exceptionList");
  if (!container) return;

  container.innerHTML = excs.length ? excs.map((x) => `
    <div class="exc-card ${x.severity.toLowerCase()}" data-id="${x.id}" data-pid="${x.product_id || ''}">
      <div class="exc-head">
        <span class="rec-severity sev-${x.severity}">${x.severity}</span>
        <b>${esc(x.type)}</b>
        <span class="status-chip st-${x.status}" style="margin-left:auto;">${x.status}</span>
      </div>
      <div class="exc-desc">${esc(x.description)}</div>
      <div class="exc-actions">
        ${x.status === "OPEN" ? `
          <button class="btn btn-accent btn-xs" data-act="resolve">Resolve</button>
          <button class="btn btn-ghost btn-xs" data-act="alt">Find Alternate SKU</button>
        ` : `<span class="muted" style="font-size:11px;">Resolved: ${esc(x.resolution || 'Yes')}</span>`}
      </div>
    </div>`).join("") : `<div class="empty-state">No exceptions found</div>`;

  container.onclick = async (e) => {
    const btn = e.target.closest("button[data-act]");
    if (!btn) return;
    const card = btn.closest(".exc-card");
    const id = card?.dataset.id, pid = card?.dataset.pid;
    if (btn.dataset.act === "resolve") {
      const resolution = prompt("Resolution note:", "Resolved by operations override") || "Resolved";
      await POST(`/exceptions/${id}/resolve`, { resolution });
      toast("Exception Resolved", resolution);
      loadExceptions(); loadDashboard();
    }
    if (btn.dataset.act === "alt" && pid) {
      const data = await GET(`/inventory/alternate/${pid}`);
      openModal(`
        <div class="modal-title">Alternate locations — ${esc(data.product?.sku)}</div>
        <div class="why-reasons">
          ${(data.alternates || []).map((a) => `<div class="why-reason"><span>${esc(a.location)} (${esc(a.sku)})</span><b>${a.available_stock} units</b></div>`).join("")}
        </div>`);
    }
  };
}

$("#excStatus")?.addEventListener("change", loadExceptions);
$("#refreshExcBtn")?.addEventListener("click", loadExceptions);

async function loadDecisions() {
  let decisions;
  try { decisions = await GET("/decisions?regenerate=true"); } catch (e) { return; }
  renderRecommendations($("#decisionList"), decisions.filter((d) => d.status === "PENDING"));
}
$("#refreshDecBtn")?.addEventListener("click", loadDecisions);
$("#applySafeBtn")?.addEventListener("click", async () => {
  const r = await POST("/decisions/apply-safe");
  toast("Safe Decisions Applied", `${r.applied} action(s) executed`, "MEDIUM");
  loadDecisions(); loadDashboard();
});
$("#applySafeBtn2")?.addEventListener("click", async () => {
  const r = await POST("/decisions/apply-safe");
  toast("Safe Decisions Applied", `${r.applied} action(s) executed`, "MEDIUM");
  loadDashboard();
});

function renderRecommendations(container, recs) {
  if (!container) return;
  if (!recs.length) { container.innerHTML = `<div class="empty-state"><div class="es-icon">🤖</div>All clear — no active recommendations</div>`; return; }
  container.innerHTML = recs.map((r) => `
    <div class="rec-card" data-id="${r.id}">
      <div class="rec-top">
        <div class="rec-problem"><span class="rec-severity sev-${r.severity}">${r.severity}</span>${esc(r.problem)}</div>
        <div class="rec-conf">${r.confidence}%</div>
      </div>
      <div class="rec-action">→ ${esc(r.recommendation)}</div>
      <div class="rec-actions">
        <button class="btn btn-ghost btn-sm" data-act="why">WHY?</button>
        <button class="btn btn-ghost btn-sm" data-act="simulate">SIMULATE</button>
        <button class="btn btn-accent btn-sm" data-act="apply">APPLY</button>
        <button class="btn btn-ghost btn-sm" data-act="dismiss">DISMISS</button>
      </div>
    </div>`).join("");
  container.onclick = async (e) => {
    const btn = e.target.closest("button[data-act]");
    if (!btn) return;
    const card = btn.closest(".rec-card");
    const id = card.dataset.id;
    const rec = recs.find((r) => r.id === id);
    if (btn.dataset.act === "why") showDecisionWhy(rec);
    if (btn.dataset.act === "simulate") await showDecisionSimulate(id, rec);
    if (btn.dataset.act === "apply") { await POST(`/decisions/${id}/apply`); toast("Decision applied", rec.recommendation, "MEDIUM"); loadView(currentView); }
    if (btn.dataset.act === "dismiss") { await POST(`/decisions/${id}/dismiss`); loadView(currentView); }
  };
}

function showDecisionWhy(rec) {
  openModal(`
    <div class="modal-title">Why this recommendation?</div>
    <div class="modal-sub">${esc(rec.problem)}</div>
    <div class="why-reasons">
      <div class="why-reason"><span>Recommendation</span><span>${esc(rec.recommendation)}</span></div>
      <div class="why-reason"><span>Confidence</span><span class="wr-pts">${rec.confidence}%</span></div>
      <div class="why-reason"><span>Severity</span><span class="rec-severity sev-${rec.severity}">${rec.severity}</span></div>
    </div>
    <p class="muted">${esc(rec.reason || "No further reasoning provided by the decision engine.")}</p>
    ${rec.alternatives && rec.alternatives.length ? `
      <div class="modal-sub" style="margin-top:14px;">Alternatives considered</div>
      <div class="alternatives-list">
        ${rec.alternatives.map((a) => `<div class="alt-row ${a.recommended ? "recommended" : ""}"><span class="alt-name">${esc(a.name || a.option)}</span><span class="alt-conf">${a.confidence}%</span></div>`).join("")}
      </div>` : ""}
  `);
}

async function showDecisionSimulate(id, rec) {
  openModal(`<div class="modal-title">Simulating…</div><div class="modal-sub">${esc(rec.recommendation)}</div>`);
  let sim;
  try { sim = await GET(`/decisions/${id}/simulate`); } catch (e) { openModal(`<div class="modal-title">Simulation failed</div><p class="muted">${esc(e.message)}</p>`); return; }
  openModal(`
    <div class="modal-title">Simulation — Act vs Do Nothing</div>
    <div class="modal-sub">${esc(sim.explanation || rec.recommendation)}</div>
    <div class="sim-compare">
      <div class="sim-col now"><div class="sc-label">Current health</div><div class="sc-val">${sim.current?.overall ?? "--"}</div></div>
      <div class="sim-col act"><div class="sc-label">If we act</div><div class="sc-val">${sim.act?.overall ?? "--"}</div></div>
    </div>
    <div class="impact-panel">
      <div class="impact-col act">
        <div class="impact-col-title">Act</div>
        <div class="impact-stat"><span>Delayed orders</span><b>${sim.impact?.delayed_orders_change?.act ?? "--"}</b></div>
        <div class="impact-stat"><span>Potential loss</span><b>${fmtMoney(sim.impact?.potential_loss?.act)}</b></div>
      </div>
      <div class="impact-col nothing">
        <div class="impact-col-title">Do nothing</div>
        <div class="impact-stat"><span>Delayed orders</span><b>${sim.impact?.delayed_orders_change?.do_nothing ?? "--"}</b></div>
        <div class="impact-stat"><span>Potential loss</span><b>${fmtMoney(sim.impact?.potential_loss?.do_nothing)}</b></div>
      </div>
    </div>
    <div class="form-actions">
      <button class="btn btn-ghost" id="simCancel">Cancel</button>
      <button class="btn btn-accent" id="simApply">Apply Decision</button>
    </div>
  `);
  $("#simCancel").onclick = closeModal;
  $("#simApply").onclick = async () => { await POST(`/decisions/${id}/apply`); toast("Decision applied", rec.recommendation); closeModal(); loadView(currentView); };
}

/* --------------------------------------------------------------------- *
 * 12. ALERTS & OUTBOX CENTER
 * --------------------------------------------------------------------- */
async function loadAlerts() {
  let alerts;
  try { alerts = await GET("/alerts?limit=40"); } catch (e) { return; }
  const activeContainer = $("#activeAlertList");
  const histContainer = $("#historyAlertList");
  const badge = $("#notifBadge");
  const topBadge = $("#topbarNotifBadge");

  const active = alerts.filter((a) => a.status === "ACTIVE");
  const count = active.filter((a) => ["HIGH", "CRITICAL"].includes(a.severity)).length;
  
  if (badge) {
    badge.textContent = count;
    badge.classList.toggle("hidden", count === 0);
  }
  if (topBadge) {
    topBadge.textContent = count;
    topBadge.classList.toggle("hidden", count === 0);
  }

  if (activeContainer) {
    activeContainer.innerHTML = active.length ? active.map((a) => `
      <div class="alert-row ${a.severity.toLowerCase()}">
        <div style="flex:1;">
          <div class="alert-title">${esc(a.title)}</div>
          <div class="alert-msg">${esc(a.body || a.message || '')}</div>
          <div class="alert-time">${fmtDateTime(a.created_at)} · <b>${a.severity}</b> · Recipient: ${esc(activeCompanyEmail)}</div>
        </div>
      </div>`).join("") : `<div class="empty-state">All systems normal — no active alerts</div>`;
  }

  if (histContainer) {
    histContainer.innerHTML = alerts.length ? alerts.map((a) => `
      <div class="alert-row ${a.severity.toLowerCase()}">
        <div style="flex:1;">
          <div class="alert-title">${esc(a.title)}</div>
          <div class="alert-msg">${esc(a.body || a.message || '')}</div>
          <div class="alert-time">${fmtDateTime(a.created_at)} · Status: <b>${a.status}</b></div>
        </div>
      </div>`).join("") : `<div class="empty-state">No alert history</div>`;
  }
}

let outboxChannelFilter = "";
async function loadOutbox() {
  const list = $("#deliveryList");
  if (!list) return;
  try {
    const items = await GET(`/outbox?channel=${encodeURIComponent(outboxChannelFilter)}&limit=50`);
    list.innerHTML = items.length ? items.map((o) => `
      <div class="outbox-row" data-id="${o.id}">
        <div class="outbox-head">
          <span class="outbox-ch">${esc(o.channel)}</span>
          <span class="outbox-status ${esc(o.status)}">${esc(o.status)}</span>
        </div>
        ${o.subject ? `<div class="outbox-subject">${esc(o.subject)}</div>` : ''}
        <div class="outbox-body">${esc(o.body || '').slice(0, 300)}</div>
        <div class="alert-time" style="display:flex;justify-content:space-between;align-items:center;margin-top:6px;">
          <span>${fmtDateTime(o.created_at)} ${o.recipient ? '→ ' + esc(o.recipient) : ''}</span>
          <button class="btn btn-ghost btn-xs btn-view-outbox" data-id="${o.id}">Preview Email</button>
        </div>
      </div>`).join("") : `<div class="empty-state">Outbox is empty</div>`;

    $$(".btn-view-outbox", list).forEach((btn) => {
      btn.addEventListener("click", () => {
        const item = items.find((x) => x.id === btn.dataset.id);
        if (item) showEmailDetailModal(item);
      });
    });
  } catch (e) { list.innerHTML = `<div class="empty-state">${esc(e.message)}</div>`; }
}

$$("#alertCenterTabs .tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    $$("#alertCenterTabs .tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    const sub = tab.dataset.sub;
    $$(".alert-sub").forEach((s) => s.classList.toggle("hidden", s.id !== `sub-${sub}`));
    if (sub === "history") loadOutbox();
  });
});

/* --------------------------------------------------------------------- *
 * 13. ANALYTICS & WAREHOUSE MAP
 * --------------------------------------------------------------------- */
async function loadAnalytics() {
  try {
    const [health, impact, radar] = await Promise.all([
      GET("/analytics/health"), GET("/analytics/impact"), GET("/analytics/risk-radar")
    ]);
    renderHealth($("#analyticsHealth"), health);
    renderImpact($("#analyticsImpact"), impact);
    const rr = $("#riskRadar");
    if (rr) {
      rr.innerHTML = radar.map((s) => `
        <div class="risk-slot">
          <div class="rs-time">${fmtTime(s.time)}</div>
          <div class="rs-level ${s.level}">${s.level}</div>
          ${s.risks.length ? s.risks.map((r) => `<div class="rs-item">${esc(r)}</div>`) : `<div class="rs-item">No issues</div>`}
        </div>`).join("");
    }
  } catch (e) { /* silent */ }
}

async function loadWarehouseMap() {
  const grid = $("#warehouseGrid");
  if (!grid) return;
  let zones;
  try { zones = await GET("/warehouse/map"); } catch (e) { grid.innerHTML = `<div class="empty-state">${esc(e.message)}</div>`; return; }
  zones.sort((a, b) => a.location.localeCompare(b.location));
  grid.innerHTML = zones.map((z) => `
    <div class="zone-cell ${z.status}" data-loc="${esc(z.location)}">
      <span class="zone-dot" style="background:${{ NORMAL: "var(--ok)", LOW: "var(--low)", CRITICAL: "var(--danger)", OUT_OF_STOCK: "var(--critical)" }[z.status]}"></span>
      <div class="zone-code">${esc(z.location)}</div>
      <div class="zone-count">${z.products.length} SKU${z.products.length === 1 ? "" : "s"}${z.issues ? ` · ${z.issues} issue${z.issues === 1 ? "" : "s"}` : ""}</div>
    </div>`).join("");
}

/* --------------------------------------------------------------------- *
 * 14. AUDIT & SETTINGS
 * --------------------------------------------------------------------- */
async function loadAudit() {
  const body = $("#auditBody");
  if (!body) return;
  try {
    const rows = await GET("/audit?limit=150");
    body.innerHTML = rows.length ? rows.map((r) => `
      <tr>
        <td class="mono">${fmtDateTime(r.at)}</td>
        <td>${esc(r.who)}</td>
        <td>${esc(r.action)}</td>
        <td>${esc(r.entity_type)}</td>
        <td class="mono" style="max-width:180px;overflow:hidden;text-overflow:ellipsis;">${esc(r.old_value || '')}</td>
        <td class="mono" style="max-width:180px;overflow:hidden;text-overflow:ellipsis;">${esc(r.new_value || '')}</td>
      </tr>`).join("") : `<tr><td colspan="6" class="empty-state">No audit entries yet</td></tr>`;
  } catch (e) { body.innerHTML = `<tr><td colspan="6" class="empty-state">${esc(e.message)}</td></tr>`; }
}

const EMAIL_SETTINGS = [
  ["automatic_email_enabled", "Automatic Email Alerts", "Background real-time email dispatch for critical shortages & digests", "toggle"],
  ["company_email", "Company / Manager Recipient Email", "Main recipient inbox for warehouse operational alerts", "text"],
  ["twilio_email_from", "Twilio Comms Sender Email", "Twilio verified email address (e.g. AC0a3b0b783c383ace8cb92e43b98a7696@twilio.email)", "text"],
  ["twilio_sendgrid_api_key", "Twilio SendGrid API Key (Optional)", "Twilio SendGrid API key for direct email delivery (starts with SG...)", "password"],
  ["smtp_host", "SMTP Host (Optional Fallback)", "e.g. smtp.gmail.com (leave blank for Twilio Email or real-time simulator)", "text"],
  ["smtp_port", "SMTP Port", "587 (STARTTLS) or 465 (SSL)", "text"],
  ["smtp_username", "SMTP Username / Login", "Your email address or SMTP username", "text"],
  ["smtp_password", "SMTP Password / App Password", "16-character Google App Password or SMTP token", "password"],
];

const WHATSAPP_SETTINGS = [
  ["automatic_whatsapp_enabled", "Automatic Twilio WhatsApp Alerts", "Dispatches WhatsApp messages for critical stockouts & digests", "toggle"],
  ["whatsapp_number", "WhatsApp Recipient Phone", "Recipient phone number in international format (e.g. +918019753996)", "text"],
  ["twilio_account_sid", "Twilio Account SID", "Twilio API SID (starts with AC... or SK...)", "text"],
  ["twilio_auth_token", "Twilio Auth Token", "Twilio Authentication Secret Token", "password"],
  ["twilio_whatsapp_from", "Twilio WhatsApp Sender", "Twilio Sender (e.g. whatsapp:+17372508034)", "text"],
  ["twilio_content_sid", "Twilio Content SID / Template", "Twilio pre-approved WhatsApp Template SID (e.g. HXfe5ab5f00277942d4d4200328b4d403c)", "text"],
];

const SUPPLIER_PO_SETTINGS = [
  ["auto_reorder_email_enabled", "Automatic Low-Stock Reorder PO Service", "Automatically dispatches PO emails to suppliers when stock drops low", "toggle"],
  ["supplier_po_recipient", "Supplier PO Target Inbox", "Email address where automated purchase orders are routed", "text"],
  ["supplier_po_template_subject", "Purchase Order Subject Template", "Default subject line for automated purchase orders", "text"],
];

const AUTO_SETTINGS = [
  ["automation_enabled", "Autopilot Automation", "Allow autonomous decisions & 1-click execution", "toggle"],
  ["warehouse_name", "Warehouse Facility Name", "Displayed across Command Center header", "text"],
];

async function loadSettings() {
  let settings;
  try { settings = await GET("/settings"); } catch (e) { return; }
  const es = $("#emailSettingsList"), ws = $("#whatsappSettingsList"), ps = $("#supplierPoSettingsList"), as = $("#autoSettingsList");
  if (es) es.innerHTML = EMAIL_SETTINGS.map(([key, label, hint, type]) => settingRow(key, label, hint, settings[key], type)).join("");
  if (ws) ws.innerHTML = WHATSAPP_SETTINGS.map(([key, label, hint, type]) => settingRow(key, label, hint, settings[key], type)).join("");
  if (ps) ps.innerHTML = SUPPLIER_PO_SETTINGS.map(([key, label, hint, type]) => settingRow(key, label, hint, settings[key], type)).join("");
  if (as) as.innerHTML = AUTO_SETTINGS.map(([key, label, hint, type]) => settingRow(key, label, hint, settings[key], type)).join("");
  bindSettingToggles();
}

function settingRow(key, label, hint, value, type) {
  if (type === "text" || type === "password") {
    return `<div class="setting-row"><div><div class="setting-label">${label}</div><div class="setting-hint">${hint}</div></div><input class="input" style="width:260px;" data-key="${key}" type="${type}" value="${esc(value ?? "")}" /></div>`;
  }
  const on = value === "true" || value === "1" || value === true;
  return `<div class="setting-row"><div><div class="setting-label">${label}</div><div class="setting-hint">${hint}</div></div><div class="toggle ${on ? "on" : ""}" data-key="${key}"></div></div>`;
}

function bindSettingToggles() {
  $$(".toggle[data-key]").forEach((t) => t.addEventListener("click", async () => {
    const on = !t.classList.contains("on");
    t.classList.toggle("on", on);
    try {
      await PUT(`/settings/${t.dataset.key}`, { value: String(on) });
      toast("Setting saved", t.dataset.key);
    } catch (e) { t.classList.toggle("on", !on); alert(e.message); }
  }));
  $$("input[data-key]").forEach((inp) => inp.addEventListener("change", async () => {
    try {
      await PUT(`/settings/${inp.dataset.key}`, { value: inp.value });
      toast("Setting saved", inp.dataset.key);
      if (inp.dataset.key === "company_email") {
        activeCompanyEmail = inp.value;
      }
    } catch (e) { alert(e.message); }
  }));
}

/* --------------------------------------------------------------------- *
 * 15. AI WAREHOUSE COPILOT (PERSISTENT & DEDICATED VIEW)
 * --------------------------------------------------------------------- */
const chatPanel = $("#aiChatPanel"), chatMessages = $("#aiChatMessages"), chatInput = $("#aiChatInput"), chatSend = $("#aiChatSend"), chatOpen = $("#aiChatOpen"), chatClose = $("#aiChatClose");
const copilotChatHistory = $("#copilotChatHistory"), copilotPageInput = $("#copilotPageInput"), copilotPageSend = $("#copilotPageSend");

let chatHistory = [];
try {
  const saved = localStorage.getItem("wa_copilot_chat");
  if (saved) chatHistory = JSON.parse(saved);
} catch (e) {}

function renderAllChatMessages() {
  const containers = [chatMessages, copilotChatHistory].filter(Boolean);
  containers.forEach((box) => {
    box.innerHTML = "";
    if (!chatHistory || chatHistory.length === 0) {
      box.innerHTML = `
        <div class="ai-msg assistant">
          <div class="ai-msg-role"><span class="ai-mini-avatar">✦</span> WAREHOUSE COPILOT</div>
          <div class="ai-msg-body">
            Ask me anything about your warehouse. I analyze live inventory runways, at-risk orders, bottlenecks, and operational decisions in real time.
          </div>
        </div>`;
    } else {
      chatHistory.forEach((msg) => {
        const el = document.createElement("div");
        el.className = `ai-msg ${msg.role === "user" ? "user" : "assistant"}`;
        el.innerHTML = `<div class="ai-msg-role">${msg.role === "user" ? "You" : "Warehouse Copilot"}</div><div class="ai-msg-body">${esc(msg.content).replace(/\n/g, "<br>")}</div>${msg.meta ? `<div class="ai-msg-meta">${esc(msg.meta)}</div>` : ""}`;
        box.appendChild(el);
      });
    }
    box.scrollTop = box.scrollHeight;
  });
}

function appendChatBubble(role, text, meta = "") {
  const item = { role, content: text, meta };
  chatHistory.push(item);
  try {
    localStorage.setItem("wa_copilot_chat", JSON.stringify(chatHistory.slice(-40)));
  } catch (e) {}

  const containers = [chatMessages, copilotChatHistory].filter(Boolean);
  containers.forEach((box) => {
    const el = document.createElement("div");
    el.className = `ai-msg ${role}`;
    el.innerHTML = `<div class="ai-msg-role">${role === "user" ? "You" : "Warehouse Copilot"}</div><div class="ai-msg-body">${esc(text).replace(/\n/g, "<br>")}</div>${meta ? `<div class="ai-msg-meta">${esc(meta)}</div>` : ""}`;
    box.appendChild(el);
    box.scrollTop = box.scrollHeight;
  });
}

async function sendChatFrom(inputEl, sendBtnEl) {
  if (!inputEl) return;
  const message = inputEl.value.trim();
  if (!message) return;
  inputEl.value = "";
  if (sendBtnEl) sendBtnEl.disabled = true;

  appendChatBubble("user", message);

  // Add thinking bubble to both containers
  const thinkingElements = [];
  [chatMessages, copilotChatHistory].filter(Boolean).forEach((box) => {
    const thinking = document.createElement("div");
    thinking.className = "ai-msg assistant thinking";
    thinking.innerHTML = `<div class="ai-msg-role">Warehouse Copilot</div><div class="ai-msg-body">Analyzing live warehouse context…</div>`;
    box.appendChild(thinking);
    box.scrollTop = box.scrollHeight;
    thinkingElements.push(thinking);
  });

  try {
    const r = await POST("/chat", { message, history: chatHistory.slice(-8) });
    thinkingElements.forEach((el) => el.remove());
    const meta = `Live context: ${r.context.active_alerts} alerts · ${r.context.open_exceptions} exceptions · ${r.context.pending_decisions} decisions`;
    appendChatBubble("assistant", r.answer, meta);
  } catch (e) {
    thinkingElements.forEach((el) => el.remove());
    appendChatBubble("assistant", `I couldn't complete that query: ${e.message}`);
  } finally {
    if (sendBtnEl) sendBtnEl.disabled = false;
    inputEl.focus();
  }
}

async function loadCopilotView() {
  renderAllChatMessages();
  const metricsEl = $("#copilotContextMetrics");
  if (metricsEl) {
    try {
      const d = await GET("/dashboard");
      const impact = d.impact || {};
      metricsEl.innerHTML = `
        <div class="copilot-metric-chip ${d.out_of_stock_products > 0 ? 'critical' : 'ok'}">
          <span>⛔ Out of Stock SKUs</span>
          <b>${d.out_of_stock_products || 0} items</b>
        </div>
        <div class="copilot-metric-chip ${d.low_stock_products > 0 ? 'warn' : 'ok'}">
          <span>📉 Low Stock Items</span>
          <b>${d.low_stock_products || 0} items</b>
        </div>
        <div class="copilot-metric-chip ${d.priority_stats?.CRITICAL > 0 ? 'critical' : 'ok'}">
          <span>🚨 Critical Priority Orders</span>
          <b>${d.priority_stats?.CRITICAL || 0} orders</b>
        </div>
        <div class="copilot-metric-chip ${impact.orders_at_risk > 0 ? 'warn' : 'ok'}">
          <span>⏱ Orders at Risk</span>
          <b>${impact.orders_at_risk || 0} orders</b>
        </div>
        <div class="copilot-metric-chip ${d.open_exceptions > 0 ? 'critical' : 'ok'}">
          <span>🧩 Active Exceptions</span>
          <b>${d.open_exceptions || 0} open</b>
        </div>
        <div class="copilot-metric-chip ok">
          <span>🤖 Autopilot Score</span>
          <b>${d.autopilot?.score || 0}/100</b>
        </div>
      `;
    } catch (e) {
      metricsEl.innerHTML = `<div class="loading-shimmer">Failed to load live metrics: ${esc(e.message)}</div>`;
    }
  }
  if (copilotPageInput) copilotPageInput.focus();
}

// Initial chat render
renderAllChatMessages();

// Wire drawers and dedicated view
if (chatOpen) chatOpen.addEventListener("click", () => { chatPanel?.classList.add("open"); chatInput?.focus(); });
if (chatClose) chatClose.addEventListener("click", () => chatPanel?.classList.remove("open"));
if (chatSend) chatSend.addEventListener("click", () => sendChatFrom(chatInput, chatSend));
if (chatInput) chatInput.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChatFrom(chatInput, chatSend); } });

if (copilotPageSend) copilotPageSend.addEventListener("click", () => sendChatFrom(copilotPageInput, copilotPageSend));
if (copilotPageInput) copilotPageInput.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChatFrom(copilotPageInput, copilotPageSend); } });

const clearBtn = $("#clearCopilotChatBtn");
if (clearBtn) {
  clearBtn.addEventListener("click", () => {
    if (confirm("Clear AI Copilot chat history?")) {
      chatHistory = [];
      try { localStorage.removeItem("wa_copilot_chat"); } catch (e) {}
      renderAllChatMessages();
      toast("Chat history cleared");
    }
  });
}

$$(".btn-quick-copilot, [data-chat-suggestion]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const prompt = btn.getAttribute("data-prompt") || btn.getAttribute("data-chat-suggestion") || "";
    if (!prompt) return;
    if (currentView === "copilot" && copilotPageInput) {
      copilotPageInput.value = prompt;
      sendChatFrom(copilotPageInput, copilotPageSend);
    } else {
      chatPanel?.classList.add("open");
      if (chatInput) {
        chatInput.value = prompt;
        sendChatFrom(chatInput, chatSend);
      }
    }
  });
});

/* --------------------------------------------------------------------- *
 * 16. GLOBAL SEARCH
 * --------------------------------------------------------------------- */
const searchInput = $("#globalSearch"), searchResults = $("#searchResults");
if (searchInput && searchResults) {
  searchInput.addEventListener("input", debounce(async () => {
    const q = searchInput.value.trim();
    if (q.length < 2) { searchResults.classList.add("hidden"); return; }
    try {
      const r = await GET(`/search?q=${encodeURIComponent(q)}`);
      const groups = [
        ["Products", r.products, (p) => `${p.sku} — ${p.name}`, () => showView("inventory")],
        ["Orders", r.orders, (o) => `${o.order_no} — ${o.customer_name}`, () => showView("orders")],
        ["Exceptions", r.exceptions, (x) => x.description, () => showView("exceptions")],
      ];
      let html = "";
      groups.forEach(([label, items, fmt, go]) => {
        if (items && items.length) {
          html += `<div class="sr-group">${label}</div>` + items.map((it) => `<div class="sr-item" data-go="${label}">${esc(fmt(it))}</div>`).join("");
        }
      });
      searchResults.innerHTML = html || `<div class="sr-item">No matches</div>`;
      searchResults.classList.remove("hidden");
      $$(".sr-item[data-go]", searchResults).forEach((el) => el.addEventListener("click", () => {
        const label = el.dataset.go;
        if (label === "Products") showView("inventory");
        if (label === "Orders") showView("orders");
        if (label === "Exceptions") showView("exceptions");
        searchResults.classList.add("hidden"); searchInput.value = "";
      }));
    } catch (e) { /* ignore */ }
  }, 250));
  document.addEventListener("click", (e) => { if (!e.target.closest(".search-box")) searchResults.classList.add("hidden"); });
}

/* --------------------------------------------------------------------- *
 * 17. REAL-TIME (SSE with Reactive Updates)
 * --------------------------------------------------------------------- */
let es = null;
let pollTimer = null;

function connectSSE() {
  try {
    if (es) es.close();
    es = new EventSource(`${API_BASE}/events/stream`);
    es.onopen = () => setConn(true);
    es.onerror = () => { setConn(false); es.close(); startPolling(); };
    es.onmessage = (evt) => {
      let data;
      try { data = JSON.parse(evt.data); } catch { return; }
      handleRealtimeEvent(data);
    };
  } catch (e) { startPolling(); }
}

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(() => { loadDashboard(); if (currentView !== "dashboard") loadView(currentView); }, 6000);
}

function handleRealtimeEvent(data) {
  const evt = data.event;
  if (evt === "ready") return;

  if (evt === "desktop_notification" || evt === "alert" || evt === "critical_alert") {
    toast(data.title || "Warehouse Alert", data.message || data.body || "", data.severity || "MEDIUM", "alert");
    loadAlerts();
  }
  if (evt === "outbox_created" || evt === "notification_dispatched" || evt === "notification_updated") {
    const ch = data.channel || "NOTIFICATION";
    let iconLabel = "Email";
    if (ch.includes("WHATSAPP")) iconLabel = "WhatsApp";
    else if (ch.includes("SUPPLIER_PO") || ch.includes("PO")) iconLabel = "Supplier PO Reorder";

    toast(`⚡ Real-Time ${iconLabel} Sent`, `${data.subject || data.body || ''} → ${data.recipient || ''}`, "MEDIUM", ch.toLowerCase());
    loadDashOutbox();
    loadOutbox();
  }
  if (evt === "reset") {
    fetchActiveEmail();
    loadDashboard();
    if (currentView !== "dashboard") loadView(currentView);
  }
  if (["inventory_updated", "order_updated", "worker_updated", "exception", "decision_applied"].includes(evt)) {
    loadDashboard();
    if (currentView !== "dashboard") loadView(currentView);
  }
}

/* --------------------------------------------------------------------- *
 * 18. CLOCK & BOOTSTRAP
 * --------------------------------------------------------------------- */
setInterval(() => { const c = $("#clock"); if (c) c.textContent = new Date().toLocaleTimeString(); }, 1000);

async function bootstrap() {
  initTheme();
  try {
    await GET("/dashboard");
    setConn(true);
  } catch (e) {
    setConn(false);
  }
  await fetchActiveEmail();
  showView(currentView);
  connectSSE();
}

document.addEventListener("DOMContentLoaded", bootstrap);
if (document.readyState !== "loading") bootstrap();

})();