using System.Linq;
using Hy3dForge.Editor;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.Networking;

namespace Hy3dForge.Editor.Tests
{
    public class SettingsTests
    {
        private static ForgeSettings NewSettings()
        {
            var settings = ScriptableObject.CreateInstance<ForgeSettings>();
            settings.baseUrl = "http://127.0.0.1:8070";
            settings.outputFolder = "Assets/Hy3dForge/Generated";
            return settings;
        }

        [Test]
        public void TrailingSlashIsStrippedFromUrl()
        {
            var settings = NewSettings();
            settings.baseUrl = "http://localhost:8070/";
            Assert.AreEqual("http://localhost:8070", settings.NormalisedBaseUrl);
        }

        [Test]
        public void EmptyUrlIsRejected()
        {
            var settings = NewSettings();
            settings.baseUrl = "";
            Assert.Throws<System.InvalidOperationException>(() => settings.Validate());
        }

        [Test]
        public void UrlWithoutSchemeIsRejected()
        {
            var settings = NewSettings();
            settings.baseUrl = "127.0.0.1:8070";
            Assert.Throws<System.InvalidOperationException>(() => settings.Validate());
        }

        [Test]
        public void OutputFolderMustBeInsideAssets()
        {
            var settings = NewSettings();
            settings.outputFolder = "/tmp/elsewhere";
            Assert.Throws<System.InvalidOperationException>(() => settings.Validate());
        }

        [Test]
        public void ValidSettingsPass()
        {
            Assert.DoesNotThrow(() => NewSettings().Validate());
        }
    }

    public class ClientTests
    {
        [Test]
        public void UrlsAreBuiltWithoutDoubleSlashes()
        {
            var client = new ForgeClient("http://localhost:8070/", "key");
            Assert.AreEqual("http://localhost:8070/v1/jobs", client.Url("/v1/jobs"));
        }

        [Test]
        public void FormCarriesEveryOption()
        {
            var settings = ScriptableObject.CreateInstance<ForgeSettings>();
            settings.backend = "hy3d21";
            settings.requirePbr = true;
            settings.texture = true;
            settings.targetFaceNum = 8000;
            settings.steps = 25;
            settings.seed = 7;

            var form = ForgeClient.BuildForm(new byte[] { 1, 2, 3 }, "cat.png", settings);
            var names = form.Select(section => section.sectionName).ToList();

            CollectionAssert.Contains(names, "image");
            CollectionAssert.Contains(names, "backend");
            CollectionAssert.Contains(names, "require_pbr");
            CollectionAssert.Contains(names, "target_face_num");
            CollectionAssert.Contains(names, "seed");
        }

        [Test]
        public void BooleansAreSerialisedAsLowercase()
        {
            var settings = ScriptableObject.CreateInstance<ForgeSettings>();
            settings.requirePbr = true;
            settings.texture = false;

            var form = ForgeClient.BuildForm(new byte[] { 1 }, "a.png", settings);
            string Value(string name) => System.Text.Encoding.UTF8.GetString(
                form.First(s => s.sectionName == name).sectionData);

            Assert.AreEqual("true", Value("require_pbr"), "Python's bool parsing expects lowercase");
            Assert.AreEqual("false", Value("texture"));
        }

        [Test]
        public void FloatsUseInvariantCulture()
        {
            // A machine with a comma decimal separator would otherwise send "5,5".
            var settings = ScriptableObject.CreateInstance<ForgeSettings>();
            settings.guidanceScale = 5.5f;

            var form = ForgeClient.BuildForm(new byte[] { 1 }, "a.png", settings);
            var value = System.Text.Encoding.UTF8.GetString(
                form.First(s => s.sectionName == "guidance_scale").sectionData);

            StringAssert.Contains(".", value);
            Assert.IsFalse(value.Contains(","));
        }

        [Test]
        public void JobJsonIsParsed()
        {
            const string json = "{\"id\":\"abc123\",\"status\":\"queued\",\"backend\":null," +
                                "\"error\":null,\"queue_position\":2}";
            var job = JsonUtility.FromJson<ForgeJob>(json);

            Assert.AreEqual("abc123", job.id);
            Assert.AreEqual("queued", job.status);
            Assert.AreEqual(2, job.queue_position);
            Assert.IsFalse(job.IsFinished);
        }

        [Test]
        public void FinishedStatesAreRecognised()
        {
            Assert.IsTrue(new ForgeJob { status = "succeeded" }.IsFinished);
            Assert.IsTrue(new ForgeJob { status = "succeeded" }.Succeeded);
            Assert.IsTrue(new ForgeJob { status = "failed" }.IsFinished);
            Assert.IsFalse(new ForgeJob { status = "failed" }.Succeeded);
            Assert.IsFalse(new ForgeJob { status = "running" }.IsFinished);
        }
    }

    public class AssetWriterTests
    {
        [Test]
        public void SpacesAndSeparatorsAreReplaced()
        {
            Assert.AreEqual("my_cat_image", GeneratedAssetWriter.SanitiseName("my cat image"));
            Assert.AreEqual("a_b", GeneratedAssetWriter.SanitiseName("a/b"));
        }

        [Test]
        public void LeadingAndTrailingJunkIsTrimmed()
        {
            Assert.AreEqual("name", GeneratedAssetWriter.SanitiseName("  name  "));
            Assert.AreEqual("name", GeneratedAssetWriter.SanitiseName("***name***"));
        }

        [Test]
        public void EmptyNameFallsBackToAsset()
        {
            Assert.AreEqual("asset", GeneratedAssetWriter.SanitiseName(""));
            Assert.AreEqual("asset", GeneratedAssetWriter.SanitiseName("   "));
            Assert.AreEqual("asset", GeneratedAssetWriter.SanitiseName("///"));
        }

        [Test]
        public void VeryLongNamesAreTruncated()
        {
            var name = GeneratedAssetWriter.SanitiseName(new string('x', 200));
            Assert.AreEqual(64, name.Length);
        }

        [Test]
        public void UnicodeIsCollapsedRatherThanPassedThrough()
        {
            // Asset paths travel to other filesystems; keep them ASCII.
            Assert.AreEqual("kedi_resmi", GeneratedAssetWriter.SanitiseName("kedi resmi"));
            StringAssert.DoesNotContain("ş", GeneratedAssetWriter.SanitiseName("şeker"));
        }
    }
}

namespace Hy3dForge.Editor.Tests
{
    public class FolderScannerTests
    {
        private static string MakeFolder(params string[] fileNames)
        {
            var folder = System.IO.Path.Combine(
                System.IO.Path.GetTempPath(), "hy3dforge_" + System.Guid.NewGuid().ToString("N"));
            System.IO.Directory.CreateDirectory(folder);
            foreach (var name in fileNames)
            {
                var full = System.IO.Path.Combine(folder, name);
                System.IO.Directory.CreateDirectory(System.IO.Path.GetDirectoryName(full));
                System.IO.File.WriteAllBytes(full, new byte[] { 1 });
            }

            return folder;
        }

        [Test]
        public void SupportedFormatsAreNotPngOnly()
        {
            // The service reads uploads with Pillow; jpg, webp and bmp were verified
            // end to end against a live backend.
            Assert.IsTrue(ImageFolderScanner.IsSupported("a.png"));
            Assert.IsTrue(ImageFolderScanner.IsSupported("a.jpg"));
            Assert.IsTrue(ImageFolderScanner.IsSupported("a.jpeg"));
            Assert.IsTrue(ImageFolderScanner.IsSupported("a.webp"));
            Assert.IsTrue(ImageFolderScanner.IsSupported("a.bmp"));
        }

        [Test]
        public void ExtensionMatchingIgnoresCase()
        {
            Assert.IsTrue(ImageFolderScanner.IsSupported("A.PNG"));
            Assert.IsTrue(ImageFolderScanner.IsSupported("B.JPeG"));
        }

        [Test]
        public void NonImagesAreRejected()
        {
            Assert.IsFalse(ImageFolderScanner.IsSupported("notes.txt"));
            Assert.IsFalse(ImageFolderScanner.IsSupported("model.glb"));
            Assert.IsFalse(ImageFolderScanner.IsSupported("noextension"));
            Assert.IsFalse(ImageFolderScanner.IsSupported(""));
            Assert.IsFalse(ImageFolderScanner.IsSupported(null));
        }

        [Test]
        public void OnlyImagesAreReturned()
        {
            var folder = MakeFolder("a.png", "b.jpg", "notes.txt", "c.webp");
            var found = ImageFolderScanner.Find(folder, false);
            Assert.AreEqual(3, found.Count);
            CollectionAssert.AllItemsAreUnique(found);
        }

        [Test]
        public void UnityMetaFilesAreIgnored()
        {
            var folder = MakeFolder("a.png", "a.png.meta");
            Assert.AreEqual(1, ImageFolderScanner.Find(folder, false).Count);
        }

        [Test]
        public void SubFoldersAreOptional()
        {
            var folder = MakeFolder("a.png", System.IO.Path.Combine("nested", "b.png"));
            Assert.AreEqual(1, ImageFolderScanner.Find(folder, false).Count);
            Assert.AreEqual(2, ImageFolderScanner.Find(folder, true).Count);
        }

        [Test]
        public void ResultsAreSortedSoRunsAreReproducible()
        {
            var folder = MakeFolder("c.png", "a.png", "b.png");
            var found = ImageFolderScanner.Find(folder, false);
            var sorted = new System.Collections.Generic.List<string>(found);
            sorted.Sort(System.StringComparer.Ordinal);
            CollectionAssert.AreEqual(sorted, found);
        }

        [Test]
        public void MissingFolderYieldsNothingRatherThanThrowing()
        {
            Assert.AreEqual(0, ImageFolderScanner.Find("/definitely/not/here", false).Count);
            Assert.AreEqual(0, ImageFolderScanner.Find("", false).Count);
        }

        [Test]
        public void ContentTypeFollowsTheExtension()
        {
            Assert.AreEqual("image/jpeg", ForgeClient.ContentTypeFor("a.jpg"));
            Assert.AreEqual("image/jpeg", ForgeClient.ContentTypeFor("a.JPEG"));
            Assert.AreEqual("image/webp", ForgeClient.ContentTypeFor("a.webp"));
            Assert.AreEqual("image/bmp", ForgeClient.ContentTypeFor("a.bmp"));
            Assert.AreEqual("image/png", ForgeClient.ContentTypeFor("a.png"));
            Assert.AreEqual("image/png", ForgeClient.ContentTypeFor("mystery"));
        }

        [Test]
        public void ExpectedAssetPathMatchesWhatWriteWouldUse()
        {
            Assert.AreEqual("Assets/Out/my_cat.glb",
                GeneratedAssetWriter.ExpectedAssetPath("Assets/Out", "my cat"));
        }
    }
}

namespace Hy3dForge.Editor.Tests
{
    public class RemoveBackgroundTests
    {
        private static string Section(ForgeSettings settings, string name)
        {
            var form = ForgeClient.BuildForm(new byte[] { 1 }, "a.png", settings);
            return System.Text.Encoding.UTF8.GetString(
                form.First(s => s.sectionName == name).sectionData);
        }

        [Test]
        public void DefaultIsAuto()
        {
            var settings = ScriptableObject.CreateInstance<ForgeSettings>();
            Assert.AreEqual(RemoveBackground.Auto, settings.removeBackground);
        }

        [Test]
        public void ModeIsSentLowercaseToMatchTheApi()
        {
            var settings = ScriptableObject.CreateInstance<ForgeSettings>();

            settings.removeBackground = RemoveBackground.Always;
            Assert.AreEqual("always", Section(settings, "remove_background"));

            settings.removeBackground = RemoveBackground.Never;
            Assert.AreEqual("never", Section(settings, "remove_background"));

            settings.removeBackground = RemoveBackground.Auto;
            Assert.AreEqual("auto", Section(settings, "remove_background"));
        }
    }
}

namespace Hy3dForge.Editor.Tests
{
    public class TextPromptTests
    {
        private static ForgeSettings NewSettings() =>
            ScriptableObject.CreateInstance<ForgeSettings>();

        [Test]
        public void PromptIsSentWhenProvided()
        {
            var form = ForgeClient.BuildForm(null, null, NewSettings(), "a stone statue");
            var prompt = form.First(s => s.sectionName == "prompt");
            Assert.AreEqual("a stone statue",
                System.Text.Encoding.UTF8.GetString(prompt.sectionData));
        }

        [Test]
        public void NoImageSectionWhenOnlyAPromptIsGiven()
        {
            var form = ForgeClient.BuildForm(null, null, NewSettings(), "a cat");
            Assert.IsFalse(form.Any(s => s.sectionName == "image"));
        }

        [Test]
        public void NoPromptSectionForAnImageJob()
        {
            var form = ForgeClient.BuildForm(new byte[] { 1 }, "a.png", NewSettings());
            Assert.IsFalse(form.Any(s => s.sectionName == "prompt"));
            Assert.IsTrue(form.Any(s => s.sectionName == "image"));
        }

        [Test]
        public void BlankPromptIsNotSent()
        {
            var form = ForgeClient.BuildForm(new byte[] { 1 }, "a.png", NewSettings(), "   ");
            Assert.IsFalse(form.Any(s => s.sectionName == "prompt"));
        }

        [Test]
        public void PromptIsTrimmed()
        {
            var form = ForgeClient.BuildForm(null, null, NewSettings(), "  a cat  ");
            var prompt = form.First(s => s.sectionName == "prompt");
            Assert.AreEqual("a cat", System.Text.Encoding.UTF8.GetString(prompt.sectionData));
        }

        [Test]
        public void OptionsStillAccompanyAPromptJob()
        {
            var form = ForgeClient.BuildForm(null, null, NewSettings(), "a cat");
            CollectionAssert.Contains(form.Select(s => s.sectionName).ToList(), "target_face_num");
        }

        [Test]
        public void PromptMakesAUsableAssetName()
        {
            Assert.AreEqual("a_stone_statue",
                GeneratedAssetWriter.SanitiseName("a stone statue"));
        }
    }
}
