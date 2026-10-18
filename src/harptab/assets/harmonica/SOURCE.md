# Recorded harmonica samples

Source: [michael02022/basic-harmonica](https://github.com/michael02022/basic-harmonica), revision `4b8d698a49db6cdb98be0ac5b4376519cf532994`.

The author dedicates the recordings to the public domain under CC0 1.0; the original dedication is included in LICENSE.txt.

These seven mono PCM16 WAVs are converted from harmonica_1.flac through harmonica_7.flac. Source SHA-256 hashes, key regions, and resulting WAV hashes are in bank.json. Conversion applies the original SFZ's tuning offsets (0, -16, -19, -5, -14, -18, -26 cents), resamples from 48 kHz to 22.05 kHz with librosa's soxr_hq resampler, and normalizes each sample to 95% peak. The embedded forward sustain-loop markers are scaled to the new sample rate. Release-trigger samples are not used.

The playback engine selects the original SFZ key region, pitch-shifts that recording to the requested note, and loops its sustain for longer notes. This bank does not distinguish blow/draw timbres or reproduce a player's bend gesture.
