// Practice progression is independent of the microphone and wall-clock scheduling.
import { comparePitches } from "./pitch.mjs";
export const PRACTICE = Object.freeze({ holdMs: 220, releaseMs: 120, countIn: 3, maxFrameGapMs: 250 }); // Longer gaps cannot prove a sustained note.

export class PracticeEngine {
  constructor(session, options = {}) {
    this.session = session; this.options = { ...PRACTICE, ...options };
    this.mode = "timed"; this.speed = 0.5; this.tolerance = 35;
    this.reset();
  }
  reset(index = 0) {
    this.index = index; this.running = false; this.done = false;
    this.matchedAt = null; this.silentAt = null; this.release = false;
    this.countdown = 0; this.position = this.session.events[index].start;
    this.hit = new Set(); this.startedAt = null; this.observedAt = null;
    this.results = this.session.events.map(() => ({ frames: 0, matching: 0, reasons: {}, missing: new Set(), extra: new Set(), closed: false, skipped: false }));
  }
  start(now) {
    if (this.done) this.reset();
    this.running = true; this.startedAt = now;
    this.offset = this.position; this.countdown = this.mode === "timed" ? this.options.countIn : 0;
    this.leadIn = this.countdown;
    this.matchedAt = null;
  }
  pause() { this.running = false; this.matchedAt = null; }
  seek(index, now) {
    // A manual move changes the target, not whether the session is running.
    if (this.done) this.reset();
    index = Math.max(0, Math.min(this.session.events.length - 1, index));
    for (let i = this.index; i < index; i++) this.closeStep(i, true);
    this.index = index;
    this.position = this.target.start; this.offset = this.position;
    this.startedAt = now; this.countdown = 0; this.leadIn = 0; this.done = false;
    this.matchedAt = null; this.release = false; this.silentAt = null;
  }
  step(delta, now = 0) {
    if (delta > 0 && this.index === this.session.events.length - 1) {
      this.closeStep(this.index, true);
      this.position = this.session.duration; this.done = true; this.pause(); return;
    }
    this.seek(this.index + delta, now);
  }
  get target() { return this.session.events[this.index]; }
  closeStep(index, skipped = false) {
    const result = this.results[index];
    if (!result.closed) result.skipped = skipped;
    result.closed = true;
  }
  observe(detected, quiet, reason, comparison) {
    const result = this.results[this.index];
    result.frames++;
    if (comparison.match) { result.matching++; return; }
    const expected = this.target.pitches;
    const sameNotes = detected.length === expected.length && expected.every((p) => detected.some((d) => Math.round(d.midi) === p));
    const issue = !detected.length ? reason === "clipped" ? "clipped" : quiet ? "quiet" : "unclear" : sameNotes ? "tuning" : comparison.extra.length ? "extra" : "missing";
    result.reasons[issue] = (result.reasons[issue] || 0) + 1;
    comparison.missing.forEach((pitch) => result.missing.add(pitch));
    comparison.extra.forEach((pitch) => result.extra.add(Math.round(pitch.midi)));
  }
  report() {
    const steps = this.results.map((result, index) => ({
      index, frames: result.frames, matching: result.matching,
      status: !this.session.events[index].pitches.length ? "unavailable" : this.hit.has(index) ? "matched" : result.skipped ? "skipped" : result.closed ? "missed" : result.frames ? "working" : "upcoming",
      reason: Object.entries(result.reasons).sort((a, b) => b[1] - a[1])[0]?.[0] || null,
      missing: [...result.missing].sort((a, b) => a - b), extra: [...result.extra].sort((a, b) => a - b),
    }));
    const count = (status) => steps.filter((step) => step.status === status).length;
    const total = steps.length - count("unavailable"), matched = count("matched");
    return { steps, total, matched, missed: count("missed"), skipped: count("skipped"), unavailable: count("unavailable"), percent: total ? Math.round(100 * matched / total) : null };
  }
  update(now, detected, quiet = detected.length === 0, reason = "") {
    if (!this.running) return;
    if (this.mode === "timed") {
      const elapsed = (now - this.startedAt) / 1000 - this.leadIn;
      this.countdown = Math.max(0, -elapsed);
      if (elapsed < 0) return;
      this.position = this.offset + elapsed * this.speed;
      for (let i = this.index; i < this.session.events.length && this.session.events[i].start + this.session.events[i].duration <= this.position; i++) this.closeStep(i);
      if (this.position >= this.session.duration) { this.position = this.session.duration; this.done = true; this.pause(); return; }
      while (this.index < this.session.events.length - 1 && this.session.events[this.index + 1].start <= this.position) {
        this.index++; this.matchedAt = null;
      }
      const event = this.target;
      if (this.position >= event.start + event.duration) { this.matchedAt = null; return; }
    }
    if (this.release) {
      if (!quiet) this.silentAt = null;
      else if (this.silentAt === null) this.silentAt = now;
      else if (now - this.silentAt >= this.options.releaseMs) { this.release = false; this.silentAt = null; }
      return;
    }
    if (!this.target.pitches.length) return; // Unplayable events require manual skip in wait mode.
    if (this.observedAt !== null && now - this.observedAt > this.options.maxFrameGapMs) this.matchedAt = null;
    this.observedAt = now;
    const comparison = comparePitches(this.target.pitches, detected, this.tolerance);
    this.observe(detected, quiet, reason, comparison);
    if (!comparison.match) { this.matchedAt = null; return; }
    if (this.matchedAt === null) this.matchedAt = now;
    const hold = this.mode === "wait" ? this.options.holdMs : Math.min(this.options.holdMs, this.target.duration / this.speed * 450);
    if (now - this.matchedAt < hold) return;
    this.hit.add(this.index);
    if (this.mode === "timed") return;
    this.closeStep(this.index);
    if (this.index === this.session.events.length - 1) { this.done = true; this.pause(); return; }
    this.index++; this.position = this.target.start; this.matchedAt = null;
    this.release = true; this.silentAt = null;
  }
  get resting() {
    return this.mode === "timed" && !this.countdown && this.position >= this.target.start + this.target.duration;
  }
}
