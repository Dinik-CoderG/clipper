const PLATFORMS = {
  youtube: {
    name: "YouTube", icon: "#i-youtube", path: "/youtube-clip-maker",
    placeholder: "Paste your YouTube link…  (youtube.com/watch?v=…)",
    step1: "Any youtube.com or youtu.be link works. We pull the whole video, even a long podcast. No download.",
  },
  twitch: {
    name: "Twitch", icon: "#i-twitch", path: "/twitch-clip-maker",
    placeholder: "Paste your Twitch VOD link…  (twitch.tv/videos/…)",
    step1: "Any twitch.tv/videos link works. We pull the whole VOD, even a long stream. No download.",
  },
  kick: {
    name: "Kick", icon: "#i-kick", path: "/kick-clip-maker",
    placeholder: "Paste your Kick VOD link…  (kick.com/…/videos/…)",
    step1: "Any kick.com VOD link works. We pull the whole stream, start to finish. No download.",
  },
};
const STAGES = ["download", "transcribe", "moments", "render"];
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch {} },
};

// ---------- platform switching
function setPlatform(key, push) {
  const p = PLATFORMS[key];
  $$("[data-p=name]").forEach(el => (el.textContent = p.name));
  $$("[data-p=step1]").forEach(el => (el.textContent = p.step1));
  $("#hero-icon use").setAttribute("href", p.icon);
  $$("[data-form] input").forEach(i => (i.placeholder = p.placeholder));
  $$(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === key));
  document.title = `${p.name} Clip Maker: Turn Videos into Clips | Clipper`;
  if (push && location.pathname !== p.path) history.pushState({}, "", p.path);
}
const initial = Object.keys(PLATFORMS).find(k => location.pathname.startsWith(PLATFORMS[k].path)) || "youtube";
setPlatform(initial);
$$(".tab").forEach(t => t.addEventListener("click", () => setPlatform(t.dataset.tab, true)));
$$(".chip, .foot-col a").forEach(a => {
  const key = Object.keys(PLATFORMS).find(k => a.getAttribute("href") === PLATFORMS[k].path);
  if (key) a.addEventListener("click", e => { e.preventDefault(); setPlatform(key, true); scrollTo({ top: 0 }); });
});
addEventListener("popstate", () => setPlatform(Object.keys(PLATFORMS).find(k => location.pathname.startsWith(PLATFORMS[k].path)) || "youtube"));

// ---------- rotating headline word (clips → Reels → Shorts → TikToks)
const words = ["clips", "Reels", "Shorts", "TikToks"];
let wi = 0;
setInterval(() => {
  const slot = $("#cycle");
  slot.classList.add("out");
  setTimeout(() => {
    wi = (wi + 1) % words.length;
    const next = document.createElement("span");
    next.className = "slot"; next.id = "cycle"; next.textContent = words[wi];
    slot.replaceWith(next);
  }, 280);
}, 2200);

// ---------- job submission + polling
let pollTimer = null;

$$("[data-form]").forEach(form => form.addEventListener("submit", async e => {
  e.preventDefault();
  const btn = $("button", form);
  const url = form.url.value.trim();
  $$(".form-error").forEach(x => x.remove());
  btn.disabled = true;
  try {
    const res = await fetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url,
        max_clips: +$("#opt-count").value,
        captions: $("#opt-captions").checked,
        highlight: $("#opt-color").value,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Please paste a valid video link.");
    form.reset();
    openJob(data.id);
  } catch (err) {
    const msg = document.createElement("div");
    msg.className = "form-error"; msg.textContent = err.message;
    form.after(msg);
  } finally {
    btn.disabled = false;
  }
}));

function openJob(id) {
  store.set("clipper:last", id);
  const studio = $("#studio");
  studio.hidden = false;
  $("#clips").innerHTML = "";
  studio.scrollIntoView({ behavior: "smooth" });
  clearTimeout(pollTimer);
  poll(id);
}

async function poll(id) {
  let job;
  try {
    const res = await fetch(`/api/jobs/${id}`);
    if (!res.ok) { $("#studio").hidden = true; return; }
    job = await res.json();
  } catch { pollTimer = setTimeout(() => poll(id), 3000); return; }
  renderJob(job);
  if (job.status === "queued" || job.status === "running") pollTimer = setTimeout(() => poll(id), 1500);
  else loadRecent();
}

function renderJob(job) {
  const meta = job.meta || {};
  $("#job-title").textContent = meta.title || job.url;
  $("#job-sub").textContent = [meta.uploader, meta.duration ? fmt(meta.duration) : "", meta.language ? meta.language.toUpperCase() : ""].filter(Boolean).join(" · ");
  const thumb = $("#job-thumb");
  if (meta.thumbnail) { thumb.src = meta.thumbnail; thumb.hidden = false; } else thumb.hidden = true;

  const cur = job.status === "done" ? STAGES.length : STAGES.indexOf(job.stage);
  $$("#stepper > div").forEach((el, i) => {
    const pct = i < cur ? 100 : i === cur ? Math.round((job.stage_progress || 0) * 100) : 0;
    $("b", el).style.width = pct + "%";
    el.classList.toggle("on", i <= cur);
  });

  const status = $("#status");
  status.classList.toggle("err", job.status === "error");
  $(".spinner", status).style.display = job.status === "queued" || job.status === "running" ? "" : "none";
  $("#status-text").textContent =
    job.status === "done" ? `${job.clips.length} clips ready` :
    job.status === "error" ? `Couldn't clip this video: ${job.message}` : job.message;

  if (job.status === "done") {
    $("#clips").innerHTML = job.clips.map(c => clipCard(job.id, c)).join("");
    $$("#clips [data-copy]").forEach(b => b.addEventListener("click", () => {
      navigator.clipboard?.writeText(b.dataset.copy);
      b.textContent = "Copied"; setTimeout(() => (b.textContent = "Copy text"), 1200);
    }));
    showcase(job);
  }
}

function clipCard(jobId, c) {
  const cls = c.score >= 70 ? "" : c.score >= 45 ? "mid" : "low";
  const src = `/media/${jobId}/${c.video}`;
  return `<article class="clip">
    <video src="${src}" poster="/media/${jobId}/${c.thumb}" controls preload="none" playsinline></video>
    <div class="body">
      <h4>${esc(c.title)}</h4>
      <div class="row"><span>${fmt(c.start)} – ${fmt(c.end)} · ${Math.round(c.duration)}s</span><span class="score ${cls}">${c.score}</span></div>
      <div class="actions">
        <a class="primary" href="${src}?download=true" download>Download</a>
        <button data-copy="${esc(c.transcript)}">Copy text</button>
      </div>
    </div>
  </article>`;
}

// swap the mock phones for real clips once you have some
function showcase(job) {
  const top = job.clips.slice(0, 3);
  if (top.length < 3) return;
  $("#phones").innerHTML = top.map(c =>
    `<div class="phone"><video src="/media/${job.id}/${c.video}" muted loop autoplay playsinline preload="metadata"></video></div>`).join("");
}

async function loadRecent() {
  try {
    const list = await (await fetch("/api/jobs")).json();
    const done = list.filter(j => j.status === "done");
    $("#recent").hidden = done.length < 2;
    $("#recent-list").innerHTML = done.map(j =>
      `<button data-job="${j.id}">${esc(j.meta?.title || j.url)}<span>${j.clips.length} clips</span></button>`).join("");
    $$("#recent-list [data-job]").forEach(b => b.addEventListener("click", () => openJob(b.dataset.job)));
    return list;
  } catch { return []; }
}

// ---------- helpers
function fmt(t) {
  t = Math.round(t);
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`;
}
function esc(s = "") {
  return String(s).replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

// ---------- reveal on scroll, cookie notice, resume last job
const io = new IntersectionObserver(es => es.forEach(e => e.isIntersecting && e.target.classList.add("in")), { threshold: 0.12 });
$$(".reveal").forEach(el => io.observe(el));

if (!store.get("clipper:cookie")) $("#cookie").hidden = false;
$("#cookie-ok").addEventListener("click", () => { $("#cookie").hidden = true; store.set("clipper:cookie", "1"); });

const openLatest = async e => {
  const last = store.get("clipper:last");
  if (last) { e?.preventDefault(); openJob(last); }
};
$("#nav-cta").addEventListener("click", openLatest);
$$("[data-open-studio]").forEach(a => a.addEventListener("click", openLatest));

(async () => {
  const last = store.get("clipper:last");
  const list = await loadRecent();
  const live = list.find(j => j.id === last && (j.status === "queued" || j.status === "running"));
  if (live) openJob(live.id);
  else {
    const latestDone = list.find(j => j.status === "done" && j.clips.length >= 3);
    if (latestDone) showcase(latestDone);
  }
})();
