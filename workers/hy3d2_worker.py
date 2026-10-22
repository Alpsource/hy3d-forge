"""Hunyuan3D 2.0 worker. Runs inside Hunyuan3D-2/env, launched with cwd=<repo>."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from worker_common import prepare_image, run_worker  # noqa: E402

NAME = "hy3d2"

parser = argparse.ArgumentParser()
parser.add_argument("--model-path", default="tencent/Hunyuan3D-2")
parser.add_argument("--subfolder", default="hunyuan3d-dit-v2-0")
parser.add_argument("--texgen-model-path", default="tencent/Hunyuan3D-2")
parser.add_argument("--texgen-subfolder", default="hunyuan3d-paint-v2-0-turbo")
parser.add_argument("--low-vram", action="store_true", default=True)
OPTS, _ = parser.parse_known_args()

_state = {}


def _load():
    """Load once, keep resident. 2.0 holds both pipelines inside 24 GB comfortably."""
    if _state:
        return _state
    import torch
    from hy3dgen.rembg import BackgroundRemover
    from hy3dgen.shapegen import (DegenerateFaceRemover, FaceReducer, FloaterRemover,
                                  Hunyuan3DDiTFlowMatchingPipeline)
    from hy3dgen.texgen import Hunyuan3DPaintPipeline

    print(f"[{NAME}] loading shape {OPTS.model_path}/{OPTS.subfolder}", flush=True)
    shape = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
        OPTS.model_path, subfolder=OPTS.subfolder, use_safetensors=True)

    print(f"[{NAME}] loading paint {OPTS.texgen_model_path}/{OPTS.texgen_subfolder}", flush=True)
    paint = Hunyuan3DPaintPipeline.from_pretrained(
        OPTS.texgen_model_path, subfolder=OPTS.texgen_subfolder)
    if OPTS.low_vram:
        paint.enable_model_cpu_offload()

    _state.update(
        torch=torch, rembg=BackgroundRemover(), shape=shape, paint=paint,
        reducer=FaceReducer(), floater=FloaterRemover(), degenerate=DegenerateFaceRemover(),
    )
    print(f"[{NAME}] ready", flush=True)
    return _state


def generate(payload):
    from PIL import Image

    state = _load()
    torch = state["torch"]
    params = payload.get("params", {})
    output_dir = Path(payload["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    stats, started = {}, time.time()

    image = Image.open(payload["image_path"])
    image = prepare_image(image, params.get("remove_background", "auto"), state["rembg"])

    step = time.time()
    mesh = state["shape"](
        image=image,
        num_inference_steps=params.get("steps", 30),
        guidance_scale=params.get("guidance_scale", 5.0),
        octree_resolution=params.get("octree_resolution", 256),
        generator=torch.manual_seed(int(params.get("seed", 1234))),
        output_type="trimesh",
    )[0]
    stats["shape_seconds"] = round(time.time() - step, 1)

    mesh = state["floater"](mesh)
    mesh = state["degenerate"](mesh)
    target = int(params.get("target_face_num", 10000))
    if target > 0:
        # Decimate before texturing: the bake is tied to the UV layout.
        mesh = state["reducer"](mesh, max_facenum=target)

    textured = bool(params.get("texture", True))
    if textured:
        step = time.time()
        mesh = state["paint"](mesh, image=image)
        stats["texture_seconds"] = round(time.time() - step, 1)

    output_path = output_dir / "model.glb"
    mesh.export(output_path, include_normals=textured)

    torch.cuda.empty_cache()
    stats.update(total_seconds=round(time.time() - started, 1), faces=len(mesh.faces),
                 backend=NAME, pbr=False)
    return {"output_path": str(output_path), "stats": stats}


if __name__ == "__main__":
    run_worker(NAME, generate)
