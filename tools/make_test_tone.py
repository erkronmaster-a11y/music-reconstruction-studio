"""Write assets/test-tone.wav: 2 s, 440 Hz, 44.1 kHz mono 16-bit. Stdlib only."""
import math
import struct
import wave
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "assets" / "test-tone.wav"
SR, SECONDS, HZ = 44100, 2.0, 440.0

with wave.open(str(OUT), "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SR)
    n = int(SR * SECONDS)
    fade = int(SR * 0.01)
    frames = bytearray()
    for i in range(n):
        env = min(1.0, i / fade, (n - i) / fade)
        frames += struct.pack("<h", int(0.3 * env * 32767 * math.sin(2 * math.pi * HZ * i / SR)))
    w.writeframes(bytes(frames))
print(f"wrote {OUT}")
