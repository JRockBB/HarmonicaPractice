// Target-independent spectral pitch estimates. All audio remains in this browser.
export const DETECTOR = Object.freeze({
  frameSize: 8192, minMidi: 48, maxMidi: 108, noiseGate: 10 ** (-50 / 20),
  relativePeak: 0.065, noiseRatio: 10, harmonicCents: 60,
  relativeVoice: 0.18, // Reject faint independent tones relative to the strongest fundamental.
  minClarity: 0.48, maxVoices: 4, maxHarmonic: 32,
});
export const midiHz = (midi) => 440 * 2 ** ((midi - 69) / 12);
export const hzMidi = (hz) => 69 + 12 * Math.log2(hz / 440);
export const noteName = (midi) => ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"][((midi % 12) + 12) % 12] + (Math.floor(midi / 12) - 1);

function spectrum(samples) {
  const n = samples.length;
  const real = new Float64Array(n), imag = new Float64Array(n);
  const mean = samples.reduce((sum, value) => sum + value, 0) / n;
  for (let i = 0; i < n; i++) real[i] = (samples[i] - mean) * (0.5 - 0.5 * Math.cos(2 * Math.PI * i / (n - 1)));
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) [real[i], real[j]] = [real[j], real[i]];
  }
  for (let size = 2; size <= n; size *= 2) {
    const angle = -2 * Math.PI / size, wr = Math.cos(angle), wi = Math.sin(angle);
    for (let offset = 0; offset < n; offset += size) {
      let cr = 1, ci = 0;
      for (let j = 0; j < size / 2; j++) {
        const a = offset + j, b = a + size / 2;
        const tr = cr * real[b] - ci * imag[b], ti = cr * imag[b] + ci * real[b];
        real[b] = real[a] - tr; imag[b] = imag[a] - ti;
        real[a] += tr; imag[a] += ti;
        [cr, ci] = [cr * wr - ci * wi, cr * wi + ci * wr];
      }
    }
  }
  return Float64Array.from(real.subarray(0, n / 2), (v, i) => Math.hypot(v, imag[i]));
}

export function detectPitches(samples, sampleRate, options = {}) {
  const p = { ...DETECTOR, ...options };
  if (samples.length < 1024 || (samples.length & (samples.length - 1)) || !Number.isFinite(sampleRate) || sampleRate < 8000) throw new Error("Expected power-of-two audio frame and valid sample rate");
  let energy = 0, peak = 0;
  for (const value of samples) { energy += value * value; peak = Math.max(peak, Math.abs(value)); }
  const rms = Math.sqrt(energy / samples.length);
  const result = { pitches: [], rms, clipped: peak >= 0.98, clarity: 0, reason: "quiet" };
  if (!Number.isFinite(rms) || rms < p.noiseGate) return result;
  const bins = spectrum(samples), step = sampleRate / samples.length;
  const first = Math.max(2, Math.floor(midiHz(p.minMidi - 0.5) / step));
  const last = Math.min(bins.length - 2, Math.ceil(12000 / step));
  const sorted = Array.from(bins.slice(first, last)).sort((a, b) => a - b);
  const noise = sorted[Math.floor(sorted.length * 0.5)];
  let maximum = 0, total = 0;
  for (let i = first; i <= last; i++) { maximum = Math.max(maximum, bins[i]); total += bins[i] ** 2; }
  const threshold = Math.max(maximum * p.relativePeak, noise * p.noiseRatio);
  const peaks = [];
  let tonal = 0;
  for (let i = first; i <= last; i++) {
    if (bins[i] < threshold || bins[i] <= bins[i - 1] || bins[i] <= bins[i + 1]) continue;
    const a = Math.log(bins[i - 1] + 1e-20), b = Math.log(bins[i] + 1e-20), c = Math.log(bins[i + 1] + 1e-20);
    const delta = Math.max(-0.5, Math.min(0.5, 0.5 * (a - c) / (a - 2 * b + c)));
    const hz = (i + delta) * step;
    peaks.push({ hz, strength: bins[i], midi: hzMidi(hz) });
    for (let j = i - 1; j <= i + 1; j++) tonal += bins[j] ** 2;
  }
  result.clarity = Math.min(1, tonal / Math.max(total, 1e-20));
  result.reason = "noisy";
  if (result.clarity < p.minClarity) return result;
  // Vibrato can split one reed into multiple nearby peaks. Keep its strongest
  // peak, with measured cents intact, before testing for upper harmonics.
  const byNote = new Map();
  for (const peak of peaks) {
    const note = Math.round(peak.midi);
    if (!byNote.has(note) || peak.strength > byNote.get(note).strength) byNote.set(note, peak);
  }
  const fundamentals = [];
  for (const candidate of Array.from(byNote.values()).sort((a, b) => a.hz - b.hz)) {
    if (candidate.midi < p.minMidi - 0.5 || candidate.midi > p.maxMidi + 0.5) continue;
    const harmonic = fundamentals.some((base) => {
      const multiple = Math.round(candidate.hz / base.hz);
      return multiple >= 2 && multiple <= p.maxHarmonic && Math.abs(1200 * Math.log2(candidate.hz / (base.hz * multiple))) < p.harmonicCents;
    });
    if (!harmonic) fundamentals.push(candidate);
  }
  // Apply the voice floor after removing harmonics: a genuine fundamental can
  // be much quieter than its own upper partials.
  const strongest = Math.max(0, ...fundamentals.map((pitch) => pitch.strength));
  const voices = fundamentals.filter((pitch) => pitch.strength >= strongest * p.relativeVoice);
  // Do not turn a noisy, many-pitched frame into a confident four-note chord.
  result.reason = "ambiguous";
  if (voices.length > p.maxVoices) return result;
  result.pitches = voices.map((item) => ({
    ...item, note: Math.round(item.midi), cents: 100 * (item.midi - Math.round(item.midi)),
  }));
  if (result.pitches.length) result.reason = "pitched";
  return result;
}

export const DISPLAY = Object.freeze({ holdMs: 1000, smoothingFrames: 3 });

// Only presentation is smoothed/held. Never feed these retained pitches into scoring.
export class PitchDisplay {
  constructor(options = {}) {
    this.options = { ...DISPLAY, ...options };
    this.reset();
  }
  reset() {
    this.frames = []; this.lastAt = -Infinity; this.last = [];
    this.value = { pitches: [], held: false, ageMs: 0 };
  }
  update(reading, now) {
    if (reading.pitches.length) {
      const sameNotes = now - this.lastAt <= this.options.holdMs &&
        reading.pitches.length === this.last.length &&
        reading.pitches.every((p, i) => p.note === this.last[i].note);
      if (!sameNotes) this.frames = [];
      this.frames.push(reading.pitches.map((p) => p.midi));
      this.frames = this.frames.slice(-this.options.smoothingFrames);
      this.last = reading.pitches.map((pitch, i) => {
        const values = this.frames.map((frame) => frame[i]).sort((a, b) => a - b);
        const midi = values[Math.floor(values.length / 2)];
        return { ...pitch, midi, hz: midiHz(midi), cents: (midi - pitch.note) * 100 };
      });
      this.lastAt = now;
      this.value = { pitches: this.last, held: false, ageMs: 0 };
    } else {
      const ageMs = now - this.lastAt;
      const held = this.last.length > 0 && ageMs <= this.options.holdMs;
      this.value = { pitches: held ? this.last : [], held, ageMs: held ? ageMs : 0 };
    }
    return this.value;
  }
}

export function comparePitches(expected, detected, tolerance = 35) {
  const missing = expected.filter((note) => !detected.some((p) => Math.abs((p.midi - note) * 100) <= tolerance));
  const extra = detected.filter((p) => !expected.some((note) => Math.abs((p.midi - note) * 100) <= tolerance));
  return { match: expected.length > 0 && !missing.length && !extra.length, missing, extra };
}
