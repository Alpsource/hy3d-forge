# Third-party software

Nothing in this list is vendored into this repository. The Python packages are resolved by
pip at install time, so what you receive from here is this project's own source only. The
list exists because a studio's legal review will ask for it, and the answer is short:
everything is permissive.

## Router and workers

| package | licence |
|---|---|
| fastapi | MIT |
| starlette | BSD-3-Clause |
| pydantic | MIT |
| uvicorn | BSD-3-Clause |
| httpx | BSD-3-Clause |
| anyio | MIT |
| PyYAML | MIT |
| python-multipart | Apache-2.0 |
| pytest (development only) | MIT |

The workers themselves import nothing outside the standard library. Whatever a backend's own
virtualenv holds is that backend's dependency tree, not this project's.

## Model backends

**Not covered by this project's licence, and not permissive.** `hy3dforge setup` clones them
from their own upstreams and requires you to accept each licence before it downloads
anything, because the person running the backend is that licence's licensee.

| backend | licence | the restrictions that matter |
|---|---|---|
| Hunyuan3D 2.0 | Tencent Hunyuan3D Community License | excludes the EU, UK and South Korea, including for generated output; separate licence needed above 1M MAU |
| Hunyuan3D 2.1 | Tencent Hunyuan3D 2.1 Community License | the same |

Both are declared in `config.yaml`, with their URLs, so the acceptance prompt reflects
whatever a given install is actually about to fetch. Adding a permissively licensed backend
is a config entry, and the prompt changes to match.
