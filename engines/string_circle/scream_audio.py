# Cri du screamer validé par Yanis. Usage : python3 scream_audio.py T  (lit audio.wav, écrit audio_scream.wav, cri à T secondes)
import numpy as np, wave, sys
T = float(sys.argv[1]); SR = 48000
w = wave.open('audio.wav'); n = w.getnframes(); x = np.frombuffer(w.readframes(n), np.int16).reshape(-1, 2).astype(float) / 32767; w.close()
rng = np.random.default_rng(4)
d = 0.95; m = int(d * SR); t = np.arange(m) / SR
f0 = 520 + 420 * (1 - np.exp(-t / 0.08)) + 60 * np.sin(2 * np.pi * 7 * t)        # shrieking voice-like pitch
ph = 2 * np.pi * np.cumsum(f0) / SR
voice = sum(np.sin(k * ph + rng.uniform(0, 6)) / k for k in range(1, 12))          # rich harmonics (saw-ish)
voice2 = sum(np.sin(k * ph * 1.013 + rng.uniform(0, 6)) / k for k in range(1, 12))   # detuned layer
noise = np.convolve(rng.standard_normal(m), np.ones(3) / 3, 'same')
boom = np.sin(2 * np.pi * (60 + 40 * np.exp(-t / 0.05)) * t) * np.exp(-t / 0.25)
env = np.minimum(1, t / 0.015) * np.where(t > d - 0.12, (d - t) / 0.12, 1)
sc = np.tanh(2.5 * (0.5 * voice + 0.4 * voice2 + 0.35 * noise)) * env * 0.75 + 0.6 * boom
i = int(T * SR); j = min(len(x), i + m)
x[:i] *= 1; x[i:j] *= 0.15                       # duck the game sound under the scream
x[i:j] += sc[:j - i, None]
x = np.clip(x, -0.98, 0.98)
w = wave.open('audio_scream.wav', 'wb'); w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
w.writeframes((x * 32767).astype(np.int16).tobytes()); w.close(); print('ok')
