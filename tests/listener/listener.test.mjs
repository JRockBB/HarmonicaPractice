import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { DETECTOR, PitchDisplay, detectPitches, comparePitches, midiHz } from "../../src/harptab/assets/listener/pitch.mjs";
import { PracticeEngine } from "../../src/harptab/assets/listener/engine.mjs";

function signal(pitches, rate = 48000, harmonics = [1, 0.6, 0.35, 0.2], cents = 0) {
  return Float32Array.from({ length: DETECTOR.frameSize }, (_, i) => pitches.reduce((sum, note) => sum + harmonics.reduce((s, gain, h) => s + gain * Math.sin(2 * Math.PI * midiHz(note + cents / 100) * (h + 1) * i / rate), 0) * 0.12 / pitches.length, 0));
}
const notes = (result) => result.pitches.map((p) => p.note);

function reedSignal(pitches, { rate = 48000, depth = 0, offset = 0, gains = [] } = {}) {
  const phases = pitches.map(() => 0);
  return Float32Array.from({ length: DETECTOR.frameSize }, (_, i) => pitches.reduce((sum, pitch, voice) => {
    const cents = depth * Math.sin(2 * Math.PI * 6 * (i / rate + offset));
    phases[voice] += 2 * Math.PI * midiHz(pitch + cents / 100) / rate;
    return sum + (gains[voice] ?? 1) * [1, 0.8, 0.65, 0.5, 0.35, 0.25].reduce((s, gain, h) => s + 0.06 * gain * Math.sin(phases[voice] * (h + 1)), 0);
  }, 0));
}

test("single-note detection across the harmonica range at browser sample rates", () => {
  for (const rate of [22050, 44100, 48000]) for (let pitch = 55; pitch <= 103; pitch++) {
    const result = detectPitches(signal([pitch], rate), rate);
    assert.deepEqual(notes(result), [pitch], `pitch ${pitch} at ${rate}`);
    assert.ok(Math.abs(result.pitches[0].cents) < 8, `tuning ${pitch}`);
  }
});
test("harmonics stronger than the fundamental are not counted as chord notes", () => {
  assert.deepEqual(notes(detectPitches(signal([71], 48000, [0.15, 1, 0.7, 0.4]), 48000)), [71]);
});
test("vibrato stays one note instead of duplicate notes or wandering upper harmonics", () => {
  for (const pitch of [60, 67, 71, 74, 78, 79, 84]) {
    for (const rate of [44100, 48000]) for (const depth of [15, 30, 40]) for (const offset of [0, 0.04, 0.08, 0.12]) {
      const result = detectPitches(reedSignal([pitch], { rate, depth, offset }), rate);
      assert.deepEqual(notes(result), [pitch], `${pitch}, ${rate}Hz, vibrato ${depth} cents at ${offset}s`);
      assert.ok(Math.abs(result.pitches[0].cents) <= depth + 8);
    }
  }
});
test("faint unrelated tones are filtered while a standalone quiet note still registers", () => {
  const result = detectPitches(reedSignal([78, 61], { gains: [1, 0.1] }), 48000);
  assert.deepEqual(notes(result), [78]);
  assert.deepEqual(notes(detectPitches(reedSignal([61], { gains: [0.1] }), 48000)), [61]);
});
test("uneven real chords survive filtering, and an audible wrong extra note remains visible", () => {
  for (const pitches of [[71, 74, 78], [71, 74, 79]]) {
    const result = detectPitches(reedSignal(pitches, { gains: [0.3, 0.5, 1] }), 48000);
    assert.deepEqual(notes(result), pitches);
    assert.equal(comparePitches(pitches, result.pitches).match, true);
  }
  const wrong = detectPitches(reedSignal([61, 78], { gains: [0.4, 1] }), 48000);
  assert.deepEqual(notes(wrong), [61, 78]);
  assert.equal(comparePitches([78], wrong.pitches).match, false);
});
test("a real Ab4 remains detectable alone or alongside the A draw chord", () => {
  const single = detectPitches(reedSignal([68]), 48000);
  assert.deepEqual(notes(single), [68]);
  const chord = detectPitches(reedSignal([68, 71, 74, 78]), 48000);
  assert.deepEqual(notes(chord), [68, 71, 74, 78]);
  assert.equal(comparePitches([71, 74, 78], chord.pitches).match, false);
});
test("same-breath chords and double stops are distinguished from single notes", () => {
  for (const pitches of [[71, 74, 78], [71, 74, 79], [74, 78], [60, 64, 67], [62, 67, 71]]) {
    for (const rate of [44100, 48000]) assert.deepEqual(notes(detectPitches(signal(pitches, rate), rate)), pitches);
  }
});
test("detuning retains signed cents, wrong octave and partial chords do not match", () => {
  for (const cents of [-43, -20, 21, 44]) {
    const found = detectPitches(signal([78], 48000, [1, 0.5], cents), 48000).pitches;
    assert.ok(Math.abs(found[0].cents - cents) < 3);
    assert.equal(comparePitches([78], found).match, Math.abs(cents) <= 35);
    assert.equal(comparePitches([66], found).match, false);
    assert.equal(comparePitches([71, 74, 78], found).match, false);
  }
});
test("silence, quiet input, noise, and clipping are handled explicitly", () => {
  assert.deepEqual(notes(detectPitches(new Float32Array(8192), 48000)), []);
  const quiet = signal([72]).map((x) => x * 0.001);
  assert.deepEqual(notes(detectPitches(quiet, 48000)), []);
  let seed = 1234;
  const noise = Float32Array.from({ length: 8192 }, () => { seed = (1664525 * seed + 1013904223) >>> 0; return (seed / 2 ** 32 - 0.5) * 0.2; });
  assert.deepEqual(notes(detectPitches(noise, 48000)), []);
  const clipped = signal([72]).map((x) => Math.max(-1, Math.min(1, x * 20)));
  assert.equal(detectPitches(clipped, 48000).clipped, true);
});
test("quiet sustained notes above the new default gate remain detectable", () => {
  const quiet = signal([78]).map((x) => x * 0.04);
  assert.deepEqual(notes(detectPitches(quiet, 48000)), [78]);
  assert.equal(detectPitches(quiet, 48000, { noiseGate: 0.008 }).reason, "quiet");
});
test("a one-frame pitch stays readable through dropouts, expires and resets", () => {
  const display = new PitchDisplay();
  const reading = detectPitches(signal([78]), 48000);
  assert.deepEqual(notes(display.update(reading, 0)), [78]);
  const empty = detectPitches(new Float32Array(8192), 48000);
  for (const now of [40, 100, 400, 1000]) {
    const shown = display.update(empty, now);
    assert.deepEqual(notes(shown), [78]); assert.equal(shown.held, true);
    assert.deepEqual(empty.pitches, []); // Raw detection is never populated with old notes.
  }
  assert.deepEqual(notes(display.update(empty, 1001)), []);
  display.update(reading, 1100); display.reset();
  assert.deepEqual(notes(display.value), []);
});
test("display smooths cents but responds immediately to new notes and chords", () => {
  const display = new PitchDisplay();
  const reading = (midis) => ({ pitches: midis.map((midi) => ({ midi, note: Math.round(midi), cents: (midi - Math.round(midi)) * 100 })) });
  display.update(reading([78.1]), 0);
  display.update(reading([78.4]), 40);
  assert.ok(Math.abs(display.update(reading([78.2]), 80).pitches[0].cents - 20) < 1e-8);
  assert.deepEqual(notes(display.update(reading([79]), 120)), [79]);
  assert.deepEqual(notes(display.update(reading([71, 74, 78]), 160)), [71, 74, 78]);
  assert.deepEqual(notes(display.update({ pitches: [] }, 200)), [71, 74, 78]);
  assert.equal(display.update(reading([71, 74, 78]), 240).held, false);
});
test("recorded CC0 harmonica fundamentals match their documented sample roots", () => {
  for (const pitch of [64, 67, 72, 76, 79, 84, 88]) {
    const wav = readFileSync(new URL(`../../src/harptab/assets/harmonica/${pitch}.wav`, import.meta.url));
    let offset = 12, data;
    while (offset < wav.length) { const size = wav.readUInt32LE(offset + 4); if (wav.toString("ascii", offset, offset + 4) === "data") { data = wav.subarray(offset + 8, offset + 8 + size); break; } offset += 8 + size + size % 2; }
    assert.ok(data);
    const samples = Float32Array.from({ length: 8192 }, (_, i) => data.readInt16LE((i + 9000) * 2) / 32768);
    const result = detectPitches(samples, 22050);
    assert.deepEqual(notes(result), [pitch], `recorded sample ${pitch}`);
    assert.ok(Math.abs(result.pitches[0].cents) < 35);
  }
});

const session = { duration: 2.4, events: [
  { start: 0, duration: 0.4, pitches: [78] },
  { start: 0.5, duration: 0.4, pitches: [78] },
  { start: 2, duration: 0.4, pitches: [71, 74, 78] },
] };
const found = (...pitches) => pitches.map((midi) => ({ midi }));
test("wait mode demands a stable match and silence before repeated notes", () => {
  const engine = new PracticeEngine(session); engine.mode = "wait"; engine.start(0);
  engine.update(0, found(77)); engine.update(400, found(77)); assert.equal(engine.index, 0);
  engine.update(500, found(78)); engine.update(600, found(78)); assert.equal(engine.index, 0);
  engine.update(750, found(78)); assert.equal(engine.index, 1);
  engine.update(1200, found(78)); assert.equal(engine.index, 1); assert.equal(engine.release, true);
  engine.update(1300, [], false); engine.update(1500, [], false); assert.equal(engine.release, true); // noisy frames are not breath breaks
  engine.update(1600, [], true); engine.update(1750, [], true); assert.equal(engine.release, false);
  engine.update(1800, found(78)); engine.update(2050, found(78)); assert.equal(engine.index, 2);
  engine.update(2100, [], true); engine.update(2250, [], true);
  engine.update(2300, found(78)); engine.update(2600, found(78)); assert.equal(engine.done, false);
  engine.update(2700, found(71, 74, 78)); engine.update(2950, found(71, 74, 78)); assert.equal(engine.done, true);
});
test("timed mode preserves count-in, slowed durations, rests and completion", () => {
  const engine = new PracticeEngine(session); engine.mode = "timed"; engine.start(1000);
  engine.update(2000, found(78)); assert.equal(engine.countdown, 2); assert.equal(engine.hit.size, 0);
  engine.update(4000, found(78)); engine.update(4250, found(78)); assert.equal(engine.hit.size, 1);
  engine.update(4900, []); assert.equal(engine.resting, true);
  engine.update(5050, found(78)); assert.equal(engine.index, 1); assert.equal(engine.resting, false);
  engine.update(6000, []); assert.equal(engine.resting, true);
  engine.update(8100, found(71, 74, 78)); assert.equal(engine.index, 2);
  engine.update(8900, []); assert.equal(engine.done, true);
});
test("pause, restart, manual skip and unplayable notes do not create matches", () => {
  const engine = new PracticeEngine(session); engine.start(0); engine.pause(); engine.update(1000, found(78)); assert.equal(engine.hit.size, 0);
  engine.step(1); assert.equal(engine.index, 1); assert.equal(engine.running, false);
  engine.reset(); assert.equal(engine.index, 0);
  const gap = new PracticeEngine({ duration: 1, events: [{ start: 0, duration: 1, pitches: [] }] });
  gap.mode = "wait";
  gap.start(0); gap.update(0, []); gap.update(500, []); assert.equal(gap.done, false);
});
test("default practice completes on time even with an extra Ab4 or no clear input", () => {
  const engine = new PracticeEngine(session); engine.start(0);
  assert.equal(engine.mode, "timed");
  engine.update(3000, found(68, 78)); engine.update(3300, found(68, 78));
  assert.equal(engine.hit.size, 0);
  engine.update(4100, []); assert.equal(engine.index, 1); assert.equal(engine.running, true);
  engine.update(8000, []); assert.equal(engine.done, true); assert.equal(engine.hit.size, 0);
  assert.equal(engine.position, session.duration);
});
test("manual skip and selection preserve the running clock and earned matches", () => {
  const engine = new PracticeEngine(session); engine.start(0);
  engine.update(3000, found(78)); engine.update(3250, found(78));
  engine.step(1, 3300);
  assert.equal(engine.running, true); assert.equal(engine.countdown, 0);
  engine.update(3500, []); assert.equal(engine.position, 0.6); assert.equal(engine.index, 1);
  engine.seek(2, 3600); engine.update(3800, []);
  assert.equal(engine.running, true); assert.equal(engine.position, 2.1);
  engine.step(1, 3900); assert.equal(engine.done, true); assert.equal(engine.running, false);
  assert.deepEqual([...engine.hit], [0]); // Skipped steps receive no credit.
  engine.start(4000); assert.equal(engine.index, 0); assert.equal(engine.hit.size, 0);
  assert.equal(engine.countdown, 3);
});
test("pause and slower resume retain the phrase position through a new count-in", () => {
  const engine = new PracticeEngine(session); engine.start(0);
  engine.update(3400, []); engine.pause();
  const pausedAt = engine.position;
  assert.ok(Math.abs(pausedAt - 0.2) < 1e-9);
  engine.update(6000, []); assert.equal(engine.position, pausedAt);
  engine.speed = 0.25; engine.start(7000);
  engine.update(8000, []); assert.equal(engine.position, pausedAt); assert.equal(engine.countdown, 2);
  engine.update(10400, []); assert.ok(Math.abs(engine.position - 0.3) < 1e-9);
});
test("results separate matched, missed, skipped and unavailable steps without penalizing unavailable notes", () => {
  const exercise = { duration: 4, events: [[60], [64, 67], [72], []].map((pitches, i) => ({ start: i, duration: 1, pitches })) };
  const engine = new PracticeEngine(exercise, { countIn: 0 }); engine.speed = 1; engine.start(0);
  engine.update(0, found(60)); engine.update(230, found(60));
  engine.update(1000, found(64)); engine.update(1230, found(64));
  engine.update(2000, found(73)); engine.step(1, 2050); engine.update(3050, []);
  const report = engine.report();
  assert.equal(engine.done, true);
  assert.deepEqual(report.steps.map((s) => s.status), ["matched", "missed", "skipped", "unavailable"]);
  assert.equal(report.percent, 33); assert.equal(report.total, 3);
  assert.equal(report.matched, 1); assert.equal(report.missed, 1); assert.equal(report.skipped, 1);
  assert.equal(report.steps[1].reason, "missing"); assert.deepEqual(report.steps[1].missing, [67]);
  engine.start(4000); assert.equal(engine.report().matched, 0);
  assert.equal(report.matched, 1); // A saved run survives the next reset.
});
test("scoring works on transposed exercises, and count-ins, pauses, rests and long frame gaps earn no credit", () => {
  for (const shift of [-5, 0, 6, 12]) {
    const pitch = 65 + shift;
    const engine = new PracticeEngine({ duration: 2, events: [{ start: 0, duration: 0.5, pitches: [pitch] }, { start: 1.5, duration: 0.5, pitches: [pitch + 2] }] });
    engine.speed = 1; engine.start(0);
    engine.update(1000, found(pitch)); assert.equal(engine.report().steps[0].frames, 0);
    engine.update(3000, found(pitch)); engine.update(3450, found(pitch));
    assert.equal(engine.hit.size, 0); // Two isolated frames cannot prove a hold.
    engine.update(3600, found(pitch)); assert.equal(engine.report().steps[0].frames, 2);
    engine.update(4500, found(pitch + 2)); engine.update(4740, found(pitch + 2));
    engine.pause(); engine.update(4800, found(pitch + 2));
    assert.equal(engine.report().steps[1].frames, 2);
    engine.start(5000); engine.update(8300, []);
    assert.equal(engine.done, true); assert.equal(engine.report().percent, 50);
  }
});
test("missed-step diagnostics distinguish tuning, extra notes, quiet, unclear and clipped input", () => {
  for (const [detected, quiet, reason, expected] of [
    [found(60.45), false, "pitched", "tuning"],
    [found(60, 63), false, "pitched", "extra"],
    [[], true, "quiet", "quiet"], [[], false, "noisy", "unclear"], [[], false, "clipped", "clipped"],
  ]) {
    const engine = new PracticeEngine({ duration: 1, events: [{ start: 0, duration: 1, pitches: [60] }] }, { countIn: 0 });
    engine.speed = 1; engine.start(0); engine.update(0, detected, quiet, reason); engine.update(1000, []);
    assert.equal(engine.report().percent, 0); assert.equal(engine.report().steps[0].reason, expected);
  }
  const empty = new PracticeEngine({ duration: 1, events: [{ start: 0, duration: 1, pitches: [] }] });
  assert.equal(empty.report().percent, null);
});
