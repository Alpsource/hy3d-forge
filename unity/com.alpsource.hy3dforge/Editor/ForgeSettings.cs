using System;
using UnityEditor;
using UnityEngine;

namespace Hy3dForge.Editor
{
    /// <summary>
    /// Project-level settings for the generation service.
    ///
    /// The API key deliberately lives in EditorPrefs rather than in this asset: a
    /// ScriptableObject gets committed, and a key in the repository is a key on GitHub.
    /// Everything here is safe to share with the team.
    /// </summary>
    public sealed class ForgeSettings : ScriptableObject
    {
        internal const string AssetPath = "Assets/Hy3dForge/ForgeSettings.asset";
        private const string ApiKeyPref = "Hy3dForge.ApiKey";

        [Tooltip("Base URL of the hy3dforge service, without a trailing slash.")]
        public string baseUrl = "http://127.0.0.1:8070";

        [Tooltip("Where generated assets are written, relative to the project root.")]
        public string outputFolder = "Assets/Hy3dForge/Generated";

        [Tooltip("'auto' lets the service pick the best backend that fits its GPU.")]
        public string backend = "auto";

        [Tooltip("Ask for metallic/roughness maps. Restricts 'auto' to capable backends.")]
        public bool requirePbr;

        public bool texture = true;

        [Range(0, 1000000)]
        public int targetFaceNum = 10000;

        [Range(1, 200)]
        public int steps = 30;

        public float guidanceScale = 5f;

        [Range(16, 512)]
        public int octreeResolution = 256;

        public int seed = 1234;

        [Tooltip("Seconds to wait for a job before giving up. PBR jobs can take minutes.")]
        public int timeoutSeconds = 900;

        /// <summary>Per-machine secret, never written into the project.</summary>
        public static string ApiKey
        {
            get => EditorPrefs.GetString(ApiKeyPref, string.Empty);
            set => EditorPrefs.SetString(ApiKeyPref, value ?? string.Empty);
        }

        /// <summary>Load the project's settings asset, creating it on first use.</summary>
        public static ForgeSettings GetOrCreate()
        {
            var settings = AssetDatabase.LoadAssetAtPath<ForgeSettings>(AssetPath);
            if (settings != null)
            {
                return settings;
            }

            settings = CreateInstance<ForgeSettings>();
            var directory = System.IO.Path.GetDirectoryName(AssetPath);
            if (!string.IsNullOrEmpty(directory))
            {
                System.IO.Directory.CreateDirectory(directory);
            }

            AssetDatabase.CreateAsset(settings, AssetPath);
            AssetDatabase.SaveAssets();
            return settings;
        }

        /// <summary>Normalised base URL with any trailing slash removed.</summary>
        public string NormalisedBaseUrl =>
            string.IsNullOrWhiteSpace(baseUrl) ? string.Empty : baseUrl.TrimEnd('/');

        public void Validate()
        {
            if (string.IsNullOrWhiteSpace(baseUrl))
            {
                throw new InvalidOperationException("Service URL is empty.");
            }

            if (!baseUrl.StartsWith("http://", StringComparison.OrdinalIgnoreCase) &&
                !baseUrl.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException($"Service URL must start with http:// or https:// (got '{baseUrl}').");
            }

            if (!outputFolder.StartsWith("Assets/", StringComparison.Ordinal))
            {
                throw new InvalidOperationException("Output folder must be inside Assets/.");
            }
        }
    }
}
