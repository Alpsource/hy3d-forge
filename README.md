# hy3dforge

A self-hosted image-to-3D service. It puts one stable HTTP API in front of several
Hunyuan3D releases and picks the right one per job, so a client - a game engine, a script,
a web page - never has to know which model ran.

```
POST /v1/jobs  (image + options)  ->  202 {"id": "...", "status": "queued"}
GET  /v1/jobs/{id}                ->  status, timings, backend used
GET  /v1/jobs/{id}/result         ->  the .glb
```

## Why it is built this way

**The backends cannot share a process.** Hunyuan3D 2.0 needs diffusers 0.40 / transformers
5.17; 2.1 pins diffusers 0.30 / transformers 4.46. No single virtualenv satisfies both, so a
plain `import` switch is impossible. Each backend keeps its own checkout and its own venv, and
the router launches a small worker with *that venv's interpreter* and talks HTTP to it. This is
the standard answer to conflicting dependency trees: isolate at the process boundary, integrate
over a protocol.

**The repositories are referenced, not vendored.** `config.yaml` holds their paths. Nothing is
copied or submoduled in, so each stays an independent checkout you can fork, rebase on upstream
and update on its own schedule. The router depends on the worker protocol, not on model code.

**One backend is resident at a time.** 2.1's texture stage peaks at 21.8 GiB on a 24 GiB card,
so two backends cannot coexist. The registry stops the loaded backend before starting another;
terminating the process is what actually returns VRAM to the driver. An idle timer unloads the
last one so the GPU is free when nobody is generating.

**Jobs are asynchronous.** A run takes one to four minutes, far beyond any sensible HTTP
timeout, so submission returns an id immediately and the client polls. Work is serialised
through a single queue because the GPU is the scarce resource; a second request waits rather
than causing an out-of-memory failure for both.

**Workers use only the standard library.** They run inside the backend venvs, where the
installed web framework differs between releases. `http.server` is available everywhere, which
keeps the router from caring what each venv holds.

**Configuration over code.** Paths, ports, VRAM budget, quality ranking and per-backend worker
flags live in `config.yaml`. Adding a third backend is a config entry plus a worker script; no
router change.

**The API is versioned** (`/v1`) and backend-agnostic. Backend-specific knobs stay in
`config.yaml` or the optional `extra` field, so the contract a Unity client compiles against
does not move when a backend is swapped.

## Layout

```
Hunyuan3D-2/        backend checkout + its own env/      (independent git repo)
Hunyuan3D-2.1/      backend checkout + its own env/      (independent git repo)
hy3d-forge/         this service                          (independent git repo)
├── src/hy3dforge/  router: config, registry, queue, API
├── workers/        one adapter script per backend, run inside that backend's venv
├── config.yaml     paths, ports, VRAM budget, selection policy
└── artifacts/      per-job input and output files
```

## Setup

Each backend is installed first, in its own repo, with its own virtualenv. Then:

```bash
cd hy3d-forge
python3 -m venv env && source env/bin/activate
pip install -e ".[dev]"
cp config.example.yaml config.yaml   # edit the paths
hy3dforge serve
```

## Using it

```bash
# fastest backend that fits, albedo texture
curl -X POST http://127.0.0.1:8070/v1/jobs \
     -F image=@cat.png -F target_face_num=8000

# require PBR maps; picks 2.1 automatically
curl -X POST http://127.0.0.1:8070/v1/jobs \
     -F image=@cat.png -F require_pbr=true

# pin a backend explicitly
curl -X POST http://127.0.0.1:8070/v1/jobs -F image=@cat.png -F backend=hy3d2

curl http://127.0.0.1:8070/v1/jobs/<id>
curl -o model.glb http://127.0.0.1:8070/v1/jobs/<id>/result
```

Options: `backend` (`auto` | a name), `require_pbr`, `texture`, `target_face_num`, `steps`,
`guidance_scale`, `octree_resolution`, `seed`.

`backend=auto` picks the highest `quality` backend whose `vram_required_gib` fits
`gpu_total_gib`, filtered by `require_pbr`. Lower the VRAM budget and it degrades to a smaller
backend rather than failing.

## Measured on a Quadro RTX 6000 (24 GiB)

| backend | job | peak VRAM | time |
|---|---|---|---|
| hy3d2 | albedo, 8k faces, 30 steps | ~6.5 GiB | 54 s |
| hy3d21 | PBR, 8k faces | 22.7 GiB | 219 s |

2.1 is slower here because shape and paint cannot be resident together on 24 GiB, so each job
loads and releases them in turn. On a larger card, pass `--keep-resident` to the 2.1 worker and
that cost disappears.

## Notes

Run `pytest` for the selection and API tests; they need no GPU.

If your shell exports `PYTHONPATH` - ROS does - the router strips it when launching workers so
foreign site-packages cannot shadow a backend's pinned dependencies. Run the router itself with
`env -u PYTHONPATH` for the same reason.

The service binds `127.0.0.1` by default. It has no authentication, so put it behind a reverse
proxy with TLS and auth before exposing it beyond localhost.
