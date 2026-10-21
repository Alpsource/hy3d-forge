using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

namespace Hy3dForge.Editor
{
    /// <summary>
    /// Finds input images in a folder.
    ///
    /// The service opens uploads with Pillow, which reads all of these, so the format list is
    /// not limited to PNG. Files are read from disk as-is rather than through Unity's texture
    /// importer, which means the folder does not have to live inside Assets and nothing is
    /// re-encoded on the way out.
    /// </summary>
    public static class ImageFolderScanner
    {
        public static readonly string[] SupportedExtensions =
        {
            ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tga", ".tif", ".tiff"
        };

        /// <summary>For display in the UI, e.g. "png, jpg, jpeg, ...".</summary>
        public static string SupportedExtensionsLabel =>
            string.Join(", ", SupportedExtensions.Select(e => e.TrimStart('.')));

        public static bool IsSupported(string path)
        {
            if (string.IsNullOrWhiteSpace(path))
            {
                return false;
            }

            var extension = Path.GetExtension(path);
            return !string.IsNullOrEmpty(extension) &&
                   SupportedExtensions.Contains(extension.ToLowerInvariant());
        }

        /// <summary>
        /// Every supported image in the folder, sorted so a run is reproducible.
        /// Unity's own .meta sidecars are skipped.
        /// </summary>
        public static List<string> Find(string folder, bool recursive)
        {
            if (string.IsNullOrWhiteSpace(folder) || !Directory.Exists(folder))
            {
                return new List<string>();
            }

            var option = recursive ? SearchOption.AllDirectories : SearchOption.TopDirectoryOnly;
            return Directory.EnumerateFiles(folder, "*", option)
                .Where(IsSupported)
                .Where(path => !path.EndsWith(".meta", StringComparison.OrdinalIgnoreCase))
                .OrderBy(path => path, StringComparer.Ordinal)
                .ToList();
        }
    }
}
