# Hy3dForge for Unity

Generate 3D assets from images inside the Unity Editor, using a self-hosted
[hy3dforge](../../README.md) service.

## Install

Package Manager → **Add package from git URL**:

```
https://github.com/Alpsource/hy3d-forge.git?path=/unity/com.alpsource.hy3dforge
```

Unity 6 (6000.0) or newer. [glTFast](https://github.com/atteneder/glTFast) is pulled in
automatically - Unity cannot read `.glb` without it, and glTFast understands PBR
metallic-roughness, so meshes from the 2.1 backend arrive with their metallic and roughness
maps wired into the material rather than flattened to albedo.

## Use

**Window → Hy3dForge → Generate 3D Asset**

Set the service URL, drop a texture into the Image slot, press Generate. The mesh is written
to `Assets/Hy3dForge/Generated/` and imported as a prefab you can drag into a scene.

The editor stays responsive while a job runs - generation takes from under a minute to a few
minutes depending on backend and settings - and the status line shows queue position, then
progress, then the backend that produced it.

### Options

| option | meaning |
|---|---|
| Backend | `auto`, or a specific backend name such as `hy3d2` / `hy3d21` |
| Require PBR | restrict `auto` to backends that emit metallic/roughness maps |
| Texture | off generates untextured geometry, which is much faster |
| Target faces | decimation target; applied before texturing so UVs stay valid |
| Steps, Octree resolution, Seed | diffusion settings passed through to the service |

### The API key

If your service has `api_keys` configured, enter it in the window. It is stored in
**EditorPrefs on your machine only** and never written into the project: a ScriptableObject
would be committed, and a key in the repository is a key on GitHub.

Everything else - URL, defaults, output folder - lives in
`Assets/Hy3dForge/ForgeSettings.asset` and is safe to share with the team.

## Generated assets

They are normal project assets. Whether to commit them is a project decision: committing
makes builds reproducible without the service running, ignoring keeps the repository small.
If you ignore them, add `Assets/Hy3dForge/Generated/` to `.gitignore` along with its `.meta`
files.

## Development

The package is editor-only, enforced by the assembly definition, so none of it can end up in
a player build.

Tests live under `Tests/Editor` and run in the Test Runner (**Window → General → Test
Runner**, EditMode), or headlessly:

```bash
Unity -batchmode -nographics -projectPath <project> \
      -runTests -testPlatform EditMode -testResults results.xml
```

One rule worth knowing if you extend this: **never block the main thread waiting on a
`UnityWebRequest`**. Its completion is delivered on that thread, so blocking deadlocks the
editor. Everything here is `async`/`await` throughout.
