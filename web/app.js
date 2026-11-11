"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtTime = (s) => { s = Math.max(0, Math.round(s || 0)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
const state = { status: null, settings: null, albums: [], personas: [], voices: null, jobs: {}, draft: JSON.parse(localStorage.getItem("mx_draft") || "{}") };

async function api(path, opts = {}) {
  const o = { ...opts, headers: { ...(opts.headers || {}) } };
  if (o.body && !(o.body instanceof FormData)) { o.headers["Content-Type"] = "application/json"; o.body = JSON.stringify(o.body); }
  const r = await fetch(path, o);
  const ct = r.headers.get("content-type") || "";
  const data = ct.includes("json") ? await r.json() : await r.text();
  if (!r.ok) throw new Error((data && data.detail) ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : r.statusText);
  return data;
}
function toast(msg, ms = 2600) { const t = $("#toast"); t.textContent = msg; t.classList.add("show"); clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("show"), ms); }
async function busy(btn, fn) { const old = btn.innerHTML; btn.disabled = true; btn.innerHTML = "Working…"; try { return await fn(); } catch (e) { toast(e.message, 5000); } finally { btn.disabled = false; btn.innerHTML = old; } }
async function upload(file) { const fd = new FormData(); fd.append("file", file); return api("/api/uploads", { method: "POST", body: fd }); }
function h(html) { const d = document.createElement("div"); d.innerHTML = html.trim(); return d.firstElementChild; }
function openModal(html) { $("#modal-body").innerHTML = html; $("#modal").classList.remove("hidden"); return $("#modal-body"); }
function closeModal() { $("#modal").classList.add("hidden"); $("#modal-body").innerHTML = ""; }
$("#modal-x").onclick = closeModal;
$("#modal").onclick = (e) => { if (e.target.id === "modal") closeModal(); };

// ------------------------------------------------------------ player
function play(t) {
  const a = $("#pl-audio");
  $("#player").classList.remove("hidden");
  $("#pl-cover").src = t.cover_url; $("#pl-title").textContent = t.title; $("#pl-style").textContent = t.style || "";
  a.src = t.audio_url; a.play().catch(() => {});
}

// ------------------------------------------------------------ status & jobs
async function refreshStatus() {
  try {
    state.status = await api("/api/status");
    const s = state.status, eng = s.music_engine, llmOn = s.llm.provider && s.llm.provider !== "offline";
    const music = eng === "mock" ? `<span class="dot mid"></span>Music: demo synth` : `<span class="dot ${s.acestep.online ? "on" : ""}"></span>Music: ACE-Step ${s.acestep.online ? "online" : "offline"}`;
    $("#engine-status").innerHTML = `<div>${music}</div>
      <div><span class="dot ${llmOn ? "on" : "mid"}"></span>Writer: ${llmOn ? esc(s.llm.provider + " · " + (s.llm.model || "")) : "offline templates"}</div>
      <div><span class="dot ${s.tts ? "on" : ""}"></span>Speech: ${s.tts ? "Kokoro" : "not installed"}</div>
      <div><span class="dot ${s.demucs ? "on" : ""}"></span>Stems: ${s.demucs ? "Demucs" : "not installed"}</div>`;
  } catch (e) { $("#engine-status").textContent = "Server unreachable"; }
}
function trackJob(job) { state.jobs[job.id] = job; renderJobs(); pollJobs(); }
let polling = false;
async function pollJobs() {
  if (polling) return; polling = true;
  while (Object.values(state.jobs).some((j) => j.status === "queued" || j.status === "running")) {
    await new Promise((r) => setTimeout(r, 1200));
    for (const j of Object.values(state.jobs)) {
      if (j.status !== "queued" && j.status !== "running") continue;
      try {
        const n = await api(`/api/jobs/${j.id}`);
        state.jobs[j.id] = n;
        if (n.status === "succeeded") { toast(`Done: ${n.label}`); onJobDone(n); }
        if (n.status === "failed") toast(`Failed: ${n.error}`, 6000);
      } catch (e) { j.status = "failed"; j.error = e.message; }
    }
    renderJobs();
  }
  polling = false;
}
function onJobDone(job) {
  const r = location.hash.split("/")[1] || "create";
  if (job.kind === "persona") loadMeta().then(() => { refreshTrackLists(); const sel = $("#persona_id"); if (sel) { sel.innerHTML = personaOptions(job.result && job.result.persona_id); sel.dispatchEvent(new Event("input")); } });
  if (["library", "create", "speech"].includes(r)) refreshTrackLists();
  if (job.kind === "video" && job.result && job.result.video) { window.open(job.result.video, "_blank"); }
}
function renderJobs() {
  const list = Object.values(state.jobs).sort((a, b) => b.created_at - a.created_at).slice(0, 30);
  $("#jobs").innerHTML = list.length ? list.map((j) => `<div class="job ${j.status}"><b>${esc(j.label)}</b><div class="muted">${esc(j.status)} · ${esc(j.message || "")}</div>
    ${j.status === "running" || j.status === "queued" ? `<div class="bar"><i style="width:${Math.round((j.progress || 0) * 100)}%"></i></div>` : ""}
    ${j.error ? `<div class="err">${esc(j.error)}</div>` : ""}</div>`).join("") : `<div class="muted small">Generations and edits show up here.</div>`;
}
async function loadJobs() { for (const j of await api("/api/jobs")) state.jobs[j.id] = j; renderJobs(); pollJobs(); }

// ------------------------------------------------------------ shared lists
async function loadMeta() {
  [state.albums, state.personas] = await Promise.all([api("/api/albums"), api("/api/personas")]);
}
const albumOptions = (sel = "") => `<option value="">No album</option>` + state.albums.map((a) => `<option value="${a.id}" ${a.id === sel ? "selected" : ""}>${esc(a.name)}</option>`).join("");
const personaOptions = (sel = "") => `<option value="">No persona</option>` + state.personas.map((p) => `<option value="${p.id}" ${p.id === sel ? "selected" : ""}>${esc(p.name)}</option>`).join("");
function trackCard(t) {
  const el = h(`<div class="track"><img src="${t.cover_url}" loading="lazy" alt=""><span class="badge">${esc(t.kind)} · ${fmtTime(t.duration)}</span>
    <button class="play" title="Play">▶</button><div class="info"><b>${t.favorite ? "★ " : ""}${esc(t.title)}</b><small>${esc(t.style || "")}</small></div></div>`);
  el.querySelector(".play").onclick = (e) => { e.stopPropagation(); play(t); };
  el.onclick = () => openTrack(t.id);
  return el;
}
let trackListRefreshers = [];
function refreshTrackLists() { trackListRefreshers.forEach((f) => f()); }

// ------------------------------------------------------------ CREATE
function viewCreate(root) {
  const d = Object.assign({ mode: "custom", instrumental: false, vocal_gender: "auto", weirdness: 50, style_influence: 50, duration: "", style: "", lyrics: "", title: "", description: "", negative: "" }, state.draft);
  const save = () => { localStorage.setItem("mx_draft", JSON.stringify(d)); state.draft = d; };
  root.innerHTML = `<h1>Create</h1><p>Describe a song or write your own lyrics. Every Pro option is available locally.</p>
  ${state.status && state.status.music_engine === "acestep" && !state.status.acestep.online ? `<div class="notice">ACE-Step isn't reachable at ${esc(state.status.acestep.url)}. Start it from the Pinokio launcher (or <code>uv run acestep-api</code>), or switch to the demo synth in <a href="#/settings">Settings</a>.</div>` : ""}
  <div class="grid2"><div>
   <div class="card">
    <div class="row between"><div class="seg" id="mode"><button data-v="simple">Simple</button><button data-v="custom">Custom</button></div>
      <label class="toggle"><input type="checkbox" id="instrumental"> Instrumental</label></div>
    <div id="simple-box"><label>Song description</label><textarea id="description" maxlength="500" placeholder="An upbeat summer pop song about road trips with friends"></textarea><div class="counter"><span id="desc-c">0</span>/500</div></div>
    <div id="custom-box">
      <div class="row between"><label>Lyrics</label><div class="row"><button class="small" id="write-lyrics">Write lyrics with AI</button><button class="small" id="open-studio">Open in Lyric Studio</button></div></div>
      <textarea id="lyrics" class="lyrics" maxlength="5000" placeholder="[Verse]\n...\n\n[Chorus]\n..."></textarea><div class="counter"><span id="lyr-c">0</span>/5000</div>
    </div>
    <div class="row between"><label>Style of music</label><div class="row"><button class="small" id="enhance">Enhance</button><button class="small" id="random">Random</button><a class="btn small" href="#/style">Style generator</a></div></div>
    <textarea id="style" maxlength="1000" style="min-height:64px" placeholder="dreamy synthwave, female vocals, 100 bpm, lush pads"></textarea>
    <label>Title</label><input type="text" id="title" maxlength="80" placeholder="Leave blank to auto-name">
   </div>
   <div class="card"><h3>Advanced <span class="tag pro">Pro</span></h3>
    <label>Vocal gender</label><div class="seg" id="vocal"><button data-v="auto">Auto</button><button data-v="female">Female</button><button data-v="male">Male</button></div>
    <label>Weirdness: <b id="w-v"></b></label><input type="range" id="weirdness" min="0" max="100">
    <label>Style influence: <b id="si-v"></b></label><input type="range" id="style_influence" min="0" max="100">
    <label>Exclude styles</label><input type="text" id="negative" placeholder="e.g. heavy metal, autotune">
    <label>Duration (seconds, up to 600 / 10 min - blank = auto)</label><input type="number" id="duration" min="10" max="600" step="5">
    <details><summary>Music theory, voice & model</summary>
     <div class="row"><div style="flex:1"><label>BPM</label><input type="number" id="bpm" min="30" max="300"></div><div style="flex:1"><label>Key</label><input type="text" id="key" placeholder="C major"></div><div style="flex:1"><label>Time sig.</label><select id="time_signature"><option value="">Auto</option><option>4</option><option>3</option><option>2</option><option>6</option></select></div></div>
     <div class="row"><div style="flex:1"><label>Vocal language</label><select id="language">${["en","es","fr","de","it","pt","ja","ko","zh","ru","hi","ar","nl","sv","pl","tr","vi","id","th"].map((l)=>`<option>${l}</option>`).join("")}</select></div>
     <div style="flex:1"><label>Versions</label><select id="batch_size"><option value="">Default</option><option>1</option><option>2</option><option>3</option><option>4</option></select></div>
     <div style="flex:1"><label>Seed</label><input type="number" id="seed" placeholder="random"></div></div>
     <div class="row between"><label>Persona</label><button class="small" id="new-persona-c">+ New persona from audio</button></div><select id="persona_id">${personaOptions(d.persona_id)}</select>
     <label>Add to album</label><select id="album_id">${albumOptions(d.album_id)}</select>
     <label>Voice / style reference audio <span class="tag pro">Upload Voice</span></label><input type="file" id="voice" accept="audio/*"><div class="small muted" id="voice-info"></div>
     <label>Model</label><select id="model"><option value="">Server default</option>${Object.values((state.status && state.status.acestep.models) || {}).flat().map((m)=>`<option>${esc(m.name || m)}</option>`).join("")}</select>
    </details>
   </div>
   <button class="primary" id="go" style="width:100%">Create</button>
  </div>
  <div><div class="card"><div class="row between"><h3>Recent creations</h3><a class="btn small" href="#/library">Library</a></div><div class="tracks" id="recent"></div></div></div></div>`;
  const fields = ["description", "lyrics", "style", "title", "negative", "duration", "bpm", "key", "time_signature", "language", "batch_size", "seed", "persona_id", "album_id", "model", "weirdness", "style_influence"];
  fields.forEach((f) => { const el = $("#" + f, root); if (d[f] !== undefined && d[f] !== null) el.value = d[f]; el.oninput = () => { d[f] = el.value; save(); counters(); }; });
  const counters = () => { $("#desc-c").textContent = $("#description").value.length; $("#lyr-c").textContent = $("#lyrics").value.length; $("#w-v").textContent = $("#weirdness").value + "%"; $("#si-v").textContent = $("#style_influence").value + "%"; };
  const seg = (id, key) => { $$(`#${id} button`, root).forEach((b) => { b.classList.toggle("on", b.dataset.v === d[key]); b.onclick = () => { d[key] = b.dataset.v; save(); seg(id, key); sync(); }; }); };
  const sync = () => { $("#simple-box").classList.toggle("hidden", d.mode !== "simple"); $("#custom-box").classList.toggle("hidden", d.mode !== "custom" || d.instrumental); $("#vocal").parentElement; };
  $("#instrumental").checked = !!d.instrumental; $("#instrumental").onchange = (e) => { d.instrumental = e.target.checked; save(); sync(); };
  seg("mode", "mode"); seg("vocal", "vocal_gender"); sync(); counters();
  let voiceUpload = null;
  $("#voice").onchange = async (e) => { const f = e.target.files[0]; if (!f) return; $("#voice-info").textContent = "Uploading…"; try { voiceUpload = await upload(f); $("#voice-info").textContent = `${f.name} · ${fmtTime(voiceUpload.duration)} - the song will follow this voice/style`; } catch (er) { $("#voice-info").textContent = er.message; } };
  $("#enhance").onclick = (e) => busy(e.target, async () => { const r = await api("/api/write/enhance-style", { method: "POST", body: { style: $("#style").value } }); $("#style").value = d.style = r.style; save(); });
  $("#random").onclick = (e) => busy(e.target, async () => { const r = await api("/api/write/random-style"); $("#style").value = d.style = r.style; save(); });
  $("#write-lyrics").onclick = (e) => busy(e.target, async () => {
    const idea = prompt("What should the song be about?", d.title || d.description || ""); if (!idea) return;
    const r = await api("/api/write/song", { method: "POST", body: { description: idea, style: $("#style").value } });
    $("#lyrics").value = d.lyrics = r.lyrics; if (!$("#style").value) $("#style").value = d.style = r.style; if (!$("#title").value) $("#title").value = d.title = r.title; save(); counters();
  });
  $("#new-persona-c").onclick = () => personaDialog();
  $("#open-studio").onclick = () => { localStorage.setItem("mx_studio_import", $("#lyrics").value); location.hash = "#/studio"; };
  $("#go").onclick = (e) => busy(e.target, async () => {
    const body = { ...d, voice_upload_id: voiceUpload && voiceUpload.id };
    ["weirdness", "style_influence"].forEach((k) => (body[k] = Number(body[k])));
    trackJob(await api("/api/generate", { method: "POST", body }));
    toast("Generation queued");
  });
  const loadRecent = async () => { const box = $("#recent"); if (!box) return; const ts = (await api("/api/tracks")).slice(0, 12); box.replaceChildren(...ts.map(trackCard)); if (!ts.length) box.innerHTML = `<div class="muted small">Nothing yet - create your first song.</div>`; };
  trackListRefreshers = [loadRecent]; loadRecent();
}

// ------------------------------------------------------------ LIBRARY
function viewLibrary(root) {
  const f = { q: "", kind: "", album_id: "", favorite: false, persona_id: "" };
  root.innerHTML = `<h1>Library</h1><p>All your songs, remixes, stems and spoken tracks - stored locally in <code>data/</code>.</p>
  <div class="filters"><input type="text" id="q" placeholder="Search title, style, lyrics"><select id="kind"><option value="">All types</option>${["song","upload","cover","refine","repaint","extend","add_vocals","add_instrumental","stem","fade","speech"].map((k)=>`<option>${k}</option>`).join("")}</select>
  <select id="album">${albumOptions()}</select><select id="persona">${personaOptions()}</select><label class="toggle"><input type="checkbox" id="fav"> Favorites</label>
  <label class="btn" style="margin:0">Upload song<input type="file" id="up" accept="audio/*" hidden multiple></label></div>
  <div class="grid2" style="grid-template-columns:1fr 260px"><div class="tracks" id="lib"></div>
  <div><div class="card"><div class="row between"><h3>Albums</h3><button class="small" id="new-album">+ New</button></div><div id="albums"></div></div>
  <div class="card"><div class="row between"><h3>Personas</h3><button class="small" id="new-persona">+ New</button></div><div id="personas"></div><div class="small muted">A persona saves a vocal style + reference voice you can reuse in Create.</div></div></div></div>`;
  $("#album", root).firstElementChild.textContent = "All albums"; $("#persona", root).firstElementChild.textContent = "All personas";
  const load = async () => {
    const qs = new URLSearchParams({ q: f.q, kind: f.kind, album_id: f.album_id, persona_id: f.persona_id, favorite: f.favorite });
    const ts = await api("/api/tracks?" + qs); const box = $("#lib"); if (!box) return;
    box.replaceChildren(...ts.map(trackCard)); if (!ts.length) box.innerHTML = `<div class="muted">No tracks found.</div>`;
  };
  const side = async () => {
    await loadMeta();
    $("#albums").innerHTML = state.albums.map((a) => `<div class="list-row" data-a="${a.id}"><div style="flex:1"><b>${esc(a.name)}</b><div class="small muted">${a.count} tracks</div></div><button class="small" data-del="${a.id}">✕</button></div>`).join("") || `<div class="small muted">No albums yet.</div>`;
    $$("#albums [data-a]").forEach((r) => (r.onclick = (e) => { if (e.target.dataset.del) return; f.album_id = r.dataset.a; $("#album").innerHTML = albumOptions(f.album_id).replace("No album", "All albums"); load(); }));
    $$("#albums [data-del]").forEach((b) => (b.onclick = async () => { if (confirm("Delete album? Tracks are kept.")) { await api(`/api/albums/${b.dataset.del}`, { method: "DELETE" }); side(); } }));
    $("#personas").innerHTML = state.personas.map((p) => `<div class="list-row"><div style="flex:1;min-width:0"><b>${esc(p.name)}</b><div class="small muted">${esc(p.vocal_gender)} · ${p.has_voice ? "voice clip" : "style only"}</div></div>${p.has_voice ? `<button class="small" data-pplay="${p.id}" title="Play voice clip">▶</button>` : ""}<button class="small" data-puse="${p.id}" title="Use in Create">Use</button><button class="small" data-pdel="${p.id}">✕</button></div>`).join("") || `<div class="small muted">No personas yet.</div>`;
    $$("#personas [data-pplay]").forEach((b) => (b.onclick = () => { const p = state.personas.find((x) => x.id === b.dataset.pplay); play({ title: `Persona: ${p.name}`, style: p.style, cover_url: "/static/persona.svg", audio_url: `/api/personas/${p.id}/voice` }); }));
    $$("#personas [data-puse]").forEach((b) => (b.onclick = () => { state.draft.persona_id = b.dataset.puse; localStorage.setItem("mx_draft", JSON.stringify(state.draft)); location.hash = "#/create"; }));
    $$("#personas [data-pdel]").forEach((b) => (b.onclick = async () => { await api(`/api/personas/${b.dataset.pdel}`, { method: "DELETE" }); side(); }));
  };
  $("#q").oninput = (e) => { f.q = e.target.value; clearTimeout(f._t); f._t = setTimeout(load, 250); };
  $("#kind").onchange = (e) => { f.kind = e.target.value; load(); };
  $("#album").onchange = (e) => { f.album_id = e.target.value; load(); };
  $("#persona").onchange = (e) => { f.persona_id = e.target.value; load(); };
  $("#fav").onchange = (e) => { f.favorite = e.target.checked; load(); };
  $("#up").onchange = async (e) => { for (const file of e.target.files) { const fd = new FormData(); fd.append("file", file); fd.append("title", file.name.replace(/\.[^.]+$/, "")); try { await api("/api/library/upload", { method: "POST", body: fd }); toast(`Uploaded ${file.name}`); } catch (er) { toast(er.message, 5000); } } load(); };
  $("#new-album").onclick = async () => { const name = prompt("Album name"); if (name) { await api("/api/albums", { method: "POST", body: { name } }); side(); } };
  $("#new-persona").onclick = () => personaDialog();
  trackListRefreshers = [load, side]; load(); side();
}
async function personaDialog(track) {
  const tracks = (await api("/api/tracks")).filter((x) => x.duration >= 3);
  const m = openModal(`<h3>New persona</h3>
   <div class="row"><div style="flex:2"><label>Name</label><input type="text" id="p-name" value="${esc(track ? track.title : "")}"></div>
   <div style="flex:1"><label>Vocal gender</label><select id="p-g"><option>auto</option><option>female</option><option>male</option></select></div></div>
   <label>Vocal style / genre</label><input type="text" id="p-style" value="${esc(track ? track.style : "")}" placeholder="raspy soulful alto, gospel runs">
   <label>Voice source</label><div class="seg" id="p-src"><button data-v="upload">Upload audio</button><button data-v="record">Record mic</button><button data-v="track">From library</button><button data-v="none">Style only</button></div>
   <div id="p-upload" class="p-pane" style="margin-top:10px"><input type="file" id="p-file" accept="audio/*,video/mp4,video/webm"><div class="small muted">MP3, WAV, FLAC, M4A, OGG, WEBM or MP4. 10-60 seconds of clear singing works best.</div></div>
   <div id="p-record" class="p-pane" style="margin-top:10px"><div class="row"><button id="p-rec">● Start recording</button><span id="p-rec-t" class="muted">0:00</span></div><div class="small muted">Sing or speak for at least 10 seconds. Your browser will ask for microphone access.</div></div>
   <div id="p-track" class="p-pane" style="margin-top:10px"><select id="p-tsel"><option value="">Choose a track…</option>${tracks.map((x) => `<option value="${x.id}" ${track && track.id === x.id ? "selected" : ""}>${esc(x.title)} (${fmtTime(x.duration)})</option>`).join("")}</select></div>
   <div id="p-clip" class="hidden"><label>Preview</label><audio id="p-audio" controls style="width:100%"></audio>
    <div class="row"><div style="flex:1"><label>Start (s)</label><input type="number" id="p-start" min="0" step="0.5" value="0"></div><div style="flex:1"><label>End (s)</label><input type="number" id="p-end" min="0" step="0.5"></div></div>
    <div class="row" style="margin-top:6px"><button class="small" id="p-set-s">Set start = playhead</button><button class="small" id="p-set-e">Set end = playhead</button><span class="small muted" id="p-len"></span></div>
    <label class="toggle" style="margin-top:10px"><input type="checkbox" id="p-iso"> Isolate vocals with Demucs (removes the music behind the voice)</label></div>
   <label>Notes</label><input type="text" id="p-notes" placeholder="optional">
   <div class="row" style="margin-top:14px"><button class="primary" id="p-save">Save persona</button><span class="small muted" id="p-msg"></span></div>`);
  let src = track ? "track" : "upload", uploadId = null, recorder = null, chunks = [], timer = null;
  const au = $("#p-audio", m), clip = $("#p-clip", m);
  const showClip = (url, dur, isolate) => { au.src = url; clip.classList.remove("hidden"); $("#p-start", m).value = 0; $("#p-end", m).value = dur ? dur.toFixed(1) : ""; $("#p-iso", m).checked = isolate; lenInfo(); };
  const lenInfo = () => { const a = +$("#p-start", m).value || 0, b = +$("#p-end", m).value || 0; $("#p-len", m).textContent = b ? `Clip length ${fmtTime(b - a)}${b - a < 3 ? " (too short)" : ""}` : ""; };
  ["#p-start", "#p-end"].forEach((k) => ($(k, m).oninput = lenInfo));
  $("#p-set-s", m).onclick = () => { $("#p-start", m).value = au.currentTime.toFixed(1); lenInfo(); };
  $("#p-set-e", m).onclick = () => { $("#p-end", m).value = au.currentTime.toFixed(1); lenInfo(); };
  const setSrc = (v) => {
    src = v; uploadId = null; clip.classList.add("hidden");
    $$("#p-src button", m).forEach((b) => b.classList.toggle("on", b.dataset.v === v));
    ["upload", "record", "track"].forEach((k) => $("#p-" + k, m).classList.toggle("hidden", k !== v));
    if (v === "track" && $("#p-tsel", m).value) $("#p-tsel", m).onchange();
  };
  $$("#p-src button", m).forEach((b) => (b.onclick = () => setSrc(b.dataset.v)));
  $("#p-file", m).onchange = async (e) => {
    const f = e.target.files[0]; if (!f) return; $("#p-msg", m).textContent = "Uploading…";
    try { const up = await upload(f); uploadId = up.id; showClip(up.url, up.duration, true); $("#p-msg", m).textContent = ""; if (!$("#p-name", m).value) $("#p-name", m).value = f.name.replace(/\.[^.]+$/, ""); }
    catch (er) { $("#p-msg", m).textContent = er.message; }
  };
  $("#p-tsel", m).onchange = () => { const t = tracks.find((x) => x.id === $("#p-tsel", m).value); if (!t) return clip.classList.add("hidden"); showClip(t.audio_url, t.duration, !["stem", "speech"].includes(t.kind)); if (!$("#p-name", m).value) $("#p-name", m).value = t.title; if (!$("#p-style", m).value) $("#p-style", m).value = t.style || ""; };
  $("#p-rec", m).onclick = async (e) => {
    const btn = e.target;
    if (recorder && recorder.state === "recording") { recorder.stop(); return; }
    if (!navigator.mediaDevices || !window.MediaRecorder) return toast("This browser can't record audio here. Use Upload instead.", 5000);
    let stream; try { stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false } }); } catch (er) { return toast("Microphone blocked: " + er.message, 5000); }
    chunks = []; recorder = new MediaRecorder(stream); const t0 = Date.now();
    recorder.ondataavailable = (ev) => ev.data.size && chunks.push(ev.data);
    recorder.onstop = async () => {
      clearInterval(timer); stream.getTracks().forEach((t) => t.stop()); btn.textContent = "● Record again";
      const type = recorder.mimeType || "audio/webm", ext = type.includes("ogg") ? "ogg" : type.includes("mp4") ? "m4a" : "webm";
      $("#p-msg", m).textContent = "Uploading recording…";
      try { const up = await upload(new File(chunks, `recording.${ext}`, { type })); uploadId = up.id; showClip(up.url, up.duration || (Date.now() - t0) / 1000, false); $("#p-msg", m).textContent = ""; }
      catch (er) { $("#p-msg", m).textContent = er.message; }
    };
    recorder.start(250); btn.textContent = "■ Stop recording";
    timer = setInterval(() => ($("#p-rec-t", m).textContent = fmtTime((Date.now() - t0) / 1000)), 250);
  };
  setSrc(src); if (track) $("#p-tsel", m).onchange();
  $("#p-save", m).onclick = (e) => busy(e.target, async () => {
    if (recorder && recorder.state === "recording") throw new Error("Stop the recording first");
    const body = { name: $("#p-name", m).value, style: $("#p-style", m).value, vocal_gender: $("#p-g", m).value, notes: $("#p-notes", m).value };
    if (src === "upload" || src === "record") { if (!uploadId) throw new Error(src === "record" ? "Record your voice first" : "Choose an audio file first"); body.voice_upload_id = uploadId; }
    if (src === "track") { body.track_id = $("#p-tsel", m).value; if (!body.track_id) throw new Error("Choose a track"); }
    if (src !== "none") Object.assign(body, { start: +$("#p-start", m).value || 0, end: $("#p-end", m).value, isolate_vocals: $("#p-iso", m).checked });
    trackJob(await api("/api/personas", { method: "POST", body }));
    closeModal(); toast(body.isolate_vocals ? "Isolating vocals - persona will appear when done" : "Saving persona");
  });
}

// ------------------------------------------------------------ TRACK DETAIL
async function openTrack(id) {
  const t = await api(`/api/tracks/${id}`);
  await loadMeta();
  const m = openModal(`<div class="detail"><div><img src="${t.cover_url}?${Date.now()}" alt=""><label class="btn small" style="margin-top:6px">Change cover<input type="file" id="cv" accept="image/*" hidden></label></div><div>
   <input type="text" id="t-title" value="${esc(t.title)}" style="font-size:18px;font-weight:600">
   <div class="small muted" style="margin:6px 0">${esc(t.kind)} · ${fmtTime(t.duration)} · ${esc(t.engine)} ${t.metas && t.metas.bpm ? "· " + t.metas.bpm + " bpm" : ""} ${t.metas && t.metas.keyscale ? "· " + esc(t.metas.keyscale) : ""}</div>
   <div class="wave" id="wave"><canvas></canvas><div class="sel hidden"></div></div><div class="small muted" id="sel-info">Drag on the waveform to select a section for Repaint / Refine / Add Instrumental.</div>
   <audio id="t-audio" controls src="${t.audio_url}" style="width:100%;margin-top:6px"></audio>
   <div class="row" style="margin-top:8px">
    <button class="small" id="fav">${t.favorite ? "★ Favorited" : "☆ Favorite"}</button>
    ${["mp3","m4a","wav","flac"].map((f)=>`<a class="btn small" href="/api/tracks/${t.id}/download?format=${f}">${f.toUpperCase()}</a>`).join("")}
    ${t.has_video ? `<a class="btn small" href="/api/tracks/${t.id}/download?format=mp4">MP4</a>` : ""}
    <select id="t-album" style="width:auto">${albumOptions(t.album_id)}</select>
    <button class="small" id="mk-persona">Make persona</button>
    <button class="small" id="del" style="color:#fca5a5">Delete</button>
   </div>
   <div class="tabs" id="ops">${[["cover","Cover"],["refine","Smart Refine"],["repaint","Repaint"],["extend","Extend"],["add_vocals","Add Vocals"],["add_instrumental","Add Instrumental"],["fade","Fade in/out"],["stems","Vocal separation"],["video","Music video"],["info","Lyrics & style"]].map(([k,l])=>`<button data-op="${k}">${l}</button>`).join("")}</div>
   <div id="op-body"></div></div></div>`);
  const audioEl = $("#t-audio", m);
  let sel = null;
  const dur = t.duration || 1;
  const wave = $("#wave", m), cv = wave.querySelector("canvas"), selEl = wave.querySelector(".sel");
  api(`/api/tracks/${t.id}/peaks?n=300`).then((pk) => {
    const W = (cv.width = wave.clientWidth * 2), H = (cv.height = 168), c = cv.getContext("2d");
    const g = c.createLinearGradient(0, 0, W, 0); g.addColorStop(0, "#8b5cf6"); g.addColorStop(1, "#ec4899"); c.fillStyle = g;
    pk.forEach((p, i) => { const x = (i / pk.length) * W, hh = Math.max(2, p * H * 0.9); c.fillRect(x, (H - hh) / 2, W / pk.length - 1, hh); });
  });
  const showSel = () => { if (!sel) { selEl.classList.add("hidden"); $("#sel-info", m).textContent = "Drag on the waveform to select a section."; return; } selEl.classList.remove("hidden"); selEl.style.left = (sel[0] / dur) * 100 + "%"; selEl.style.width = ((sel[1] - sel[0]) / dur) * 100 + "%"; $("#sel-info", m).innerHTML = `Selected ${fmtTime(sel[0])} - ${fmtTime(sel[1])} <button class="small" id="clr">Clear</button>`; $("#clr", m).onclick = () => { sel = null; showSel(); }; };
  const posT = (e) => { const r = wave.getBoundingClientRect(); return Math.max(0, Math.min(dur, ((e.clientX - r.left) / r.width) * dur)); };
  wave.onmousedown = (e) => { const a = posT(e); let moved = false; const mv = (ev) => { moved = true; const b = posT(ev); sel = [Math.min(a, b), Math.max(a, b)]; showSel(); }; const up = (ev) => { removeEventListener("mousemove", mv); removeEventListener("mouseup", up); if (!moved || (sel && sel[1] - sel[0] < 0.5)) { sel = null; showSel(); audioEl.currentTime = posT(ev); audioEl.play(); } }; addEventListener("mousemove", mv); addEventListener("mouseup", up); };
  $("#t-title", m).onchange = async (e) => { await api(`/api/tracks/${t.id}`, { method: "PATCH", body: { title: e.target.value } }); refreshTrackLists(); };
  $("#fav", m).onclick = async (e) => { t.favorite = !t.favorite; await api(`/api/tracks/${t.id}`, { method: "PATCH", body: { favorite: t.favorite } }); e.target.textContent = t.favorite ? "★ Favorited" : "☆ Favorite"; refreshTrackLists(); };
  $("#t-album", m).onchange = async (e) => { await api(`/api/tracks/${t.id}`, { method: "PATCH", body: { album_id: e.target.value || null } }); toast("Album updated"); refreshTrackLists(); };
  $("#mk-persona", m).onclick = () => personaDialog(t);
  $("#del", m).onclick = async () => { if (!confirm("Delete this track?")) return; await api(`/api/tracks/${t.id}`, { method: "DELETE" }); closeModal(); refreshTrackLists(); };
  $("#cv", m).onchange = async (e) => { const fd = new FormData(); fd.append("file", e.target.files[0]); await api(`/api/tracks/${t.id}/cover`, { method: "POST", body: fd }); m.querySelector("img").src = t.cover_url + "?" + Date.now(); refreshTrackLists(); };
  const body = $("#op-body", m);
  const submit = async (btn, path, payload) => busy(btn, async () => { trackJob(await api(path, { method: "POST", body: payload })); toast("Queued - see Activity"); });
  const range = () => (sel ? { start: +sel[0].toFixed(2), end: +sel[1].toFixed(2) } : {});
  const ops = {
    cover: () => { body.innerHTML = `<p class="small muted">Re-imagine this track in a new style, keeping its melody and structure.</p><label>New style</label><textarea id="o-style" style="min-height:60px">${esc(t.style)}</textarea><label>Keep original: <b id="o-sv">50%</b></label><input type="range" id="o-s" min="0" max="100" value="50"><label>Lyrics (edit to change words)</label><textarea id="o-lyr" class="lyrics" style="min-height:140px">${esc(t.lyrics)}</textarea><button class="primary" id="o-go">Create cover</button>`; $("#o-s").oninput = (e) => ($("#o-sv").textContent = e.target.value + "%"); $("#o-go").onclick = (e) => submit(e.target, `/api/tracks/${t.id}/remix`, { op: "cover", style: $("#o-style").value, lyrics: $("#o-lyr").value, strength: $("#o-s").value / 100 }); },
    refine: () => { body.innerHTML = `<p class="small muted">Describe the change in plain words. Select a section on the waveform to only change that part.</p><label>Instruction</label><textarea id="o-ins" placeholder="Make the chorus more energetic and add a saxophone solo"></textarea><button class="primary" id="o-go">Smart Refine</button>`; $("#o-go").onclick = (e) => submit(e.target, `/api/tracks/${t.id}/remix`, { op: "refine", instruction: $("#o-ins").value, ...range() }); },
    repaint: () => { body.innerHTML = `<p class="small muted">Regenerate the selected section (or the whole track) with new lyrics/style while keeping the rest.</p><label>Style</label><textarea id="o-style" style="min-height:60px">${esc(t.style)}</textarea><label>Lyrics</label><textarea id="o-lyr" class="lyrics" style="min-height:140px">${esc(t.lyrics)}</textarea><button class="primary" id="o-go">Repaint ${sel ? "selection" : "track"}</button>`; $("#o-go").onclick = (e) => submit(e.target, `/api/tracks/${t.id}/remix`, { op: "repaint", style: $("#o-style").value, lyrics: $("#o-lyr").value, ...range() }); },
    extend: () => { body.innerHTML = `<p class="small muted">Continue the song past its current ending.</p><label>Add seconds</label><input type="number" id="o-x" value="30" min="5" max="240"><label>Lyrics for the new part (optional)</label><textarea id="o-lyr" class="lyrics" style="min-height:120px">${esc(t.lyrics)}</textarea><label>Style</label><input type="text" id="o-style" value="${esc(t.style)}"><button class="primary" id="o-go">Extend</button>`; $("#o-go").onclick = (e) => submit(e.target, `/api/tracks/${t.id}/remix`, { op: "extend", extra: +$("#o-x").value, lyrics: $("#o-lyr").value, style: $("#o-style").value }); },
    add_vocals: () => { body.innerHTML = `<p class="small muted">Sing new vocals over this instrumental (uses the ACE-Step base model).</p><label>Vocal style</label><input type="text" id="o-style" value="${esc(t.style)}"><label>Vocal gender</label><select id="o-g"><option>auto</option><option>female</option><option>male</option></select><label>Lyrics</label><textarea id="o-lyr" class="lyrics" style="min-height:160px">${esc(t.lyrics && t.lyrics !== "[Instrumental]" ? t.lyrics : "")}</textarea><button class="primary" id="o-go">Add vocals</button>`; $("#o-go").onclick = (e) => submit(e.target, `/api/tracks/${t.id}/remix`, { op: "add_vocals", style: $("#o-style").value, vocal_gender: $("#o-g").value, lyrics: $("#o-lyr").value, ...range() }); },
    add_instrumental: () => { const tr = ["drums","bass","guitar","keyboard","strings","synth","brass","woodwinds","percussion","backing_vocals"]; body.innerHTML = `<p class="small muted">Build a backing track around an a cappella / vocal recording.</p><label>Instrument style</label><input type="text" id="o-style" value="${esc(t.style)}"><label>Instruments</label><div class="row">${tr.map((x,i)=>`<label class="toggle"><input type="checkbox" value="${x}" ${i<5?"checked":""}> ${x}</label>`).join("")}</div><button class="primary" id="o-go" style="margin-top:10px">Add instrumental</button>`; $("#o-go").onclick = (e) => submit(e.target, `/api/tracks/${t.id}/remix`, { op: "add_instrumental", style: $("#o-style").value, instruments: $$("#op-body input:checked").map((x) => x.value), ...range() }); },
    fade: () => { body.innerHTML = `<div class="row"><div style="flex:1"><label>Fade in (s)</label><input type="number" id="o-fi" value="2" min="0" max="30" step="0.5"></div><div style="flex:1"><label>Fade out (s)</label><input type="number" id="o-fo" value="4" min="0" max="60" step="0.5"></div><div style="flex:1"><label>Fade out starts at (s, blank = end)</label><input type="number" id="o-fs" step="0.5"></div></div><button class="primary" id="o-go" style="margin-top:10px">Apply fade</button>`; if (sel) $("#o-fs").value = sel[0].toFixed(1); $("#o-go").onclick = (e) => submit(e.target, `/api/tracks/${t.id}/fade`, { fade_in: +$("#o-fi").value, fade_out: +$("#o-fo").value, fade_out_start: $("#o-fs").value }); },
    stems: () => { body.innerHTML = `<p class="small muted">Split the track with Demucs. Results appear as new tracks in your library.</p><div class="seg" id="o-m"><button data-v="two" class="on">Vocals + Instrumental</button><button data-v="four">4 stems (vocals, drums, bass, other)</button></div><div style="margin-top:10px"><button class="primary" id="o-go">Separate</button></div>`; let mode = "two"; $$("#o-m button").forEach((b) => (b.onclick = () => { mode = b.dataset.v; $$("#o-m button").forEach((x) => x.classList.toggle("on", x === b)); })); $("#o-go").onclick = (e) => submit(e.target, `/api/tracks/${t.id}/separate`, { mode }); },
    video: () => { body.innerHTML = `<p class="small muted">Render an MP4 music video: cover art, title and an animated waveform${t.lyrics ? ", plus lyrics" : ""}.</p><label class="toggle"><input type="checkbox" id="o-l" checked> Show lyrics</label><div style="margin-top:10px"><button class="primary" id="o-go">Render MP4</button> ${t.has_video ? `<a class="btn" href="/api/tracks/${t.id}/download?format=mp4">Download existing MP4</a>` : ""}</div>`; $("#o-go").onclick = (e) => submit(e.target, `/api/tracks/${t.id}/video`, { lyrics: $("#o-l").checked }); },
    info: () => { body.innerHTML = `<label>Style</label><textarea id="i-style" style="min-height:60px">${esc(t.style)}</textarea><label>Lyrics</label><textarea id="i-lyr" class="lyrics">${esc(t.lyrics)}</textarea><div class="row"><button id="i-save">Save</button><button id="i-reuse">Reuse in Create</button></div>`; $("#i-save").onclick = async () => { await api(`/api/tracks/${t.id}`, { method: "PATCH", body: { style: $("#i-style").value, lyrics: $("#i-lyr").value } }); toast("Saved"); }; $("#i-reuse").onclick = () => { Object.assign(state.draft, { mode: "custom", style: $("#i-style").value, lyrics: $("#i-lyr").value, title: t.title, instrumental: t.lyrics === "[Instrumental]" }); localStorage.setItem("mx_draft", JSON.stringify(state.draft)); closeModal(); location.hash = "#/create"; route(); }; },
  };
  $$("#ops button", m).forEach((b) => (b.onclick = () => { $$("#ops button", m).forEach((x) => x.classList.toggle("on", x === b)); ops[b.dataset.op](); }));
  $$("#ops button", m)[t.kind === "speech" ? 6 : 0].click();
}

// ------------------------------------------------------------ LYRIC STUDIO
async function viewStudio(root) {
  const docs = await api("/api/lyric-docs");
  let doc = docs[0] || (await api("/api/lyric-docs", { method: "POST", body: { title: "Untitled draft", content: "" } }));
  const imp = localStorage.getItem("mx_studio_import");
  if (imp) { localStorage.removeItem("mx_studio_import"); doc = await api("/api/lyric-docs", { method: "POST", body: { title: "From Create", content: imp } }); }
  const actions = [["opening_lines","Opening lines"],["full_draft","Full draft"],["next_line","Next line"],["continue_section","Continue section"],["rewrite","Rewrite selection"],["add_verse","Add verse"],["add_chorus","Add chorus"],["add_bridge","Add bridge"],["strengthen_hook","Strengthen hook"],["refine_rhyme","Refine rhyme"],["deepen_emotion","Deepen emotion"],["simplify","Simplify"],["title","Suggest titles"]];
  const render = async () => {
    const all = await api("/api/lyric-docs");
    root.innerHTML = `<h1>AI Lyric Studio</h1><p>Write line by line with an AI co-writer. Drafts autosave with version history.</p>
    <div class="grid2" style="grid-template-columns:200px minmax(0,1.3fr) minmax(0,1fr)">
     <div class="card"><div class="row between"><h3>Drafts</h3><button class="small" id="nd">+ New</button></div>${all.map((x) => `<div class="list-row ${x.id === doc.id ? "active" : ""}" data-d="${x.id}" style="${x.id === doc.id ? "background:var(--panel2)" : ""}"><div style="flex:1;min-width:0"><b class="small">${esc(x.title || "Untitled")}</b></div></div>`).join("")}</div>
     <div class="card"><input type="text" id="d-title" value="${esc(doc.title)}"><label>Song idea / theme</label><input type="text" id="d-idea" value="${esc(doc.idea)}" placeholder="What is this song about?">
      <label>Lyrics <span class="small muted" id="saved"></span></label><textarea id="d-content" class="lyrics" style="min-height:420px">${esc(doc.content)}</textarea>
      <div class="row"><button id="snap">Save version</button><select id="hist" style="width:auto"><option value="">History (${(doc.versions || []).length})</option>${(doc.versions || []).map((v, i) => `<option value="${i}">${new Date(v.at * 1000).toLocaleString()}</option>`).reverse().join("")}</select><button id="to-create">Use in Create</button><button id="dd" style="color:#fca5a5">Delete draft</button></div></div>
     <div class="card"><h3>AI co-writer</h3><div class="presets">${actions.map(([k, l]) => `<button class="small" data-act="${k}">${l}</button>`).join("")}</div><p class="small muted">Place the cursor or select lines in the editor, then pick an action.</p><div class="sugg" id="sugg"></div></div>
    </div>`;
    const ta = $("#d-content");
    let tm;
    const autosave = () => { $("#saved").textContent = "editing…"; clearTimeout(tm); tm = setTimeout(async () => { doc = await api(`/api/lyric-docs/${doc.id}`, { method: "PUT", body: { title: $("#d-title").value, idea: $("#d-idea").value, content: ta.value } }); $("#saved").textContent = "saved"; }, 600); };
    [ta, $("#d-title"), $("#d-idea")].forEach((x) => (x.oninput = autosave));
    $$("[data-d]").forEach((r) => (r.onclick = async () => { doc = (await api("/api/lyric-docs")).find((x) => x.id === r.dataset.d); render(); }));
    $("#nd").onclick = async () => { doc = await api("/api/lyric-docs", { method: "POST", body: { title: "Untitled draft", content: "" } }); render(); };
    $("#dd").onclick = async () => { if (!confirm("Delete this draft?")) return; await api(`/api/lyric-docs/${doc.id}`, { method: "DELETE" }); const left = await api("/api/lyric-docs"); doc = left[0] || (await api("/api/lyric-docs", { method: "POST", body: { title: "Untitled draft", content: "" } })); render(); };
    $("#snap").onclick = async () => { doc = await api(`/api/lyric-docs/${doc.id}`, { method: "PUT", body: { content: ta.value, snapshot: true } }); toast("Version saved"); render(); };
    $("#hist").onchange = (e) => { if (e.target.value === "") return; const v = doc.versions[+e.target.value]; if (confirm("Restore this version? Current text is kept in history.")) { api(`/api/lyric-docs/${doc.id}`, { method: "PUT", body: { content: v.content, snapshot: true } }).then((d) => { doc = d; render(); }); } };
    $("#to-create").onclick = () => { Object.assign(state.draft, { mode: "custom", lyrics: ta.value, title: $("#d-title").value, instrumental: false }); localStorage.setItem("mx_draft", JSON.stringify(state.draft)); location.hash = "#/create"; };
    $$("[data-act]").forEach((b) => (b.onclick = () => busy(b, async () => {
      const s0 = ta.selectionStart, s1 = ta.selectionEnd, v = ta.value;
      const r = await api("/api/write/studio", { method: "POST", body: { action: b.dataset.act, lyrics: v, selection: v.slice(s0, s1), before: v.slice(0, s0), after: v.slice(s1), idea: $("#d-idea").value } });
      const box = $("#sugg"); box.innerHTML = r.source === "offline" ? `<div class="small muted">Offline suggestions - connect Ollama or an OpenAI-compatible model in Settings for smarter results.</div>` : "";
      r.suggestions.forEach((s) => {
        const el = h(`<div class="s">${esc(s)}<div class="row"><button class="small" data-k="ins">${s0 !== s1 ? "Replace selection" : "Insert at cursor"}</button><button class="small" data-k="copy">Copy</button></div></div>`);
        el.querySelector('[data-k="ins"]').onclick = () => {
          if (b.dataset.act === "title") { $("#d-title").value = s.replace(/^["']|["']$/g, ""); autosave(); return; }
          const cur = ta.value, pre = cur.slice(0, s0), post = cur.slice(s1);
          const ins = s0 !== s1 ? s : (pre && !pre.endsWith("\n") ? "\n" : "") + s + (post.startsWith("\n") ? "" : "\n");
          ta.value = pre + ins + post; ta.focus(); ta.selectionStart = ta.selectionEnd = (pre + ins).length; autosave();
        };
        el.querySelector('[data-k="copy"]').onclick = () => { navigator.clipboard.writeText(s); toast("Copied"); };
        box.appendChild(el);
      });
    })));
  };
  render();
}

// ------------------------------------------------------------ SPEECH
async function viewSpeech(root) {
  if (!state.voices) state.voices = await api("/api/tts/voices");
  const V = state.voices;
  const d = { mode: "simple", preset: "voiceover" };
  root.innerHTML = `<h1>AI Speech Generator</h1><p>Voice-overs, ASMR, bedtime stories and meditations with optional AI background music.</p>
  ${V.available ? "" : `<div class="notice">Kokoro TTS isn't installed. Run Install from Pinokio, or <code>pip install kokoro soundfile</code> (plus <code>espeak-ng</code>).</div>`}
  <div class="grid2"><div><div class="card">
   <div class="seg" id="mode"><button data-v="simple" class="on">Simple</button><button data-v="advanced">Advanced</button></div>
   <label>Preset</label><div class="presets" id="presets">${Object.keys(V.presets).map((k) => `<button class="small" data-p="${k}">${k.replace("-", " ")}</button>`).join("")}</div>
   <div id="s-simple"><label>Describe the speech</label><textarea id="desc" maxlength="500" placeholder="A 30-second calming intro for a sleep podcast about the ocean"></textarea>
    <label>Length</label><select id="len"><option value="short">Short (~30s)</option><option value="medium">Medium (~1 min)</option><option value="long">Long (~2-3 min)</option></select></div>
   <div id="s-adv" class="hidden"><div class="row between"><label>Script</label><button class="small" id="draft">Draft from description</button></div><textarea id="script" class="lyrics" style="min-height:200px" maxlength="8000" placeholder="Type exactly what should be spoken. Blank lines become pauses."></textarea>
    <label>Tone</label><input type="text" id="tone"><label>Title</label><input type="text" id="title"></div>
   <label>Voice</label><select id="voice">${V.voices.map((v) => `<option value="${v.id}">${esc(v.name)}</option>`).join("")}</select>
   <div class="row"><div style="flex:1"><label>Speed: <b id="sp-v">1.0</b></label><input type="range" id="speed" min="0.6" max="1.4" step="0.05" value="1"></div><div style="flex:1"><label>Variety: <b id="va-v">40%</b></label><input type="range" id="variety" min="0" max="100" value="40"></div></div>
   <label class="toggle" style="margin-top:10px"><input type="checkbox" id="bg" checked> Background music</label>
   <div id="bg-box"><label>Music style</label><input type="text" id="music_style"><label>Music volume: <b id="mv-v">35%</b></label><input type="range" id="music_volume" min="5" max="80" value="35"></div>
   <label>Versions</label><select id="versions"><option value="2">2 takes</option><option value="1">1 take</option></select>
   <label>Album</label><select id="album_id">${albumOptions()}</select>
  </div><button class="primary" id="go" style="width:100%">Generate speech</button></div>
  <div><div class="card"><h3>Recent spoken tracks</h3><div class="tracks" id="recent"></div></div></div></div>`;
  const applyPreset = (k) => { d.preset = k; const p = V.presets[k]; $("#voice").value = p.voice; $("#speed").value = p.speed; $("#tone").value = p.tone; $("#music_style").value = p.music; $("#sp-v").textContent = p.speed; $$("#presets button").forEach((b) => b.classList.toggle("on", b.dataset.p === k)); };
  $$("#presets button").forEach((b) => (b.onclick = () => applyPreset(b.dataset.p))); applyPreset("voiceover");
  $$("#mode button").forEach((b) => (b.onclick = () => { d.mode = b.dataset.v; $$("#mode button").forEach((x) => x.classList.toggle("on", x === b)); $("#s-simple").classList.toggle("hidden", d.mode !== "simple"); $("#s-adv").classList.toggle("hidden", d.mode === "simple"); }));
  $("#speed").oninput = (e) => ($("#sp-v").textContent = e.target.value); $("#variety").oninput = (e) => ($("#va-v").textContent = e.target.value + "%"); $("#music_volume").oninput = (e) => ($("#mv-v").textContent = e.target.value + "%");
  $("#bg").onchange = (e) => $("#bg-box").classList.toggle("hidden", !e.target.checked);
  $("#draft").onclick = (e) => busy(e.target, async () => { const desc = $("#desc").value || prompt("Describe the speech"); if (!desc) return; const r = await api("/api/write/speech", { method: "POST", body: { description: desc, preset: d.preset, length: $("#len").value } }); $("#script").value = r.script; $("#tone").value = r.tone; $("#title").value = r.title; $("#music_style").value = r.music_style; });
  $("#go").onclick = (e) => busy(e.target, async () => {
    const body = { mode: d.mode, preset: d.preset, description: $("#desc").value, length: $("#len").value, script: $("#script").value, tone: $("#tone").value, title: $("#title").value, voice: $("#voice").value, speed: +$("#speed").value, variety: +$("#variety").value, background: $("#bg").checked, music_style: $("#music_style").value, music_volume: $("#music_volume").value / 100, versions: +$("#versions").value, album_id: $("#album_id").value || null };
    trackJob(await api("/api/speech", { method: "POST", body })); toast("Speech queued");
  });
  const loadRecent = async () => { const box = $("#recent"); if (!box) return; const ts = await api("/api/tracks?kind=speech"); box.replaceChildren(...ts.slice(0, 12).map(trackCard)); if (!ts.length) box.innerHTML = `<div class="muted small">No spoken tracks yet.</div>`; };
  trackListRefreshers = [loadRecent]; loadRecent();
}

// ------------------------------------------------------------ STYLE & LYRICS GENERATORS
function viewStyle(root) {
  root.innerHTML = `<h1>Style Generator</h1><p>Build a detailed style prompt from genre, era, instruments and mood.</p><div class="grid2"><div class="card">
   <div class="row"><div style="flex:1"><label>Genre</label><input type="text" id="genre" placeholder="pop, hip hop, jazz…"></div><div style="flex:1"><label>Sub-genre</label><input type="text" id="subgenre" placeholder="synthwave, trap, bossa nova…"></div></div>
   <div class="row"><div style="flex:1"><label>Era</label><select id="era"><option value="">Any</option><option>60s</option><option>70s</option><option>80s</option><option>90s</option><option>2000s</option><option>2010s</option><option>modern</option><option>futuristic</option></select></div><div style="flex:1"><label>Tempo</label><select id="tempo"><option value="">Any</option><option>slow</option><option>mid-tempo</option><option>upbeat</option><option>fast</option></select></div></div>
   <label>Instruments</label><input type="text" id="instruments" placeholder="analog synths, gated drums, saxophone">
   <label>Mood</label><input type="text" id="mood" placeholder="nostalgic, euphoric, dark…">
   <label>Complexity: <b id="cx-v">50%</b></label><input type="range" id="complexity" min="0" max="100" value="50">
   <label>Anything else</label><input type="text" id="custom" placeholder="female breathy vocals, wide stereo">
   <div class="row" style="margin-top:12px"><button class="primary" id="go">Generate style</button><button id="rnd">Random</button></div></div>
   <div class="card"><h3>Result</h3><textarea id="out" style="min-height:140px"></textarea><div class="row"><button id="enh">Enhance</button><button id="use">Use in Create</button><button id="cp">Copy</button></div></div></div>`;
  $("#complexity").oninput = (e) => ($("#cx-v").textContent = e.target.value + "%");
  $("#go").onclick = (e) => busy(e.target, async () => { const b = {}; ["genre", "subgenre", "era", "tempo", "instruments", "mood", "custom"].forEach((k) => (b[k] = $("#" + k).value)); b.complexity = +$("#complexity").value; $("#out").value = (await api("/api/write/style", { method: "POST", body: b })).style; });
  $("#rnd").onclick = (e) => busy(e.target, async () => ($("#out").value = (await api("/api/write/random-style")).style));
  $("#enh").onclick = (e) => busy(e.target, async () => ($("#out").value = (await api("/api/write/enhance-style", { method: "POST", body: { style: $("#out").value } })).style));
  $("#use").onclick = () => { state.draft.style = $("#out").value; localStorage.setItem("mx_draft", JSON.stringify(state.draft)); location.hash = "#/create"; };
  $("#cp").onclick = () => { navigator.clipboard.writeText($("#out").value); toast("Copied"); };
}
function viewLyrics(root) {
  root.innerHTML = `<h1>Lyrics Generator</h1><p>Turn an idea into complete, structured song lyrics.</p><div class="grid2"><div class="card">
   <label>Song idea</label><textarea id="idea" maxlength="600" placeholder="Two friends reuniting after ten years at a summer festival"></textarea>
   <div class="row"><div style="flex:1"><label>Genre</label><input type="text" id="genre" placeholder="indie pop"></div><div style="flex:1"><label>Mood</label><input type="text" id="mood" placeholder="bittersweet"></div></div>
   <div class="row"><div style="flex:1"><label>Structure</label><select id="structure"><option value="">Classic (verse/chorus/bridge)</option><option>Verse, Pre-Chorus, Chorus, Verse, Pre-Chorus, Chorus, Bridge, Chorus</option><option>Intro, Verse, Chorus, Verse, Chorus, Outro</option><option>Verse, Hook, Verse, Hook (rap)</option><option>Short (Verse, Chorus)</option></select></div>
   <div style="flex:1"><label>Language</label><input type="text" id="language" value="English"></div></div>
   <label>Rhyme scheme</label><select id="rhyme"><option value="">Natural</option><option>AABB</option><option>ABAB</option><option>ABCB</option><option>Free verse</option></select>
   <button class="primary" id="go" style="margin-top:12px">Generate lyrics</button></div>
   <div class="card"><h3>Lyrics</h3><textarea id="out" class="lyrics"></textarea><div class="row"><button id="use">Use in Create</button><button id="studio">Edit in Lyric Studio</button><button id="cp">Copy</button></div></div></div>`;
  $("#go").onclick = (e) => busy(e.target, async () => { const b = {}; ["idea", "genre", "mood", "structure", "language", "rhyme"].forEach((k) => (b[k] = $("#" + k).value)); $("#out").value = (await api("/api/write/lyrics", { method: "POST", body: b })).lyrics; });
  $("#use").onclick = () => { Object.assign(state.draft, { mode: "custom", lyrics: $("#out").value, instrumental: false }); localStorage.setItem("mx_draft", JSON.stringify(state.draft)); location.hash = "#/create"; };
  $("#studio").onclick = () => { localStorage.setItem("mx_studio_import", $("#out").value); location.hash = "#/studio"; };
  $("#cp").onclick = () => { navigator.clipboard.writeText($("#out").value); toast("Copied"); };
}

// ------------------------------------------------------------ SETTINGS
async function viewSettings(root) {
  const s = (state.settings = await api("/api/settings"));
  root.innerHTML = `<h1>Settings</h1><p>Everything runs on your machine. No account, no credits, no limits.</p><div class="grid2"><div>
  <div class="card"><h3>Music engine</h3><select id="music_engine"><option value="acestep">ACE-Step 1.5 (real AI songs with vocals)</option><option value="mock">Demo synth (instant, no GPU - for testing the app)</option></select>
   <label>ACE-Step API URL</label><input type="text" id="acestep_url"><label>ACE-Step API key (if you set one)</label><input type="text" id="acestep_api_key">
   <div class="row"><div style="flex:1"><label>Inference steps</label><input type="number" id="acestep_steps" min="4" max="200"></div><div style="flex:1"><label>Versions per create</label><input type="number" id="batch_size" min="1" max="4"></div></div>
   <label>Base model (for Add Vocals / Add Instrumental)</label><input type="text" id="acestep_base_model">
   <label class="toggle" style="margin-top:10px"><input type="checkbox" id="acestep_thinking"> Let ACE-Step's LM plan song structure ("thinking")</label></div>
  <div class="card"><h3>Songwriter LLM</h3><select id="llm_provider"><option value="auto">Auto (Ollama if running, else OpenAI-compatible if a key is set)</option><option value="ollama">Ollama</option><option value="openai">OpenAI-compatible API</option><option value="offline">Offline templates only</option></select>
   <label>Ollama URL</label><input type="text" id="ollama_url"><label>Ollama model (blank = first installed)</label><input type="text" id="ollama_model" placeholder="qwen2.5:7b">
   <label>OpenAI-compatible base URL</label><input type="text" id="openai_base_url"><label>API key</label><input type="text" id="openai_api_key"><label>Model</label><input type="text" id="openai_model"></div>
  <div class="card"><h3>Speech</h3><label>Default voice</label><input type="text" id="default_voice"></div>
  <button class="primary" id="save">Save settings</button></div>
  <div><div class="card"><h3>Status</h3><pre class="lyr" id="st"></pre><button id="re">Refresh</button></div></div></div>`;
  const keys = Object.keys(s);
  keys.forEach((k) => { const el = $("#" + k); if (!el) return; if (el.type === "checkbox") el.checked = !!s[k]; else el.value = s[k] ?? ""; });
  const showSt = async () => { await refreshStatus(); $("#st").textContent = JSON.stringify(state.status, null, 2); };
  $("#re").onclick = showSt; showSt();
  $("#save").onclick = (e) => busy(e.target, async () => {
    const p = {}; keys.forEach((k) => { const el = $("#" + k); if (!el) return; p[k] = el.type === "checkbox" ? el.checked : el.type === "number" ? Number(el.value) : el.value; });
    state.settings = await api("/api/settings", { method: "PUT", body: p }); toast("Settings saved"); showSt();
  });
}

// ------------------------------------------------------------ router
const routes = { create: viewCreate, library: viewLibrary, studio: viewStudio, speech: viewSpeech, style: viewStyle, lyrics: viewLyrics, settings: viewSettings };
async function route() {
  const r = (location.hash.split("/")[1] || "create");
  $$("nav a").forEach((a) => a.classList.toggle("active", a.dataset.route === r));
  trackListRefreshers = [];
  try { await (routes[r] || viewCreate)($("#view")); } catch (e) { $("#view").innerHTML = `<div class="notice">${esc(e.message)}</div>`; }
}
window.addEventListener("hashchange", route);
(async () => { await Promise.all([refreshStatus(), loadMeta()]); route(); loadJobs(); setInterval(refreshStatus, 15000); })();
