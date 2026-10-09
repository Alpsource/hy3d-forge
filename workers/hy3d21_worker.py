"""Hunyuan3D 2.1 worker (PBR). Runs inside Hunyuan3D-2.1/env, launched with cwd=<repo>.

Unlike 2.0, the shape and paint pipelines cannot both be resident: measured peaks are
9.8 GiB and 21.8 GiB, so together they exceed a 24 GiB card. Each stage therefore loads,
runs and is released. That costs model-load time per job and is the price of PBR on this
hardware; on a larger card, raise `keep_resident` to hold both.
"""

from __future__ import annotations

import argparse
import gc
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from worker_common import run_worker  # noqa: E402

# The repo's own modules expect to be importable from the checkout root.
sys.path.insert(0, ".")
sys.path.insert(0, "./hy3dshape")
sys.path.insert(0, "./hy3dpaint")

NAME = "hy3d21"

parser = argparse.ArgumentParser()
parser.add_argument("--model-path", default="tencent/Hunyuan3D-2.1")
parser.add_argument("--max-num-view", type=int, default=6, help="6-9; higher costs more VRAM")
parser.add_argument("--resolution", type=int, default=512, help="512 or 768")
parser.add_argument("--keep-resident", action="store_true",
                    help="hold both pipelines in VRAM (needs roughly 32 GiB)")
OPTS, _ = parser.parse_known_args()

try:
    from torchvision_fix import apply_fix

    apply_fix()  # basicsr imports torchvision.transforms.functional_tensor, removed in 0.17+
except Exception as error:  # pragma: no cover
    print(f"[{NAME}] torchvision_fix unavailable: {error}", flush=True)

_resident = {}


def _free(*objects):
    import torch

    for obj in objects:
        del obj
    gc.collect()
    torch.cuda.empty_cache()


def _shape_pipeline():
    if "shape" in _resident:
        return _resident["shape"]
    from hy3dshape.pipelines import Hunyuan3DDiTFlowMatchingPipeline

    print(f"[{NAME}] loading shape {OPTS.model_path}", flush=True)
    pipeline = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(OPTS.model_path)
    if OPTS.keep_resident:
        _resident["shape"] = pipeline
    return pipeline


def _paint_pipeline():
    if "paint" in _resident:
        return _resident["paint"]
    from textureGenPipeline import Hunyuan3DPaintConfig, Hunyuan3DPaintPipeline

    print(f"[{NAME}] loading paint ({OPTS.max_num_view} views, {OPTS.resolution}px)", flush=True)
    config = Hunyuan3DPaintConfig(OPTS.max_num_view, OPTS.resolution)
    config.realesrgan_ckpt_path = "hy3dpaint/ckpt/RealESRGAN_x4plus.pth"
    config.multiview_cfg_path = "hy3dpaint/cfgs/hunyuan-paint-pbr.yaml"
    config.custom_pipeline = "hy3dpaint/hunyuanpaintpbr"
    pipeline = Hunyuan3DPaintPipeline(config)
    if OPTS.keep_resident:
        _resident["paint"] = pipeline
    return pipeline


def generate(payload):
    import torch
    from PIL import Image

    from hy3dshape.postprocessors import FaceReducer
    from hy3dshape.rembg import BackgroundRemover

    params = payload.get("params", {})
    output_dir = Path(payload["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    stats, started = {}, time.time()

    image_path = payload["image_path"]
    image = Image.open(image_path)
    if image.mode != "RGBA" or image.getextrema()[3][0] == 255:
        image = BackgroundRemover()(image.convert("RGB"))
        image_path = str(output_dir / "input_rgba.png")
        image.save(image_path)

    step = time.time()
    shape = _shape_pipeline()
    mesh = shape(image=image)[0]
    stats["shape_seconds"] = round(time.time() - step, 1)

    target = int(params.get("target_face_num", 10000))
    if target > 0:
        mesh = FaceReducer()(mesh, max_facenum=target)

    white_path = output_dir / "white_mesh.glb"
    mesh.export(white_path)
    if not OPTS.keep_resident:
        _free(shape)  # release ~10 GiB before the paint stage claims ~22 GiB

    if not bool(params.get("texture", True)):
        stats.update(total_seconds=round(time.time() - started, 1),
                     faces=len(mesh.faces), backend=NAME, pbr=False)
        return {"output_path": str(white_path), "stats": stats}

    step = time.time()
    paint = _paint_pipeline()
    output_obj = output_dir / "model.obj"
    paint(mesh_path=str(white_path), image_path=image_path,
          output_mesh_path=str(output_obj), save_glb=True)
    stats["texture_seconds"] = round(time.time() - step, 1)
    if not OPTS.keep_resident:
        _free(paint)

    output_path = output_obj.with_suffix(".glb")
    if not output_path.exists():
        raise RuntimeError(f"paint stage produced no GLB at {output_path}")

    torch.cuda.empty_cache()
    stats.update(total_seconds=round(time.time() - started, 1), faces=len(mesh.faces),
                 backend=NAME, pbr=True, views=OPTS.max_num_view, resolution=OPTS.resolution)
    return {"output_path": str(output_path), "stats": stats}


if __name__ == "__main__":
    run_worker(NAME, generate)
