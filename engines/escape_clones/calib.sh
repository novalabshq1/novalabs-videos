# Usage: bash calib.sh DUR ST SDB -> prints decoded AAC peaks (scream / game)
python3 audio_esc.py $1 $2 $3 >/dev/null && ffmpeg -v error -y -i esc_audio.wav -c:a aac -b:a 320k -ar 48000 c.m4a && ffmpeg -v error -y -i c.m4a -f f32le -ac 2 -ar 48000 c.raw && python3 -c "
import numpy as np;a=np.fromfile('c.raw',np.float32).reshape(-1,2);SR=48000;i0,i1=int($2*SR),int(($2+0.6)*SR)
d=lambda x:20*np.log10(np.abs(x).max()); print('SDB $3 -> scream %.2f game %.2f'%(d(a[i0:i1]),d(np.r_[a[:i0-2000],a[i1+2000:]])))"; rm -f c.m4a c.raw
