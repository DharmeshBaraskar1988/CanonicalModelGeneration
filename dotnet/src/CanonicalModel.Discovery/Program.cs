using System.Text.Json;

namespace CanonicalModel.Discovery;

internal static class Program
{
    private static async Task<int> Main(string[] args)
    {
        var options = args
            .Chunk(2)
            .Where(pair => pair.Length == 2 && pair[0].StartsWith("--", StringComparison.Ordinal))
            .ToDictionary(pair => pair[0], pair => pair[1], StringComparer.Ordinal);
        if (options.TryGetValue("--chunk-input", out var chunkInput) &&
            options.TryGetValue("--output", out var chunkOutput))
        {
            await CodeHierarchy.WriteAsync(chunkInput, chunkOutput);
            return 0;
        }
        if (!options.TryGetValue("--project", out var project) ||
            !options.TryGetValue("--output", out var output))
        {
            Console.Error.WriteLine("Usage: --project <csproj> --output <json>");
            return 2;
        }

        var result = await RoslynExtractor.ExtractAsync(Path.GetFullPath(project));
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output))!);
        await File.WriteAllTextAsync(
            output,
            JsonSerializer.Serialize(result, JsonContext.Default.ExtractionResult));
        return result.Diagnostics.Any(item => item.Severity == "error") ? 1 : 0;
    }
}
