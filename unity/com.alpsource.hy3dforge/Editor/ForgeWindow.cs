using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using UnityEditor;
using UnityEngine;

namespace Hy3dForge.Editor
{
    /// <summary>
    /// The editor window: pick an image, generate a mesh, import it.
    ///
    /// Generation runs asynchronously so the editor stays usable while a job runs - a PBR
    /// job takes minutes, and a frozen Unity for that long is not acceptable.
    /// </summary>
    public sealed class ForgeWindow : EditorWindow
    {
        private ForgeSettings _settings;
        private Texture2D _sourceImage;
        private Vector2 _scroll;

        private string _status = "Idle";
        private string _lastError;
        private string _lastAssetPath;
        private bool _busy;
        private CancellationTokenSource _cancellation;
        private string _apiKeyField = string.Empty;

        [MenuItem("Window/Hy3dForge/Generate 3D Asset")]
        public static void Open()
        {
            var window = GetWindow<ForgeWindow>();
            window.titleContent = new GUIContent("Hy3dForge");
            window.minSize = new Vector2(340, 440);
            window.Show();
        }

        private void OnEnable()
        {
            _settings = ForgeSettings.GetOrCreate();
            _apiKeyField = ForgeSettings.ApiKey;
        }

        private void OnDisable() => _cancellation?.Cancel();

        private void OnGUI()
        {
            _scroll = EditorGUILayout.BeginScrollView(_scroll);

            if (_settings == null)
            {
                _settings = ForgeSettings.GetOrCreate();
            }

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

                EditorGUILayout.HelpBox(
                    "The key is stored in EditorPrefs on this machine only, never in the project.",
                    MessageType.None);
            }

            EditorGUILayout.Space();
            EditorGUILayout.LabelField("Input", EditorStyles.boldLabel);
            using (new EditorGUI.DisabledScope(_busy))
            {
                _sourceImage = (Texture2D)EditorGUILayout.ObjectField(
                    "Image", _sourceImage, typeof(Texture2D), false);
            }

            EditorGUILayout.Space();
            EditorGUILayout.LabelField("Options", EditorStyles.boldLabel);
            using (new EditorGUI.DisabledScope(_busy))
            {
                _settings.backend = EditorGUILayout.TextField("Backend", _settings.backend);
                _settings.requirePbr = EditorGUILayout.Toggle("Require PBR", _settings.requirePbr);
                _settings.texture = EditorGUILayout.Toggle("Texture", _settings.texture);
                _settings.targetFaceNum = EditorGUILayout.IntField("Target faces", _settings.targetFaceNum);
                _settings.steps = EditorGUILayout.IntSlider("Steps", _settings.steps, 1, 100);
                _settings.octreeResolution = EditorGUILayout.IntSlider(
                    "Octree resolution", _settings.octreeResolution, 16, 512);
                _settings.seed = EditorGUILayout.IntField("Seed", _settings.seed);
            }

            EditorGUILayout.Space();
            using (new EditorGUI.DisabledScope(_busy || _sourceImage == null))
            {
                if (GUILayout.Button("Generate", GUILayout.Height(30)))
                {
                    _ = GenerateAsync();
                }
            }

            if (_busy && GUILayout.Button("Cancel"))
            {
                _cancellation?.Cancel();
            }

            EditorGUILayout.Space();
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

            EditorGUILayout.EndScrollView();

            if (GUI.changed && !_busy)
            {
                EditorUtility.SetDirty(_settings);
            }
        }

        /// <summary>Read the selected texture as PNG bytes, regardless of its import settings.</summary>
        private static byte[] ReadImageBytes(Texture2D texture)
        {
            var path = AssetDatabase.GetAssetPath(texture);
            if (!string.IsNullOrEmpty(path) && File.Exists(path) &&
                path.EndsWith(".png", StringComparison.OrdinalIgnoreCase))
            {
                // Use the original file: it avoids the readable/compressed import dance.
                return File.ReadAllBytes(path);
            }

            // Fall back to re-encoding, which needs a readable copy.
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

        private async Task GenerateAsync()
        {
            _busy = true;
            _lastError = null;
            _lastAssetPath = null;
            _cancellation = new CancellationTokenSource();
            var token = _cancellation.Token;

            try
            {
                _settings.Validate();
                var client = new ForgeClient(_settings.NormalisedBaseUrl, ForgeSettings.ApiKey);

                SetStatus("Reading image...");
                var bytes = ReadImageBytes(_sourceImage);
                var name = _sourceImage.name;

                SetStatus("Submitting...");
                var job = await client.SubmitAsync(bytes, $"{name}.png", _settings, token);

                var progress = new Progress<ForgeJob>(update =>
                {
                    SetStatus(update.status == "queued"
                        ? $"Queued (position {update.queue_position})..."
                        : $"Generating on {update.backend ?? "?"}...");
                });

                job = await client.WaitForCompletionAsync(
                    job.id, _settings.timeoutSeconds, progress, token);

                if (!job.Succeeded)
                {
                    throw new ForgeException(job.error ?? "Generation failed.");
                }

                SetStatus("Downloading...");
                var glb = await client.DownloadResultAsync(job.id, token);

                SetStatus("Importing...");
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
                _busy = false;
                _cancellation?.Dispose();
                _cancellation = null;
                Repaint();
            }
        }

        private void SetStatus(string message)
        {
            _status = message;
            Repaint();
        }
    }
}
