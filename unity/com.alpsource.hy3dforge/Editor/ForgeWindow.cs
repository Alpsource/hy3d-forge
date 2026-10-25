using System;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using UnityEditor;
using UnityEngine;

namespace Hy3dForge.Editor
{
    /// <summary>
    /// The editor window: generate a mesh from one image, or from every image in a folder.
    ///
    /// Generation runs asynchronously so the editor stays usable while a job runs - a PBR
    /// job takes minutes, and a frozen Unity for that long is not acceptable.
    /// </summary>
    public sealed class ForgeWindow : EditorWindow
    {
        private enum Mode { Single, Batch, Text }

        private const string FolderPref = "Hy3dForge.BatchFolder";

        private ForgeSettings _settings;
        private Texture2D _sourceImage;
        private Mode _mode = Mode.Single;
        private Vector2 _scroll;
        private Vector2 _logScroll;

        private string _batchFolder = string.Empty;
        private string _prompt = string.Empty;
        private bool _recursive;
        private bool _skipExisting = true;
        private int _foundCount = -1;

        private string _status = "Idle";
        private string _lastError;
        private string _lastAssetPath;
        private readonly List<string> _log = new List<string>();
        private bool _busy;
        private CancellationTokenSource _cancellation;
        private string _apiKeyField = string.Empty;

        [MenuItem("Window/Hy3dForge/Generate 3D Asset")]
        public static void Open()
        {
            var window = GetWindow<ForgeWindow>();
            window.titleContent = new GUIContent("Hy3dForge");
            window.minSize = new Vector2(360, 520);
            window.Show();
        }

        private void OnEnable()
        {
            _settings = ForgeSettings.GetOrCreate();
            _apiKeyField = ForgeSettings.ApiKey;
            _batchFolder = EditorPrefs.GetString(FolderPref, string.Empty);
        }

        private void OnDisable() => _cancellation?.Cancel();

        private void OnGUI()
        {
            _scroll = EditorGUILayout.BeginScrollView(_scroll);

            if (_settings == null)
            {
                _settings = ForgeSettings.GetOrCreate();
            }

            DrawService();
            EditorGUILayout.Space();

            using (new EditorGUI.DisabledScope(_busy))
            {
                _mode = (Mode)GUILayout.Toolbar((int)_mode, new[] { "Single", "Batch", "Text" });
            }

            EditorGUILayout.Space();
            switch (_mode)
            {
                case Mode.Single:
                    DrawSingleInput();
                    break;
                case Mode.Batch:
                    DrawBatchInput();
                    break;
                default:
                    DrawTextInput();
                    break;
            }

            EditorGUILayout.Space();
            DrawOptions();
            EditorGUILayout.Space();
            DrawActions();
            EditorGUILayout.Space();
            DrawStatus();

            EditorGUILayout.EndScrollView();

            if (GUI.changed && !_busy)
            {
                EditorUtility.SetDirty(_settings);
            }
        }

        private void DrawService()
        {
            EditorGUILayout.LabelField("Service", EditorStyles.boldLabel);
            using (new EditorGUI.DisabledScope(_busy))
            {
                _settings.baseUrl = EditorGUILayout.TextField("URL", _settings.baseUrl);

                EditorGUI.BeginChangeCheck();
                _apiKeyField = EditorGUILayout.PasswordField("API key", _apiKeyField);
                if (EditorGUI.EndChangeCheck())
                {
                    ForgeSettings.ApiKey = _apiKeyField;
                }
            }
        }

        private void DrawSingleInput()
        {
            EditorGUILayout.LabelField("Input", EditorStyles.boldLabel);
            using (new EditorGUI.DisabledScope(_busy))
            {
                _sourceImage = (Texture2D)EditorGUILayout.ObjectField(
                    "Image", _sourceImage, typeof(Texture2D), false);
            }
        }

        private void DrawBatchInput()
        {
            EditorGUILayout.LabelField("Input folder", EditorStyles.boldLabel);
            using (new EditorGUI.DisabledScope(_busy))
            {
                EditorGUILayout.BeginHorizontal();
                EditorGUI.BeginChangeCheck();
                _batchFolder = EditorGUILayout.TextField(_batchFolder);
                if (GUILayout.Button("Browse", GUILayout.Width(70)))
                {
                    var chosen = EditorUtility.OpenFolderPanel(
                        "Folder of images", _batchFolder, string.Empty);
                    if (!string.IsNullOrEmpty(chosen))
                    {
                        _batchFolder = chosen;
                        GUI.FocusControl(null);
                    }
                }

                if (EditorGUI.EndChangeCheck())
                {
                    EditorPrefs.SetString(FolderPref, _batchFolder);
                    _foundCount = -1;
                }

                EditorGUILayout.EndHorizontal();

                EditorGUI.BeginChangeCheck();
                _recursive = EditorGUILayout.Toggle("Include sub-folders", _recursive);
                if (EditorGUI.EndChangeCheck())
                {
                    _foundCount = -1;
                }

                _skipExisting = EditorGUILayout.Toggle("Skip already generated", _skipExisting);
            }

            if (_foundCount < 0 && !string.IsNullOrEmpty(_batchFolder))
            {
                _foundCount = ImageFolderScanner.Find(_batchFolder, _recursive).Count;
            }

            if (!string.IsNullOrEmpty(_batchFolder) && !Directory.Exists(_batchFolder))
            {
                EditorGUILayout.HelpBox("That folder does not exist.", MessageType.Warning);
            }
            else if (_foundCount >= 0)
            {
                EditorGUILayout.HelpBox(
                    $"{_foundCount} image(s) found.\nSupported: {ImageFolderScanner.SupportedExtensionsLabel}",
                    _foundCount > 0 ? MessageType.Info : MessageType.Warning);
            }

            // The folder may live anywhere: files are read from disk, not through Unity's
            // importer, so inputs do not have to be inside Assets.
        }

        private void DrawTextInput()
        {
            EditorGUILayout.LabelField("Prompt", EditorStyles.boldLabel);
            using (new EditorGUI.DisabledScope(_busy))
            {
                _prompt = EditorGUILayout.TextArea(_prompt, GUILayout.Height(60));
            }

            EditorGUILayout.HelpBox(
                "Text is turned into an image first, then meshed. Only backends with the " +
                "'text' capability can serve it, and the text-to-image model is a separate " +
                "multi-gigabyte download on first use.\n" +
                "The prompt is truncated to 60 characters upstream, so keep it short.",
                MessageType.Info);

            if (_prompt.Trim().Length > 60)
            {
                EditorGUILayout.HelpBox(
                    $"This prompt is {_prompt.Trim().Length} characters; everything after 60 " +
                    "will be ignored.", MessageType.Warning);
            }
        }

        private void DrawOptions()
        {
            EditorGUILayout.LabelField("Options", EditorStyles.boldLabel);
            using (new EditorGUI.DisabledScope(_busy))
            {
                _settings.backend = EditorGUILayout.TextField("Backend", _settings.backend);
                _settings.requirePbr = EditorGUILayout.Toggle("Require PBR", _settings.requirePbr);
                _settings.texture = EditorGUILayout.Toggle("Texture", _settings.texture);
                _settings.removeBackground = (RemoveBackground)EditorGUILayout.EnumPopup(
                    "Remove background", _settings.removeBackground);
                _settings.targetFaceNum = EditorGUILayout.IntField("Target faces", _settings.targetFaceNum);
                _settings.steps = EditorGUILayout.IntSlider("Steps", _settings.steps, 1, 100);
                _settings.octreeResolution = EditorGUILayout.IntSlider(
                    "Octree resolution", _settings.octreeResolution, 16, 512);
                _settings.seed = EditorGUILayout.IntField("Seed", _settings.seed);
            }
        }

        private void DrawActions()
        {
            bool canRun;
            switch (_mode)
            {
                case Mode.Single: canRun = _sourceImage != null; break;
                case Mode.Batch: canRun = _foundCount > 0; break;
                default: canRun = !string.IsNullOrWhiteSpace(_prompt); break;
            }

            using (new EditorGUI.DisabledScope(_busy || !canRun))
            {
                var label = _mode == Mode.Batch
                    ? $"Generate All ({Math.Max(_foundCount, 0)})"
                    : "Generate";
                if (GUILayout.Button(label, GUILayout.Height(30)))
                {
                    switch (_mode)
                    {
                        case Mode.Single: _ = RunSingleAsync(); break;
                        case Mode.Batch: _ = RunBatchAsync(); break;
                        default: _ = RunTextAsync(); break;
                    }
                }
            }

            if (_busy && GUILayout.Button("Cancel"))
            {
                _cancellation?.Cancel();
            }
        }

        private void DrawStatus()
        {
            EditorGUILayout.LabelField("Status", EditorStyles.boldLabel);
            EditorGUILayout.LabelField(_status, EditorStyles.wordWrappedLabel);

            if (!string.IsNullOrEmpty(_lastError))
            {
                EditorGUILayout.HelpBox(_lastError, MessageType.Error);
            }

            if (!string.IsNullOrEmpty(_lastAssetPath))
            {
                EditorGUILayout.HelpBox($"Imported: {_lastAssetPath}", MessageType.Info);
                if (GUILayout.Button("Select asset"))
                {
                    GeneratedAssetWriter.Reveal(_lastAssetPath);
                }
            }

            if (_log.Count == 0)
            {
                return;
            }

            EditorGUILayout.LabelField("Log", EditorStyles.boldLabel);
            _logScroll = EditorGUILayout.BeginScrollView(_logScroll, GUILayout.Height(120));
            foreach (var line in _log)
            {
                EditorGUILayout.LabelField(line, EditorStyles.miniLabel);
            }

            EditorGUILayout.EndScrollView();
        }

        /// <summary>Read an image as bytes. PNG assets are sent untouched; others re-encode.</summary>
        private static byte[] ReadTextureBytes(Texture2D texture)
        {
            var path = AssetDatabase.GetAssetPath(texture);
            if (!string.IsNullOrEmpty(path) && File.Exists(path) && ImageFolderScanner.IsSupported(path))
            {
                // Send the original file: it avoids the readable/compressed import dance,
                // and the service reads every format in the supported list.
                return File.ReadAllBytes(path);
            }

            var temporary = RenderTexture.GetTemporary(
                texture.width, texture.height, 0, RenderTextureFormat.ARGB32);
            Graphics.Blit(texture, temporary);
            var previous = RenderTexture.active;
            RenderTexture.active = temporary;
            var readable = new Texture2D(texture.width, texture.height, TextureFormat.RGBA32, false);
            readable.ReadPixels(new Rect(0, 0, texture.width, texture.height), 0, 0);
            readable.Apply();
            RenderTexture.active = previous;
            RenderTexture.ReleaseTemporary(temporary);

            var bytes = readable.EncodeToPNG();
            DestroyImmediate(readable);
            return bytes;
        }

        /// <summary>Submit one image, wait for it, download and import. Shared by both modes.</summary>
        private async Task<string> GenerateOneAsync(
            ForgeClient client, byte[] bytes, string fileName, string assetName,
            string prefix, CancellationToken token)
        {
            SetStatus($"{prefix}Submitting {assetName}...");
            var job = await client.SubmitAsync(bytes, fileName, _settings, token);

            var progress = new Progress<ForgeJob>(update =>
            {
                SetStatus(update.status == "queued"
                    ? $"{prefix}{assetName}: queued (position {update.queue_position})..."
                    : $"{prefix}{assetName}: generating on {update.backend ?? "?"}...");
            });

            job = await client.WaitForCompletionAsync(job.id, _settings.timeoutSeconds, progress, token);
            if (!job.Succeeded)
            {
                throw new ForgeException(job.error ?? "Generation failed.");
            }

            SetStatus($"{prefix}{assetName}: downloading...");
            var glb = await client.DownloadResultAsync(job.id, token);

            SetStatus($"{prefix}{assetName}: importing...");
            return GeneratedAssetWriter.Write(glb, assetName, _settings);
        }

        private async Task RunSingleAsync()
        {
            BeginRun();
            try
            {
                _settings.Validate();
                var client = new ForgeClient(_settings.NormalisedBaseUrl, ForgeSettings.ApiKey);
                var bytes = ReadTextureBytes(_sourceImage);
                var sourcePath = AssetDatabase.GetAssetPath(_sourceImage);
                var fileName = string.IsNullOrEmpty(sourcePath)
                    ? $"{_sourceImage.name}.png"
                    : Path.GetFileName(sourcePath);

                _lastAssetPath = await GenerateOneAsync(
                    client, bytes, fileName, _sourceImage.name, string.Empty, _cancellation.Token);
                GeneratedAssetWriter.Reveal(_lastAssetPath);
                SetStatus("Done.");
            }
            catch (OperationCanceledException)
            {
                SetStatus("Cancelled.");
            }
            catch (Exception error)
            {
                _lastError = error.Message;
                SetStatus("Failed.");
                Debug.LogException(error);
            }
            finally
            {
                EndRun();
            }
        }

        private async Task RunTextAsync()
        {
            BeginRun();
            try
            {
                _settings.Validate();
                var client = new ForgeClient(_settings.NormalisedBaseUrl, ForgeSettings.ApiKey);
                var name = GeneratedAssetWriter.SanitiseName(_prompt);

                SetStatus("Submitting prompt...");
                var job = await client.SubmitAsync(
                    null, null, _settings, _cancellation.Token, _prompt);

                var progress = new Progress<ForgeJob>(update =>
                {
                    SetStatus(update.status == "queued"
                        ? $"Queued (position {update.queue_position})..."
                        : $"Rendering image, then meshing on {update.backend ?? "?"}...");
                });

                job = await client.WaitForCompletionAsync(
                    job.id, _settings.timeoutSeconds, progress, _cancellation.Token);
                if (!job.Succeeded)
                {
                    throw new ForgeException(job.error ?? "Generation failed.");
                }

                SetStatus("Downloading...");
                var glb = await client.DownloadResultAsync(job.id, _cancellation.Token);
                _lastAssetPath = GeneratedAssetWriter.Write(glb, name, _settings);
                GeneratedAssetWriter.Reveal(_lastAssetPath);
                SetStatus($"Done on {job.backend}.");
            }
            catch (OperationCanceledException)
            {
                SetStatus("Cancelled.");
            }
            catch (Exception error)
            {
                _lastError = error.Message;
                SetStatus("Failed.");
                Debug.LogException(error);
            }
            finally
            {
                EndRun();
            }
        }

        private async Task RunBatchAsync()
        {
            BeginRun();
            var succeeded = 0;
            var failed = 0;
            var skipped = 0;

            try
            {
                _settings.Validate();
                var client = new ForgeClient(_settings.NormalisedBaseUrl, ForgeSettings.ApiKey);
                var images = ImageFolderScanner.Find(_batchFolder, _recursive);
                Log($"Found {images.Count} image(s) in {_batchFolder}");

                for (var index = 0; index < images.Count; index++)
                {
                    _cancellation.Token.ThrowIfCancellationRequested();

                    var path = images[index];
                    var assetName = Path.GetFileNameWithoutExtension(path);
                    var prefix = $"[{index + 1}/{images.Count}] ";

                    if (_skipExisting &&
                        File.Exists(GeneratedAssetWriter.ExpectedAssetPath(_settings.outputFolder, assetName)))
                    {
                        skipped++;
                        Log($"{prefix}{assetName}: skipped, already generated");
                        continue;
                    }

                    try
                    {
                        var bytes = File.ReadAllBytes(path);
                        var asset = await GenerateOneAsync(
                            client, bytes, Path.GetFileName(path), assetName, prefix, _cancellation.Token);
                        _lastAssetPath = asset;
                        succeeded++;
                        Log($"{prefix}{assetName}: done -> {asset}");
                    }
                    catch (OperationCanceledException)
                    {
                        throw;
                    }
                    catch (Exception error)
                    {
                        // One bad image must not end the run.
                        failed++;
                        Log($"{prefix}{assetName}: FAILED - {error.Message}");
                        Debug.LogWarning($"Hy3dForge: {assetName} failed: {error.Message}");
                    }
                }

                SetStatus($"Batch finished: {succeeded} generated, {failed} failed, {skipped} skipped.");
            }
            catch (OperationCanceledException)
            {
                SetStatus($"Cancelled after {succeeded} generated, {failed} failed, {skipped} skipped.");
            }
            catch (Exception error)
            {
                _lastError = error.Message;
                SetStatus("Batch failed to start.");
                Debug.LogException(error);
            }
            finally
            {
                AssetDatabase.Refresh();
                EndRun();
            }
        }

        private void BeginRun()
        {
            _busy = true;
            _lastError = null;
            _lastAssetPath = null;
            _log.Clear();
            _cancellation = new CancellationTokenSource();
        }

        private void EndRun()
        {
            _busy = false;
            _cancellation?.Dispose();
            _cancellation = null;
            _foundCount = -1;
            Repaint();
        }

        private void Log(string line)
        {
            _log.Add(line);
            Repaint();
        }

        private void SetStatus(string message)
        {
            _status = message;
            Repaint();
        }
    }
}
