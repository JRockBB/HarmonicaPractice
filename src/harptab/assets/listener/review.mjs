import { noteName } from "./pitch.mjs";
import { audioExtension, seekableAudio, takeFrameAt } from "./takes.mjs";

export class TakeReview {
  constructor({ get, canvas, onPlayback, isRecording = () => false }) {
    this.get = get; this.canvas = canvas; this.onPlayback = onPlayback;
    this.isRecording = isRecording;
    this.takes = []; this.selected = null; this.cursor = 0;
    const audio = get("take-audio");
    get("take-select").onchange = () => this.select(Number(get("take-select").value));
    get("take-seek").oninput = () => this.seek(Number(get("take-seek").value));
    get("take-step").onchange = () => this.seek(Number(get("take-step").value));
    get("take-chart").onclick = (event) => {
      if (!this.selected) return;
      const rect = get("take-chart").getBoundingClientRect();
      this.seek((event.clientX - rect.left - 43) / Math.max(1, rect.width - 52) * this.selected.duration);
    };
    get("play-take").onclick = async () => {
      if (!this.selected?.blob) return;
      if (this.cursor >= this.selected.duration - 0.02) this.cursor = this.selected.frames.find((frame) => frame.phase === "play")?.time || 0;
      this.onPlayback();
      try { audio.currentTime = this.cursor; await audio.play(); }
      catch (error) { get("take-message").textContent = `Could not play this recording: ${error.message}. You can still download it.`; }
    };
    audio.onplay = () => this.onPlayback();
    audio.ontimeupdate = () => this.update();
    audio.onseeked = () => this.update();
    audio.onloadedmetadata = () => { if (this.selected?.blob) { try { audio.currentTime = this.cursor; } catch {} } };
    audio.onerror = () => { get("take-message").textContent = "This browser could not play the recording. Download the audio to open it in another player."; };
    get("download-take").onclick = () => this.download(false);
    get("download-take-notes").onclick = () => this.download(true);
    get("delete-take").onclick = () => this.remove();
    this.controls();
  }
  controls() {
    const chosen = !!this.selected, audio = !!this.selected?.blob;
    for (const id of ["take-select", "take-seek", "take-step", "download-take-notes", "delete-take"]) this.get(id).disabled = !chosen;
    for (const id of ["play-take", "download-take"]) this.get(id).disabled = !audio;
    this.get("take-audio").hidden = !audio;
    this.get("take-detail").hidden = !chosen;
  }
  async add(take) {
    if (take.blob && globalThis.OfflineAudioContext) {
      try { take.blob = await seekableAudio(take.blob); }
      catch { take.playbackWarning = "Audio is available in the browser's original format. WAV preparation failed; seeking may depend on your browser. You can download the audio and full note timeline."; }
    }
    if (take.blob) take.url = URL.createObjectURL(take.blob);
    this.takes.push(take); this.takes.sort((a, b) => a.id - b.id);
    this.options();
    if (!this.selected || take.id > this.selected.id && take.selectOnReady !== false && this.get("take-audio").paused) this.select(take.id);
  }
  options() {
    this.get("take-select").replaceChildren(...this.takes.map((take) => new Option(`Take ${take.id} · ${take.metadata.title} · ${take.metadata.harp} harp · ${take.duration.toFixed(1)}s · ${take.reason}`, take.id)));
    if (this.selected) this.get("take-select").value = String(this.selected.id);
  }
  select(id) {
    const take = this.takes.find((t) => t.id === id); if (!take) return;
    const audio = this.get("take-audio"); audio.pause();
    this.selected = take; this.get("take-select").value = String(id);
    if (!this.isRecording()) this.get("take-panel").open = true;
    this.cursor = take.frames.find((frame) => frame.phase === "play")?.time || 0;
    if (take.url) audio.src = take.url; else audio.removeAttribute("src");
    audio.load();
    const steps = new Map();
    for (const frame of take.frames) if (frame.phase === "play" && !steps.has(frame.step)) steps.set(frame.step, frame.time);
    this.get("take-step").replaceChildren(new Option("Beginning (includes count-in)", "0"), ...Array.from(steps, ([step, time]) => new Option(`Step ${step + 1}: ${take.metadata.events[step].tab} · ${time.toFixed(2)}s`, time)));
    this.get("take-seek").max = String(Math.max(0.01, take.duration));
    this.get("take-message").textContent = take.error || take.playbackWarning || `Your microphone recording · ${take.reason} · ${take.metadata.speed * 100}% practice speed. Playback starts at your first target; choose Beginning to hear the count-in.`;
    this.controls(); this.draw();
  }
  seek(time) {
    if (!this.selected) return;
    this.cursor = Math.max(0, Math.min(this.selected.duration, time));
    if (this.selected.blob) { try { this.get("take-audio").currentTime = this.cursor; } catch {} }
    this.draw();
  }
  update() {
    if (!this.selected) return;
    this.cursor = Math.max(0, Math.min(this.selected.duration, this.get("take-audio").currentTime || 0));
    this.draw();
  }
  draw() {
    const take = this.selected; if (!take) return;
    const $ = this.get, frame = takeFrameAt(take, this.cursor);
    $("take-seek").value = String(this.cursor);
    $("take-time").textContent = `${this.cursor.toFixed(2)} / ${take.duration.toFixed(2)}s`;
    $("take-expected").textContent = frame ? frame.expected.length ? `${frame.expected.map(noteName).join(" + ")} · ${take.metadata.events[frame.step]?.tab || ""}` : frame.phase === "count-in" ? "Count-in" : "Rest / breath break" : "No target reading at this time";
    $("take-heard").textContent = frame ? frame.detected.map((p) => `${noteName(Math.round(p.midi))} (${p.cents >= 0 ? "+" : ""}${p.cents.toFixed(0)}¢)`).join(" + ") || "No clear note detected" : "No microphone reading at this time";
    const { ctx, width, height } = this.canvas("take-chart");
    let low = Infinity, high = -Infinity;
    for (const sample of take.frames) for (const pitch of [...sample.expected, ...sample.detected.map((p) => p.midi)]) { low = Math.min(low, pitch); high = Math.max(high, pitch); }
    if (!Number.isFinite(low)) { low = 60; high = 72; }
    low = Math.floor(low) - 1; high = Math.ceil(high) + 1;
    const y = (pitch) => height - 30 - (pitch - low) / Math.max(2, high - low) * (height - 48);
    const x = (time) => 43 + time / Math.max(0.01, take.duration) * (width - 52);
    ctx.font = "10px Segoe UI";
    for (let pitch = low; pitch <= high; pitch++) {
      if (high - low > 24 && pitch % 2) continue;
      ctx.fillStyle = "#a8b7b3"; ctx.fillText(noteName(pitch), 0, y(pitch) + 3);
    }
    for (const sample of take.frames) {
      const px = x(sample.time);
      ctx.strokeStyle = "#b4ec94"; ctx.lineWidth = 3;
      for (const pitch of sample.expected) { ctx.beginPath(); ctx.moveTo(px - 2, y(pitch)); ctx.lineTo(px + 2, y(pitch)); ctx.stroke(); }
      ctx.fillStyle = "#ffd39c";
      for (const pitch of sample.detected) { ctx.beginPath(); ctx.arc(px, y(pitch.midi), 2, 0, Math.PI * 2); ctx.fill(); }
    }
    for (let i = 0; i <= 5; i++) { ctx.fillStyle = "#a8b7b3"; ctx.fillText(`${(take.duration * i / 5).toFixed(1)}s`, Math.min(width - 30, x(take.duration * i / 5)), height - 6); }
    ctx.strokeStyle = "#edf4ea"; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(x(this.cursor), 0); ctx.lineTo(x(this.cursor), height - 20); ctx.stroke();
  }
  download(notes) {
    const take = this.selected; if (!take || !notes && !take.blob) return;
    const anchor = document.createElement("a");
    const name = `${take.metadata.title}-${take.metadata.harp}-take-${take.id}`.replace(/[<>:"/\\|?*]/g, "_");
    if (notes) {
      const { metadata, frames, duration, reason, report } = take;
      anchor.href = URL.createObjectURL(new Blob([JSON.stringify({ version: 1, metadata, frames, duration, reason, report }, null, 2)], { type: "application/json" }));
      anchor.download = `${name}-notes.json`; setTimeout(() => URL.revokeObjectURL(anchor.href), 1000);
    } else { anchor.href = take.url; anchor.download = `${name}.${audioExtension(take.blob.type)}`; }
    anchor.click();
  }
  remove() {
    if (!this.selected) return;
    const take = this.selected, audio = this.get("take-audio"); audio.pause(); audio.removeAttribute("src"); audio.load();
    if (take.url) URL.revokeObjectURL(take.url);
    this.takes = this.takes.filter((t) => t !== take); this.selected = null; this.options();
    if (this.takes.length) this.select(this.takes.at(-1).id);
    else { this.get("take-message").textContent = "Start practice to record a new take."; this.controls(); }
  }
}
