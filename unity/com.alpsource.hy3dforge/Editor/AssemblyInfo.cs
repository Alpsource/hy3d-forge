using System.Runtime.CompilerServices;

// The test assembly is separate, and `internal` is assembly-scoped. Exposing internals to
// it keeps helpers like ForgeClient.BuildForm testable without widening the public API.
[assembly: InternalsVisibleTo("Hy3dForge.Editor.Tests")]
