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
