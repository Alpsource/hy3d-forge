using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.Networking;

namespace Hy3dForge.Editor
{
    /// <summary>A job as the service reports it. Field names match the JSON.</summary>
    [Serializable]
    public class ForgeJob
    {
        public string id;
        public string status;
        public string backend;
        public string error;
        public int queue_position;

        public bool IsFinished => status == "succeeded" || status == "failed";
        public bool Succeeded => status == "succeeded";
    }

    [Serializable]
    public class ForgeBackend
    {
        public string name;
        public string label;
        public float vram_required_gib;
        public bool loaded;
        public bool healthy;
    }

    [Serializable]
    internal class BackendList
    {
        public ForgeBackend[] items;
    }

    public class ForgeException : Exception
    {
        public long StatusCode { get; }

        public ForgeException(string message, long statusCode = 0) : base(message)
        {
            StatusCode = statusCode;
        }
    }

    /// <summary>
    /// Talks to the hy3dforge REST API.
    ///
    /// Everything is asynchronous: a PBR job takes minutes, and blocking the editor's main
    /// thread for that long would freeze Unity. Submission returns a job id and the caller
    /// polls, which is what the service expects.
    /// </summary>
    public sealed class ForgeClient
    {
        private readonly string _baseUrl;
        private readonly string _apiKey;

        public ForgeClient(string baseUrl, string apiKey)
        {
            _baseUrl = (baseUrl ?? string.Empty).TrimEnd('/');
            _apiKey = apiKey ?? string.Empty;
        }

        /// <summary>How often a running job is polled. Generation is slow; this need not be tight.</summary>
        public float PollIntervalSeconds { get; set; } = 2f;

        internal string Url(string path) => $"{_baseUrl}{path}";

        private void Authorise(UnityWebRequest request)
        {
            if (!string.IsNullOrEmpty(_apiKey))
            {
                request.SetRequestHeader("X-API-Key", _apiKey);
            }
        }

        public async Task<bool> IsReachableAsync(CancellationToken token = default)
        {
            using var request = UnityWebRequest.Get(Url("/healthz"));
            request.timeout = 5;
            try
            {
                await request.SendWebRequest();
                return request.result == UnityWebRequest.Result.Success;
            }
            catch (Exception)
            {
                return false;
            }
        }

        public async Task<ForgeBackend[]> GetBackendsAsync(CancellationToken token = default)
        {
            using var request = UnityWebRequest.Get(Url("/v1/backends"));
            Authorise(request);
            await request.SendWebRequest();
            ThrowIfFailed(request);
            // JsonUtility cannot parse a bare top-level array, so wrap it.
            var wrapped = "{\"items\":" + request.downloadHandler.text + "}";
            return JsonUtility.FromJson<BackendList>(wrapped).items;
        }

        /// <summary>
        /// Map a file name to a MIME type. The service reads the bytes with Pillow, which
        /// sniffs the real format, but sending an honest content type keeps the upload
        /// readable to anything in between.
        /// </summary>
        internal static string ContentTypeFor(string fileName)
        {
            var extension = System.IO.Path.GetExtension(fileName ?? string.Empty).ToLowerInvariant();
            switch (extension)
            {
                case ".jpg":
                case ".jpeg": return "image/jpeg";
                case ".webp": return "image/webp";
                case ".bmp": return "image/bmp";
                case ".tga": return "image/x-targa";
                case ".tif":
                case ".tiff": return "image/tiff";
                default: return "image/png";
            }
        }

        /// <summary>Build the multipart form the service expects. Separated out so it can be tested.</summary>
        internal static List<IMultipartFormSection> BuildForm(
            byte[] image, string fileName, ForgeSettings settings)
        {
            return new List<IMultipartFormSection>
            {
                new MultipartFormFileSection("image", image, fileName, ContentTypeFor(fileName)),
                new MultipartFormDataSection("backend", settings.backend),
                new MultipartFormDataSection("require_pbr", settings.requirePbr ? "true" : "false"),
                new MultipartFormDataSection("texture", settings.texture ? "true" : "false"),
                new MultipartFormDataSection("remove_background",
                    settings.removeBackground.ToString().ToLowerInvariant()),
                new MultipartFormDataSection("target_face_num", settings.targetFaceNum.ToString()),
                new MultipartFormDataSection("steps", settings.steps.ToString()),
                new MultipartFormDataSection("guidance_scale",
                    settings.guidanceScale.ToString(System.Globalization.CultureInfo.InvariantCulture)),
                new MultipartFormDataSection("octree_resolution", settings.octreeResolution.ToString()),
                new MultipartFormDataSection("seed", settings.seed.ToString()),
            };
        }

        public async Task<ForgeJob> SubmitAsync(
            byte[] image, string fileName, ForgeSettings settings, CancellationToken token = default)
        {
            using var request = UnityWebRequest.Post(Url("/v1/jobs"), BuildForm(image, fileName, settings));
            Authorise(request);
            await request.SendWebRequest();
            ThrowIfFailed(request);
            return JsonUtility.FromJson<ForgeJob>(request.downloadHandler.text);
        }

        public async Task<ForgeJob> GetJobAsync(string jobId, CancellationToken token = default)
        {
            using var request = UnityWebRequest.Get(Url($"/v1/jobs/{jobId}"));
            Authorise(request);
            await request.SendWebRequest();
            ThrowIfFailed(request);
            return JsonUtility.FromJson<ForgeJob>(request.downloadHandler.text);
        }

        public async Task<byte[]> DownloadResultAsync(string jobId, CancellationToken token = default)
        {
            using var request = UnityWebRequest.Get(Url($"/v1/jobs/{jobId}/result"));
            Authorise(request);
            await request.SendWebRequest();
            ThrowIfFailed(request);
            return request.downloadHandler.data;
        }

        /// <summary>Poll until the job finishes, reporting status changes as they happen.</summary>
        public async Task<ForgeJob> WaitForCompletionAsync(
            string jobId, int timeoutSeconds, IProgress<ForgeJob> progress = null,
            CancellationToken token = default)
        {
            var deadline = DateTime.UtcNow.AddSeconds(timeoutSeconds);
            while (DateTime.UtcNow < deadline)
            {
                token.ThrowIfCancellationRequested();
                var job = await GetJobAsync(jobId, token);
                progress?.Report(job);
                if (job.IsFinished)
                {
                    return job;
                }

                await Task.Delay(TimeSpan.FromSeconds(PollIntervalSeconds), token);
            }

            throw new ForgeException($"Job {jobId} did not finish within {timeoutSeconds}s.");
        }

        private static void ThrowIfFailed(UnityWebRequest request)
        {
            if (request.result == UnityWebRequest.Result.Success)
            {
                return;
            }

            var code = request.responseCode;
            var detail = request.downloadHandler?.text;
            var message = code switch
            {
                401 => "Unauthorised: the service requires an API key. Set one in the Hy3dForge window.",
                403 => "Forbidden: the API key was rejected.",
                0 => $"Could not reach the service at {request.url}. Is it running?",
                _ => $"Request failed ({code}): {Truncate(detail ?? request.error)}"
            };
            throw new ForgeException(message, code);
        }

        private static string Truncate(string text) =>
            string.IsNullOrEmpty(text) || text.Length <= 300 ? text : text.Substring(0, 300) + "...";
    }

    /// <summary>
    /// Lets UnityWebRequest be awaited. Unity's async operations are not awaitable out of
    /// the box, and this pattern keeps continuations on the main thread, which matters
    /// because editor APIs may only be touched there.
    /// </summary>
    internal static class UnityWebRequestAwaiterExtensions
    {
        public static UnityWebRequestAwaiter GetAwaiter(this UnityWebRequestAsyncOperation operation)
            => new UnityWebRequestAwaiter(operation);
    }

    internal readonly struct UnityWebRequestAwaiter : INotifyCompletion
    {
        private readonly UnityWebRequestAsyncOperation _operation;

        public UnityWebRequestAwaiter(UnityWebRequestAsyncOperation operation) => _operation = operation;

        public bool IsCompleted => _operation.isDone;

        public void GetResult() { }

        public void OnCompleted(Action continuation)
        {
            if (_operation.isDone)
            {
                continuation();
            }
            else
            {
                _operation.completed += _ => continuation();
            }
        }
    }
}
