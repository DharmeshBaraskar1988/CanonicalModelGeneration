using System.Text.Json.Serialization;

namespace CanonicalModel.Discovery;

public sealed record SourceRecord(string Path, string Sha256);

public sealed record LocationRecord(string Path, int StartLine, int EndLine);

public sealed record AttributeRecord(string Name, IReadOnlyList<string> Arguments);

public sealed record PropertyRecord(
    string Name,
    string Type,
    bool Nullable,
    bool Collection,
    string? ElementType,
    IReadOnlyList<AttributeRecord> Attributes,
    LocationRecord Location);

public sealed record TypeRecord(
    string Name,
    string FullName,
    string Kind,
    string? BaseType,
    IReadOnlyList<PropertyRecord> Properties,
    IReadOnlyList<string> EnumValues,
    LocationRecord Location);

public sealed record ParameterRecord(string Name, string Type, string Location, bool Required);

public sealed record ResponseRecord(int StatusCode, string? Type);

public sealed record MappingRecord(string From, string To, string Via);

public sealed record FlowRecord(
    string Kind,
    string Command,
    string? Handler,
    IReadOnlyList<MappingRecord> Mappings,
    IReadOnlyList<string> Backends,
    LocationRecord Location);

public sealed record OperationRecord(
    string Name,
    string Method,
    string Route,
    string? RequestType,
    IReadOnlyList<ParameterRecord> Parameters,
    IReadOnlyList<ResponseRecord> Responses,
    LocationRecord Location,
    FlowRecord? Flow = null);

public sealed record DiagnosticRecord(string Severity, string Code, string Message);

public sealed record ExtractionResult(
    string Version,
    IReadOnlyList<SourceRecord> Sources,
    IReadOnlyList<OperationRecord> Operations,
    IReadOnlyList<TypeRecord> Types,
    IReadOnlyList<DiagnosticRecord> Diagnostics);

[JsonSourceGenerationOptions(PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase, WriteIndented = true)]
[JsonSerializable(typeof(ExtractionResult))]
internal partial class JsonContext : JsonSerializerContext;
