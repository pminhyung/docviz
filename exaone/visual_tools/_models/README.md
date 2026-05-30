# visual_tools/_models — super-resolution weights (untracked)

`exaone/visual_tools/_image_ops.py` uses OpenCV's `cv2.dnn_superres` to do
optional `upscale` preprocessing inside `analyze_visual` and `get_visuals`.
The pretrained EDSR `.pb` weights are NOT tracked in git (large binaries,
license-bearing). Download once per checkout.

## Files

| Filename | Purpose | Scale | Size |
|----------|---------|-------|------|
| `EDSR_x2.pb` | Enhanced Deep Super-Resolution, ×2 | 2 | ~38 MB |
| `EDSR_x3.pb` | Enhanced Deep Super-Resolution, ×3 | 3 | ~38 MB |
| `EDSR_x4.pb` | Enhanced Deep Super-Resolution, ×4 | 4 | ~38 MB |

CPU-only — no GPU needed (`cv2.dnn` default backend). ~3-5 s per
1024×1024 upscale on a modern CPU.

## Download

```sh
cd exaone/visual_tools/_models/

# x4 covers the common case; pull the others only if you need them.
wget https://github.com/Saafke/EDSR_Tensorflow/raw/master/models/EDSR_x4.pb
# Optional:
wget https://github.com/Saafke/EDSR_Tensorflow/raw/master/models/EDSR_x2.pb
wget https://github.com/Saafke/EDSR_Tensorflow/raw/master/models/EDSR_x3.pb
```

## Behavior when missing

`_image_ops.py::upscale()` checks for the matching `EDSR_x{scale}.pb`. If
absent (or `cv2` not installed), it falls back to PIL `Image.LANCZOS` —
lower quality but never fails. The agent's `upscale` flag stays a no-op
free decision.

## License

EDSR weights from [Saafke/EDSR_Tensorflow](https://github.com/Saafke/EDSR_Tensorflow)
— BSD-2-Clause. Original paper: Lim et al., *Enhanced Deep Residual
Networks for Single Image Super-Resolution*, CVPR 2017.
