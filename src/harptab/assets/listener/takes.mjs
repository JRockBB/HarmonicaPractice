// A take owns its audio and full pitch history, independently of the live six-second trail.
export class TakeRecorder {
  constructor({ Recorder = globalThis.MediaRecorder, clock = () => performance.now(), onReady = () => {}, onState = () => {} } = {}) {
    this.Recorder = Recorder; this.clock = clock; this.onReady = onReady; this.onState = onState;
    this.active = null; this.nextId = 1;
  }
  start(stream, metadata) {
    if (this.active) throw new Error("Finish the current take before starting another.");
    const take = { id: this.nextId++, metadata, startedAt: this.clock(), frames: [], duration: 0, blob: null, error: null, state: "recording" };
    this.active = take;
    try {
      if (!this.Recorder) throw new Error("Audio recording is unavailable in this browser. The note timeline is still saved.");
      const mimeType = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4"].find((type) => this.Recorder.isTypeSupported?.(type));
      const recorder = new this.Recorder(stream, mimeType ? { mimeType } : {});
      take.recorder = recorder; const chunks = [];
      recorder.ondataavailable = ({ data }) => { if (data?.size) chunks.push(data); };
      recorder.onerror = ({ error }) => { take.error = `Recording failed: ${error?.message || "audio capture error"}. The note timeline is still available.`; this.onState(take); };
      recorder.onstop = () => {
        if (this.active === take) { this.active = null; take.duration = Math.max(0, (this.clock() - take.startedAt) / 1000); take.reason = "Microphone ended"; }
        const blob = new Blob(chunks, { type: recorder.mimeType || chunks[0]?.type || "audio/webm" });
        if (blob.size) take.blob = blob;
        else take.error ||= "No audio was captured. The note timeline is still available.";
        take.state = "ready"; delete take.recorder;
        this.onReady(take); this.onState(take);
      };
      recorder.start(1000);
    } catch (error) { delete take.recorder; take.error = error.message; }
    this.onState(take); return take;
  }
  addFrame(now, frame) {
    if (!this.active) return;
    this.active.frames.push({ ...frame, time: Math.max(0, (now - this.active.startedAt) / 1000), expected: [...frame.expected], detected: frame.detected.map((p) => ({ ...p })) });
  }
  finish(reason, report = null) {
    const take = this.active; if (!take) return null;
    this.active = null; take.reason = reason; take.report = report;
    take.duration = Math.max(0, (this.clock() - take.startedAt) / 1000);
    take.state = "saving"; this.onState(take);
    if (take.recorder && take.recorder.state !== "inactive") take.recorder.stop();
    else if (!take.recorder) { take.state = "ready"; this.onReady(take); this.onState(take); }
    // An already inactive recorder may still be delivering its final dataavailable/stop events.
    return take;
  }
}

export function takeFrameAt(take, seconds, maxGap = 0.25) {
  let lo = 0, hi = take.frames.length;
  while (lo < hi) { const mid = (lo + hi) >>> 1; if (take.frames[mid].time <= seconds) lo = mid + 1; else hi = mid; }
  const frame = take.frames[lo - 1];
  return frame && seconds - frame.time <= maxGap ? frame : null;
}

export function audioExtension(type) {
  return type.includes("wav") ? "wav" : type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm";
}

export function waveFromAudioBuffer(audio) {
  const channels = audio.numberOfChannels, bytes = audio.length * channels * 2;
  const data = new ArrayBuffer(44 + bytes), view = new DataView(data);
  const label = (offset, value) => { for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i)); };
  label(0, "RIFF"); view.setUint32(4, 36 + bytes, true); label(8, "WAVE");
  label(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
  view.setUint16(22, channels, true); view.setUint32(24, audio.sampleRate, true);
  view.setUint32(28, audio.sampleRate * channels * 2, true); view.setUint16(32, channels * 2, true); view.setUint16(34, 16, true);
  label(36, "data"); view.setUint32(40, bytes, true);
  const samples = Array.from({ length: channels }, (_, channel) => audio.getChannelData(channel));
  for (let i = 0, offset = 44; i < audio.length; i++) for (const channel of samples) {
    const sample = Math.max(-1, Math.min(1, channel[i]));
    view.setInt16(offset, Math.round(sample * (sample < 0 ? 32768 : 32767)), true); offset += 2;
  }
  return new Blob([data], { type: "audio/wav" });
}

export async function seekableAudio(blob, OfflineContext = globalThis.OfflineAudioContext) {
  // Decode the complete recording, then give the player a PCM file with an explicit length.
  // No audio is synthesized, played, or sent anywhere during this conversion.
  const context = new OfflineContext(1, 1, 48000);
  const decoded = await context.decodeAudioData(await blob.arrayBuffer());
  return waveFromAudioBuffer(decoded);
}
