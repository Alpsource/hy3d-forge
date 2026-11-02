# Changelog

Versions follow [semantic versioning](https://semver.org). The HTTP API carries its own
version in the path (`/v1`); a breaking change there would mean `/v2` alongside it, not a
silent change under the same route.

## 1.0.0

First released version. Everything below already worked before this tag; what makes it 1.0.0
is that the licence and the API contract are now things you can rely on rather than things
that might move.

### Service

- One HTTP API in front of several Hunyuan3D releases, picking a backend per job by quality,
  VRAM budget, PBR requirement and whether a text prompt was given.
- Backends run as isolated worker processes in their own virtualenvs, because 2.0 and 2.1
  pin incompatible dependency trees and cannot share an interpreter.
- One backend resident at a time, with an idle timeout that frees the GPU when nobody is
  generating. Terminating the worker is what actually returns VRAM to the driver.
- Asynchronous jobs through a single queue, since the GPU is the scarce resource.
- Image to 3D, text to 3D, optional PBR, optional texture, background removal control,
  face-count targeting and the diffusion settings behind them.
- Per-job `peak_vram_gib` in the stats, for spotting a backend that is holding memory it
  should have released.

### Operations

- `hy3dforge setup` clones and installs the backends declared in `config.yaml`, showing each
  one's licence and requiring acceptance first.
- API-key authentication, constant-time compared, with `HY3DFORGE_API_KEYS` overriding the
  file. Binding to a non-loopback address without keys is refused.
- Artifact retention by age and total size, sweeping orphaned directories left by a previous
  run.
- `hy3dforge --version`, and the same version reported by `/healthz`.

### Unity

- Editor package for Unity 6, installable by git URL, with Single, Batch and Text modes.
- Generated meshes imported as prefabs through glTFast, so PBR maps survive.
- Batch mode walks a folder anywhere on disk, resumable and skipping failures rather than
  stopping.
- The API key is held in EditorPrefs, never in a committed asset.

### Licence

- Released under the PolyForm Small Business License 1.0.0: free under 100 people and $1M
  revenue, commercial licence above that. See [COMMERCIAL.md](COMMERCIAL.md).
