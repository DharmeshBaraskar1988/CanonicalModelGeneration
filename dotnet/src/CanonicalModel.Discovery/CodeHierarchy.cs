using System.Text.Json;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace CanonicalModel.Discovery;

// Syntax only: parses bounded, preselected source text. Does not load or build uploaded projects.
internal static class CodeHierarchy
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        PropertyNameCaseInsensitive = true
    };

    internal static async Task WriteAsync(string input, string output)
    {
        var files = JsonSerializer.Deserialize<List<SourceFile>>(
            await File.ReadAllTextAsync(input), JsonOptions)!;
        var result = files.Select(Parse).ToArray();
        await File.WriteAllTextAsync(output, JsonSerializer.Serialize(result, JsonOptions));
    }

    private static object Parse(SourceFile file)
    {
        var tree = CSharpSyntaxTree.ParseText(file.Text);
        var root = tree.GetRoot();
        var nodes = root.DescendantNodes().Where(IsChunk).ToArray();
        return new
        {
            file.Path,
            HasSyntaxErrors = tree.GetDiagnostics().Any(d => d.Severity == DiagnosticSeverity.Error),
            Nodes = nodes.Select(node =>
            {
                var parent = node.Ancestors().FirstOrDefault(IsChunk);
                var span = tree.GetLineSpan(node.Span);
                var owner = string.Join(".", node.Ancestors().Reverse().Select(Name)
                    .Where(name => name.Length > 0));
                var name = Name(node);
                var suffix = node switch
                {
                    BaseMethodDeclarationSyntax method => method.ParameterList.ToString(),
                    LocalFunctionStatementSyntax local => local.ParameterList.ToString(),
                    _ => ""
                };
                var ownNodes = node.DescendantNodes().Where(n =>
                    n.Ancestors().FirstOrDefault(IsChunk) == node).ToArray();
                var references = ownNodes.OfType<IdentifierNameSyntax>()
                    .Select(n => new
                    {
                        Name = n.Identifier.ValueText,
                        Kind = n.Ancestors().TakeWhile(a => a != node).Any(a => a is BaseListSyntax)
                            ? "INHERITS_CANDIDATE"
                            : n.Parent is InvocationExpressionSyntax ||
                            (n.Parent is MemberAccessExpressionSyntax m &&
                             m.Name == n && m.Parent is InvocationExpressionSyntax)
                            ? "CALLS_CANDIDATE" : "REFERENCES_CANDIDATE"
                    }).Distinct().OrderBy(n => n.Name).ThenBy(n => n.Kind).ToArray();
                return new
                {
                    // A top-level statement and its local function can have the same span.
                    // Include syntax kind and the complete span so they retain separate identities.
                    Key = NodeKey(node),
                    ParentKey = parent is null ? null : NodeKey(parent),
                    Kind = node.Kind().ToString(),
                    Name = name,
                    Symbol = (owner.Length > 0 ? owner + "." : "") + name + suffix,
                    StartLine = span.StartLinePosition.Line + 1,
                    EndLine = span.EndLinePosition.Line + 1,
                    StartOffset = node.SpanStart,
                    EndOffset = node.Span.End,
                    References = references
                };
            }).ToArray()
        };
    }

    private static bool IsChunk(SyntaxNode node) => node is BaseTypeDeclarationSyntax
        or BaseMethodDeclarationSyntax or PropertyDeclarationSyntax or FieldDeclarationSyntax
        or EnumMemberDeclarationSyntax or DelegateDeclarationSyntax
        or GlobalStatementSyntax or LocalFunctionStatementSyntax;

    private static string NodeKey(SyntaxNode node) => string.Join(":",
        node.Kind().ToString(),
        node.SpanStart.ToString(System.Globalization.CultureInfo.InvariantCulture),
        node.Span.End.ToString(System.Globalization.CultureInfo.InvariantCulture));

    private static string Name(SyntaxNode node) => node switch
    {
        BaseNamespaceDeclarationSyntax n => n.Name.ToString(),
        BaseTypeDeclarationSyntax n => n.Identifier.ValueText,
        MethodDeclarationSyntax n => n.Identifier.ValueText,
        ConstructorDeclarationSyntax n => n.Identifier.ValueText,
        PropertyDeclarationSyntax n => n.Identifier.ValueText,
        FieldDeclarationSyntax n => string.Join(",", n.Declaration.Variables.Select(v => v.Identifier.ValueText)),
        EnumMemberDeclarationSyntax n => n.Identifier.ValueText,
        DelegateDeclarationSyntax n => n.Identifier.ValueText,
        LocalFunctionStatementSyntax n => n.Identifier.ValueText,
        GlobalStatementSyntax n => "top-level@" + n.SpanStart.ToString(System.Globalization.CultureInfo.InvariantCulture),
        _ => ""
    };

    private sealed record SourceFile(string Path, string Text);
}
