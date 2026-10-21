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

Set the service URL, then pick a mode.

**Single** - drop a texture into the Image slot and press Generate. The mesh is written
to `Assets/Hy3dForge/Generated/` and imported as a prefab you can drag into a scene.

The editor stays responsive while a job runs - generation takes from under a minute to a few
minutes depending on backend and settings - and the status line shows queue position, then
progress, then the backend that produced it.

**Batch** - choose a folder and press Generate All. Every supported image in it is
generated in turn.

The folder can live anywhere on disk, not just inside `Assets`: files are read directly
rather than through Unity's texture importer, so your source images do not have to be part
of the project. *Include sub-folders* walks the tree; *Skip already generated* passes over
inputs whose output already exists, which makes an interrupted run resumable.

A failing image is logged and skipped rather than ending the run, and the window keeps a
per-image log with a final count of generated, failed and skipped.

### Supported image formats

`png`, `jpg`, `jpeg`, `webp`, `bmp`, `tga`, `tif`, `tiff`.

The service reads uploads with Pillow, so it is not PNG-only. Files are sent byte for byte
with a content type derived from the extension, so nothing is re-encoded on the way out.
JPEG, WebP and BMP were verified end to end against a live backend.

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

### Iterating on the package

Consumers install by git URL, but that re-downloads on every change, which is no way to
work. For development, reference the package by path instead - add this to the test
project's `Packages/manifest.json`:

```json
"com.alpsource.hy3dforge": "file:../../hy3d-forge/unity/com.alpsource.hy3dforge"
```

A `file:` package is referenced in place rather than copied, so edits to the source are the
same files Unity compiles. Change a `.cs`, switch back to the editor, and it recompiles on
focus - no reimport, no Package Manager round trip.

Two cases do need more: editing `package.json` (a version or dependency change) means
re-resolution, so reopen the project; and if the editor ends up in a confused state, close
it and delete `Library/` for a clean reimport.

### Tests

Tests live under `Tests/Editor` and run in the Test Runner (**Window → General → Test
Runner**, EditMode), or headlessly:

```bash
Unity -batchmode -nographics -projectPath <project> \
      -runTests -testPlatform EditMode -testResults results.xml
```

One rule worth knowing if you extend this: **never block the main thread waiting on a
`UnityWebRequest`**. Its completion is delivered on that thread, so blocking deadlocks the
editor. Everything here is `async`/`await` throughout.
