import assert from "node:assert/strict";
import test from "node:test";
import { TakeRecorder, audioExtension, takeFrameAt, waveFromAudioBuffer, seekableAudio } from "../../src/harptab/assets/listener/takes.mjs";

class Recorder {
  static instances = [];
  static isTypeSupported(type) { return type.includes("ogg"); }
  constructor(stream, options) { this.stream = stream; this.mimeType = options.mimeType; this.state = "inactive"; Recorder.instances.push(this); }
  start() { this.state = "recording"; }
  stop() { this.state = "inactive"; }
  chunk(text) { this.ondataavailable({ data: new Blob([text], { type: this.mimeType }) }); }
  end() { this.onstop(); }
}
const frame = (pitch) => ({ expected: [60], detected: [{ midi: pitch, note: Math.round(pitch), cents: 0, hz: 440 }], phase: "play", step: 0 });

test("take audio includes the final chunk and histories outlive six seconds", async () => {
  let now = 100, ready;
  const recorder = new TakeRecorder({ Recorder, clock: () => now, onReady: (take) => { ready = take; } });
  const take = recorder.start({}, { title: "Synthetic exercise" });
  const reading = frame(60); recorder.addFrame(100, reading); reading.detected[0].midi = 90;
  recorder.addFrame(8100, frame(62)); now = 8200;
  const media = take.recorder; media.chunk("first-");
  recorder.finish("Completed", { matched: 1 });
  assert.equal(ready, undefined); assert.equal(take.state, "saving");
  media.chunk("last"); media.end();
  assert.equal(await ready.blob.text(), "first-last");
  assert.equal(ready.blob.type, "audio/ogg;codecs=opus");
  assert.equal(ready.duration, 8.1); assert.equal(ready.frames.length, 2);
  assert.equal(ready.frames[0].detected[0].midi, 60); assert.equal(ready.frames[1].time, 8);
  assert.equal(audioExtension(ready.blob.type), "ogg");
});
test("finalizing one loop cannot attach its audio or frames to the next take", async () => {
  let now = 0; const ready = [];
  const recorder = new TakeRecorder({ Recorder, clock: () => now, onReady: (take) => ready.push(take) });
  const first = recorder.start({}, { title: "First" }), firstMedia = first.recorder;
  recorder.addFrame(100, frame(60)); now = 1000; recorder.finish("Completed");
  const second = recorder.start({}, { title: "Second" }), secondMedia = second.recorder;
  recorder.addFrame(1100, frame(72));
  firstMedia.chunk("first take"); firstMedia.end();
  assert.equal(recorder.active, second);
  now = 2000; recorder.finish("Paused"); secondMedia.chunk("second take"); secondMedia.end();
  assert.deepEqual(ready.map((t) => t.metadata.title), ["First", "Second"]);
  assert.equal(await ready[0].blob.text(), "first take"); assert.equal(await ready[1].blob.text(), "second take");
  assert.equal(ready[0].frames[0].detected[0].midi, 60); assert.equal(ready[1].frames[0].detected[0].midi, 72);
});
test("unsupported or failed recording keeps an honest timeline-only take", () => {
  let ready; const recorder = new TakeRecorder({ Recorder: null, clock: () => 1000, onReady: (take) => { ready = take; } });
  recorder.start({}, {}); recorder.addFrame(1100, frame(60)); recorder.finish("Paused");
  assert.equal(ready.blob, null); assert.match(ready.error, /unavailable/); assert.equal(ready.frames.length, 1);
  const failing = new TakeRecorder({ Recorder, clock: () => 1000, onReady: (take) => { ready = take; } });
  const take = failing.start({}, {}), media = take.recorder;
  media.onerror({ error: new Error("device lost") }); failing.finish("Disconnected"); media.end();
  assert.equal(ready.blob, null); assert.match(ready.error, /device lost/);
});
test("review lookup does not invent held readings across missing frames", () => {
  const take = { frames: [{ ...frame(60), time: 0 }, { ...frame(62), time: 8 }] };
  assert.equal(takeFrameAt(take, 0.1).detected[0].midi, 60);
  assert.equal(takeFrameAt(take, 4), null);
  assert.equal(takeFrameAt(take, 8).detected[0].midi, 62);
  assert.equal(audioExtension("audio/mp4"), "m4a"); assert.equal(audioExtension("audio/webm"), "webm");
});
test("seekable WAV has correct duration fields and interleaved recorded samples", async () => {
  const buffer = { length: 3, numberOfChannels: 2, sampleRate: 44100, getChannelData: (channel) => channel ? [0.5, 0, -0.5] : [-1, 0, 1] };
  const blob = waveFromAudioBuffer(buffer), bytes = await blob.arrayBuffer(), view = new DataView(bytes);
  assert.equal(blob.type, "audio/wav"); assert.equal(audioExtension(blob.type), "wav");
  assert.equal(new TextDecoder().decode(bytes.slice(0, 4)), "RIFF");
  assert.equal(view.getUint32(4, true), bytes.byteLength - 8);
  assert.equal(view.getUint16(22, true), 2); assert.equal(view.getUint32(24, true), 44100);
  assert.equal(view.getUint32(28, true), 44100 * 4); assert.equal(view.getUint32(40, true), 12);
  assert.deepEqual(Array.from({ length: 6 }, (_, i) => view.getInt16(44 + 2 * i, true)), [-32768, 16384, 0, 0, 32767, -16384]);
});
test("audio conversion decodes the complete take and preserves its samples", async () => {
  let decodedInput;
  class OfflineContext {
    async decodeAudioData(data) {
      decodedInput = new TextDecoder().decode(data);
      return { length: 2, numberOfChannels: 1, sampleRate: 48000, getChannelData: () => [0.25, -0.25] };
    }
  }
  const blob = await seekableAudio(new Blob(["whole-take"]), OfflineContext);
  assert.equal(decodedInput, "whole-take");
  const data = new DataView(await blob.arrayBuffer());
  assert.equal(data.getInt16(44, true), 8192); assert.equal(data.getInt16(46, true), -8192);
});
