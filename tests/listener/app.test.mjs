// UI controller integration without a physical microphone or external DOM dependency.
import assert from "node:assert/strict";
import test from "node:test";
import { midiHz, noteName } from "../../src/harptab/assets/listener/pitch.mjs";
const downloads = [];

class Element {
  constructor(value = "") {
    this.value = value; this.textContent = ""; this.children = []; this.attributes = {};
    this.disabled = false; this.checked = false; this.width = 1000; this.height = 240;
    this.paused = true; this.currentTime = 0;
    this.classList = { toggle() {} };
    this.drawnLabels = [];
  }
  replaceChildren(...items) { this.children = items; }
  append(item) { this.children.push(item); }
  click() { if (this.download) downloads.push({ name: this.download, href: this.href }); }
  async play() { this.paused = false; this.onplay?.(); }
  pause() { this.paused = true; }
  load() {}
  removeAttribute(name) { delete this.attributes[name]; delete this[name]; }
  setAttribute(name, value) { this.attributes[name] = value; }
  scrollIntoView() {}
  getBoundingClientRect() { return { left: 0, width: 1000, height: 240 }; }
  getContext() { return { setTransform() {}, clearRect: () => { this.drawnLabels = []; }, fillRect() {}, beginPath() {}, arc() {}, fill() {}, fillText: (text) => { this.drawnLabels.push(text); }, moveTo() {}, lineTo() {}, stroke() {} }; }
}
const elements = new Map();
const get = (id) => { if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id); };
const documentEvents = {}, windowEvents = {};
globalThis.document = {
  getElementById: get, querySelector: () => get("heard-card"),
  createElement: () => new Element(), hidden: false,
  addEventListener: (name, handler) => { documentEvents[name] = handler; },
};
globalThis.window = { devicePixelRatio: 1, addEventListener: (name, handler) => { windowEvents[name] = handler; } };
globalThis.Option = class extends Element { constructor(label, value) { super(value); this.textContent = label; } };
let animation, clock = 0;
Object.defineProperty(globalThis, "performance", { value: { now: () => clock }, configurable: true });
globalThis.requestAnimationFrame = (handler) => { animation = (now) => { clock = now; handler(now); }; };
get("mode").value = "timed"; get("session").value = "0"; get("speed").value = "0.5";
get("tolerance").value = "35"; get("gate").value = "-50";
// Synthetic exercises, unrelated to any recording. Production receives these fields from JSON.
const action = (hole, technique, pitch, bend_semitones = 0) => ({ hole, technique, pitch, bend_semitones });
const event = (actions, tab, start) => ({ pitches: actions.map((a) => a.pitch), actions, notes: actions.map((a) => noteName(a.pitch)), tab, start, sourceStart: start + 10, duration: 0.4, omitted: [], instruction: "Test instruction" });
globalThis.fetch = async () => ({ ok: true, json: async () => ({ sessions: [
  { title: "A exercise", harp: "A", sourceStart: 10, duration: 2, transpose: 0, fingerings: { 68: [{ tab: "-3", instruction: "Draw (inhale) through hole 3" }] }, events: [event([action(4, "draw", 71), action(5, "draw", 74), action(6, "draw", 78)], "[-4 -5 -6]", 0), event([action(6, "overblow", 79)], "6o", 1.6)] },
  { title: "G exercise", harp: "G", sourceStart: 10, duration: 2, transpose: 0, events: [event([action(7, "draw", 78)], "-7", 0), event([action(5, "blow", 71), action(6, "blow", 74), action(7, "blow", 79)], "[5 6 7]", 1.6)] },
  { title: "Another song", harp: "C", sourceStart: 10, duration: 2, transpose: 0, events: [event([action(3, "draw_bend", 69, 2)], "-3''", 0), event([action(8, "blow_bend", 87, 1)], "8'", 0.8), event([action(7, "overdraw", 85)], "7o", 1.6)] },
] }) });
let acquisition, stopped = 0, closed = 0, constraint, destinations = 0;
let microphoneSamples = new Float32Array(8192);
const media = {
  getUserMedia: async (options) => { constraint = options; return acquisition(); },
  enumerateDevices: async () => [{ kind: "audioinput", label: "Test microphone", deviceId: "test" }],
};
Object.defineProperty(globalThis, "navigator", { value: { mediaDevices: media }, configurable: true });
function newStream() {
  const track = { stop() { stopped++; }, onended: null };
  return { getTracks: () => [track] };
}
globalThis.AudioContext = class {
  constructor() { this.sampleRate = 48000; }
  async resume() {}
  async close() { closed++; }
  createAnalyser() { return { fftSize: 0, getFloatTimeDomainData(array) { array.set(microphoneSamples); } }; }
  createMediaStreamSource() { return { connect(target) { if (target === "speakers") destinations++; }, disconnect() {} }; }
  get destination() { return "speakers"; }
};
const recordings = [];
globalThis.MediaRecorder = class {
  static isTypeSupported(type) { return type.startsWith("audio/webm"); }
  constructor(stream, options) { this.stream = stream; this.mimeType = options.mimeType; this.state = "inactive"; recordings.push(this); }
  start() { this.state = "recording"; }
  stop() {
    this.state = "inactive";
    queueMicrotask(() => { this.ondataavailable({ data: new Blob(["test microphone bytes"], { type: this.mimeType }) }); this.onstop(); });
  }
};
await import("../../src/harptab/assets/listener/app.mjs");

test("session controls show actual A and G chord targets", () => {
  assert.equal(get("target-note").textContent, "B4 + D5 + F#5");
  assert.equal(get("play").disabled, false);
  get("next").onclick(); assert.equal(get("target-tab").textContent, "6o");
  get("session").value = "1"; get("session").onchange();
  assert.equal(get("target-tab").textContent, "-7");
  get("next").onclick(); assert.equal(get("target-note").textContent, "B4 + D5 + G5");
  get("session").value = "0"; get("session").onchange();
});
test("labeled demo exercises detection, practice completion and restart", () => {
  get("mode").value = "wait"; get("mode").onchange();
  get("demo").onclick(); assert.equal(get("input-state").textContent, "DEMO · Simulated input");
  animation(performance.now() + 50);
  assert.equal(get("heard-note").textContent, "B4 + D5 + F#5");
  get("play").onclick();
  const start = performance.now();
  for (let t = 100; t <= 1500; t += 50) animation(start + t);
  assert.match(get("status").textContent, /Phrase complete.*simulated/);
  get("restart").onclick(); assert.equal(get("target-tab").textContent, "[-4 -5 -6]");
  get("demo").onclick(); assert.equal(get("play").disabled, false);
  assert.equal(recordings.length, 0); // Simulated input must never be labeled as a microphone recording.
});
test("permission denial is actionable and leaves microphone off", async () => {
  acquisition = () => { throw Object.assign(new Error("denied"), { name: "NotAllowedError" }); };
  await get("microphone").onclick();
  assert.match(get("status").textContent, /permission was denied/);
  assert.equal(get("input-state").textContent, "Microphone off");
});
test("start and stop release every track and never monitor to speakers", async () => {
  acquisition = newStream;
  await get("microphone").onclick();
  assert.equal(get("input-state").textContent, "Microphone listening");
  assert.equal(constraint.video, false); assert.equal(constraint.audio.echoCancellation, false);
  assert.equal(get("play").disabled, false);
  const before = stopped;
  await get("microphone").onclick();
  assert.equal(stopped, before + 1); assert.ok(closed > 0); assert.equal(destinations, 0);
});
test("canceling a pending microphone request releases a late stream", async () => {
  let resolve;
  acquisition = () => new Promise((done) => { resolve = done; });
  const pending = get("microphone").onclick();
  assert.match(get("microphone").textContent, /Cancel/);
  await get("microphone").onclick(); const before = stopped;
  resolve(newStream()); await pending;
  assert.equal(stopped, before + 1); assert.equal(get("input-state").textContent, "Microphone off");
});
test("hidden tab stops capture and device loss gives recovery instructions", async () => {
  let acquired;
  acquisition = () => { acquired = newStream(); return acquired; };
  await get("microphone").onclick();
  acquired.getTracks()[0].onended();
  assert.match(get("status").textContent, /disconnected/);
  await get("microphone").onclick();
  document.hidden = true; documentEvents.visibilitychange(); document.hidden = false;
  assert.equal(get("input-state").textContent, "Microphone off");
  assert.match(get("status").textContent, /hidden/);
});
test("live mic notes survive frame dropouts without stale notes earning matches", async () => {
  get("session").value = "0"; get("session").onchange();
  acquisition = newStream; await get("microphone").onclick();
  const synth = (pitches) => Float32Array.from({ length: 8192 }, (_, i) => pitches.reduce((sum, pitch) => sum + 0.06 * Math.sin(2 * Math.PI * midiHz(pitch) * i / 48000), 0));
  const now = performance.now() + 10000;
  microphoneSamples = synth([60]); animation(now);
  assert.equal(get("heard-note").textContent, "C4"); // Visible before Start practice.
  microphoneSamples.fill(0); animation(now + 500);
  assert.equal(get("heard-note").textContent, "C4");
  assert.equal(get("heard-label").textContent, "LAST HEARD");
  assert.match(get("input-detail").textContent, /Below noise gate/);
  assert.ok(get("trace").drawnLabels.includes("C4")); // History stays in view after detection drops.
  animation(now + 1100); assert.equal(get("heard-note").textContent, "—");
  assert.ok(get("trace").drawnLabels.includes("C4"));
  get("play").onclick();
  microphoneSamples = synth([71, 74, 78]); animation(now + 1200);
  assert.equal(get("heard-note").textContent, "B4 + D5 + F#5");
  microphoneSamples.fill(0); animation(now + 1500); animation(now + 1800);
  assert.equal(get("heard-note").textContent, "B4 + D5 + F#5");
  assert.equal(get("event-number").textContent, "1 / 2"); // Retained match is display-only.
  await get("microphone").onclick(); assert.equal(get("heard-note").textContent, "—");
});
test("Ab4 diagnostics show actual frequency and possible A-harp fingering without recording audio", async () => {
  get("session").value = "0"; get("session").onchange();
  acquisition = newStream; await get("microphone").onclick();
  microphoneSamples = Float32Array.from({ length: 8192 }, (_, i) => 0.06 * Math.sin(2 * Math.PI * midiHz(68) * i / 48000));
  animation(performance.now() + 20000);
  assert.equal(get("heard-note").textContent, "Ab4");
  assert.match(get("heard-details").textContent, /Ab4.*415\..*Hz.*-3: Draw.*hole 3/);
  let saved;
  const original = URL.createObjectURL;
  try {
    URL.createObjectURL = (blob) => { saved = blob; return "blob:diagnostics-test"; };
    get("diagnostics").onclick();
    const payload = JSON.parse(await saved.text());
    assert.equal(payload.harp, "A");
    assert.equal(payload.frames.at(-1).detected[0].note, 68);
    assert.ok(Math.abs(payload.frames.at(-1).detected[0].hz - midiHz(68)) < 1);
    assert.deepEqual(Object.keys(payload.frames.at(-1)).sort(), ["detected", "expected", "reason", "rms", "secondsAgo"]);
    assert.match(get("status").textContent, /diagnostics file contains no audio/);
  } finally { URL.createObjectURL = original; await get("microphone").onclick(); }
});
test("one Start click opens the mic, counts in, shows rests and completes despite extra notes", async () => {
  get("mode").value = "timed"; get("mode").onchange();
  acquisition = newStream;
  microphoneSamples = Float32Array.from({ length: 8192 }, (_, i) => [68, 71, 74, 78].reduce((sum, pitch) => sum + 0.04 * Math.sin(2 * Math.PI * midiHz(pitch) * i / 48000), 0));
  await get("play").onclick();
  const start = performance.now();
  assert.equal(get("input-state").textContent, "Microphone listening");
  assert.equal(get("play").textContent, "Pause practice");
  assert.equal(get("practice-cue").textContent, "3");
  animation(start + 1000); assert.equal(get("practice-cue").textContent, "2");
  assert.match(get("feedback").textContent, /begin when the countdown ends/);
  assert.match(get("up-next").textContent, /6o.*G5/);
  assert.ok(get("timeline").drawnLabels.includes("NOW"));
  animation(start + 2000); assert.equal(get("practice-cue").textContent, "1");
  animation(start + 3000); assert.equal(get("practice-cue").textContent, "Play");
  animation(start + 3300); assert.match(get("feedback").textContent, /extra or off-pitch/);
  animation(start + 3900); assert.equal(get("practice-cue").textContent, "Rest");
  assert.ok(get("harp-holes").children.every((hole) => !hole.className.includes(" lit")));
  assert.equal(get("target-note").textContent, "Rest");
  assert.match(get("time-left").textContent, /^Rest/);
  animation(start + 6400); assert.equal(get("event-number").textContent, "2 / 2");
  assert.equal(get("practice-cue").textContent, "Play");
  animation(start + 7100); assert.equal(get("practice-cue").textContent, "Complete");
  assert.match(get("status").textContent, /0 of 2 steps matched/);
  assert.equal(get("phrase-progress").value, 1);
  assert.equal(get("play").textContent, "Play again");
  await get("microphone").onclick();
});
test("running skip, step selection, restart and loop continue without another Start click", async () => {
  get("session").onchange(); acquisition = newStream; microphoneSamples.fill(0);
  await get("play").onclick();
  get("next").onclick();
  assert.equal(get("event-number").textContent, "2 / 2");
  assert.equal(get("play").textContent, "Pause practice");
  assert.equal(get("practice-cue").textContent, "Play");
  get("sequence").children[0].onclick();
  animation(performance.now() + 300);
  assert.equal(get("event-number").textContent, "1 / 2");
  assert.equal(get("practice-cue").textContent, "Play");
  assert.ok(get("phrase-progress").value > 0);
  get("restart").onclick(); assert.equal(get("practice-cue").textContent, "3");
  get("loop").checked = true;
  animation(performance.now() + 7100);
  assert.equal(get("results").hidden, false);
  assert.equal(get("result-score").textContent, "0%");
  assert.equal(get("result-review").open, false);
  assert.equal(get("live-score").textContent, "0 / 2 steps matched");
  assert.equal(get("practice-cue").textContent, "3");
  assert.equal(get("event-number").textContent, "1 / 2");
  assert.equal(get("play").textContent, "Pause practice");
  get("loop").checked = false; await get("microphone").onclick();
});
test("Start permission denial and canceled acquisition cannot start the practice clock", async () => {
  get("session").onchange();
  acquisition = () => { throw Object.assign(new Error("denied"), { name: "NotAllowedError" }); };
  await get("play").onclick();
  assert.match(get("status").textContent, /permission was denied/);
  assert.equal(get("practice-cue").textContent, "Ready");
  let resolve;
  acquisition = () => new Promise((done) => { resolve = done; });
  const pending = get("play").onclick();
  assert.equal(get("play").disabled, true);
  await get("microphone").onclick(); const before = stopped;
  resolve(newStream()); await pending;
  animation(performance.now() + 5000);
  assert.equal(stopped, before + 1);
  assert.equal(get("practice-cue").textContent, "Ready");
  assert.equal(get("phrase-progress").value, 0);
  assert.equal(get("play").disabled, false);
});
test("hole lights follow each selected song's actions, including chords, bends and over-notes", () => {
  const litHoles = () => get("harp-holes").children.flatMap((hole, i) => hole.className.includes(" lit") ? [i + 1] : []);
  get("session").value = "0"; get("session").onchange();
  assert.deepEqual(litHoles(), [4, 5, 6]); assert.match(get("harp-direction").textContent, /Draw.*inhale/);
  assert.equal(get("harp-holes").children[3].children[1].textContent, "B4");
  get("next").onclick(); assert.deepEqual(litHoles(), [6]);
  assert.match(get("harp-direction").textContent, /Overblow.*exhale.*advanced/);
  get("session").value = "1"; get("session").onchange();
  assert.equal(get("current-song").textContent, "G exercise");
  assert.deepEqual(litHoles(), [7]);
  get("next").onclick(); assert.deepEqual(litHoles(), [5, 6, 7]);
  assert.match(get("harp-direction").textContent, /Blow.*exhale/);
  get("session").value = "2"; get("session").onchange();
  assert.equal(get("current-song").textContent, "Another song");
  assert.match(get("harp-key").textContent, /C HARMONICA/);
  assert.deepEqual(litHoles(), [3]);
  assert.match(get("harp-direction").textContent, /Draw.*bend 2 semitones/);
  get("next").onclick(); assert.deepEqual(litHoles(), [8]);
  assert.match(get("harp-direction").textContent, /Blow.*bend 1 semitone$/);
  get("next").onclick(); assert.deepEqual(litHoles(), [7]);
  assert.match(get("harp-direction").textContent, /Overdraw.*inhale/);
  assert.match(get("harp-holes").attributes["aria-label"], /C harmonica.*Holes 7/);
  get("session").value = "0"; get("session").onchange();
});
test("a completed run gives a percentage and actionable per-step review that survives replay", async () => {
  get("session").value = "0"; get("session").onchange(); acquisition = newStream;
  const samples = (pitches) => Float32Array.from({ length: 8192 }, (_, i) => pitches.reduce((sum, pitch) => sum + 0.04 * Math.sin(2 * Math.PI * midiHz(pitch) * i / 48000), 0));
  await get("play").onclick(); const start = performance.now();
  microphoneSamples = samples([71, 74, 78]);
  animation(start + 3000); animation(start + 3100); animation(start + 3250);
  assert.equal(get("live-score").textContent, "1 / 2 steps matched");
  assert.match(get("sequence").children[0].children[1].textContent, /Matched/);
  microphoneSamples = samples([68]);
  animation(start + 6200); animation(start + 6300); animation(start + 6400); animation(start + 7050);
  assert.equal(get("results").hidden, false); assert.equal(get("result-score").textContent, "50%");
  assert.match(get("result-summary").textContent, /1 of 2.*1 missed.*0 skipped/);
  assert.match(get("result-context").textContent, /A exercise.*A harp.*50% speed/);
  assert.match(get("result-steps").children[1].children[1].children[1].textContent, /Ab4/);
  assert.ok(get("harp-holes").children.every((hole) => !hole.className.includes(" lit")));
  await get("play").onclick();
  assert.equal(get("live-score").textContent, "0 / 2 steps matched");
  assert.equal(get("result-score").textContent, "50%"); assert.equal(get("result-review").open, false);
  get("result-steps").children[1].children[0].onclick();
  assert.equal(get("target-tab").textContent, "6o"); assert.equal(get("play").textContent, "Start practice");
  assert.equal(get("result-score").textContent, "50%");
  await get("microphone").onclick();
  get("session").value = "2"; get("session").onchange();
  assert.equal(get("results").hidden, true); assert.equal(get("live-score").textContent, "0 / 3 steps matched");
});
test("actual take review retains early notes, plays audio, seeks and survives song changes", async () => {
  get("session").value = "0"; get("session").onchange(); acquisition = newStream;
  await get("play").onclick(); const start = performance.now();
  assert.match(get("recording-state").textContent, /Recording your practice take/);
  const samples = (pitches) => Float32Array.from({ length: 8192 }, (_, i) => pitches.reduce((sum, pitch) => sum + 0.04 * Math.sin(2 * Math.PI * midiHz(pitch) * i / 48000), 0));
  microphoneSamples = samples([60]); animation(start + 50);
  microphoneSamples = samples([71, 74, 78]); animation(start + 3000); animation(start + 3250);
  microphoneSamples = samples([79]); animation(start + 6200); animation(start + 6450); animation(start + 7100);
  await Promise.resolve();
  assert.equal(get("take-panel").open, true); assert.equal(get("play-take").disabled, false);
  assert.equal(get("take-audio").hidden, false); assert.match(get("take-audio").src, /^blob:/);
  const takeId = get("take-select").value, url = get("take-audio").src;
  get("take-seek").value = "0.05"; get("take-seek").oninput();
  assert.match(get("take-heard").textContent, /C4/); assert.equal(get("take-expected").textContent, "Count-in");
  assert.ok(get("take-chart").drawnLabels.includes("C4")); // The early reading survived >6s.
  get("take-seek").value = "6.2"; get("take-seek").oninput();
  assert.match(get("take-heard").textContent, /G5/); assert.match(get("take-expected").textContent, /G5.*6o/);
  const before = stopped; await get("play-take").onclick();
  assert.equal(get("take-audio").paused, false); assert.equal(get("input-state").textContent, "Microphone off");
  assert.equal(stopped, before + 1);
  get("download-take").onclick(); assert.equal(downloads.at(-1).href, url); assert.match(downloads.at(-1).name, /\.webm$/);
  let saved; const original = URL.createObjectURL;
  try {
    URL.createObjectURL = (blob) => { saved = blob; return "blob:take-notes-test"; };
    get("download-take-notes").onclick();
    const data = JSON.parse(await saved.text());
    assert.equal(data.metadata.title, "A exercise"); assert.equal(data.duration, 7.1);
    assert.equal(data.frames[0].detected[0].note, 60); assert.equal(data.frames[0].time, 0.05);
    assert.equal(data.frames.at(-1).time, 7.1); assert.equal(data.reason, "Completed");
  } finally { URL.createObjectURL = original; }
  get("session").value = "2"; get("session").onchange();
  assert.equal(get("take-select").value, takeId); assert.equal(get("take-audio").src, url);
  get("take-audio").pause();
});
test("Finish and review saves a partial take, and the take can be deleted", async () => {
  acquisition = newStream; await get("play").onclick();
  animation(performance.now() + 100); get("finish-review").onclick(); await Promise.resolve();
  assert.equal(get("input-state").textContent, "Microphone off");
  assert.match(get("take-message").textContent, /Finished early/);
  assert.equal(get("play-take").disabled, false);
  const count = get("take-select").children.length, selected = get("take-select").value;
  get("delete-take").onclick();
  assert.equal(get("take-select").children.length, count - 1); assert.notEqual(get("take-select").value, selected);
});
