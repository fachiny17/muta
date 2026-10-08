// Drives the REAL page + REAL tutor.js in jsdom against the REAL running Flask server (mock gateway behind it).
const { JSDOM } = require("jsdom");
const BASE = process.env.BASE_URL || "http://127.0.0.1:5055";
const jar = {};
async function nfetch(u, o = {}) {
  const url = new URL(u, BASE);
  const h = Object.assign({}, o.headers || {});
  const c = Object.entries(jar).map(([k, v]) => `${k}=${v}`).join("; ");
  if (c) h["cookie"] = c;
  const r = await fetch(url, { ...o, headers: h });
  for (const sc of r.headers.getSetCookie?.() || []) { const [kv] = sc.split(";"); const [k, v] = kv.split("="); jar[k] = v; }
  return r;
}
function wavBytes(sec = 2, sr = 16000) {
  const n = sec * sr, buf = Buffer.alloc(44 + n * 2);
  buf.write("RIFF", 0); buf.writeUInt32LE(36 + n * 2, 4); buf.write("WAVEfmt ", 8); buf.writeUInt32LE(16, 16);
  buf.writeUInt16LE(1, 20); buf.writeUInt16LE(1, 22); buf.writeUInt32LE(sr, 24); buf.writeUInt32LE(sr * 2, 28);
  buf.writeUInt16LE(2, 32); buf.writeUInt16LE(16, 34); buf.write("data", 36); buf.writeUInt32LE(n * 2, 40);
  for (let i = 0; i < n; i++) buf.writeInt16LE(Math.round(8000 * Math.sin(2 * Math.PI * 220 * i / sr)), 44 + i * 2);
  return buf;
}
const wait = (ms) => new Promise(r => setTimeout(r, ms));
let fails = 0;
const ok = (n, c) => { console.log((c ? "PASS  " : "FAIL  ") + n); if (!c) fails++; };

(async () => {
  const html = await (await nfetch("/")).text();
  const dom = new JSDOM(html, { url: BASE + "/", runScripts: "outside-only", pretendToBeVisual: true });
  const w = dom.window, d = w.document;
  // browser APIs jsdom lacks
  w.fetch = (u, o) => nfetch(u, o);
  w.FormData = FormData; w.Blob = Blob;
  const track = { stop: () => {} };
  w.navigator.mediaDevices = { getUserMedia: async () => ({ getTracks: () => [track] }) };
  w.MediaRecorder = class {
    static isTypeSupported(t) { return t.startsWith("audio/webm"); }
    constructor(s, o) { this.state = "inactive"; this.mimeType = (o && o.mimeType) || "audio/webm"; }
    start() { this.state = "recording"; const b = wavBytes(); this.ondataavailable({ data: new Blob([b], { type: "audio/webm" }), size: b.length }); }
    stop() { this.state = "inactive"; setTimeout(() => this.onstop(), 0); }
  };
  w.URL.createObjectURL = () => "blob:x"; w.URL.revokeObjectURL = () => {};
  const src = require("fs").readFileSync(require("path").join(__dirname, "../../static/js/tutor.js"), "utf8");
  w.eval(src);
  await wait(300);

  ok("health chip says N-ATLAS online", d.getElementById("gw").textContent === "N-ATLAS online");
  ok("offline banner hidden", d.getElementById("offline").hidden === true);
  ok("consent visible first, tutor hidden", !d.getElementById("consent").hidden && d.getElementById("tutor").hidden);
  d.getElementById("agree").click();
  ok("after agreeing the tutor appears", d.getElementById("consent").hidden && !d.getElementById("tutor").hidden);
  ok("language list has 4 options", d.getElementById("lang").options.length === 4);

  d.getElementById("lang").value = "yo";
  d.querySelector('#mode button[data-m="summary"]').click();
  ok("mode switches to summary", d.querySelector('#mode button[data-m="summary"]').classList.contains("sel"));
  d.querySelector('#mode button[data-m="question"]').click();

  d.getElementById("mic").click(); await wait(100);
  ok("recording state shown", d.body.classList.contains("is-recording"));
  d.getElementById("mic").click(); await wait(1500);
  ok("answer panel appears", !d.getElementById("out").hidden);
  ok("transcript rendered", d.getElementById("transcription-text").textContent.includes("explain stress and strain"));
  ok("answer rendered", d.getElementById("answer").textContent.includes("Stress is force"));
  ok("feedback card visible", d.getElementById("fb").hidden === false);

  d.querySelector('#stars button[data-r="4"]').click(); await wait(200);
  ok("after rating only, the survey is still there with a 'rating only' option", d.getElementById("fb").hidden === false && d.getElementById("fb-submit").hidden === false);
  d.querySelector('#task button[data-t="1"]').click(); await wait(500);
  ok("survey questions disappear after both answers", d.getElementById("fb").hidden === true);
  ok("success message is displayed", d.getElementById("fb-done").hidden === false && d.getElementById("fb-done").textContent.includes("Survey successfully saved! Thank you."));
  ok("toast notification shown", d.getElementById("toast-root").textContent.includes("Survey successfully saved"));

  const s = await (await nfetch("/api/stats?key=" + (process.env.DASHBOARD_KEY || "k"))).json();
  ok("database recorded rating 4 and task completed for yo", s.by_language.yo === 1 && s.avg_rating >= 4 && s.task_completion_rate === 100);
  console.log(fails ? `\n${fails} FAILED` : "\nFront-end flow works end to end.");
  process.exit(fails ? 1 : 0);
})().catch(e => { console.error("ERROR", e); process.exit(1); });
