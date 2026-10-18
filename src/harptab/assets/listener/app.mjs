import { DETECTOR, PitchDisplay, detectPitches, comparePitches, noteName, midiHz } from "./pitch.mjs";
import { PracticeEngine } from "./engine.mjs";
import { TakeRecorder } from "./takes.mjs";
import { TakeReview } from "./review.mjs";

const $ = (id) => document.getElementById(id);
let sessions = [], engine, stream = null, context = null, analyser = null, input = null;
let demo = false, requesting = false, requestId = 0, history = [], lastFrame = 0, lastIndex = -1;
let lastReport = null, finishedResults = null;
let reading = { pitches: [], rms: 0, clipped: false, clarity: 0 };
const frame = new Float32Array(DETECTOR.frameSize);
const pitchDisplay = new PitchDisplay();
const status = (message, error = false) => { $("status").textContent = message; $("status").classList.toggle("error", error); };
const sourceTime = (t) => `${Math.floor(t / 60).toString().padStart(2, "0")}:${(t % 60).toFixed(2).padStart(5, "0")}`;
const review = new TakeReview({ get: $, canvas: canvasContext, isRecording: () => !!recorder.active, onPlayback: () => { finishTake("Stopped for review", false); stopInput(); } });
const recorder = new TakeRecorder({
  onReady: (take) => review.add(take),
  onState: (take) => {
    const current = recorder.active || take;
    $("recording-state").textContent = current.state === "recording" ? current.error ? `Audio unavailable · ${current.error}` : "● Recording your practice take locally" : current.state === "saving" ? "Saving your take…" : `Take ${current.id} ready to review${current.error ? " · audio unavailable" : ""}.`;
    $("finish-review").disabled = !recorder.active;
  },
});

function beginTake() {
  $("take-audio").pause();
  $("take-panel").open = false;
  if (stream && !demo) recorder.start(stream, {
    title: engine.session.title, harp: engine.session.harp, speed: engine.speed, mode: engine.mode,
    createdAt: new Date().toISOString(), events: engine.session.events,
  });
}
function finishTake(reason, select = true) {
  if (recorder.active) recorder.active.selectOnReady = select;
  return recorder.finish(reason, engine?.report());
}

function chooseSession() {
  finishTake("Arrangement changed");
  engine = new PracticeEngine(sessions[Number($("session").value)]);
  engine.mode = $("mode").value; engine.speed = Number($("speed").value);
  engine.tolerance = Number($("tolerance").value);
  history = []; lastIndex = -1; lastReport = null; finishedResults = null;
  $("results").hidden = true;
  const session = engine.session;
  $("current-song").textContent = session.title;
  $("song-info").textContent = `${session.harp} harmonica · ${session.events.length} steps · ${sourceTime(session.sourceStart)}–${sourceTime(session.sourceStart + session.duration)} in source · ${session.transpose ? `Shifted ${session.transpose > 0 ? "+" : ""}${session.transpose} semitones` : "Original pitch"}`;
  $("sequence").replaceChildren(...session.events.map((event, i) => {
    const button = document.createElement("button"); button.className = "step";
    button.textContent = event.tab;
    button.setAttribute("aria-label", `Step ${i + 1}: ${event.instruction}`);
    const detail = document.createElement("small"); detail.textContent = `${i + 1} · ${sourceTime(event.sourceStart)}`;
    button.append(detail);
    const outcome = document.createElement("em"); outcome.textContent = "Upcoming"; button.append(outcome);
    button.onclick = () => { engine.seek(i, performance.now()); history = []; status(engine.running ? "Continuing from the selected step." : "Step selected. Press Start practice when ready."); render(); };
    return button;
  }));
  $("harp-holes").replaceChildren(...Array.from({ length: 10 }, (_, i) => {
    const hole = document.createElement("div"); hole.className = "harp-hole";
    const number = document.createElement("strong"); number.textContent = String(i + 1); hole.append(number);
    const note = document.createElement("small"); note.textContent = ""; hole.append(note);
    return hole;
  }));
  status("Press Start practice. It opens the microphone and counts you in.");
  render();
}

function render() {
  if (!engine) return;
  const target = engine.target, rest = engine.resting;
  $("target-note").textContent = rest ? "Rest" : target.notes.join(" + ") || "Rest";
  $("event-number").textContent = `${engine.index + 1} / ${engine.session.events.length}`;
  $("target-tab").textContent = rest ? "—" : target.tab;
  $("instruction").textContent = rest ? "Leave this gap silent." : target.instruction;
  $("omitted").textContent = target.omitted.length ? `Arrangement leaves out ${target.omitted.map(noteName).join(", ")}. These are not targets.` : "";
  const shown = pitchDisplay.value;
  $("heard-note").textContent = shown.pitches.map((p) => noteName(p.note)).join(" + ") || "—";
  $("heard-label").textContent = shown.held ? "LAST HEARD" : "YOU ARE PLAYING";
  $("level").value = reading.rms;
  $("signal-quality").textContent = reading.clipped ? "Input clipping" : shown.held ? "Briefly holding display" : reading.pitches.length > 1 ? "Chord estimate" : "";
  const decibels = 20 * Math.log10(Math.max(reading.rms, 1e-6));
  const inputDetail = reading.clipped ? "Too loud" : reading.reason === "quiet" ? "Below noise gate" : reading.reason === "noisy" ? "Sound detected; pitch unclear" : reading.reason === "ambiguous" ? "Multiple peaks; pitch unclear" : "Pitch detected";
  $("input-detail").textContent = stream || demo ? `${decibels.toFixed(0)} dB · ${inputDetail}` : "Microphone off";
  const expected = rest ? [] : target.pitches;
  const comparison = comparePitches(expected, reading.pitches, engine.tolerance);
  const card = document.querySelector(".heard");
  card.classList.toggle("match", comparison.match && !reading.clipped);
  card.classList.toggle("mismatch", !!reading.pitches.length && !comparison.match);
  card.classList.toggle("held", shown.held);
  let feedback = stream || demo ? "Waiting for a clear note…" : "Press Start practice, or start the microphone to check a note.";
  if (reading.clipped) feedback = "Too loud — move a little farther from the microphone.";
  else if (engine.running && engine.countdown) feedback = "Get ready — begin when the countdown ends.";
  else if (engine.running && engine.release) feedback = "Matched. Pause your breath briefly before the next step.";
  else if (rest) feedback = reading.pitches.length ? "This is a rest — pause your breath." : "Good, keep this gap silent.";
  else if (comparison.match) feedback = expected.length > 1 ? "Chord pitches match." : "On target.";
  else if (reading.pitches.length) {
    if (expected.length === 1 && reading.pitches.length === 1) {
      const offset = (reading.pitches[0].midi - expected[0]) * 100;
      feedback = Math.abs(offset) < 100 ? (offset < 0 ? "A little flat — raise the pitch." : "A little sharp — lower the pitch.") : `Aim for ${target.notes[0]}.`;
    } else feedback = `Still need ${comparison.missing.map(noteName).join(", ") || "a cleaner chord"}${comparison.extra.length ? "; extra or off-pitch notes detected" : ""}.`;
  }
  else if (stream || demo) {
    feedback = reading.reason === "quiet" ? "Input is quiet. Keep playing, move closer, or lower the noise gate." : "I hear sound, but the pitch is unclear. Try a steady note.";
    if (shown.held) feedback = "Last detected note — listening for the next clear reading.";
  }
  $("feedback").textContent = feedback;
  $("cents").textContent = shown.pitches.length ? `${shown.held ? "Last reading: " : ""}${shown.pitches.map((p) => `${noteName(p.note)} ${p.cents >= 0 ? "+" : ""}${p.cents.toFixed(0)}¢`).join(" · ")}` : "Pitch feedback appears here.";
  const strongest = Math.max(0, ...shown.pitches.map((p) => p.strength));
  $("heard-details").textContent = shown.pitches.map((p) => {
    const choices = engine.session.fingerings?.[p.note] || [];
    const fingering = choices.length ? choices.map((choice) => `${choice.tab}: ${choice.instruction}`).join(" / ") : engine.session.fingerings ? "No standard fingering on this harp" : "Fingering information unavailable";
    return `${noteName(p.note)} · ${p.hz.toFixed(1)} Hz · ${Math.round(p.strength / strongest * 100)}% relative level · ${fingering}`;
  }).join("\n");
  $("play").disabled = requesting;
  $("play").textContent = requesting ? "Waiting for microphone…" : engine.running ? "Pause practice" : engine.done ? "Play again" : "Start practice";
  $("microphone").textContent = requesting ? "Cancel microphone request" : stream ? "Stop microphone" : "Start microphone";
  $("input-state").textContent = demo ? "DEMO · Simulated input" : stream ? "Microphone listening" : "Microphone off";
  $("input-state").className = `badge ${demo ? "demo" : stream ? "active" : ""}`;
  $("demo").textContent = demo ? "Stop demo" : "Try visual demo";
  const report = engine.report();
  $("live-score").textContent = `${demo ? "DEMO · " : ""}${report.matched} / ${report.total} steps matched`;
  $("live-misses").textContent = `${report.missed} missed · ${report.skipped} skipped`;
  for (const [i, button] of Array.from($("sequence").children).entries()) {
    const outcome = report.steps[i].status;
    button.classList.toggle("current", i === engine.index);
    button.classList.toggle("hit", engine.hit.has(i));
    button.classList.toggle("missed", outcome === "missed");
    button.classList.toggle("skipped", outcome === "skipped");
    button.children[1].textContent = outcomeLabel(outcome);
    button.setAttribute("aria-label", `Step ${i + 1}: ${engine.session.events[i].instruction}. ${outcomeLabel(outcome)}`);
    button.setAttribute("aria-current", i === engine.index ? "step" : "false");
  }
  if (lastIndex !== engine.index) {
    const sequence = $("sequence"), button = sequence.children[engine.index];
    sequence.scrollLeft = Math.max(0, button.offsetLeft - sequence.offsetLeft - (sequence.clientWidth - button.offsetWidth) / 2);
    lastIndex = engine.index;
  }
  drawTuner(expected);
  renderPractice();
  renderHarmonica();
  captureResult();
}

function outcomeLabel(outcome) {
  return { matched: "✓ Matched", missed: "× Missed", skipped: "↷ Skipped", unavailable: "Unavailable", working: "Listening", upcoming: "Upcoming" }[outcome];
}

function reviewDetail(step) {
  if (step.status === "unavailable") return "No playable voicing on this harp; excluded from the score.";
  if (step.status === "matched") return "Held a matching note or chord.";
  if (step.status === "skipped") return "Manually skipped; no match credit.";
  if (!step.frames) return "No reading captured during this step.";
  if (step.matching) return "Matched briefly, but not long enough. Hold it steady.";
  const notes = (pitches) => pitches.map(noteName).join(", ");
  return {
    quiet: "No note detected above the noise gate.",
    unclear: "Sound was present, but the listener could not identify a clear pitch.",
    clipped: "Input was too loud to score. Move farther from the microphone.",
    tuning: `Right note names, but outside the ±${lastReport.tolerance}¢ tuning range.`,
    extra: `Extra or different notes detected: ${notes(step.extra)}.${step.missing.length ? ` Target notes not matched: ${notes(step.missing)}.` : ""}`,
    missing: `Incomplete chord. Notes not matched: ${notes(step.missing)}.`,
  }[step.reason] || "No sustained match detected.";
}

function captureResult() {
  if (!engine.done || finishedResults === engine.results) return;
  finishTake("Completed");
  finishedResults = engine.results;
  lastReport = { ...engine.report(), tolerance: engine.tolerance, demo, speed: engine.speed, mode: engine.mode };
  $("results").hidden = false;
  $("result-review").open = !$("loop").checked;
  $("result-title").textContent = demo ? "Demo result · simulated input" : "Your last run";
  $("result-score").textContent = lastReport.percent === null ? "—" : `${lastReport.percent}%`;
  $("result-summary").textContent = `${lastReport.matched} of ${lastReport.total} playable steps matched · ${lastReport.missed} missed · ${lastReport.skipped} skipped`;
  $("result-context").textContent = `${engine.session.title} · ${engine.session.harp} harp · ${lastReport.speed * 100}% speed · ${lastReport.mode === "timed" ? "Follow along" : "Step by step"}${lastReport.unavailable ? ` · ${lastReport.unavailable} unavailable, excluded` : ""}`;
  $("result-advice").textContent = !lastReport.total ? "This arrangement has no playable targets. Choose another arrangement." : lastReport.matched === lastReport.total ? "Every step matched. Try another run, or increase the speed." : !lastReport.steps.some((step) => step.frames && step.reason !== "quiet") && !lastReport.matched ? "No clear playing was captured. Check the input meter and microphone before trying again." : "Review the marked steps below. Select one to practice it again.";
  $("result-steps").replaceChildren(...lastReport.steps.map((step) => {
    const row = document.createElement("div"); row.className = `result-step ${step.status}`;
    const button = document.createElement("button"); button.textContent = `${step.index + 1}. ${engine.session.events[step.index].tab}`;
    button.setAttribute("aria-label", `Practice step ${step.index + 1}`);
    button.onclick = () => { finishTake("Review step selected"); engine.reset(); engine.seek(step.index, performance.now()); status("Review step selected. Press Start practice to try it again."); render(); };
    const detail = document.createElement("div");
    const label = document.createElement("strong"); label.textContent = outcomeLabel(step.status); detail.append(label);
    const reason = document.createElement("p"); reason.textContent = reviewDetail(step); detail.append(reason);
    row.append(button); row.append(detail); return row;
  }));
}

function renderHarmonica() {
  const silent = engine.done || engine.resting || engine.release;
  const actions = silent ? [] : engine.target.actions || [];
  const first = actions[0], technique = first?.technique;
  const draw = ["draw", "draw_bend", "overdraw"].includes(technique);
  const advanced = ["overblow", "overdraw"].includes(technique);
  const bend = first?.bend_semitones || 0;
  const direction = !first ? engine.done ? "Phrase complete" : engine.release ? "Release · pause your breath" : engine.resting ? "Rest · no holes" : "No playable holes" : `${draw ? "↓" : "↑"} ${advanced ? draw ? "Overdraw" : "Overblow" : draw ? "Draw" : "Blow"} · ${draw ? "inhale" : "exhale"}${bend ? ` · bend ${bend} semitone${bend > 1 ? "s" : ""}` : advanced ? " · advanced" : ""}`;
  $("harp-direction").textContent = direction;
  $("harp-key").textContent = `${engine.session.harp} HARMONICA · HOLES TO PLAY`;
  $("harp-holes").setAttribute("aria-label", `${engine.session.harp} harmonica. ${direction}${first ? `. Holes ${actions.map((a) => a.hole).join(", ")}` : ""}`);
  for (const [index, hole] of Array.from($("harp-holes").children).entries()) {
    const action = actions.find((a) => a.hole === index + 1);
    hole.className = `harp-hole${action ? ` lit ${draw ? "draw" : "blow"}${advanced || bend ? " technique" : ""}${engine.countdown || !engine.running ? " preview" : ""}` : ""}`;
    hole.children[1].textContent = action ? noteName(action.pitch) : "";
  }
}

function renderPractice() {
  const target = engine.target;
  const next = engine.session.events[engine.index + 1];
  const end = target.start + target.duration;
  const remaining = Math.max(0, (engine.resting ? (next?.start ?? engine.session.duration) : end) - engine.position) / engine.speed;
  $("practice-cue").textContent = engine.done ? "Complete" : engine.countdown && engine.running ? String(Math.ceil(engine.countdown)) : !engine.running ? "Ready" : engine.release ? "Release" : engine.resting ? "Rest" : !target.pitches.length ? "Skip" : "Play";
  $("practice-help").textContent = engine.done ? "Run it again, or select a step to work on." : !engine.running ? "Press Start practice when ready." : engine.countdown ? `Get ready: ${target.tab} · ${target.instruction}` : engine.release ? "Briefly stop your breath, then play the next step. Use Next to skip." : engine.mode === "timed" ? "Follow the moving line. Misses and extra notes won’t stop the phrase." : "Hold a matching note/chord, or use Next to move on at any time.";
  $("time-left").textContent = engine.done ? "End of phrase" : engine.countdown && engine.running ? "Count-in · get ready" : engine.mode === "timed" ? `${engine.resting ? "Rest" : "Hold"} ${remaining.toFixed(2)}s · ${engine.speed * 100}% speed` : engine.release ? "Waiting for a breath break" : "Advance on a match, or use Next";
  $("up-next").textContent = next ? `Next: ${next.tab} · ${next.notes.join(" + ") || "Rest"}` : "Last step";
  $("phrase-progress").value = engine.done ? 1 : engine.mode === "timed" ? engine.position / engine.session.duration : engine.index / engine.session.events.length;
  drawTimeline();
}

function drawTimeline() {
  const { ctx, width, height } = canvasContext("timeline");
  const pitches = engine.session.events.flatMap((event) => event.pitches);
  if (!pitches.length) pitches.push(60, 72);
  const low = Math.min(...pitches) - 1, high = Math.max(...pitches) + 1;
  const span = Math.min(engine.session.duration, 8 * engine.speed);
  const left = Math.max(0, Math.min(engine.session.duration - span, engine.position - span * 0.2));
  const x = (position) => 40 + (position - left) / span * (width - 50);
  const y = (pitch) => height - 14 - (pitch - low) / Math.max(2, high - low) * (height - 40);
  ctx.font = "10px Segoe UI";
  for (const pitch of [...new Set(pitches)].sort((a, b) => a - b)) {
    ctx.fillStyle = "#a8b7b3"; ctx.fillText(noteName(pitch), 0, y(pitch) + 3);
  }
  engine.session.events.forEach((event, i) => {
    if (event.start + event.duration < left || event.start > left + span) return;
    const start = Math.max(40, x(event.start)), stop = Math.min(width, x(event.start + event.duration));
    ctx.fillStyle = i === engine.index ? "#b4ec94" : i < engine.index ? "#486440" : "#66817b";
    for (const pitch of event.pitches) ctx.fillRect(start, y(pitch) - 4, Math.max(1, stop - start), 8);
  });
  const cursor = Math.min(width - 10, x(engine.position));
  ctx.strokeStyle = "#ffd39c"; ctx.lineWidth = 2;
  ctx.beginPath(); ctx.moveTo(cursor, 18); ctx.lineTo(cursor, height); ctx.stroke();
  ctx.fillStyle = "#ffd39c"; ctx.fillText("NOW", Math.max(40, cursor - 12), 12);
}

function canvasContext(id) {
  const canvas = $(id), rect = canvas.getBoundingClientRect(), ratio = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.round(rect.width * ratio)), height = Math.max(1, Math.round(rect.height * ratio));
  if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
  const ctx = canvas.getContext("2d"); ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, rect.width, rect.height);
  return { ctx, width: rect.width, height: rect.height };
}

function drawTuner(expected) {
  const { ctx, width, height } = canvasContext("tuner");
  ctx.fillStyle = "#354647"; ctx.fillRect(0, height / 2 - 1, width, 2);
  ctx.fillStyle = "#486440"; ctx.fillRect(width * 0.4, 3, width * 0.2, height - 6);
  ctx.fillStyle = "#b4ec94"; ctx.fillRect(width / 2 - 1, 1, 2, height - 2);
  const shown = pitchDisplay.value;
  if (expected.length !== 1 || shown.pitches.length !== 1) return;
  const offset = Math.max(-100, Math.min(100, (shown.pitches[0].midi - expected[0]) * 100));
  ctx.fillStyle = "#ffd39c"; ctx.beginPath(); ctx.arc(width * (0.5 + offset / 210), height / 2, 5, 0, 2 * Math.PI); ctx.fill();
}

function drawTrace(now) {
  if (!engine) return;
  const { ctx, width, height } = canvasContext("trace");
  const targets = engine.session.events.flatMap((e) => e.pitches);
  if (!targets.length) targets.push(60, 72);
  const heard = history.flatMap((point) => point.pitches);
  const low = Math.floor(Math.min(...targets, ...heard)) - 2;
  const high = Math.ceil(Math.max(...targets, ...heard)) + 2;
  const y = (midi) => height - 18 - (midi - low) / Math.max(4, high - low) * (height - 32);
  const x = (at) => 43 + (at - now + 6000) / 6000 * (width - 52);
  ctx.font = "10px Segoe UI";
  for (let note = low; note <= high; note++) {
    if (high - low > 24 && note % 2) continue;
    ctx.fillStyle = "#a8b7b3"; ctx.fillText(noteName(note), 0, y(note) + 3);
    ctx.strokeStyle = "#304142"; ctx.beginPath(); ctx.moveTo(40, y(note)); ctx.lineTo(width, y(note)); ctx.stroke();
  }
  for (const point of history) {
    const px = x(point.at);
    ctx.strokeStyle = "#b4ec94"; ctx.lineWidth = 3;
    for (const note of point.expected) { ctx.beginPath(); ctx.moveTo(px - 2, y(note)); ctx.lineTo(px + 3, y(note)); ctx.stroke(); }
    ctx.fillStyle = "#ffd39c";
    for (const pitch of point.pitches) { ctx.beginPath(); ctx.arc(px, y(pitch), 2.3, 0, 2 * Math.PI); ctx.fill(); }
  }
}

async function devices() {
  const list = await navigator.mediaDevices.enumerateDevices();
  const selected = $("device").value;
  $("device").replaceChildren(new Option("System default", ""), ...list.filter((d) => d.kind === "audioinput").map((d, i) => new Option(d.label || `Microphone ${i + 1}`, d.deviceId)));
  $("device").value = selected;
}

function stopInput() {
  finishTake("Microphone stopped");
  requestId++; requesting = false;
  const tracks = stream?.getTracks() || []; stream = null;
  tracks.forEach((track) => { track.onended = null; track.stop(); });
  input?.disconnect(); input = null; analyser = null;
  if (context) { context.close().catch(() => {}); context = null; }
  demo = false; engine?.pause(); reading = { pitches: [], rms: 0, clipped: false, clarity: 0 };
  pitchDisplay.reset();
  render();
}

async function startMicrophone() {
  if (stream || requesting) { stopInput(); status("Microphone stopped."); return; }
  stopInput();
  if (!navigator.mediaDevices?.getUserMedia) { status("Microphone access is unavailable. Open this localhost URL in a browser with microphone support.", true); return; }
  const id = ++requestId; requesting = true; render();
  status("Allow microphone access in your browser to begin listening.");
  try {
    const selected = $("device").value;
    const audio = { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 };
    if (selected) audio.deviceId = { exact: selected };
    const acquired = await navigator.mediaDevices.getUserMedia({ audio, video: false });
    if (id !== requestId) { acquired.getTracks().forEach((track) => track.stop()); return; }
    stream = acquired;
    context = new AudioContext(); await context.resume();
    if (id !== requestId) return;
    analyser = context.createAnalyser(); analyser.fftSize = DETECTOR.frameSize;
    input = context.createMediaStreamSource(stream); input.connect(analyser);
    // Deliberately no connection to speakers: avoid monitoring/feedback loops.
    stream.getTracks().forEach((track) => { track.onended = () => { stopInput(); status("Microphone disconnected. Reconnect it and start again.", true); }; });
    requesting = false; render(); status("Listening. Play a note to check your pitch, or press Start practice.");
    devices().catch(() => {}); // Listing devices must not delay starting a working stream.
    return true;
  } catch (error) {
    if (id !== requestId) return;
    stopInput();
    const messages = { NotAllowedError: "Microphone permission was denied. Allow it in your browser’s site settings, then try again.", NotFoundError: "No microphone was found. Connect one and try again.", NotReadableError: "The microphone is unavailable or busy. Check the device and other audio apps.", OverconstrainedError: "The selected microphone is unavailable. Choose System default and try again." };
    status(messages[error.name] || `Could not start listening: ${error.message}`, true);
  }
}

function demoFrame(now) {
  // Labeled visual-only simulation exercises the same detector as microphone input.
  frame.fill(0);
  if (engine.release || engine.resting || engine.countdown || engine.done) return;
  const pitches = engine.target.pitches;
  for (let i = 0; i < frame.length; i++) {
    const t = i / 48000 + now / 1000;
    for (const note of pitches) {
      const phase = 2 * Math.PI * midiHz(note) * t;
      frame[i] += 0.08 / Math.max(1, pitches.length) * (Math.sin(phase) + 0.4 * Math.sin(2 * phase) + 0.2 * Math.sin(3 * phase));
    }
  }
}

function tick(now) {
  if (engine && now - lastFrame >= 40) {
    lastFrame = now;
    if (demo) demoFrame(now);
    else if (analyser) analyser.getFloatTimeDomainData(frame);
    if (demo || analyser) {
      const gate = 10 ** (Number($("gate").value) / 20);
      reading = detectPitches(frame, demo ? 48000 : context.sampleRate, { noiseGate: gate });
      pitchDisplay.update(reading, now);
      const wasRunning = engine.running, previousTarget = engine.target, previousIndex = engine.index, wasReleasing = engine.release;
      engine.update(now, reading.clipped ? [] : reading.pitches, reading.rms < gate, reading.clipped ? "clipped" : reading.reason);
      const target = engine.mode === "wait" ? previousTarget : engine.target;
      const phase = engine.mode === "wait" ? wasReleasing ? "release" : "play" : engine.countdown ? "count-in" : engine.resting || engine.done ? "rest" : "play";
      const expected = phase === "play" ? target.pitches : [];
      if (wasRunning) recorder.addFrame(now, {
        phase, step: engine.mode === "wait" ? previousIndex : engine.index, position: engine.position,
        expected, detected: reading.pitches, rms: reading.rms, clipped: reading.clipped, reason: reading.reason,
      });
      history.push({
        at: now, expected, pitches: reading.pitches.map((p) => p.midi),
        details: reading.pitches.map(({ note, hz, cents, strength }) => ({ note, hz, cents, strength })),
        rms: reading.rms, reason: reading.reason,
      });
      if (engine.done) {
        captureResult();
        status(`Phrase complete · ${engine.hit.size} of ${engine.session.events.filter((e) => e.pitches.length).length} steps matched${demo ? " with simulated input" : ""}.`);
        if ($("loop").checked) { engine.reset(); engine.start(now); beginTake(); history = []; }
      } else if (engine.running) {
        status(engine.countdown ? `Get ready… ${Math.ceil(engine.countdown)}` : engine.release ? "Matched. Pause your breath briefly for the next step." : engine.resting ? "Rest — let the phrase breathe." : !engine.target.pitches.length ? "This note is unavailable on this harp. Use Next to skip it." : engine.mode === "wait" ? "Hold the target until it matches. Then pause your breath." : `Following the timing · ${(engine.position / engine.speed).toFixed(1)}s`);
      }
    }
    history = history.filter((point) => now - point.at <= 6000);
    render(); drawTrace(now);
    if (!$("take-audio").paused) review.update();
  }
  requestAnimationFrame(tick);
}

$("microphone").onclick = startMicrophone;
$("device").onchange = () => { if (stream) { stopInput(); startMicrophone(); } };
$("demo").onclick = () => { const start = !demo; stopInput(); demo = start; engine.reset(); history = []; status(demo ? "Demo uses simulated notes; your microphone is off. Press Start practice to watch it progress." : "Demo stopped."); render(); };
$("play").onclick = async () => {
  if (engine.running) { engine.pause(); finishTake("Paused"); status("Practice paused. Your take is being saved for review; continuing records a new take."); render(); return; }
  if (requesting) return;
  const selected = engine;
  if (!stream && !demo && !await startMicrophone()) return;
  if (selected !== engine || document.hidden) return;
  engine.start(performance.now());
  beginTake();
  $("result-review").open = false;
  status(engine.mode === "timed" ? "Get ready — practice starts after the count-in." : "Step-by-step practice started. Match the target or use Next.");
  render();
};
$("restart").onclick = () => { const running = engine.running; finishTake("Restarted"); engine.reset(); history = []; if (running) { engine.start(performance.now()); beginTake(); } status(running ? engine.mode === "timed" ? "Counting in from the beginning." : "Starting from the beginning." : "Ready from the beginning."); render(); };
$("previous").onclick = () => { engine.step(-1, performance.now()); status(engine.running ? "Continuing from the previous step." : "Press Start practice to resume here."); render(); };
$("next").onclick = () => { engine.step(1, performance.now()); status(engine.done ? "End of phrase." : engine.running ? "Continuing with the next step." : "Press Start practice to resume here."); render(); };
$("session").onchange = chooseSession;
$("mode").onchange = () => { finishTake("Mode changed"); engine.reset(); engine.mode = $("mode").value; history = []; status("Mode changed. Press Start practice when ready."); render(); };
$("speed").onchange = () => { finishTake("Speed changed"); engine.pause(); engine.speed = Number($("speed").value); status("Speed changed. Press Start practice to resume."); render(); };
$("finish-review").onclick = () => { finishTake("Finished early"); stopInput(); status("Practice stopped. Your take is being saved below for playback and review."); render(); };
$("gate").oninput = () => { $("gate-value").textContent = `${$("gate").value} dB`; };
$("tolerance").oninput = () => { engine.tolerance = Number($("tolerance").value); $("tolerance-value").textContent = `±${engine.tolerance} cents`; };
$("guide").onclick = () => {
  const blob = new Blob([engine.session.guide], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob), anchor = document.createElement("a");
  anchor.href = url; anchor.download = `${engine.session.harp.toLowerCase()}-practice-guide.md`; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
$("diagnostics").onclick = () => {
  // Export only note measurements already shown by the listener, never microphone audio.
  const payload = {
    version: 1, harp: engine.session.harp, gateDb: Number($("gate").value),
    sampleRate: context?.sampleRate ?? null,
    frames: history.map((point) => ({
      secondsAgo: (performance.now() - point.at) / 1000,
      expected: point.expected, detected: point.details,
      rms: point.rms, reason: point.reason,
    })),
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob), anchor = document.createElement("a");
  anchor.href = url; anchor.download = "harptab-note-diagnostics.json"; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  status("Saved six seconds of note measurements locally. This diagnostics file contains no audio; nothing was uploaded.");
};
window.addEventListener("pagehide", stopInput);
document.addEventListener("visibilitychange", () => { if (document.hidden) { stopInput(); status("Listening stopped while this tab was hidden. Start the microphone to resume."); } });

try {
  const response = await fetch("/api/sessions");
  if (!response.ok) throw new Error(`Server returned ${response.status}`);
  ({ sessions } = await response.json());
  $("session").replaceChildren(...sessions.map((session, i) => new Option(`${session.title} · ${session.harp} harp · ${sourceTime(session.sourceStart)}`, i)));
  chooseSession(); requestAnimationFrame(tick);
} catch (error) { status(`Could not load your practice session: ${error.message}. Restart the local server and reload.`, true); }
