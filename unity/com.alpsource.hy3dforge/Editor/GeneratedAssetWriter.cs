using System;
using System.IO;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEngine;

namespace Hy3dForge.Editor
{
    /// <summary>Writes a downloaded GLB into the project and lets Unity import it.</summary>
    public static class GeneratedAssetWriter
    {
        private static readonly Regex Unsafe = new Regex(@"[^A-Za-z0-9_\-]", RegexOptions.Compiled);

        /// <summary>
        /// Turn an arbitrary source name into something usable as a file name.
        /// Asset paths end up in version control and on other people's filesystems, so
        /// spaces, separators and non-ASCII are collapsed rather than passed through.
        /// </summary>
        public static string SanitiseName(string name)
        {
            if (string.IsNullOrWhiteSpace(name))
            {
                return "asset";
            }

            var cleaned = Unsafe.Replace(name.Trim(), "_").Trim('_');
            if (cleaned.Length == 0)
            {
                return "asset";
            }

            return cleaned.Length > 64 ? cleaned.Substring(0, 64) : cleaned;
        }

        /// <summary>Pick a path that does not collide with an existing asset.</summary>
        public static string UniqueAssetPath(string folder, string baseName, string extension)
        {
            var candidate = $"{folder}/{baseName}{extension}";
            var index = 1;
            while (File.Exists(candidate))
            {
                candidate = $"{folder}/{baseName}_{index}{extension}";
                index++;
            }

            return candidate;
        }

        /// <summary>
        /// Where a given source image would land if nothing else had claimed the name.
        /// Used to skip inputs that have already been generated.
        /// </summary>
        public static string ExpectedAssetPath(string folder, string sourceName)
            => $"{folder}/{SanitiseName(sourceName)}.glb";

        /// <summary>
        /// Save the GLB under the configured output folder and import it.
        /// Returns the asset path.
        /// </summary>
        public static string Write(byte[] glb, string sourceName, ForgeSettings settings)
        {
            if (glb == null || glb.Length == 0)
            {
                throw new ArgumentException("No data to write.", nameof(glb));
            }

            Directory.CreateDirectory(settings.outputFolder);
            var path = UniqueAssetPath(settings.outputFolder, SanitiseName(sourceName), ".glb");
            File.WriteAllBytes(path, glb);

            AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceSynchronousImport);
            return path;
        }

        /// <summary>Select and reveal the imported asset, so it is obvious where it landed.</summary>
        public static void Reveal(string assetPath)
        {
            var asset = AssetDatabase.LoadAssetAtPath<UnityEngine.Object>(assetPath);
            if (asset == null)
            {
                return;
            }

            Selection.activeObject = asset;
            EditorGUIUtility.PingObject(asset);
        }
    }
}
