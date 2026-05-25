// Minimal pywebview bridge stub for browser preview (no-op promises)
let api = window.pywebview?.api || {
  get_config: async () => ({
    run_mode: null,
    depth: 2,
    max_nodes: 500,
    rate_limit_rpm: 120,
    skip_private_profiles: true,
    include_group_links: true,
    include_game_overlap: false,
    hub_percentile: 0.99,
  }),
  set_config: async (cfg) => cfg,
  apply_preset: async () => ({}),
  run_scan: async () => ({ ok: false, error: "Not running inside app." }),
  dry_run: async () => ({ ok: false, error: "Not running inside app." }),
  open_outputs: async () => false,
  has_api_key: async () => ({ ok: true, present: false }),
  set_api_key: async () => ({ ok: true }),
  validate_api_key: async () => ({ ok: true }),
  list_recent: async () => ({ ok: true, items: [] }),
  list_profiles: async () => ([]),
  load_profile: async (name) => ({ run_mode: "full", depth: 2, max_nodes: 500, rate_limit_rpm: 120, skip_private_profiles: true, include_group_links: true, include_game_overlap: false, hub_percentile: 0.99 }),
  save_profile: async (name, subset) => true,
  resolve_target: async (target) => ({ ok: true, personaname: target || "", avatar: "../assets/placeholder.jpg" }),
};

/* If running inside pywebview, adopt the real bridge API when it becomes ready
   and install observers to keep window sized to content (no scrollbars). */
function adoptRealApi(){
  if (window.pywebview && window.pywebview.api) {
    try {
      api = window.pywebview.api;
      // Initial tighten to content
      scheduleResize?.();

      // Observe main content area for size changes
      const views = document.querySelector('.views');
      if (window.ResizeObserver && views) {
        const ro = new ResizeObserver(() => scheduleResize?.());
        ro.observe(views);
      }

      // Broadly observe DOM/content changes to keep height in sync
      const mo = new MutationObserver(() => scheduleResize?.());
      mo.observe(document.body, { childList: true, subtree: true, attributes: true, characterData: true });
    } catch {}
  }
}
window.addEventListener('pywebviewready', adoptRealApi);

// Helpers
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));
const logEl = $("#log");
// Auto-resize helpers to keep window free of scrollbars
function resizeToFit() {
  if (!api || !api.win_resize) return;
  const bar = document.querySelector('.toolbar');
  const views = document.querySelector('.views');
  if (!bar || !views) return;
  const totalH = Math.ceil(bar.getBoundingClientRect().height + views.scrollHeight);
  const targetH = Math.max(400, totalH + 6);
  try { api.win_resize(1280, targetH); } catch {}
}
let __vaporaResizeRAF = 0;
function scheduleResize() {
  if (window.__suspendAutoResize || document.body?.classList?.contains('design-mode')) return;
  if (typeof requestAnimationFrame !== 'function') { resizeToFit(); return; }
  if (__vaporaResizeRAF) cancelAnimationFrame(__vaporaResizeRAF);
  __vaporaResizeRAF = requestAnimationFrame(() => {
    __vaporaResizeRAF = 0;
    resizeToFit();
  });
}
function log(msg) {
  if (!logEl) return;
  logEl.textContent += `\n${msg}`;
  logEl.scrollTop = logEl.scrollHeight;
  try { scheduleResize(); } catch {}
}

function selectTab(name) {
  $$(".nav-link").forEach((l) => l.classList.remove("active"));
  $$(".view").forEach((v) => v.classList.remove("active"));
  $(`.nav-link[data-tab="${name}"]`)?.classList.add("active");
  $(`#view-${name}`)?.classList.add("active");
  try { scheduleResize(); } catch {}
}

// Toast utility
function showToast(message, timeout = 1800){
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = message;
  el.hidden = false;
  try { scheduleResize(); } catch {}
  clearTimeout(showToast._t);
  showToast._t = setTimeout(()=>{ el.hidden = true; try { scheduleResize(); } catch {} }, timeout);
}

// Tab switching
$$(".nav-link[data-tab]").forEach((link) => {
  link.addEventListener("click", (e) => {
    e.preventDefault();
    selectTab(link.dataset.tab);
  });
});

// Depth toggle (visual only; applied when clicking Apply)
$$(".btn-depth").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$(".btn-depth").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
  });
});

// Mode toggle -> push run_mode immediately
$$(".btn-mode").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const isActive = btn.classList.contains("active");
    // Always clear all button states first
    $$(".btn-mode").forEach((b) => b.classList.remove("active"));
    
    let run_mode = null;
    if (!isActive) {
      // If it wasn't active, we now activate it.
      btn.classList.add("active");
      run_mode = btn.dataset.mode;
    }
    // If it was active, it remains deactivated and run_mode is null.

    try {
      await api.set_config({ run_mode: run_mode || '' }); // Send empty string for "none"
      log(run_mode ? `[Mode] ${btn.textContent.trim()} (${run_mode})` : "[Mode] None");
      applyModeColors(run_mode);
    } catch (e) {
      log(`[Error] set_config(run_mode): ${e}`);
    }
  });
});

function readUI() {
  const depth = parseInt($(".btn-depth.active")?.dataset.depth || "2", 10);
  const max_nodes = parseInt($("#nodes")?.value || "", 10) || undefined;
  const rate_limit_rpm = parseInt($("#rpm")?.value || "", 10) || undefined;
  const skip_private_profiles = $("#cb-skip-private")?.checked ?? true;
  const include_group_links = $("#cb-groups")?.checked ?? true;
  const include_game_overlap = $("#cb-games")?.checked ?? false;
  return {
    depth,
    ...(max_nodes ? { max_nodes } : {}),
    ...(rate_limit_rpm ? { rate_limit_rpm } : {}),
    skip_private_profiles,
    include_group_links,
    include_game_overlap,
  };
}

function applyConfigUI(cfg) {
  // Depth
  const d = cfg.depth ?? 2;
  const depthBtn = $(`.btn-depth[data-depth="${d}"]`);
  if (depthBtn) {
    $$(".btn-depth").forEach((b) => b.classList.remove("active"));
    depthBtn.classList.add("active");
  }
  // Checkboxes
  if ("skip_private_profiles" in cfg && $("#cb-skip-private"))
    $("#cb-skip-private").checked = !!cfg.skip_private_profiles;
  if ("include_group_links" in cfg && $("#cb-groups"))
    $("#cb-groups").checked = !!cfg.include_group_links;
  if ("include_game_overlap" in cfg && $("#cb-games"))
    $("#cb-games").checked = !!cfg.include_game_overlap;
  // Text inputs
  if (cfg.max_nodes && $("#nodes")) $("#nodes").value = String(cfg.max_nodes);
  if (cfg.rate_limit_rpm && $("#rpm")) $("#rpm").value = String(cfg.rate_limit_rpm);
  // Mode buttons
  $$(".btn-mode").forEach((b) => b.classList.remove("active"));
  const mode = cfg.run_mode ? cfg.run_mode.toLowerCase() : null;
  if (mode) {
    const modeBtn = $(`.btn-mode[data-mode="${mode}"]`);
    if(modeBtn) modeBtn.classList.add("active");
  }
}

// Apply button -> set_config
$("#apply-btn")?.addEventListener("click", async () => {
  const partial = readUI();
  try {
    const newCfg = await api.set_config(partial);
    applyConfigUI(newCfg);
    applyModeColors(newCfg.run_mode || "full");
    log(
      `[Applied] Depth=${newCfg.depth}, Nodes=${newCfg.max_nodes}, RPM=${newCfg.rate_limit_rpm}, ` +
        `SkipPrivate=${newCfg.skip_private_profiles}, Groups=${newCfg.include_group_links}, Games=${newCfg.include_game_overlap}`
    );
  } catch (e) {
    log(`[Error] set_config: ${e}`);
  }
});

// Open output folder via Bridge
$("#open-output")?.addEventListener("click", async () => {
  try {
    await api.open_outputs();
  } catch (e) {
    log(`[Error] open_outputs: ${e}`);
  }
});

// Window control events for frameless window
document.getElementById('btn-win-min')?.addEventListener('click', async () => {
  try { await api.win_minimize(); } catch {}
});
document.getElementById('btn-win-close')?.addEventListener('click', async () => {
  try { await api.win_close(); } catch {}
});

// Manual drag fallback: only allow toolbar background to initiate movement
(function setupManualDrag(){
  const bar = document.querySelector('.toolbar');
  if (!bar) return;
  let dragging = false;
  let lastX = 0, lastY = 0;
  let raf = 0;
  let accumDX = 0, accumDY = 0;

  const isInteractive = (el) => !!el.closest('.window-controls, .tabs, .button, .icon-btn, .align-icon, #btn-key');

  const onMouseDown = (e) => {
    // start only when pressing toolbar background (not on its buttons/links)
    if (isInteractive(e.target)) return;
    dragging = true;
    lastX = e.screenX;
    lastY = e.screenY;
    accumDX = 0; accumDY = 0;
    e.preventDefault();
  };
  const applyMove = () => {
    if (!dragging) return;
    const dx = accumDX; const dy = accumDY;
    accumDX = 0; accumDY = 0;
    if (dx || dy) { try { api.win_move_by(dx, dy); } catch {} }
    raf = dragging ? requestAnimationFrame(applyMove) : 0;
  };
  const onMouseMove = (e) => {
    if (!dragging) return;
    accumDX += (e.screenX - lastX);
    accumDY += (e.screenY - lastY);
    lastX = e.screenX;
    lastY = e.screenY;
    if (!raf) raf = requestAnimationFrame(applyMove);
  };
  const onMouseUp = () => {
    dragging = false;
    if (raf) cancelAnimationFrame(raf); raf = 0;
  };

  bar.addEventListener('mousedown', onMouseDown);
  window.addEventListener('mousemove', onMouseMove);
  window.addEventListener('mouseup', onMouseUp);
})();

// Autodetect target: debounce resolve_target on input
let _verifyTimer = null;
async function verifyAndFill() {
  if (!window.__apiReady) return;
  const target = document.getElementById('target')?.value?.trim();
  if (!target) {
    const nameEl = document.getElementById('target-username');
    if (nameEl) nameEl.textContent = '';
    const img = document.querySelector('.target-avatar img');
    if (img) img.src = '../assets/placeholder.jpg';
    return;
  }
  try {
    const fn = api.resolve_target || (async (t)=>({ ok:true, personaname:t, avatar:'../assets/placeholder.jpg' }));
    const res = await fn(target);
    if (!res?.ok) {
      log(`[Warn] Could not resolve target '${target}'.`);
      return;
    }
    const name = res.personaname || target;
    const avatar = res.avatar || '../assets/placeholder.jpg';
    const nameEl = document.getElementById('target-username');
    if (nameEl) nameEl.textContent = name;
    const img = document.querySelector('.target-avatar img');
    if (img) img.src = avatar;
    try { scheduleResize(); } catch {}
  } catch (e) {
    log(`[Error] resolve_target failed: ${e}`);
  }
}
document.getElementById('target')?.addEventListener('input', () => {
  if (_verifyTimer) clearTimeout(_verifyTimer);
  _verifyTimer = setTimeout(verifyAndFill, 600);
});
document.getElementById('target')?.addEventListener('blur', () => {
  if (_verifyTimer) clearTimeout(_verifyTimer);
  _verifyTimer = setTimeout(verifyAndFill, 50);
});
$("#btn-analyze")?.addEventListener("click", async () => {
  const target = $("#target")?.value?.trim();
  if (!target) {
    log("[Warn] Enter a target first.");
    return;
  }
  log(`[Run] Scanning ${target}…`);
  try {
    const res = await api.run_scan({ target });
    if (!res?.ok) {
      log(`[Error] ${res?.error || "run_scan failed"}`);
      return;
    }
    // Update output tree preview
    const out = res.outputDir || "<steamid64>/<yyyymmdd_hhmmss>";
  const tree = `
<span class="tree-root" data-key="root">${out.replace(/\\/g, "/")}/</span>
<span class="tree-branch">├─</span> <span class="tree-folder" data-key="gephi">gephi/</span>
<span class="tree-branch">│  ├─</span> <span class="tree-file" data-key="nodes">nodes.csv</span>
<span class="tree-branch">│  └─</span> <span class="tree-file" data-key="edges">edges.csv</span>
<span class="tree-branch">├─</span> <span class="tree-file" data-key="estimates">estimates.json</span>
<span class="tree-branch">├─</span> <span class="tree-file" data-key="scan">scan.json</span>
<span class="tree-branch">└─</span> <span class="tree-file" data-key="runlog">run.log</span>`;
    const outEl = $("#output-tree");
    if (outEl) outEl.innerHTML = tree;
  applyModeColors($(".btn-mode.active")?.dataset.mode || null);

    // Results list
    const items = $("#result-items");
    if (items) {
      items.innerHTML = "";
      if (res.nodesCsv) {
        const li = document.createElement("li");
        li.textContent = `nodes.csv → ${res.nodesCsv}`;
        items.appendChild(li);
      }
      if (res.edgesCsv) {
        const li = document.createElement("li");
        li.textContent = `edges.csv → ${res.edgesCsv}`;
        items.appendChild(li);
      }
      if (res.estimates) {
        const li = document.createElement("li");
        const cf = res.estimates.closestFriends?.slice(0, 5) || [];
        li.textContent = `closestFriends(top5): ${cf.map((x) => x.personaname || x.name || x.steamid).join(", ")}`;
        items.appendChild(li);
      }
    }
    try { scheduleResize(); } catch {}
    log(`[OK] Output → ${res.outputDir}`);
    // Switch to Results tab
    selectTab("results");
  } catch (e) {
    log(`[Error] run_scan exception: ${e}`);
  }
});

// API key modal and lock overlay
function openKeyModal(){
  const modal = document.getElementById('key-modal');
  const input = document.getElementById('api-key-input');
  if (!modal || !input) return;
  input.value = '';
  modal.hidden = false;
  setTimeout(()=>{ input.focus(); }, 20);
}
function closeKeyModal(){ const modal = document.getElementById('key-modal'); if (modal) modal.hidden = true; }
document.getElementById('btn-key')?.addEventListener('click', async () => {
  try {
    const s = await api.has_api_key();
    // Only warn about replacement if a persisted key exists in a file
    if (s && s.present && (s.source === 'file')) {
      const m = document.getElementById('key-note-modal');
      if (m) { m.hidden = false; return; }
    }
  } catch {}
  openKeyModal();
});
document.getElementById('api-key-cancel')?.addEventListener('click', closeKeyModal);
document.getElementById('api-key-save')?.addEventListener('click', async () => {
  const val = document.getElementById('api-key-input')?.value?.trim();
  const errEl = document.getElementById('api-key-error');
  const key = (val || '').toUpperCase();
  const validFormat = /^[A-Z0-9]{25,40}$/.test(key);
  if (!validFormat){
    if (errEl){ errEl.textContent = 'Invalid API key format.'; errEl.hidden = false; }
    return;
  } else if (errEl){ errEl.hidden = true; }
  try{
    const check = await (api.validate_api_key ? api.validate_api_key(key) : { ok: true });
    if (!check?.ok){
      if (errEl){ errEl.textContent = check?.error || 'Steam rejected the API key.'; errEl.hidden = false; }
      return;
    }
    const res = await api.set_api_key(key);
    if (!res?.ok){ showToast(res?.error || 'Failed to save key'); return; }
    window.__apiReady = true;
    const lock = document.getElementById('lock-overlay');
    if (lock) lock.hidden = true;
    const hint = document.getElementById('api-key-hint');
    if (hint) hint.hidden = true;
    closeKeyModal();
    showToast('API key saved.');
    verifyAndFill();
  }catch(e){ showToast('Error saving key'); }
});

// Live format validation feedback
document.getElementById('api-key-input')?.addEventListener('input', (e) => {
  const t = e.target?.value?.trim() || '';
  const key = t.toUpperCase();
  const errEl = document.getElementById('api-key-error');
  if (!errEl) return;
  if (!key){ errEl.hidden = true; return; }
  const valid = /^[A-Z0-9]{25,40}$/.test(key);
  errEl.textContent = valid ? '' : 'Invalid API key format.';
  errEl.hidden = !!valid;
});
// Note modal actions -> proceed to key entry or cancel
document.getElementById('key-note-ok')?.addEventListener('click', () => {
  const m = document.getElementById('key-note-modal');
  if (m) m.hidden = true;
  openKeyModal();
});
document.getElementById('key-note-cancel')?.addEventListener('click', () => {
  const m = document.getElementById('key-note-modal');
  if (m) m.hidden = true;
});
document.getElementById('lock-overlay')?.addEventListener('click', () => {
  showToast('API key required. Press the key icon to set it.');
});

// Estimate only (dry-run)
$("#btn-estimate")?.addEventListener("click", async () => {
  const target = $("#target")?.value?.trim();
  if (!target) {
    log("[Warn] Enter a target first.");
    return;
  }
  try {
    const res = await api.dry_run(target);
    if (!res?.ok) {
      log(`[Error] ${res?.error || "dry_run failed"}`);
      return;
    }
    log(`[Estimate] Seed friends ~ ${res.seed_friends}`);
    selectTab("results");
  } catch (e) {
    log(`[Error] dry_run exception: ${e}`);
  }
});

// Save / Load profile via simple prompts on the vertical rail
document.getElementById('btn-load')?.addEventListener('click', async () => {
  try {
    const names = await api.list_profiles();
    const hint = Array.isArray(names) && names.length ? `Available: ${names.join(', ')}` : 'Enter profile name';
    const name = window.prompt(`Load profile\n${hint}`, names?.[0] || 'default');
    if (!name) return;
    const cfg = await api.load_profile(name);
    applyConfigUI(cfg);
    applyModeColors(cfg.run_mode || 'full');
    log(`[Profile] Loaded '${name}'`);
  } catch (e) {
    log(`[Error] load_profile: ${e}`);
  }
});

document.getElementById('btn-save')?.addEventListener('click', async () => {
  try {
    const name = window.prompt('Save profile as', 'default');
    if (!name) return;
    const subset = { ...readUI(), run_mode: document.querySelector('.btn-mode.active')?.dataset.mode || 'full' };
    const ok = await api.save_profile(name, subset);
    if (ok) log(`[Profile] Saved '${name}'`);
  } catch (e) {
    log(`[Error] save_profile: ${e}`);
  }
});

// Initial config load
(async () => {
  // If running under pywebview, pick up the real bridge API now
  if (window.pywebview && window.pywebview.api) { api = window.pywebview.api; }
  try {
    const cfg = await api.get_config();
    applyConfigUI(cfg);
    applyModeColors(cfg.run_mode);
    log("Loaded config.");
  } catch (e) {
    log(`[Error] get_config: ${e}`);
  }
  // API key presence -> lock overlay
  try {
    const s = await api.has_api_key();
    window.__apiReady = !!(s?.present);
  } catch { window.__apiReady = false; }
  const lock = document.getElementById('lock-overlay');
  if (lock) lock.hidden = !!window.__apiReady;
  const hint = document.getElementById('api-key-hint');
  if (hint) hint.hidden = !!window.__apiReady;
  // Populate recent thumbnails
  try {
    const list = await api.list_recent();
  const host = document.querySelector('#recent-thumbs');
    if (host && list?.ok) {
      host.innerHTML = '';
      const items = (list.items || []).slice(0, 6);
      if (!items.length) {
        for (let i = 0; i < 4; i++) {
          const div = document.createElement('div');
          div.className = 'recent-thumb';
          const img = document.createElement('img');
          img.src = '../assets/placeholder.jpg';
          img.alt = 'recent';
          div.appendChild(img);
          host.appendChild(div);
        }
      } else {
        items.forEach((it) => {
          const div = document.createElement('div');
          div.className = 'recent-thumb';
          div.title = it.steamid64;
          const img = document.createElement('img');
          img.src = '../assets/placeholder.jpg';
          img.alt = it.steamid64;
          div.appendChild(img);
          div.addEventListener('click', () => {
            const input = document.querySelector('#target');
            if (input) input.value = it.steamid64;
          });
          host.appendChild(div);
        });
      }
    }
    try { scheduleResize(); } catch {}
  } catch {}
})();

  // Mode-based coloring of the output tree
function applyModeColors(mode){
  // Clear all previous active states first
  document.querySelectorAll('#output-tree span').forEach(el => el.classList.remove('tree-active'));

  if (!mode) return; // If mode is null/undefined, do nothing else.
  
  const keys = {
    root: document.querySelector('[data-key="root"]'),
    gephi: document.querySelector('[data-key="gephi"]'),
    nodes: document.querySelector('[data-key="nodes"]'),
    edges: document.querySelector('[data-key="edges"]'),
    estimates: document.querySelector('[data-key="estimates"]'),
    scan: document.querySelector('[data-key="scan"]'),
    runlog: document.querySelector('[data-key="runlog"]'),
  };

  const setActive = (arr) => {
    arr.forEach((k) => {
      const el = keys[k];
      if (el) {
        el.classList.add('tree-active');
        // Also activate the preceding tree branch character if it exists
        let prev = el.previousElementSibling;
        while(prev && prev.classList.contains('tree-branch')) {
          prev.classList.add('tree-active');
          prev = prev.previousElementSibling;
        }
      }
    });
  };

  const m = mode.toLowerCase();
  if (m === 'full') { // Deep
    setActive(['root','gephi','nodes','edges','estimates','scan','runlog']);
  } else if (m === 'basic') { // Surface
    setActive(['root', 'estimates','runlog']);
  } else if (m === 'gephi') { // gephi
    setActive(['root', 'gephi','nodes','edges']);
  }
}


 // Lightweight UI design tool (direct-manipulation, grid-snapped)
(function setupDesignTool(){
  const panel = document.getElementById('design-panel');
  if (!panel) return;

  // Panel elements
  const gridInput   = document.getElementById('design-grid');
  const snapInput   = document.getElementById('design-snap');
  const infoSpan    = document.getElementById('design-info');
  const btnCopy     = document.getElementById('design-copy');
  const btnCopyAll  = document.getElementById('design-copy-all');
  const btnApply    = document.getElementById('design-apply');
  const btnExit     = document.getElementById('design-exit');
  const scopeSelect = document.getElementById('design-scope');
  const customInput = document.getElementById('design-custom');
  const btnAll      = document.getElementById('design-all');
  const btnClear    = document.getElementById('design-clear');

  let enabled = false;
  let currentContainer = null;
  const selected = new Set(); // Set<HTMLElement>
  let active = null;          // { type:'move'|'resize', targets:Set<HTMLElement>, base:Array<{el,left,top,width,height}>, startX, startY }
  let capture = { x:0, y:0 };
  let nudging = false;
  const frozen = new Set();
  const lockBounds = false;

  function clampMove(left, top, el){
    if (!lockBounds) return { left, top };
    const c = getContainer();
    const cw = c?.clientWidth ?? 1e9;
    const ch = c?.clientHeight ?? 1e9;
    const r = el.getBoundingClientRect();
    const w = Math.round(r.width);
    const h = Math.round(r.height);
    return {
      left: Math.max(0, Math.min(left, cw - w)),
      top: Math.max(0, Math.min(top, ch - h)),
    };
  }

  function clampBox(edge, left, top, width, height, el){
    if (!lockBounds) return { left, top, width, height };
    const c = getContainer();
    const cw = c?.clientWidth ?? 1e9;
    const ch = c?.clientHeight ?? 1e9;

    const MIN = 16;
    width = Math.max(MIN, width);
    height = Math.max(MIN, height);

    if (left < 0){
      if (edge.includes('w')) width += left;
      left = 0;
    }
    if (top < 0){
      if (edge.includes('n')) height += top;
      top = 0;
    }
    if (left + width > cw){
      if (edge.includes('e')) width = cw - left;
      else left = Math.max(0, cw - width);
    }
    if (top + height > ch){
      if (edge.includes('s')) height = ch - top;
      else top = Math.max(0, ch - height);
    }

    width = Math.max(MIN, width);
    height = Math.max(MIN, height);
    return { left, top, width, height };
  }

  // Undo history (array of snapshots)
  const history = [];
  function captureSnapshot(){
    const list = Array.from(getContainer()?.querySelectorAll(scopeSelector())||[]);
    return list.map((el, idx)=>({
      el,
      id: el.id || el.dataset.label || `${el.tagName.toLowerCase()}#${idx}`,
      left: el.style.left || '',
      top: el.style.top || '',
      width: el.style.width || '',
      height: el.style.height || ''
    }));
  }
  function pushHistory(){
    try {
      history.push(captureSnapshot());
      if (history.length > 120) history.shift();
    } catch {}
  }
  function restoreSnapshot(snap){
    if (!snap) return;
    snap.forEach(item=>{
      const el = item.el;
      if (!el) return;
      ensureAbsolute(el);
      if (item.left) el.style.left = item.left;
      if (item.top) el.style.top = item.top;
      if (item.width) el.style.width = item.width;
      if (item.height) el.style.height = item.height;
    });
    updateInfo();
    showToast?.('Undo');
  }

  const getContainer = () => document.querySelector('.view.active') || document.querySelector('.views');
  const getContainerRect = () => (getContainer()?.getBoundingClientRect() || { left:0, top:0, width:0, height:0 });

  function getGrid(){ return Math.max(1, parseInt(gridInput?.value||'8',10)); }
  function snap(n){ if (!snapInput?.checked) return Math.round(n); const g = getGrid(); return Math.round(n/g)*g; }

  function scopeSelector(){
    const v = scopeSelect?.value || 'auto';
    if (v==='auto')     return '[data-designable]';
    if (v==='panels')   return '.panel';
    if (v==='rows')     return '.param-row, .mode-output-row, .target-top, .target-username, .target-avatar, .output-panel, .mode-panel, .results-panel, .results-log, .results-list';
    if (v==='controls') return 'button, .button, input, select, .btn-mode, .btn-depth, .rail-btn, .icon-btn';
    if (v==='all')      return '*';
    if (v==='custom')   return customInput?.value?.trim() || '[data-designable]';
    return '[data-designable]';
  }
  function inScope(el){
    try { return !!el.closest(scopeSelector()); } catch { return false; }
  }

  function ensureAbsolute(el){
    const container = getContainer();
    const cr = getContainerRect();
    const r = el.getBoundingClientRect();
    if (!container) return;
    // Save previous inline style once
    if (!el.dataset.designPrev){
      const prev = {
        position: el.style.position || '',
        left: el.style.left || '',
        top: el.style.top || '',
        width: el.style.width || '',
        height: el.style.height || '',
        gridArea: el.style.gridArea || '',
        gridColumn: el.style.gridColumn || '',
        gridRow: el.style.gridRow || '',
        flex: el.style.flex || '',
        alignSelf: el.style.alignSelf || '',
        justifySelf: el.style.justifySelf || '',
      };
      el.dataset.designPrev = JSON.stringify(prev);
    }
    // Anchor container for abs children
    if (getComputedStyle(container).position === 'static'){
      container.style.position = 'relative';
      container.dataset.designPos = '1';
    }
    // Clear conflicting layout props
    ['gridArea','gridColumn','gridRow','flex','alignSelf','justifySelf'].forEach(p=>{
      try { el.style[p] = ''; } catch {}
    });
    // Remove size limits and clipping that can cap or hide elements while resizing
    try {
      el.style.minWidth = '0px';
      el.style.minHeight = '0px';
      el.style.maxWidth = 'none';
      el.style.maxHeight = 'none';
      el.style.overflow = 'visible';
      el.style.boxSizing = 'border-box';
      // Bring above siblings while designing
      const z = parseInt(el.style.zIndex || '0', 10) || 0;
      el.style.zIndex = String(Math.max(1000, z));
    } catch {}
    el.style.position = 'absolute';
    const op = el.offsetParent || container;
    const pr = (op && op.getBoundingClientRect) ? op.getBoundingClientRect() : { left: 0, top: 0 };
    const leftPx = Math.round(r.left - pr.left + (op?.scrollLeft || 0));
    const topPx  = Math.round(r.top  - pr.top  + (op?.scrollTop  || 0));
    el.style.left = `${leftPx}px`;
    el.style.top = `${topPx}px`;
    el.style.width = `${Math.round(r.width)}px`;
    el.style.height = `${Math.round(r.height)}px`;
  }

  function updateInfo(){
    if (!infoSpan) return;
    if (!selected.size){ infoSpan.textContent = ''; return; }
    if (selected.size === 1){
      const el = [...selected][0];
      const left = parseInt(el.style.left||'0',10);
      const top = parseInt(el.style.top||'0',10);
      const w = parseInt(el.style.width||`${Math.round(el.getBoundingClientRect().width)}`,10);
      const h = parseInt(el.style.height||`${Math.round(el.getBoundingClientRect().height)}`,10);
      const label = el.dataset.label || el.id || el.tagName.toLowerCase();
      infoSpan.textContent = `${label} → x:${left}, y:${top}, w:${w}, h:${h}`;
    } else {
      infoSpan.textContent = `${selected.size} selected`;
    }
  }

  function updateSelectionStyles(){
    const list = Array.from(getContainer()?.querySelectorAll(scopeSelector())||[]);
    list.forEach(el=>{
      el.style.outline = '';
      el.style.outlineOffset = '';
      el.style.filter = '';
    });
    selected.forEach(el=>{
      try {
        el.style.outline = '2px dashed #4DA3FF';
        el.style.outlineOffset = '0px';
        el.style.filter = 'drop-shadow(0 0 0.5px #4DA3FF)';
      } catch {}
    });
  }

  function selectOnly(el){
    selected.clear();
    if (el) selected.add(el);
    updateSelectionStyles();
    updateInfo();
  }
  function toggleSelect(el){
    if (selected.has(el)) selected.delete(el);
    else selected.add(el);
    updateSelectionStyles();
    updateInfo();
  }
  function clearSelection(){
    selected.clear();
    updateSelectionStyles();
    updateInfo();
  }

  // Freeze only currently selected elements to avoid collapsing the whole UI
  function freezeLayout(){
    const container = getContainer();
    if (!container) return;
    const list = selected.size ? [...selected] : [];
    list.forEach(el => {
      if (panel && panel.contains(el)) return;
      ensureAbsolute(el);
      frozen.add(el);
    });
  }

  // Restore all elements back to their previous inline styles
  function restoreLayout(){
    const container = getContainer();
    try {
      frozen.forEach(el=>{
        try {
          const prev = el.dataset.designPrev ? JSON.parse(el.dataset.designPrev) : {};
          [
            'position','left','top','width','height',
            'gridArea','gridColumn','gridRow','flex','alignSelf','justifySelf',
            'zIndex','overflow','boxSizing','minWidth','minHeight','maxWidth','maxHeight',
            'outline','outlineOffset','filter'
          ].forEach(p=>{ try { el.style[p] = (prev[p] ?? ''); } catch {} });
          delete el.dataset.designPrev;
        } catch {}
      });
      frozen.clear();
      if (container && container.dataset && container.dataset.designPos){
        container.style.position = '';
        delete container.dataset.designPos;
      }
    } catch {}
    updateSelectionStyles();
    updateInfo();
  }

  function beginInteraction(e, type){
    const target = e.target.closest(scopeSelector());
    if (!target) return;
    if (!selected.has(target) && !(e.ctrlKey||e.metaKey)) selectOnly(target);
    if ((e.ctrlKey||e.metaKey) && !selected.has(target)) toggleSelect(target);
    // Snapshot BEFORE change for undo
    pushHistory();
    // Ensure all selected are absolutely positioned and track for restore
    [...selected].forEach(el=> { ensureAbsolute(el); frozen.add(el); });
    // Determine resize edge/corner near the pointer for single selection
    let edge = 'se';
    if (type==='resize' && selected.size===1){
      const r = target.getBoundingClientRect();
      const px = e.clientX, py = e.clientY;
      const near = 14;
      const leftEdge = (px - r.left) <= near;
      const rightEdge = (r.right - px) <= near;
      const topEdge = (py - r.top) <= near;
      const bottomEdge = (r.bottom - py) <= near;
      if (topEdge && leftEdge) edge = 'nw';
      else if (topEdge && rightEdge) edge = 'ne';
      else if (bottomEdge && leftEdge) edge = 'sw';
      else if (bottomEdge && rightEdge) edge = 'se';
      else if (leftEdge) edge = 'w';
      else if (rightEdge) edge = 'e';
      else if (topEdge) edge = 'n';
      else if (bottomEdge) edge = 's';
    }
    const base = [...selected].map(el=>({
      el,
      left: parseInt(el.style.left||'0',10),
      top: parseInt(el.style.top||'0',10),
      width: parseInt(el.style.width||`${Math.round(el.getBoundingClientRect().width)}`,10),
      height: parseInt(el.style.height||`${Math.round(el.getBoundingClientRect().height)}`,10),
    }));
    active = { type, edge, targets: new Set(selected), base, startX: e.clientX, startY: e.clientY };
    capture.x = e.clientX; capture.y = e.clientY;
    e.preventDefault();
  }

  function onDocDown(e){
    if (!enabled) return;
    if (!inScope(e.target)) return;
    // Alt+Drag moves, Alt+Shift resizes
    if (e.altKey){
      const type = e.shiftKey ? 'resize' : 'move';
      beginInteraction(e, type);
    } else {
      // simple selection without modifiers
      const el = e.target.closest(scopeSelector());
      if (el && !panel.contains(e.target)){
        if (e.ctrlKey||e.metaKey) toggleSelect(el);
        else selectOnly(el);
      }
    }
  }

  function onDocMove(e){
    if (!enabled || !active) return;
    const dx = e.clientX - active.startX;
    const dy = e.clientY - active.startY;
    active.base.forEach(b=>{
      if (active.type==='move'){
        let nx = snap(b.left + dx);
        let ny = snap(b.top + dy);
        const pos = clampMove(nx, ny, b.el);
        b.el.style.left = `${pos.left}px`;
        b.el.style.top = `${pos.top}px`;
      } else { // edge/corner-aware resize
        const MIN = 16;
        const edge = active.edge || 'se';
        let left = b.left, top = b.top, width = b.width, height = b.height;

        if (edge.includes('w')) { left = snap(b.left + dx); width = snap(b.width - dx); }
        if (edge.includes('e')) { width = snap(b.width + dx); }
        if (edge.includes('n')) { top = snap(b.top + dy); height = snap(b.height - dy); }
        if (edge.includes('s')) { height = snap(b.height + dy); }

        if (width < MIN){
          if (edge.includes('w')) left += (width - MIN);
          width = MIN;
        }
        if (height < MIN){
          if (edge.includes('n')) top += (height - MIN);
          height = MIN;
        }

        const box = clampBox(edge, left, top, width, height, b.el);
        b.el.style.left = `${box.left}px`;
        b.el.style.top = `${box.top}px`;
        b.el.style.width = `${box.width}px`;
        b.el.style.height = `${box.height}px`;
      }
    });
    updateInfo();
    e.preventDefault();
  }
  function onDocUp(){
    if (!enabled) return;
    if (active){ // interaction finished -> snapshot AFTER change for undo
      pushHistory();
    }
    active = null;
  }

  function applySelection(){
    if (!selected.size) return;
    [...selected].forEach(el=> ensureAbsolute(el));
    pushHistory();
    showToast?.('Applied to elements');
  }

  function toJSON(all = false){
    const out = {};
    const list = (all || !selected.size) 
      ? Array.from(getContainer()?.querySelectorAll('[data-label]') || [])
      : [...selected];
    list.forEach((el, idx)=>{
      const id = el.id || el.dataset.label || `${el.tagName.toLowerCase()}#${idx}`;
      out[id] = {
        x: parseInt(el.style.left||'0',10),
        y: parseInt(el.style.top||'0',10),
        w: parseInt(el.style.width||`${Math.round(el.getBoundingClientRect().width)}`,10),
        h: parseInt(el.style.height||`${Math.round(el.getBoundingClientRect().height)}`,10),
        label: el.dataset.label || id
      };
    });
    return JSON.stringify(out, null, 2);
  }

  function enable(on){
    enabled = !!on;
    panel.hidden = !enabled;
    document.body.classList.toggle('design-mode', enabled);
    // Ensure lock overlay does not block interactions in design mode and show quick help
    try {
      const lock = document.getElementById('lock-overlay');
      if (enabled) {
        if (lock) { lock.dataset.prevPe = lock.style.pointerEvents || ''; lock.style.pointerEvents = 'none'; }
        if (infoSpan) infoSpan.textContent = 'Alt+Drag move | Alt+Shift drag / Alt+Shift Arrows resize | Ctrl+Z undo';
        document.body.dataset.prevOverflow = document.body.style.overflow || '';
        document.body.style.overflow = 'visible';
      } else {
        if (lock && lock.dataset && 'prevPe' in lock.dataset) { lock.style.pointerEvents = lock.dataset.prevPe; delete lock.dataset.prevPe; }
        if (infoSpan) infoSpan.textContent = '';
        if (document.body.dataset && 'prevOverflow' in document.body.dataset) {
            document.body.style.overflow = document.body.dataset.prevOverflow;
            delete document.body.dataset.prevOverflow;
        }
      }
    } catch {}
    // Allow interacting with UI while holding Alt to move/resize
    if (enabled){
      currentContainer = getContainer();
      try {
        if (currentContainer) {
          if (!currentContainer.dataset.prevOverflow) currentContainer.dataset.prevOverflow = currentContainer.style.overflow || '';
          currentContainer.style.overflow = 'visible';
        }
      } catch {}
      window.addEventListener('mousedown', onDocDown, true);
      window.addEventListener('mousemove', onDocMove, true);
      window.addEventListener('mouseup', onDocUp, true);
      // Pin container size to prevent collapse while editing
      try {
        const cr = currentContainer?.getBoundingClientRect();
        if (currentContainer && cr) {
          if (!currentContainer.dataset.prevMinW) currentContainer.dataset.prevMinW = currentContainer.style.minWidth || '';
          if (!currentContainer.dataset.prevMinH) currentContainer.dataset.prevMinH = currentContainer.style.minHeight || '';
          currentContainer.style.minWidth = `${Math.round(cr.width)}px`;
          const h = Math.max(cr.height, currentContainer.scrollHeight || 0);
          currentContainer.style.minHeight = `${Math.round(h)}px`;
        }
      } catch {}
      // Initial baseline snapshot
      pushHistory();
    } else {
      window.removeEventListener('mousedown', onDocDown, true);
      window.removeEventListener('mousemove', onDocMove, true);
      window.removeEventListener('mouseup', onDocUp, true);
      try {
        if (currentContainer && currentContainer.dataset && 'prevOverflow' in currentContainer.dataset){
          currentContainer.style.overflow = currentContainer.dataset.prevOverflow;
          delete currentContainer.dataset.prevOverflow;
        }
        if (currentContainer && currentContainer.dataset && 'prevMinW' in currentContainer.dataset){
          currentContainer.style.minWidth = currentContainer.dataset.prevMinW;
          delete currentContainer.dataset.prevMinW;
        }
        if (currentContainer && currentContainer.dataset && 'prevMinH' in currentContainer.dataset){
          currentContainer.style.minHeight = currentContainer.dataset.prevMinH;
          delete currentContainer.dataset.prevMinH;
        }
      } catch {}
      restoreLayout();
      clearSelection();
    }
    try { window.__suspendAutoResize = !!enabled; } catch {}
    try { scheduleResize?.(); } catch {}
  }

  // Panel buttons
  btnExit?.addEventListener('click', ()=> enable(false));
  btnApply?.addEventListener('click', applySelection);
  btnCopy?.addEventListener('click', async ()=>{
    const text = toJSON();
    try { await navigator.clipboard.writeText(text); showToast?.('Copied layout JSON'); }
    catch { try { window.prompt('Layout JSON (copy):', text); } catch {} }
  });
  btnCopyAll?.addEventListener('click', async ()=>{
    const text = toJSON(true);
    try { await navigator.clipboard.writeText(text); showToast?.('Copied all layout JSON'); }
    catch { try { window.prompt('Layout JSON (copy):', text); } catch {} }
  });
  btnAll?.addEventListener('click', ()=>{
    const list = Array.from(getContainer()?.querySelectorAll(scopeSelector())||[]);
    selected.clear();
    list.forEach(el=> selected.add(el));
    updateInfo();
  });
  btnClear?.addEventListener('click', clearSelection);

  // Toolbar toggle
  document.getElementById('btn-design')?.addEventListener('click', (e)=>{
    e.preventDefault();
    enable(!enabled);
  });
  
  const btnLayout = document.getElementById('btn-layout');
  const updateLayoutButton = () => {
    if (!btnLayout) return;
    const on = document.body.classList.contains('layout-abs');
    btnLayout.textContent = on ? 'Coords: Off' : 'Coords: On';
  };

  btnLayout?.addEventListener('click', (e) => {
    e.preventDefault();
    const on = !document.body.classList.contains('layout-abs');
    document.body.classList.toggle('layout-abs', on);
    updateLayoutButton();
    showToast?.(on ? 'Coordinate layout ON' : 'Coordinate layout OFF');
    try { scheduleResize?.(); } catch {}
  });

  // Keyboard shortcuts
  window.addEventListener('keydown', (e)=>{
    // Toggle design
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase()==='d'){
      e.preventDefault(); enable(!enabled); return;
    }
    // Undo
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase()==='z'){
      if (enabled && history.length > 1){
        e.preventDefault();
        // Drop current state then restore previous
        history.pop();
        restoreSnapshot(history[history.length - 1]);
      }
      return;
    }
    if (!enabled) return;
    // Select all
    if ((e.ctrlKey||e.metaKey) && e.key.toLowerCase()==='a'){
      e.preventDefault();
      const list = Array.from(getContainer()?.querySelectorAll(scopeSelector())||[]);
      selected.clear(); list.forEach(el=> selected.add(el)); updateInfo(); return;
    }
    // Esc
    if (e.key==='Escape'){
      e.preventDefault();
      if (selected.size) clearSelection(); else enable(false);
      return;
    }
    const arrows = ['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'];
    if (arrows.includes(e.key) && selected.size){
      e.preventDefault();
      // Start an undo group on first nudge
      if (!nudging){ pushHistory(); nudging = true; }
      const baseStep = (snap(1) - snap(0)) || 1;
      const step = e.shiftKey ? baseStep * 5 : baseStep;
      let dx = 0, dy = 0;
      if (e.key==='ArrowLeft')  dx = -step;
      if (e.key==='ArrowRight') dx =  step;
      if (e.key==='ArrowUp')    dy = -step;
      if (e.key==='ArrowDown')  dy =  step;
      [...selected].forEach(el=>{
        ensureAbsolute(el);
        const left = parseInt(el.style.left||'0',10);
        const top = parseInt(el.style.top||'0',10);
        if (e.altKey && e.shiftKey){
          // Resize instead of move (horizontal arrows -> width, vertical -> height)
          const width = parseInt(el.style.width||`${Math.round(el.getBoundingClientRect().width)}`,10);
          const height = parseInt(el.style.height||`${Math.round(el.getBoundingClientRect().height)}`,10);
          if (e.key==='ArrowLeft' || e.key==='ArrowRight'){
            const nw = Math.max(16, snap(width + dx));
            el.style.width = `${nw}px`;
          } else {
            const nh = Math.max(16, snap(height + dy));
            el.style.height = `${nh}px`;
          }
        } else {
          el.style.left = `${snap(left + dx)}px`;
          el.style.top  = `${snap(top + dy)}px`;
        }
      });
      updateInfo();
    }
  });

  // Finish nudge sessions on keyup to create one undo step
  window.addEventListener('keyup', (e)=>{
    const arrows = ['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'];
    if (nudging && arrows.includes(e.key)){
      pushHistory();
      nudging = false;
    }
  });

  // Auto-enable with ?design=1
  const params = new URLSearchParams(location.search);
  if (params.get('design')==='1'){ enable(true); }
  updateLayoutButton();
})();