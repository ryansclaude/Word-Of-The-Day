# ComfyUI Setup Handoff — WOTD Pipeline

## Project
- **Repo:** This directory (`ClaudeSurvival/`)
- **Goal:** Run `python main.py` successfully — it calls ComfyUI at
  `http://127.0.0.1:8188` to render a word-of-the-day video using FLUX Schnell
  + Wan 2.1 I2V.
- **Workflow file:** `comfyui_workflow.json` in this repo — load this into
  ComfyUI to get the node graph.

## What Was Already Done (Mac session)

| Step | Status |
|------|--------|
| ComfyUI installed and running | ✓ Done |
| Custom nodes installed via Manager | ✓ Done: ComfyUI-GGUF, ComfyUI-WanVideoWrapper, ComfyUI-VideoHelperSuite |
| `clip_l.safetensors` (235 MB) | ✓ Downloaded → `models/clip/` |
| `t5xxl_fp8_e4m3fn.safetensors` (4.6 GB) | ✓ Downloaded → `models/clip/` |

## What Still Needs to Be Done

### 1. Download FLUX Schnell GGUF (~9 GB)
```
Destination: <ComfyUI>/models/unet/flux1-schnell-Q8_0.gguf
```
```bash
huggingface-cli download city96/FLUX.1-schnell-gguf flux1-schnell-Q8_0.gguf \
  --local-dir "<ComfyUI>/models/unet/"
```

### 2. Download FLUX VAE (~335 MB)
```
Destination: <ComfyUI>/models/vae/ae.safetensors
```
**Note:** `black-forest-labs/FLUX.1-schnell` is a gated repo.
Accept the license at https://huggingface.co/black-forest-labs/FLUX.1-schnell
(log in as `ryanwpark`), then:
```bash
huggingface-cli download black-forest-labs/FLUX.1-schnell ae.safetensors \
  --local-dir "<ComfyUI>/models/vae/"
```

### 3. Download Wan 2.1 I2V 14B 480p (~28 GB)
```
Destination: <ComfyUI>/models/diffusion_models/wan2.1-i2v-14b-480p.safetensors
```
**Important:** The `WanModelLoader` node expects a **single** `.safetensors` file
named exactly `wan2.1-i2v-14b-480p.safetensors`. The official `Wan-AI/Wan2.1-I2V-14B-480P`
repo only has 7 shards — do not download those. Get the correct single-file
ComfyUI-compatible version from the
[ComfyUI-WanVideoWrapper README](https://github.com/kijai/ComfyUI-WanVideoWrapper).

### 4. Load workflow in ComfyUI browser (manual)
1. Open `http://127.0.0.1:8188`
2. Click **Load** → select `comfyui_workflow.json` from this repo
3. All nodes should appear with no red borders
4. Node `"4"` (UnetLoaderGGUF) should show `flux1-schnell-Q8_0.gguf`
5. If any node shows red / "missing node" — re-install custom nodes via Manager

### 5. Verify API + run test
```bash
curl http://127.0.0.1:8188/system_stats
python main.py --test
```
Expected output: `exports/word_of_the_day.mp4`

## Windows Path Notes
- Replace `<ComfyUI>` with your Windows ComfyUI path, e.g.:
  `C:\Users\<you>\Documents\ComfyUI`
- Install huggingface_hub if needed: `pip install huggingface_hub`
- Log in to HuggingFace: `huggingface-cli login`
  (get a token from https://huggingface.co/settings/tokens)
