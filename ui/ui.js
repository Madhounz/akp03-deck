const TOKEN = "__TOKEN__";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
const src = p => !p ? "" : (p.startsWith("pack/") || p.startsWith("icons/") ? "/" + p : "");

const TYPE_NAMES = {none:"Nothing", open:"Open", hotkey:"Shortcut", media:"Media key", np:"Now playing", page:"Change page",
  macro:"Macro", ai:"AI", timer:"Focus timer", mic:"Microphone", game:"Mini game", fun:"Fun", command:"Run command", text:"Type text", scroll:"Scroll", wait:"Wait"};
const KNOB_NAMES = {1:"Big knob", 0:"Left knob", 2:"Right knob"};
const GEST = [["action","Tap"],["double","Double tap"],["hold","Hold"]];
const a_ = (type, value) => ({type, value});
const KNOB_PRESETS = {
  "Dial modes": {modes:["volume","app_media","brightness","scrub"]},
  "Volume":   {left:a_("media","volume_down"), right:a_("media","volume_up"), press:a_("media","mute"), modes:[]},
  "Tracks":   {left:a_("np","previous"), right:a_("np","next"), press:a_("np","toggle"), modes:[]},
  "Scroll":   {left:a_("scroll","-3"), right:a_("scroll","3"), press:a_("none",""), modes:[]},
  "Zoom":     {left:a_("hotkey","ctrl+minus"), right:a_("hotkey","ctrl+plus"), press:a_("hotkey","ctrl+0"), modes:[]},
  "Pages":    {left:a_("page","prev"), right:a_("page","next"), press:a_("page","1"), modes:[]},
  "Desktops": {left:a_("hotkey","ctrl+win+left"), right:a_("hotkey","ctrl+win+right"), press:a_("hotkey","win+tab"), modes:[]},
};
const MODE_ICON = {volume:"speaker_high_volume", app_media:"musical_note", app_focus:"speaker_medium_volume", brightness:"sun",
  scroll:"computer_mouse", scrub:"fast_forward_button", zoom:"magnifying_glass_tilted_left", pages:"bookmark_tabs", tracks:"next_track_button"};

let S, sel = {kind:"key", idx:0}, tab = "edit", iconTab = null, gest = "action", libCb = null, libCat = "All";
let MAN = null, galCat = "Popular", heat = false;
const rot = {0:0, 1:0, 2:0};
const cur = () => S.cfg.current_page;
const page = () => S.cfg.pages[cur()];

async function api(name, body = {}) {
  const r = await fetch("/api/" + name, {method:"POST", headers:{"Content-Type":"application/json","X-Deck-Token":TOKEN}, body:JSON.stringify(body)});
  const j = await r.json();
  if (!r.ok) toast(j.error || "Something went wrong", true);
  return j;
}
async function upload(file) {
  const r = await fetch("/upload", {method:"POST", headers:{"X-Deck-Token":TOKEN, "X-Name":file.name}, body:file});
  return (await r.json()).path;
}
function toast(msg, err, title, ms) {
  const t = document.createElement("div");
  t.className = "toast" + (err ? " err" : "") + (title ? " big" : "");
  t.innerHTML = (title ? `<b>${esc(title)}</b>` : "") + esc(msg);
  $("#toasts").append(t);
  setTimeout(() => t.remove(), ms || 2800);
}

/* ================= boot ================= */
async function boot() {
  S = await api("state");
  const c = S.credits;
  $("#byline").textContent = `by ${c.studio}`;
  $("#sigStudio").textContent = c.studio.toUpperCase();
  $("#sigWho").textContent = `Designed and built by ${c.author}`;
  $("#aVer").textContent = `Version ${c.version}`;
  $("#aWho").textContent = `Designed and built by ${c.author}`;
  $("#aStudio").textContent = c.studio.toUpperCase();
  setStatus(S.connected);
  bindStatic();
  fit();
  $$(".key").forEach((el, i) => el.style.setProperty("--d", (i % 3) * 90 + Math.floor(i / 3) * 140 + "ms"));
  document.body.classList.add("boot");
  setTimeout(() => document.body.classList.remove("boot"), 2400);
  render();
  if (S.game) showGame(S.game);
  listen();
  fetch("/pack/manifest.json").then(r => r.json()).then(m => { MAN = m; if (tab === "edit" && sel.kind === "key") renderInspector(); });
}

function render(anim) {
  document.documentElement.style.setProperty("--accent", page().accent || "#7c5cff");
  document.documentElement.classList.toggle("rgb", !!page().rgb);
  renderPages();
  renderVitals();
  paintDevice(anim);
  renderInspector();
}
function setStatus(on, state) {
  const st = $("#status");
  st.classList.toggle("on", on);
  st.classList.toggle("warn", !on && state === "reconnecting");
  $("#status span").textContent = on ? "Deck connected" : state === "reconnecting" ? "Reconnecting…" : "Plug in your deck";
}

/* ================= device ================= */
function fit() {
  const area = $("#area"), w = area.clientWidth - 40, h = area.clientHeight - 60;
  const s = Math.max(.5, Math.min(1.35, w / 660, h / 400));
  $("#device").style.transform = `scale(${s})`;
  $("#wrap").style.width = 660 * s + "px";
  $("#wrap").style.height = 400 * s + "px";
}
addEventListener("resize", fit);

const glowCanvas = document.createElement("canvas");
glowCanvas.width = glowCanvas.height = 12;
function setGlow(el, img) {
  try {
    const g = glowCanvas.getContext("2d", {willReadFrequently:true});
    g.clearRect(0, 0, 12, 12); g.drawImage(img, 0, 0, 12, 12);
    const px = g.getImageData(0, 0, 12, 12).data;
    let r = 0, gg = 0, b = 0, n = 0;
    for (let i = 0; i < px.length; i += 4) {
      const mx = Math.max(px[i], px[i+1], px[i+2]), mn = Math.min(px[i], px[i+1], px[i+2]);
      const w = mx < 40 ? 0 : (mx - mn + 20) / 275;
      r += px[i] * w; gg += px[i+1] * w; b += px[i+2] * w; n += w;
    }
    el.style.setProperty("--glow", n > .4 ? `rgb(${r/n|0} ${gg/n|0} ${b/n|0} / .5)` : "transparent");
  } catch (e) {}
}
function setKeyImg(i, url) {
  const el = $$(".key")[i], img = $("img", el);
  if (img.src !== url) { img.onload = () => setGlow(el, img); img.src = url; }
}

async function loadPreviews(p, anim) {
  const r = await api("previews", {page:p});
  S.previews[p] = r.previews;
  if (p === cur()) paintDevice(anim);
}
function paintDevice(anim) {
  const pv = S.previews[cur()];
  if (!pv) { loadPreviews(cur(), anim); return; }
  $$(".key").forEach((el, i) => {
    setKeyImg(i, pv[i]);
    el.dataset.tip = page().keys[i].label || "Empty key";
    el.classList.toggle("sel", sel.kind === "key" && sel.idx === i);
    if (anim) { el.style.setProperty("--d", (i * 45) + "ms"); el.classList.remove("flip"); void el.offsetWidth; el.classList.add("flip"); }
  });
  if (sel.kind === "key" && tab === "edit" && $("#heroImg")) $("#heroImg").src = pv[sel.idx];
  $$(".rbtn").forEach((el, i) => {
    el.dataset.tip = S.cfg.buttons[i].label || `Button ${i + 1}`;
    el.classList.toggle("sel", sel.kind === "button" && sel.idx === i);
  });
  $$(".knob").forEach(el => {
    const k = +el.dataset.k, kn = S.cfg.knobs[k];
    const m = kn.modes && kn.modes.length ? ` (${modeName(kn.modes[(kn.mode || 0) % kn.modes.length])})` : "";
    el.dataset.tip = (kn.label || KNOB_NAMES[k]) + m;
    $(".cap", el).style.setProperty("--rot", rot[k] + "deg");
    el.classList.toggle("sel", sel.kind === "knob" && sel.idx === k);
  });
  paintHeat();
}
function pulse(el) { if (!el) return; el.classList.remove("pulse"); void el.offsetWidth; el.classList.add("pulse"); }
function select(kind, idx) { sel = {kind, idx}; iconTab = null; gest = "action"; setTab("edit"); paintDevice(); }

/* heatmap */
function heatColor(f) {
  const h = 230 - 230 * Math.min(1, f);
  return `hsl(${h} 90% 50% / ${.25 + .55 * Math.min(1, f)})`;
}
function paintHeat() {
  const dev = $("#device");
  dev.classList.toggle("heat", heat);
  $("#heatBtn").classList.toggle("on", heat);
  if (!heat) return;
  const pr = (S.cfg.stats && S.cfg.stats.presses) || {};
  const vals = [0,1,2,3,4,5].map(i => pr[`p${cur()}:k${i}`] || 0);
  const bv = [0,1,2].map(i => pr[`b${i}`] || 0), kv = [0,1,2].map(i => (pr[`n${i}`] || 0) + (pr[`t${i}`] || 0));
  const mx = Math.max(1, ...vals, ...bv);
  $$(".key").forEach((el, i) => { const l = $(".lcd", el); l.dataset.n = vals[i]; l.style.setProperty("--heat", heatColor(vals[i] / mx)); });
  $$(".rbtn").forEach((el, i) => { el.dataset.n = bv[i]; el.style.setProperty("--heat", heatColor(bv[i] / mx)); });
  const km = Math.max(1, ...kv);
  $$(".knob").forEach(el => { const k = +el.dataset.k; el.dataset.n = kv[k]; el.style.setProperty("--heat", heatColor(kv[k] / km)); });
}

/* ================= pages ================= */
function renderPages() {
  $("#pages").innerHTML = S.cfg.pages.map((p, i) =>
    `<button class="pg ${i === cur() ? "on" : ""}" data-i="${i}" title="${p.apps && p.apps.length ? "Opens by itself for " + esc(p.apps.join(", ")) : ""}">
      <span class="em">${esc(p.emoji)}</span><span>${esc(p.name)}</span>${(p.apps && p.apps.length) || p.games ? `<span class="auto">auto</span>` : ""}</button>`
  ).join("") + `<button class="pg add" id="addPage">+ New page</button>`;
  $$(".pg[data-i]").forEach(b => { b.onclick = () => gotoPage(+b.dataset.i); b.ondblclick = () => setTab("page"); });
  $("#addPage").onclick = async () => { const r = await api("add_page"); S.cfg = r.cfg; render(true); setTab("page"); toast("Page added"); };
}
function gotoPage(p) {
  if (p === cur()) return;
  flushAll();
  S.cfg.current_page = p; iconTab = null;
  render(true);
  api("goto_page", {page:p});
}

/* ================= saving ================= */
const pend = {};
function queueKey(i, patch) {
  const p = cur();
  Object.assign(S.cfg.pages[p].keys[i], patch);
  const id = p + ":" + i;
  pend[id] = {kind:"key", page:p, idx:i, patch:{...(pend[id]?.patch || {}), ...patch}};
  flushSoon();
}
function queueCtl(kind, i, patch) {
  Object.assign(S.cfg[kind === "button" ? "buttons" : "knobs"][i], patch);
  const id = kind + ":" + i;
  pend[id] = {kind, idx:i, patch:{...(pend[id]?.patch || {}), ...patch}};
  flushSoon();
  paintDevice();
}
const flushSoon = debounce(() => flushAll(), 180);
function flushAll() {
  for (const id of Object.keys(pend)) {
    const job = pend[id]; delete pend[id];
    if (job.kind === "key") {
      api("update_key", {page:job.page, idx:job.idx, patch:job.patch}).then(r => {
        if (!S.previews[r.page]) return;
        S.previews[r.page][r.idx] = r.preview;
        if (r.page === cur()) {
          setKeyImg(r.idx, r.preview);
          $$(".key")[r.idx].dataset.tip = S.cfg.pages[r.page].keys[r.idx].label || "Empty key";
          if (sel.kind === "key" && sel.idx === r.idx && $("#heroImg")) $("#heroImg").src = r.preview;
        }
      });
    } else api("update_control", {kind:job.kind, idx:job.idx, patch:job.patch});
  }
}

/* ================= inspector ================= */
function setTab(t) {
  tab = t;
  $$("#tabs button").forEach(b => b.classList.toggle("on", b.dataset.tab === t));
  renderInspector();
  $("#insp").scrollTop = 0;
}
function renderInspector() {
  const el = $("#insp");
  if (tab === "page") { el.innerHTML = pageHTML(); bindPage(); return; }
  if (tab === "settings") { el.innerHTML = settingsHTML(); bindSettings(); return; }
  if (tab === "stats") { el.innerHTML = statsHTML(); bindStats(); return; }
  if (sel.kind === "key") { el.innerHTML = keyHTML(); bindKey(); }
  else if (sel.kind === "button") { el.innerHTML = buttonHTML(); bindButton(); }
  else { el.innerHTML = knobHTML(); bindKnob(); }
}
function seg(id, opts, val) {
  return `<div class="seg" id="${id}">${opts.map(([v, t]) => `<button data-v="${v}" class="${v === val ? "on" : ""}">${t}</button>`).join("")}</div>`;
}
function bindSeg(id, cb) {
  $$(`#${id} button`).forEach(b => b.onclick = () => { $$(`#${id} button`).forEach(x => x.classList.toggle("on", x === b)); cb(b.dataset.v); });
}
function bindDrop(zone, onFile) {
  const input = $("input[type=file]", zone);
  input.onchange = () => input.files[0] && onFile(input.files[0]);
  zone.ondragover = e => { e.preventDefault(); zone.classList.add("over"); };
  zone.ondragleave = () => zone.classList.remove("over");
  zone.ondrop = e => { e.preventDefault(); zone.classList.remove("over"); const f = e.dataTransfer.files[0]; if (f) onFile(f); };
}

/* ----- action editor (with macros and AI) ----- */
function describe(a) {
  if (!a || a.type === "none") return "Nothing";
  if (a.type === "macro") return `Macro: ${(a.steps || []).length} steps`;
  if (a.type === "ai") return `AI: ${S.ai_modes[a.value] || a.value}`;
  return `${TYPE_NAMES[a.type] || a.type}: ${a.value}`;
}
function actionHTML(id, title) {
  return `<div class="act" data-act="${id}">${title ? `<h4>${title}</h4>` : ""}
    <div class="act-line">
      <select class="in a-type">${S.types.map(t => `<option value="${t}">${TYPE_NAMES[t] || t}</option>`).join("")}</select>
      <div class="a-slot"></div>
    </div>
    <div class="a-extra"></div>
    <div class="act-tools">
      <button class="btn a-lib">Library</button><button class="btn a-browse">Browse</button><button class="btn primary a-test">Test</button>
    </div>
    <p class="hint a-hint"></p></div>`;
}
function bindAction(el, get, set, onLib) {
  const tSel = $(".a-type", el), slot = $(".a-slot", el), extra = $(".a-extra", el), hint = $(".a-hint", el);
  const draw = () => {
    const a = get() || {type:"none", value:""}, t = a.type || "none";
    tSel.value = t;
    hint.textContent = S.hints[t] || "";
    extra.innerHTML = "";
    if (t === "ai") {
      slot.innerHTML = `<select class="in a-val">${Object.entries(S.ai_modes).map(([k, n]) => `<option value="${k}">${esc(n)}</option>`).join("")}</select>`;
      $(".a-val", slot).value = a.value || "fix";
      $(".a-val", slot).onchange = e => { set({...get(), type:"ai", value:e.target.value}); draw(); };
      if ((a.value || "") === "custom") {
        extra.innerHTML = `<textarea class="in" style="margin-top:8px" placeholder="Tell Claude what to do with the selected text">${esc(a.prompt || "")}</textarea>`;
        $("textarea", extra).oninput = e => set({...get(), prompt:e.target.value});
      }
      if (!S.ai.has_key) hint.innerHTML = `Needs a Claude API key. Add it in <b>Settings</b>.`;
    } else if (t === "macro") {
      slot.innerHTML = `<div class="muted" style="align-self:center">${(a.steps || []).length} steps</div>`;
      drawSteps();
    } else {
      slot.innerHTML = `<input class="in a-val" list="dl-${el.dataset.act}" spellcheck="false"><datalist id="dl-${el.dataset.act}">${(S.suggestions[t] || []).map(s => `<option value="${esc(s)}">`).join("")}</datalist>`;
      const v = $(".a-val", slot);
      v.value = a.value || ""; v.disabled = t === "none"; v.placeholder = t === "none" ? "" : "Type or pick a suggestion";
      v.oninput = () => set({type:tSel.value, value:v.value});
    }
  };
  const drawSteps = () => {
    const a = get(), steps = a.steps || [];
    extra.innerHTML = `<div class="steps">${steps.map((s, j) => `<div class="step" data-j="${j}"><span class="n">${j + 1}</span>
        <select class="in">${S.types.filter(t => !["macro", "none"].includes(t)).concat(["wait"]).map(t => `<option value="${t}" ${t === s.type ? "selected" : ""}>${TYPE_NAMES[t] || t}</option>`).join("")}</select>
        <input class="in" value="${esc(s.value)}" placeholder="${s.type === "wait" ? "milliseconds" : ""}"><button class="x" title="Remove">✕</button></div>`).join("")}</div>
      <div class="row" style="margin-top:8px"><button class="btn" data-add="open">+ Step</button><button class="btn" data-add="wait">+ Wait</button></div>`;
    const upd = fn => { const st = JSON.parse(JSON.stringify(get().steps || [])); fn(st); set({type:"macro", value:"", steps:st}); };
    $$(".step", extra).forEach(row => {
      const j = +row.dataset.j, [sl, inp] = [$("select", row), $("input", row)];
      sl.onchange = () => upd(st => st[j].type = sl.value);
      inp.oninput = () => upd(st => st[j].value = inp.value);
      $(".x", row).onclick = () => { upd(st => st.splice(j, 1)); draw(); };
    });
    $$("[data-add]", extra).forEach(b => b.onclick = () => { upd(st => st.push(b.dataset.add === "wait" ? a_("wait", "500") : a_("open", ""))); draw(); });
  };
  tSel.onchange = () => {
    const t = tSel.value, old = get() || {};
    const next = t === "macro" ? {type:"macro", value:"", steps:old.steps || []} : t === "ai" ? {type:"ai", value:"fix"} : {type:t, value:old.type === t ? old.value : ""};
    set(next); draw();
  };
  $(".a-test", el).onclick = () => { flushAll(); setTimeout(() => api("test_action", {action:get()}), 200); };
  $(".a-browse", el).onclick = async () => { const r = await api("browse_app"); if (r.path) { set({type:"open", value:r.path}); draw(); } };
  $(".a-lib", el).onclick = () => openLib(item => { onLib ? onLib(item) : set(JSON.parse(JSON.stringify(item.action))); draw(); });
  draw();
}

/* ----- gestures ----- */
function gestHTML(obj) {
  return `<div class="gest" id="gest">${GEST.map(([k, n]) => {
    const a = obj[k], isSet = a && a.type && a.type !== "none";
    return `<button data-g="${k}" class="${gest === k ? "on" : ""} ${isSet ? "set" : ""}">${n}</button>`;
  }).join("")}</div>`;
}
function bindGest(rerender) { $$("#gest button").forEach(b => b.onclick = () => { gest = b.dataset.g; rerender(); }); }

/* ----- icon gallery ----- */
function iconTabFor(k) {
  if (iconTab) return iconTab;
  if (k.live) return "live";
  if (k.icon && /(^|[\\/])icons[\\/]app_/.test(k.icon)) return "app";
  if (k.icon && !k.icon.startsWith("pack/")) return "image";
  return "icons";
}
function galItems() {
  if (!MAN) return [];
  const q = ($("#galSearch")?.value || "").trim().toLowerCase();
  let items;
  if (galCat === "Brands") items = MAN.brands.map(b => ({f:b.f, n:b.n}));
  else if (galCat === "Popular") items = S.emojis.map(e => ({e, f:MAN.emoji[e.replace(/\ufe0f/g, "")], n:e})).filter(x => x.f).map(x => MAN.icons.find(i => i.f === x.f) || x);
  else items = MAN.icons.filter(i => galCat === "All" || i.g === galCat);
  if (q) {
    const all = [...MAN.brands.map(b => ({f:b.f, n:b.n})), ...MAN.icons];
    items = all.filter(i => (i.n + " " + (i.k || "")).toLowerCase().includes(q));
  }
  return items.slice(0, 400);
}
function galleryHTML(k) {
  const cats = ["Popular", "Brands", "Objects", "Activities", "Symbols", "Smileys", "Animals", "Food", "Travel", "People", "All"];
  return `<div class="gal-top"><input class="in" id="galSearch" placeholder="Search 1,400 icons and brands"><input class="in big" id="fEmoji" style="width:56px;height:38px;font-size:20px" value="${esc(k.icon ? "" : k.emoji)}" title="Or type an emoji"></div>
    <div class="gal-cats">${cats.map(c => `<button data-c="${c}" class="${c === galCat ? "on" : ""}">${c}</button>`).join("")}</div>
    <div class="gallery" id="gallery">${galGrid(k)}</div>`;
}
function galGrid(k) {
  if (!MAN) return `<p class="muted">Loading icons</p>`;
  const items = galItems();
  if (!items.length) return `<p class="muted">No icons match. Try another word.</p>`;
  return items.map(i => `<button data-f="${i.f}" class="${("pack/" + i.f) === k.icon ? "on" : ""} ${i.r ? "remote" : ""}" title="${esc(i.n)}">
      <img loading="lazy" src="${i.r ? i.r : "/pack/" + i.f}" alt=""></button>`).join("");
}
function bindGallery(i) {
  const k = () => page().keys[i];
  const redraw = () => { $("#gallery").innerHTML = galGrid(k()); bindGrid(); };
  const bindGrid = () => $$("#gallery button").forEach(b => b.onclick = async () => {
    const it = [...(MAN.brands || []), ...MAN.icons].find(x => x.f === b.dataset.f);
    let path = "pack/" + b.dataset.f;
    if (it && it.r) { const r = await api("fetch_icon", {f:it.f}); if (r.error) return toast(r.error, true); it.r = null; }
    queueKey(i, {icon:path, live:""});
    $$("#gallery button").forEach(x => x.classList.toggle("on", x === b));
  });
  $("#galSearch").oninput = debounce(redraw, 120);
  $$(".gal-cats button").forEach(b => b.onclick = () => { galCat = b.dataset.c; $$(".gal-cats button").forEach(x => x.classList.toggle("on", x === b)); redraw(); });
  $("#fEmoji").oninput = e => queueKey(i, {emoji:e.target.value.trim(), icon:"", live:""});
  bindGrid();
}

/* ----- key editor ----- */
function liveHelper() {
  const m = S.monitor;
  const parts = [];
  if (!m.lhm) parts.push(`<p><b>CPU temperature${m.nvidia ? "" : " and GPU stats"}</b> need LibreHardwareMonitor running with Options, then Remote Web Server turned on.</p><button class="btn" id="getLhm">Get LibreHardwareMonitor</button>`);
  if (!m.media) parts.push(`<p style="margin-top:10px"><b>Now playing</b> needs the Windows media package. Run run.bat once more to install it.</p>`);
  return parts.length ? `<div class="helper">${parts.join("")}</div>` : "";
}
function iconPane(it, k) {
  if (it === "icons") return galleryHTML(k);
  if (it === "live") return `
    <p class="note" style="margin:0 0 12px">A live tile that refreshes on your deck by itself.</p>
    <div class="metrics">${S.metrics.map(m => `<button class="metric ${k.live === m.id ? "on" : ""}" data-m="${m.id}">
      <b>${esc(m.name)}</b>${S.monitor.available[m.id] ? `<small class="ok">Ready</small>` : `<small>Needs setup</small>`}</button>`).join("")}</div>
    ${k.live ? `<div class="row" style="margin-top:12px"><button class="btn" id="liveOff">Turn off live tile</button></div>` : ""}
    ${liveHelper()}`;
  if (it === "image") return `
    <label class="drop" id="drop"><input type="file" accept="image/*" hidden><b>Drop an image or GIF here</b><span>or click to choose. Animated GIFs play on the deck.</span></label>
    ${k.icon && !k.icon.startsWith("pack/") ? `<div class="filechip"><span>${esc(k.icon.split(/[\\/]/).pop())}</span><button class="btn" id="rmIcon">Remove</button></div>` : ""}`;
  const target = k.exe || k.action?.value || "";
  return `<p class="note" style="margin-top:0">Uses the real icon of the app this key opens${target ? `: <b>${esc(target)}</b>` : ". Set an Open action first."}</p>
    <div class="row" style="margin-top:12px"><button class="btn primary" id="grabIcon" ${target ? "" : "disabled"}>Use app icon</button>
    ${k.icon ? `<button class="btn" id="rmIcon">Remove</button>` : ""}</div>`;
}
function bindIconPane(i) {
  const k = () => page().keys[i];
  const rerender = () => { $("#iconPane").innerHTML = iconPane(iconTabFor(k()), k()); bindIconPane(i); };
  if ($("#gallery")) bindGallery(i);
  const drop = $("#drop");
  if (drop) bindDrop(drop, async f => { const p = await upload(f); queueKey(i, {icon:p, live:""}); rerender(); });
  const rm = $("#rmIcon"); if (rm) rm.onclick = () => { queueKey(i, {icon:""}); rerender(); };
  const g = $("#grabIcon");
  if (g) g.onclick = async () => {
    const r = await api("app_icon", {value:k().exe || k().action?.value || ""});
    if (r.path) { queueKey(i, {icon:r.path, live:""}); toast("App icon added"); rerender(); }
    else toast("No icon found for that app. Pick one from Icons instead.", true);
  };
  $$(".metric").forEach(b => b.onclick = () => {
    const m = S.metrics.find(x => x.id === b.dataset.m), patch = {live:m.id}, kk = k();
    if (!kk.label || S.metrics.some(x => x.name === kk.label)) { patch.label = m.name; const n = $("#fName"); if (n) n.value = m.name; }
    const lib = S.library.find(x => x.live === m.id);
    if (lib && (!kk.action || kk.action.type === "none" || kk.action.type === "hotkey")) Object.assign(patch, {action:lib.action, double:lib.double || a_("none",""), hold:lib.hold || a_("none","")});
    else if (!kk.action || kk.action.type === "none") patch.action = a_("hotkey", "ctrl+shift+esc");
    queueKey(i, patch); rerender(); renderVitals();
  });
  const off = $("#liveOff"); if (off) off.onclick = () => { queueKey(i, {live:""}); iconTab = "icons"; rerender(); renderVitals(); };
  const lhm = $("#getLhm"); if (lhm) lhm.onclick = () => api("open_url", {url:"https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases"});
}
function keyHTML() {
  const i = sel.idx, k = page().keys[i], it = iconTabFor(k), bg = k.bg || "none";
  return `
  <div class="head"><h2>Key ${i + 1}</h2><p>On the ${esc(page().name)} page</p></div>
  <div class="hero">
    <div class="lcd-big"><img id="heroImg" alt="" src="${S.previews[cur()]?.[i] || ""}"></div>
    <div class="hero-f">
      <label class="f"><span>Name</span><input class="in" id="fName" value="${esc(k.label)}" placeholder="Name this key"></label>
      <label class="tg"><span>Show name on the key</span><input type="checkbox" class="sw" id="fShow" ${k.show_label ? "checked" : ""}></label>
      <label class="f"><span>Icon size</span><input type="range" id="fScale" min="50" max="100" value="${Math.round((k.icon_scale ?? .9) * 100)}"></label>
    </div>
  </div>
  <section class="blk">
    <div class="blk-h"><h3>Icon</h3>${seg("iconSeg", [["icons","Icons"],["image","Image"],["app","App icon"],["live","Live"]], it)}</div>
    <div id="iconPane">${iconPane(it, k)}</div>
  </section>
  <section class="blk"><h3>Actions</h3>${gestHTML(k)}
    ${actionHTML("main")}
    <p class="note">Tap, double tap and hold can each do something different.${gest !== "action" ? " Double tap makes single taps wait a moment." : ""}</p>
  </section>
  <section class="blk">
    <div class="blk-h"><h3>Badge</h3>${seg("badgeSeg", [["","None"],["outlook","Unread mail"],["mic","Mic muted"]], k.badge || "")}</div>
    <p class="note" style="margin-top:0">A small live marker in the corner of the key.</p>
  </section>
  <section class="blk">
    <div class="blk-h"><h3>Background</h3>${seg("bgSeg", [["none","None"],["solid","Solid"],["gradient","Gradient"]], bg)}</div>
    ${bg === "none" ? `<p class="note" style="margin-top:0">${page().wallpaper ? "The page wallpaper shows behind this icon." : "Pure black, so the icon stands on its own."}</p>`
      : `<div class="row"><input type="color" id="fColor" value="${esc(k.color || "#7c5cff")}"><span class="muted">Key color</span></div>`}
  </section>`;
}
function applyLibToKey(i, item) {
  const patch = {label:item.name, emoji:"", icon:item.icon || "", live:item.live || "", badge:item.badge || "",
    action:JSON.parse(JSON.stringify(item.action)), double:item.double || a_("none",""), hold:item.hold || a_("none",""), exe:item.exe || ""};
  queueKey(i, patch);
  iconTab = null; renderInspector();
  if (item.exe) api("app_icon", {value:item.exe}).then(r => {
    if (r.path && page().keys[i].label === item.name) { queueKey(i, {icon:r.path}); if (sel.idx === i && tab === "edit") renderInspector(); }
  });
}
function bindKey() {
  const i = sel.idx;
  $("#fName").oninput = e => queueKey(i, {label:e.target.value});
  $("#fShow").onchange = e => queueKey(i, {show_label:e.target.checked});
  $("#fScale").oninput = e => queueKey(i, {icon_scale:e.target.value / 100});
  bindSeg("iconSeg", async v => {
    iconTab = v;
    if (v === "live") S.monitor = await api("monitor");
    $("#iconPane").innerHTML = iconPane(v, page().keys[i]); bindIconPane(i);
  });
  bindSeg("bgSeg", v => { queueKey(i, {bg:v}); renderInspector(); });
  bindSeg("badgeSeg", v => queueKey(i, {badge:v}));
  const c = $("#fColor"); if (c) c.oninput = () => queueKey(i, {color:c.value});
  bindIconPane(i);
  bindGest(() => renderInspector());
  bindAction($("[data-act=main]"), () => page().keys[i][gest], a => { queueKey(i, {[gest]:a}); $(`#gest [data-g=${gest}]`).classList.toggle("set", a.type !== "none"); },
    item => gest === "action" ? applyLibToKey(i, item) : queueKey(i, {[gest]:JSON.parse(JSON.stringify(item.action))}));
}

/* ----- buttons ----- */
function buttonHTML() {
  const i = sel.idx, b = S.cfg.buttons[i];
  return `<div class="head"><h2>Button ${i + 1}</h2><p>Works the same on every page</p></div>
    <label class="f"><span>Name</span><input class="in" id="fName" value="${esc(b.label)}"></label>
    <section class="blk"><h3>Actions</h3>${gestHTML(b)}${actionHTML("main")}</section>`;
}
function bindButton() {
  const i = sel.idx;
  $("#fName").oninput = e => queueCtl("button", i, {label:e.target.value});
  bindGest(() => renderInspector());
  bindAction($("[data-act=main]"), () => S.cfg.buttons[i][gest], a => { queueCtl("button", i, {[gest]:a}); $(`#gest [data-g=${gest}]`).classList.toggle("set", a.type !== "none"); },
    item => { const p = {[gest]:JSON.parse(JSON.stringify(item.action))}; if (gest === "action") { p.label = item.name; $("#fName").value = item.name; } queueCtl("button", i, p); });
}

/* ----- knobs ----- */
function modeName(m) { return m && m.startsWith("app:") ? m.slice(4).replace(".exe", "") : (S.knob_modes[m] || m); }
function knobHTML() {
  const k = sel.idx, kn = S.cfg.knobs[k], modes = kn.modes || [];
  return `<div class="head"><h2>${KNOB_NAMES[k]}</h2><p>Turn it or press it. Works the same on every page.</p></div>
    <label class="f"><span>Name</span><input class="in" id="fName" value="${esc(kn.label)}"></label>
    <section class="blk"><h3>Quick setup</h3><div class="presets">${Object.keys(KNOB_PRESETS).map(n => `<button data-p="${n}">${n}</button>`).join("")}</div></section>
    <section class="blk"><label class="tg"><span><b>Dial modes</b><br><small class="muted">Press to switch between modes, hold for extra (mute, reset). Your deck shows a little dashboard.</small></span>
      <input type="checkbox" class="sw" id="kModes" ${modes.length ? "checked" : ""}></label>
      ${modes.length ? `<div class="modechips" style="margin-top:12px">${Object.entries(S.knob_modes).map(([id, n]) => {
        const o = modes.indexOf(id); return `<button data-m="${id}" class="${o >= 0 ? "on" : ""}">${o >= 0 ? `<span class="o">${o + 1}</span>` : ""}${esc(n)}</button>`; }).join("")}
        ${modes.filter(m => m.startsWith("app:")).map(m => `<button data-m="${m}" class="on"><span class="o">${modes.indexOf(m) + 1}</span>${esc(modeName(m))}</button>`).join("")}
        <button id="addAppMode">+ Pick an app</button></div>
        <div class="applist" id="appPick"></div>` : ""}
    </section>
    ${modes.length ? "" : `<section class="blk"><h3>Turning</h3>${actionHTML("left", "Turn left")}${actionHTML("right", "Turn right")}</section>
    <section class="blk"><h3>Pressing</h3>${gestHTML({action:kn.press, double:kn.double, hold:kn.hold})}${actionHTML("press")}</section>`}`;
}
function bindKnob() {
  const k = sel.idx, kn = () => S.cfg.knobs[k];
  $("#fName").oninput = e => queueCtl("knob", k, {label:e.target.value});
  $$(".presets button").forEach(b => b.onclick = () => {
    const p = JSON.parse(JSON.stringify(KNOB_PRESETS[b.dataset.p]));
    queueCtl("knob", k, {label:b.dataset.p === "Dial modes" ? "Dial" : b.dataset.p, mode:0, ...p});
    renderInspector(); toast(`${KNOB_NAMES[k]} set to ${b.dataset.p}`);
  });
  $("#kModes").onchange = e => { queueCtl("knob", k, {modes:e.target.checked ? ["volume", "app_media", "brightness", "scrub"] : [], mode:0}); renderInspector(); };
  $$(".modechips button[data-m]").forEach(b => b.onclick = () => {
    const m = [...(kn().modes || [])], id = b.dataset.m, at = m.indexOf(id);
    at >= 0 ? m.splice(at, 1) : m.push(id);
    if (!m.length) return toast("Keep at least one mode, or turn Dial modes off.", true);
    queueCtl("knob", k, {modes:m, mode:0}); renderInspector();
  });
  const add = $("#addAppMode");
  if (add) add.onclick = async () => {
    const r = await api("running_apps");
    const apps = [...new Set([...(r.audio || []), ...(r.apps || [])].map(x => x.toLowerCase()))];
    $("#appPick").innerHTML = apps.length ? apps.map(a => `<button data-a="${esc(a)}">${esc(a.replace(".exe", ""))}</button>`).join("") : `<span class="muted">Open the app first, then try again.</span>`;
    $$("#appPick button").forEach(b => b.onclick = () => { queueCtl("knob", k, {modes:[...(kn().modes || []), "app:" + b.dataset.a], mode:0}); renderInspector(); });
  };
  if (!(kn().modes || []).length) {
    for (const part of ["left", "right"]) bindAction($(`[data-act=${part}]`), () => kn()[part], a => queueCtl("knob", k, {[part]:a}));
    const gkey = gest === "action" ? "press" : gest;
    bindGest(() => renderInspector());
    bindAction($("[data-act=press]"), () => kn()[gkey], a => { queueCtl("knob", k, {[gkey]:a}); $(`#gest [data-g=${gest}]`).classList.toggle("set", a.type !== "none"); });
  }
}

/* ----- page tab ----- */
function pageHTML() {
  const p = page(), n = S.cfg.pages.length, apps = p.apps || [];
  return `<div class="head"><h2>${esc(p.emoji)} ${esc(p.name)}</h2><p>Page ${cur() + 1} of ${n}. Your deck shows this page now.</p></div>
    <label class="f"><span>Page name</span><input class="in" id="pName" value="${esc(p.name)}"></label>
    <section class="blk"><h3>Opens by itself</h3><p class="note" style="margin-top:0">When one of these apps is in front, your deck jumps to this page. When you leave, it goes back.</p>
      <div class="applist">${apps.map(a => `<button class="rm" data-a="${esc(a)}">${esc(a.replace(".exe", ""))}</button>`).join("")}<button id="pAddApp">+ Add app</button></div>
      <div class="applist" id="pPick"></div>
      <label class="tg"><span>Any game<br><small class="muted">Steam, Epic, Riot, Battle.net, Xbox and more</small></span><input type="checkbox" class="sw" id="pGames" ${p.games ? "checked" : ""}></label>
      <label class="tg"><span>Skip when flipping pages<br><small class="muted">Only opens by itself or from a key</small></span><input type="checkbox" class="sw" id="pHidden" ${p.hidden ? "checked" : ""}></label>
    </section>
    <section class="blk"><h3>Page icon</h3>
      <div class="emoji-in"><input class="in big" id="pEmoji" value="${esc(p.emoji)}"><span class="muted">Shows in the tabs and on the page banner.</span></div>
      <div class="palette">${S.emojis.map(e => `<button data-e="${e}" class="${e === p.emoji ? "on" : ""}">${e}</button>`).join("")}</div>
    </section>
    <section class="blk"><h3>Color</h3>
      <div class="swatches">${S.accents.map(c => `<button class="sw-c ${c === p.accent ? "on" : ""}" data-c="${c}" style="--c:${c}" aria-label="${c}"></button>`).join("")}
      <input type="color" id="pColor" value="${esc(p.accent)}" title="Custom color"></div>
      <label class="tg"><span>RGB glow<br><small class="muted">Cycles through colors in the studio and on the page banner</small></span><input type="checkbox" class="sw" id="pRgb" ${p.rgb ? "checked" : ""}></label>
    </section>
    <section class="blk"><h3>Wallpaper</h3><p class="note" style="margin-top:0">One picture spread across all six keys, behind the icons.</p>
      <label class="drop" id="wdrop" style="margin-top:12px"><input type="file" accept="image/*" hidden><b>Drop a picture here</b><span>or click to choose one</span></label>
      ${p.wallpaper ? `<div class="filechip"><span>${esc(p.wallpaper.split(/[\\/]/).pop())}</span><button class="btn" id="rmWall">Remove</button></div>` : ""}
    </section>
    <section class="blk"><h3>Arrange</h3><div class="row">
      <button class="btn" id="pLeft" ${cur() === 0 ? "disabled" : ""}>Move left</button>
      <button class="btn" id="pRight" ${cur() === n - 1 ? "disabled" : ""}>Move right</button>
      <button class="btn" id="pDup">Duplicate</button>
      <button class="btn danger" id="pDel" ${n < 2 ? "disabled" : ""}>Delete page</button></div>
    </section>`;
}
const sendPage = debounce(async (p, patch) => {
  const r = await api("update_page", {page:p, patch});
  S.previews[p] = r.previews;
  if (p === cur()) paintDevice();
}, 220);
let pagePatch = {};
function queuePage(patch) {
  Object.assign(page(), patch);
  pagePatch = {...pagePatch, ...patch};
  const p = cur(), pp = pagePatch;
  sendPage(p, pp);
  setTimeout(() => { if (pagePatch === pp) pagePatch = {}; }, 240);
  document.documentElement.style.setProperty("--accent", page().accent);
  renderPages();
}
function bindPage() {
  $("#pName").oninput = e => { queuePage({name:e.target.value}); $(".head h2").textContent = `${page().emoji} ${e.target.value}`; };
  $("#pEmoji").oninput = e => queuePage({emoji:e.target.value.trim()});
  $$(".palette button").forEach(b => b.onclick = () => { queuePage({emoji:b.dataset.e}); renderInspector(); });
  $$(".sw-c").forEach(b => b.onclick = () => { queuePage({accent:b.dataset.c}); renderInspector(); });
  $("#pColor").oninput = e => queuePage({accent:e.target.value});
  $("#pRgb").onchange = e => { queuePage({rgb:e.target.checked}); document.documentElement.classList.toggle("rgb", e.target.checked); };
  $("#pGames").onchange = e => queuePage({games:e.target.checked});
  $("#pHidden").onchange = e => queuePage({hidden:e.target.checked});
  $$(".applist .rm").forEach(b => b.onclick = () => { queuePage({apps:(page().apps || []).filter(a => a !== b.dataset.a)}); renderInspector(); });
  $("#pAddApp").onclick = async () => {
    const r = await api("running_apps");
    const have = new Set(page().apps || []);
    const apps = (r.apps || []).filter(a => !have.has(a));
    $("#pPick").innerHTML = apps.length ? apps.map(a => `<button data-a="${esc(a)}">${esc(a.replace(".exe", ""))}</button>`).join("") : `<span class="muted">Open the app first, then try again.</span>`;
    $$("#pPick button").forEach(b => b.onclick = () => { queuePage({apps:[...(page().apps || []), b.dataset.a]}); renderInspector(); toast(`${page().name} opens with ${b.dataset.a.replace(".exe", "")}`); });
  };
  bindDrop($("#wdrop"), async f => { const path = await upload(f); queuePage({wallpaper:path}); renderInspector(); toast("Wallpaper set"); });
  const rm = $("#rmWall"); if (rm) rm.onclick = () => { queuePage({wallpaper:""}); renderInspector(); };
  const after = r => { S.cfg = r.cfg; S.previews = {}; render(true); };
  $("#pLeft").onclick = async () => after(await api("move_page", {page:cur(), dir:-1}));
  $("#pRight").onclick = async () => after(await api("move_page", {page:cur(), dir:1}));
  $("#pDup").onclick = async () => { after(await api("duplicate_page", {page:cur()})); toast("Page duplicated"); };
  $("#pDel").onclick = async () => { if (!confirm(`Delete the ${page().name} page?`)) return; after(await api("delete_page", {page:cur()})); toast("Page deleted"); };
}

/* ----- stats tab ----- */
function statsHTML() {
  const st = S.cfg.stats || {}, pr = st.presses || {}, best = st.best || {};
  const rows = [];
  S.cfg.pages.forEach((p, pi) => [0,1,2,3,4,5].forEach(i => { const n = pr[`p${pi}:k${i}`]; if (n) rows.push({n, name:p.keys[i].label || `Key ${i + 1}`, where:p.name, icon:p.keys[i].icon}); }));
  [0,1,2].forEach(i => { if (pr[`b${i}`]) rows.push({n:pr[`b${i}`], name:S.cfg.buttons[i].label || `Button ${i + 1}`, where:"Button", icon:"pack/3d/radio_button.png"}); });
  rows.sort((a, b) => b.n - a.n);
  const total = Object.entries(pr).filter(([k]) => !k.startsWith("t")).reduce((s, [, v]) => s + v, 0);
  const turns = [0,1,2].reduce((s, i) => s + (pr[`t${i}`] || 0), 0);
  const mx = rows[0]?.n || 1;
  return `<div class="head"><h2>Your stats</h2><p>What you use most. Turn on Heatmap above the deck to see it live.</p></div>
    <div class="stat-top"><div><b>${total}</b><span>presses</span></div><div><b>${turns}</b><span>knob clicks</span></div><div><b>${rows.length}</b><span>keys used</span></div></div>
    <section class="blk"><h3>Most used</h3>${rows.length ? `<div class="rank">${rows.slice(0, 8).map(r => `<div>
      ${src(r.icon) ? `<img src="${src(r.icon)}" alt="">` : `<img alt="">`}<span><b>${esc(r.name)}</b> <small>${esc(r.where)}</small><i style="width:${Math.max(4, r.n / mx * 100)}%"></i></span><b>${r.n}</b></div>`).join("")}</div>`
      : `<p class="note">Press some keys on your deck and they show up here.</p>`}
      ${rows.length > 3 ? `<p class="note">Tip: move your top keys to the Home page so they are one press away.</p>` : ""}</section>
    <section class="blk"><h3>Arcade bests</h3><div class="stat-top" style="grid-template-columns:1fr 1fr">
      <div><b>${best.simon ?? "--"}</b><span>Simon level</span></div><div><b>${best.reaction ? best.reaction + " ms" : "--"}</b><span>Reaction average</span></div></div>
      <div class="row" style="margin-top:12px"><button class="btn primary" data-game="simon">Play Simon</button><button class="btn primary" data-game="reaction">Play Reaction</button></div></section>
    <section class="blk"><button class="btn danger" id="rsStats">Reset press counts</button></section>`;
}
function bindStats() {
  $$("[data-game]").forEach(b => b.onclick = () => api("start_game", {name:b.dataset.game}));
  $("#rsStats").onclick = async () => { if (!confirm("Reset all press counts?")) return; const r = await api("reset_stats"); S.cfg.stats = r.stats; renderInspector(); paintHeat(); };
}

/* ----- settings tab ----- */
function settingsHTML() {
  const sm = S.cfg.smart || {};
  return `<div class="head"><h2>Settings</h2><p>These apply to the whole deck.</p></div>
    <label class="f"><span>Screen brightness</span><input type="range" id="sBright" min="0" max="100" value="${S.cfg.brightness ?? 80}"></label>
    <section class="blk">
      <label class="tg"><span>Start when Windows starts<br><small class="muted">Runs quietly in the tray and restarts itself if it ever stops</small></span><input type="checkbox" class="sw" id="sStart" ${S.startup ? "checked" : ""}></label>
      <label class="tg"><span>Show a banner when switching pages</span><input type="checkbox" class="sw" id="sSplash" ${S.cfg.splash !== false ? "checked" : ""}></label>
    </section>
    <section class="blk"><div class="blk-h"><h3>Sleep</h3><button class="btn" id="sSleepNow">Sleep now</button></div>
      <label class="f"><span>Turn the screens off after</span><select class="in" id="sSleep" style="width:160px">${
        [0, 1, 2, 3, 5, 10, 15, 30, 60].map(m => `<option value="${m}" ${(S.cfg.sleep_minutes || 0) === m ? "selected" : ""}>${m ? `${m} minute${m > 1 ? "s" : ""}` : "Never"}</option>`).join("")
      }</select></label>
      <p class="note">Counts from the last press or knob turn. Any press wakes the deck, and that press only wakes it.</p></section>
    <section class="blk"><h3>Smart pages</h3>
      <label class="tg"><span>Follow the app in front<br><small class="muted">Pages with apps set open by themselves</small></span><input type="checkbox" class="sw" id="sSmart" ${sm.enabled !== false ? "checked" : ""}></label>
      <label class="tg"><span>Go back when I leave the app</span><input type="checkbox" class="sw" id="sBack" ${sm.go_back !== false ? "checked" : ""}></label>
    </section>
    <section class="blk"><h3>Focus timer</h3>
      <label class="f"><span>Minutes</span><input class="in" id="sMin" type="number" min="1" max="240" value="${S.cfg.timer_minutes || 25}" style="width:110px"></label>
      <p class="note">Tap the timer key to start or pause, double tap for 5 more minutes, hold to reset.</p></section>
    <section class="blk"><h3>AI keys</h3>
      <p class="note" style="margin-top:0">Select text anywhere, press an AI key, and Claude rewrites, translates or summarizes it. Needs your own Claude API key from console.anthropic.com. It stays on this PC in secret.json.</p>
      <label class="f"><span>API key ${S.ai.has_key ? "(saved)" : ""}</span><input class="in" id="sKey" type="password" placeholder="${S.ai.has_key ? "Saved. Paste a new one to replace it" : "sk-ant-..."}"></label>
      <label class="f"><span>Model</span><input class="in" id="sModel" value="${esc(S.ai.model)}"></label>
      <div class="row" style="margin-top:12px"><button class="btn primary" id="sSaveAi">Save</button><button class="btn" id="sTestAi">Test</button><button class="btn" id="sConsole">Get a key</button></div>
    </section>
    <section class="blk"><div class="blk-h"><h3>Deck health</h3><button class="btn" id="sReconnect">Reconnect</button></div>
      <div class="health" id="healthBox"><div><b>--</b><span>status</span></div></div>
      <p class="note">If the deck ever stops responding, the app notices within a few seconds and reconnects by itself.
        Details go to akp03.log in the app folder.</p></section>
    <section class="blk"><h3>Backup</h3><div class="row"><button class="btn" id="sExport">Export setup</button><button class="btn" id="sImport">Import setup</button></div>
      <p class="note">Saves all pages, keys, knobs and stats to one file. Handy for a second PC or a fresh start.</p></section>
    <section class="blk"><h3>Files</h3><div class="row"><button class="btn" id="sFolder">Open app folder</button><button class="btn danger" id="sReset">Reset pages</button></div>
      <p class="note">Your setup is saved in config.json inside the app folder.</p></section>`;
}
function bindSettings() {
  const send = debounce(v => api("settings", {patch:{brightness:+v}}), 60);
  $("#sBright").oninput = e => { S.cfg.brightness = +e.target.value; send(e.target.value); };
  $("#sStart").onchange = async e => { const r = await api("settings", {patch:{startup:e.target.checked}}); S.startup = r.startup; e.target.checked = r.startup; toast(r.startup ? "Starts with Windows" : "Won't start with Windows"); };
  $("#sSplash").onchange = e => { S.cfg.splash = e.target.checked; api("settings", {patch:{splash:e.target.checked}}); };
  const smart = () => { const v = {enabled:$("#sSmart").checked, go_back:$("#sBack").checked}; S.cfg.smart = v; api("settings", {patch:{smart:v}}); };
  $("#sSmart").onchange = smart; $("#sBack").onchange = smart;
  $("#sSleep").onchange = e => { const m = +e.target.value; S.cfg.sleep_minutes = m; api("settings", {patch:{sleep_minutes:m}}); toast(m ? `Deck sleeps after ${m} minute${m > 1 ? "s" : ""} untouched` : "Deck never sleeps by itself"); };
  $("#sSleepNow").onclick = () => api("sleep_now", {});
  $("#sMin").onchange = e => { S.cfg.timer_minutes = +e.target.value; api("settings", {patch:{timer_minutes:+e.target.value}}); toast(`Focus timer set to ${e.target.value} minutes`); };
  $("#sSaveAi").onclick = async () => {
    const body = {model:$("#sModel").value}; if ($("#sKey").value.trim()) body.key = $("#sKey").value.trim();
    S.ai = await api("set_ai", body); toast("AI settings saved"); renderInspector();
  };
  $("#sTestAi").onclick = async () => { toast("Asking Claude"); const r = await api("test_ai"); r.ok ? toast(r.text, false, "Claude says") : toast(r.error, true); };
  $("#sConsole").onclick = () => api("open_url", {url:"https://console.anthropic.com/settings/keys"});
  $("#sFolder").onclick = () => api("open_folder");
  $("#sReconnect").onclick = async () => { await api("reconnect"); toast("Reconnecting to your deck"); setTimeout(renderHealth, 2500); };
  $("#sExport").onclick = async () => {
    const r = await api("export_config");
    const blob = new Blob([JSON.stringify(r.cfg, null, 2)], {type:"application/json"});
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = `akp03-setup-${new Date().toISOString().slice(0, 10)}.json`; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    toast("Setup exported");
  };
  $("#sImport").onclick = () => $("#importFile").click();
  renderHealth();
  $("#sReset").onclick = () => { if (confirm("Reset all pages, buttons and knobs to the starter setup? Your stats stay.")) api("reset"); };
}

async function renderHealth() {
  const box = $("#healthBox"); if (!box) return;
  const h = await api("health");
  const st = {connected:"Connected", reconnecting:"Reconnecting", searching:"Not plugged in"}[h.state] || h.state;
  const up = h.connected ? Math.round((Date.now() / 1000 - h.since) / 60) : 0;
  box.innerHTML = `<div><b>${esc(st)}</b><span>${h.connected ? `for ${up < 60 ? up + " min" : Math.round(up / 60) + " h"}` : "waiting for the deck"}</span></div>
    <div><b>${h.reconnects}</b><span>auto reconnects</span></div>
    <div><b>${(h.io && h.io.images) || 0}</b><span>images sent, ${(h.io && h.io.skipped) || 0} skipped as unchanged</span></div>
    <div><b>${h.memory_mb ?? "--"} MB</b><span>app memory</span></div>`;
}

/* ================= command palette (Ctrl+K) ================= */
let palItems = [], palSel = 0;
function palSource() {
  const out = [];
  S.cfg.pages.forEach((p, pi) => {
    out.push({t:`${p.name} page`, sub:"Go to page", em:p.emoji, run:() => gotoPage(pi)});
    [0,1,2,3,4,5].forEach(i => { const k = p.keys[i]; if (k.label) out.push({t:k.label, sub:`${p.name}, key ${i + 1}`, img:src(k.icon), em:k.icon ? "" : k.emoji,
      run:() => { gotoPage(pi); select("key", i); }}); });
  });
  [0,1,2].forEach(i => out.push({t:S.cfg.buttons[i].label || `Button ${i + 1}`, sub:`Round button ${i + 1}`, img:"/pack/3d/radio_button.png", run:() => select("button", i)}));
  [1,0,2].forEach(i => out.push({t:KNOB_NAMES[i], sub:S.cfg.knobs[i].label || "Knob", img:"/pack/3d/control_knobs.png", run:() => select("knob", i)}));
  [["Settings","settings","gear"],["Stats and heatmap","stats","bar_chart"],["Page settings","page","bookmark_tabs"]].forEach(([t, tb, ic]) =>
    out.push({t, sub:"Open tab", img:`/pack/3d/${ic}.png`, run:() => setTab(tb)}));
  out.push({t:"Reconnect deck", sub:"Fix a stuck deck", img:"/pack/3d/counterclockwise_arrows_button.png", run:() => { api("reconnect"); toast("Reconnecting"); }});
  out.push({t:"Play Simon", sub:"Arcade", img:"/pack/3d/joystick.png", run:() => api("start_game", {name:"simon"})});
  out.push({t:"Play Reaction", sub:"Arcade", img:"/pack/3d/high_voltage.png", run:() => api("start_game", {name:"reaction"})});
  out.push({t:"Toggle heatmap", sub:"Show most pressed keys", img:"/pack/3d/fire.png", run:() => { heat = !heat; paintHeat(); }});
  S.library.forEach(x => out.push({t:x.name, sub:`Test now: ${describe(x.action)}`, img:src(x.icon), run:() => api("test_action", {action:x.action})}));
  return out;
}
function openPal() { $("#pal").hidden = false; $("#palIn").value = ""; palSel = 0; renderPal(); $("#palIn").focus(); }
function closePal() { $("#pal").hidden = true; }
function renderPal() {
  const q = $("#palIn").value.trim().toLowerCase();
  const all = palSource();
  palItems = (q ? all.filter(x => (x.t + " " + x.sub).toLowerCase().includes(q)) : all.slice(0, 14)).slice(0, 40);
  palSel = Math.min(palSel, Math.max(0, palItems.length - 1));
  $("#palList").innerHTML = palItems.map((x, i) => `<button class="pal-item ${i === palSel ? "on" : ""}" data-i="${i}">
      ${x.img ? `<img src="${x.img}" alt="">` : `<span class="em">${esc(x.em || "")}</span>`}<b>${esc(x.t)}</b><small>${esc(x.sub)}</small></button>`).join("")
    || `<p class="muted" style="padding:12px">Nothing matches.</p>`;
  $$(".pal-item").forEach(b => { b.onclick = () => runPal(+b.dataset.i); b.onmousemove = () => { if (palSel !== +b.dataset.i) { palSel = +b.dataset.i; $$(".pal-item").forEach((x, i) => x.classList.toggle("on", i === palSel)); } }; });
}
function runPal(i) { const x = palItems[i]; closePal(); if (x) x.run(); }

/* ================= library ================= */
function openLib(cb) { libCb = cb; $("#lib").hidden = false; $("#libSearch").value = ""; renderLib(); $("#libSearch").focus(); }
function closeLib() { $("#lib").hidden = true; libCb = null; }
function renderLib() {
  const cats = ["All", ...new Set(S.library.map(x => x.cat))];
  $("#libCats").innerHTML = cats.map(c => `<button class="${c === libCat ? "on" : ""}" data-c="${c}">${c}</button>`).join("");
  $$("#libCats button").forEach(b => b.onclick = () => { libCat = b.dataset.c; renderLib(); });
  const q = $("#libSearch").value.trim().toLowerCase();
  const items = S.library.filter(x => (libCat === "All" || x.cat === libCat) &&
    (!q || x.name.toLowerCase().includes(q) || String(x.action.value).toLowerCase().includes(q) || x.cat.toLowerCase().includes(q)));
  $("#libGrid").innerHTML = items.map(x => {
    const extra = [x.double && "double tap", x.hold && "hold", x.live && "live"].filter(Boolean).join(", ");
    return `<button class="li" data-id="${x.id}"><span class="e"><img src="${src(x.icon)}" alt="" style="width:40px;height:40px"></span>
      <span><b>${esc(x.name)}</b><small>${esc(describe(x.action))}${extra ? " + " + extra : ""}</small></span></button>`;
  }).join("") || `<p class="muted">Nothing matches. Try another word, or set it up by hand with Open or Shortcut.</p>`;
  $$("#libGrid .li").forEach(b => b.onclick = () => { const item = S.library.find(x => x.id === b.dataset.id); const cb = libCb; closeLib(); cb && cb(item); });
}

/* ================= live events ================= */
function tick(what, name) {
  const t = $("#ticker");
  t.innerHTML = `<b>${esc(what)}</b>${name ? `<span>${esc(name)}</span>` : ""}`;
  t.classList.remove("ping"); void t.offsetWidth; t.classList.add("ping");
}
function renderVitals(v) {
  const p = page(), live = [0,1,2,3,4,5].filter(i => p.keys[i].live);
  if (!live.length) { $("#vitals").innerHTML = ""; return; }
  $("#vitals").innerHTML = live.map(i => {
    const k = p.keys[i];
    return `<div class="vital"><span>${esc(k.label || k.live)}</span><b>${esc((v && v[k.live]) || "--")}</b></div>`;
  }).join("");
}
let hudT;
function showHud(ev) {
  const h = $("#hud");
  $("img", h).src = "/" + ev.icon; $("b", h).textContent = ev.title; $("small", h).textContent = ev.text || "";
  $(".bar", h).style.display = ev.frac == null ? "none" : "";
  $(".bar i", h).style.width = Math.round((ev.frac || 0) * 100) + "%";
  h.classList.add("show"); clearTimeout(hudT); hudT = setTimeout(() => h.classList.remove("show"), 1600);
}
function showGame(name) {
  $("#gamebar").hidden = !name;
  if (name) $("#gameTxt").textContent = `Playing ${name === "simon" ? "Simon" : "Reaction"} on your deck. Any round button quits.`;
}
async function refresh() {
  const s = await api("state"); S = s; render();
}
function listen() {
  const es = new EventSource("/events?token=" + TOKEN);
  es.onmessage = e => {
    const ev = JSON.parse(e.data);
    if (ev.t === "status") { setStatus(ev.connected, ev.state); if (tab === "settings") renderHealth(); }
    else if (ev.t === "reload") location.reload();
    else if (ev.t === "refresh") refresh();
    else if (ev.t === "toast") toast(ev.msg, ev.err);
    else if (ev.t === "hud") showHud(ev);
    else if (ev.t === "game") showGame(ev.on ? ev.name : "");
    else if (ev.t === "ai") toast(ev.text, false, `${ev.mode} done. Copied to clipboard.`, 9000);
    else if (ev.t === "mode") { S.cfg.knobs[ev.idx].mode = (S.cfg.knobs[ev.idx].modes || []).indexOf(ev.mode); paintDevice(); }
    else if (ev.t === "auto") {
      if (ev.page !== cur()) { flushAll(); S.cfg.current_page = ev.page; render(true); }
      toast(ev.back ? `Back to ${page().name}` : `${S.cfg.pages[ev.page].name} page opened for ${ev.app.replace(".exe", "")}`);
    }
    else if (ev.t === "live") {
      if (ev.page !== cur() || !S.previews[ev.page]) return;
      for (const [i, url] of Object.entries(ev.previews)) {
        S.previews[ev.page][+i] = url; setKeyImg(+i, url);
        if (tab === "edit" && sel.kind === "key" && sel.idx === +i && $("#heroImg")) $("#heroImg").src = url;
      }
      if (ev.vitals) renderVitals(ev.vitals);
    }
    else if (ev.t === "page") { if (ev.page !== cur()) { flushAll(); S.cfg.current_page = ev.page; iconTab = null; render(true); } }
    else if (ev.t === "press") {
      const g = ev.gesture && ev.gesture !== "tap" ? ` ${ev.gesture === "double" ? "double tap" : "hold"}` : "";
      const pr = S.cfg.stats = S.cfg.stats || {presses:{}}; pr.presses = pr.presses || {};
      const key = ev.kind === "key" ? `p${cur()}:k${ev.idx}` : ev.kind === "button" ? `b${ev.idx}` : `n${ev.idx}`;
      pr.presses[key] = (pr.presses[key] || 0) + 1;
      if (ev.kind === "key") { pulse($$(".key")[ev.idx]); tick(`Key ${ev.idx + 1}${g}`, ev.name); }
      if (ev.kind === "button") { pulse($$(".rbtn")[ev.idx]); tick(`Button ${ev.idx + 1}${g}`, ev.name); }
      if (ev.kind === "knob") { pulse($(`.knob[data-k="${ev.idx}"]`)); tick(`${KNOB_NAMES[ev.idx]}${g || " pressed"}`, ev.name); }
      if (heat) paintHeat();
    } else if (ev.t === "turn") {
      rot[ev.idx] += ev.delta * 18;
      const pr = S.cfg.stats = S.cfg.stats || {presses:{}}; pr.presses = pr.presses || {};
      pr.presses[`t${ev.idx}`] = (pr.presses[`t${ev.idx}`] || 0) + 1;
      $(`.knob[data-k="${ev.idx}"] .cap`).style.setProperty("--rot", rot[ev.idx] + "deg");
      tick(`${KNOB_NAMES[ev.idx]} ${ev.delta > 0 ? "↻" : "↺"}`, ev.name);
    }
  };
}

/* ================= static bindings ================= */
function bindStatic() {
  $$(".key").forEach(el => {
    const i = +el.dataset.i;
    el.onclick = () => select("key", i);
    el.ondragover = e => { e.preventDefault(); el.classList.add("drag"); };
    el.ondragleave = () => el.classList.remove("drag");
    el.ondrop = async e => {
      e.preventDefault(); el.classList.remove("drag");
      const f = e.dataTransfer.files[0];
      if (!f || !f.type.startsWith("image/")) return;
      sel = {kind:"key", idx:i}; iconTab = "image";
      queueKey(i, {icon:await upload(f), live:""});
      setTab("edit"); paintDevice(); toast(`Icon set on Key ${i + 1}`);
    };
  });
  $$(".rbtn").forEach(el => el.onclick = () => select("button", +el.dataset.i));
  $$(".knob").forEach(el => el.onclick = () => select("knob", +el.dataset.k));
  $$("#tabs button").forEach(b => b.onclick = () => setTab(b.dataset.tab));
  $("#heatBtn").onclick = () => { heat = !heat; paintHeat(); };
  $("#quitGame").onclick = () => api("stop_game");
  $("#libClose").onclick = closeLib;
  $("#lib").onclick = e => { if (e.target.id === "lib") closeLib(); };
  $("#libSearch").oninput = renderLib;
  const openAbout = () => $("#about").hidden = false;
  $("#brand").onclick = openAbout; $("#sig").onclick = openAbout;
  $("#aClose").onclick = () => $("#about").hidden = true;
  $("#about").onclick = e => { if (e.target.id === "about") $("#about").hidden = true; };
  $$("#about a").forEach(a => a.onclick = () => api("open_url", {url:a.dataset.u}));
  addEventListener("keydown", e => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); $("#pal").hidden ? openPal() : closePal(); return; }
    if (!$("#pal").hidden) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); palSel = (palSel + (e.key === "ArrowDown" ? 1 : -1) + palItems.length) % Math.max(1, palItems.length); renderPal(); $(".pal-item.on")?.scrollIntoView({block:"nearest"}); }
      if (e.key === "Enter") { e.preventDefault(); runPal(palSel); }
    }
    if (e.key === "Escape") { if (!$("#lib").hidden) closeLib(); $("#about").hidden = true; closePal(); }
  });
  $("#cmdBtn").onclick = openPal;
  $("#palIn").oninput = () => { palSel = 0; renderPal(); };
  $("#pal").onclick = e => { if (e.target.id === "pal") closePal(); };
  $("#status").onclick = () => { if (!$("#status").classList.contains("on")) { api("reconnect"); toast("Looking for your deck"); } else { setTab("settings"); } };
  $("#importFile").onchange = async e => {
    const f = e.target.files[0]; if (!f) return;
    try {
      const cfg = JSON.parse(await f.text());
      if (!confirm("Replace your current setup with this file? A backup of the current one is kept.")) return;
      const r = await api("import_config", {cfg});
      if (r.error) toast(r.error, true);
    } catch (err) { toast("That file could not be read.", true); }
    e.target.value = "";
  };
}

boot();
