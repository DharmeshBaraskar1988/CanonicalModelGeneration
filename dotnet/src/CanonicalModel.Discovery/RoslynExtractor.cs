using System.Collections.Immutable;
using System.Security.Cryptography;
using Microsoft.Build.Locator;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.MSBuild;
using Microsoft.CodeAnalysis.Operations;

namespace CanonicalModel.Discovery;

public static class RoslynExtractor
{
    public static async Task<ExtractionResult> ExtractAsync(string projectPath)
    {
        if (!File.Exists(projectPath))
        {
            throw new FileNotFoundException("Project file was not found.", projectPath);
        }

        if (!MSBuildLocator.IsRegistered)
        {
            MSBuildLocator.RegisterDefaults();
        }

        using var workspace = MSBuildWorkspace.Create();
        var workspaceDiagnostics = new List<DiagnosticRecord>();
        workspace.WorkspaceFailed += (_, eventArgs) => workspaceDiagnostics.Add(
            new DiagnosticRecord("warning", "MSBUILD", eventArgs.Diagnostic.Message));
        var project = await workspace.OpenProjectAsync(projectPath);
        var compilation = await project.GetCompilationAsync()
            ?? throw new InvalidOperationException("Roslyn did not produce a compilation.");

        var operations = new List<OperationRecord>();
        var referencedTypes = new HashSet<INamedTypeSymbol>(SymbolEqualityComparer.Default);
        foreach (var type in AllTypes(compilation.Assembly.GlobalNamespace))
        {
            var isController = IsController(type);
            var attributedActions = type.GetMembers().OfType<IMethodSymbol>()
                .Any(method => HttpAttribute(method.GetAttributes()) is not null);
            if (!isController && !attributedActions)
            {
                continue;
            }

            var declaredControllerRoute = AttributeValue(type.GetAttributes(), "Route");
            foreach (var method in type.GetMembers().OfType<IMethodSymbol>())
            {
                var declaredHttp = HttpAttribute(method.GetAttributes());
                var methodSyntax = method.DeclaringSyntaxReferences.FirstOrDefault()?.GetSyntax()
                    as MethodDeclarationSyntax;
                if (declaredHttp is null && methodSyntax is not null &&
                    SyntaxHttpAttribute(methodSyntax.AttributeLists) is not null)
                {
                    continue;
                }
                if (!IsAction(method) || (!isController && declaredHttp is null))
                {
                    continue;
                }

                var http = declaredHttp ??
                    (Method: "GET", Route: (string?)null);
                var controllerRoute = declaredControllerRoute ??
                    (declaredHttp?.Route is not null ? string.Empty : isController ? "[controller]" : string.Empty);
                var methodRoute = http.Route ?? AttributeValue(method.GetAttributes(), "Route") ??
                    (declaredControllerRoute is null ? "[action]" : string.Empty);
                var route = CombineRoute(controllerRoute, methodRoute, type.Name, method.Name);
                var parameters = method.Parameters.Select(parameter => ToParameter(parameter)).ToArray();
                var request = method.Parameters.FirstOrDefault(parameter =>
                    HasAttribute(parameter.GetAttributes(), "FromBody"))?.Type as INamedTypeSymbol;
                request ??= http.Method is "POST" or "PUT" or "PATCH"
                    ? method.Parameters.Select(parameter => parameter.Type)
                        .OfType<INamedTypeSymbol>()
                        .FirstOrDefault(IsRequestType)
                    : null;
                if (request is not null)
                {
                    referencedTypes.Add(request);
                }

                var viewModelType = methodSyntax is null
                    ? null
                    : ViewModelType(methodSyntax, compilation);
                if (viewModelType is not null)
                {
                    referencedTypes.Add(viewModelType);
                }

                var responses = Responses(method, viewModelType).ToArray();
                foreach (var response in responses)
                {
                    var responseType = FindType(compilation, response.Type);
                    if (responseType is not null)
                    {
                        referencedTypes.Add(responseType);
                    }
                }

                operations.Add(new OperationRecord(
                    method.Name,
                    http.Method,
                    route,
                    Display(request),
                    parameters,
                    responses,
                    Location(method)));
            }
        }

        foreach (var tree in compilation.SyntaxTrees)
        {
            var semanticModel = compilation.GetSemanticModel(tree);
            foreach (var invocation in tree.GetRoot().DescendantNodes().OfType<InvocationExpressionSyntax>())
            {
                if (invocation.Expression is not MemberAccessExpressionSyntax memberAccess ||
                    !TryHttpMethod(memberAccess.Name.Identifier.Text, out var httpMethod) ||
                    invocation.ArgumentList.Arguments.Count < 2)
                {
                    continue;
                }

                var routeValue = semanticModel.GetConstantValue(
                    invocation.ArgumentList.Arguments[0].Expression);
                if (!routeValue.HasValue || routeValue.Value is not string route)
                {
                    continue;
                }

                var handler = invocation.ArgumentList.Arguments[1].Expression;
                if (semanticModel.GetOperation(handler) is not IAnonymousFunctionOperation lambda)
                {
                    continue;
                }

                var request = lambda.Symbol.Parameters.Select(parameter => parameter.Type)
                    .OfType<INamedTypeSymbol>()
                    .FirstOrDefault(IsRequestType);
                if (request is not null)
                {
                    referencedTypes.Add(request);
                }

                var responseType = ProducedType(invocation, semanticModel);
                if (responseType is not null)
                {
                    referencedTypes.Add(responseType);
                }

                var parameters = lambda.Symbol.Parameters
                    .Where(parameter => !IsInjectedService(parameter.Type))
                    .Select(parameter => new ParameterRecord(
                        parameter.Name,
                        Display(parameter.Type)!,
                        route.Contains($"{{{parameter.Name}}}", StringComparison.OrdinalIgnoreCase)
                            ? "route"
                            : IsRequestType(parameter.Type) ? "body" : "query",
                        parameter.NullableAnnotation != NullableAnnotation.Annotated &&
                            !parameter.HasExplicitDefaultValue))
                    .ToArray();
                var container = invocation.Ancestors().OfType<TypeDeclarationSyntax>()
                    .FirstOrDefault()?.Identifier.Text ?? "MinimalApi";
                operations.Add(new OperationRecord(
                    container,
                    httpMethod,
                    "/" + route.TrimStart('/'),
                    Display(request),
                    parameters,
                    [new ResponseRecord(200, Display(responseType))],
                    Location(invocation)));
            }
        }

        var operationKeys = operations
            .Select(item => $"{item.Method}:{item.Route}")
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        foreach (var tree in compilation.SyntaxTrees)
        {
            foreach (var type in tree.GetRoot().DescendantNodes().OfType<ClassDeclarationSyntax>())
            {
                var controllerRoute = SyntaxAttributeValue(type.AttributeLists, "Route");
                var controllerLike = type.Identifier.Text.EndsWith("Controller", StringComparison.Ordinal) ||
                    type.BaseList?.Types.Any(baseType =>
                        baseType.Type.ToString().Contains("Controller", StringComparison.Ordinal)) == true;
                foreach (var method in type.Members.OfType<MethodDeclarationSyntax>())
                {
                    var http = SyntaxHttpAttribute(method.AttributeLists);
                    if (http is null && !controllerLike ||
                        !method.Modifiers.Any(modifier => modifier.IsKind(Microsoft.CodeAnalysis.CSharp.SyntaxKind.PublicKeyword)) ||
                        HasSyntaxAttribute(method.AttributeLists, "NonAction"))
                    {
                        continue;
                    }

                    http ??= (Method: "GET", Route: (string?)null);
                    var declaredMethodRoute = SyntaxAttributeValue(method.AttributeLists, "Route");
                    var routePrefix = controllerRoute ??
                        (http.Value.Route is not null || declaredMethodRoute is not null
                            ? string.Empty
                            : "[controller]");
                    var actionRoute = http.Value.Route ?? declaredMethodRoute ??
                        (controllerRoute is null ? "[action]" : string.Empty);
                    var route = CombineRoute(
                        routePrefix,
                        actionRoute,
                        type.Identifier.Text,
                        method.Identifier.Text);
                    if (!operationKeys.Add($"{http.Value.Method}:{route}"))
                    {
                        continue;
                    }

                    var semanticModel = compilation.GetSemanticModel(method.SyntaxTree);
                    var resolvedParameterTypes = method.ParameterList.Parameters.ToDictionary(
                        parameter => parameter,
                        parameter => parameter.Type is null
                            ? null
                            : ResolveProjectType(parameter.Type, semanticModel, compilation));
                    var parameters = method.ParameterList.Parameters.Select(parameter =>
                    {
                        var name = parameter.Identifier.Text;
                        var location = route.Contains($"{{{name}}}", StringComparison.OrdinalIgnoreCase)
                            ? "route"
                            : HasSyntaxAttribute(parameter.AttributeLists, "FromBody") ? "body" : "query";
                        var resolvedType = resolvedParameterTypes[parameter];
                        return new ParameterRecord(
                            name,
                            Display(resolvedType) ?? parameter.Type?.ToString() ?? "unknown",
                            location,
                            parameter.Default is null && parameter.Type is not NullableTypeSyntax);
                    }).ToArray();
                    var requestParameter = method.ParameterList.Parameters.FirstOrDefault(parameter =>
                        HasSyntaxAttribute(parameter.AttributeLists, "FromBody"));
                    requestParameter ??= http.Value.Method is "POST" or "PUT" or "PATCH"
                        ? method.ParameterList.Parameters.FirstOrDefault(parameter =>
                            resolvedParameterTypes[parameter] is not null)
                        : null;
                    var requestType = requestParameter is null
                        ? null
                        : resolvedParameterTypes[requestParameter];
                    if (requestType is not null)
                    {
                        referencedTypes.Add(requestType);
                    }
                    var viewModelType = ViewModelType(method, compilation);
                    if (viewModelType is not null)
                    {
                        referencedTypes.Add(viewModelType);
                    }
                    var declaredResponseType = ResolveProjectType(
                        method.ReturnType,
                        semanticModel,
                        compilation);
                    var responseType = viewModelType ?? declaredResponseType;
                    if (responseType is not null)
                    {
                        referencedTypes.Add(responseType);
                    }
                    operations.Add(new OperationRecord(
                        method.Identifier.Text,
                        http.Value.Method,
                        route,
                        Display(requestType),
                        parameters,
                        [new ResponseRecord(200, Display(responseType))],
                        Location(method)));
                }
            }
        }

        ExpandReferencedTypes(referencedTypes);
        var types = referencedTypes
            .Where(type => type.Locations.Any(location => location.IsInSource))
            .Select(ToTypeRecord)
            .OrderBy(type => type.FullName, StringComparer.Ordinal)
            .ToArray();
        var sourcePaths = operations.Select(item => item.Location.Path)
            .Concat(types.Select(item => item.Location.Path))
            .Concat(types.SelectMany(item => item.Properties.Select(property => property.Location.Path)))
            .Distinct(StringComparer.Ordinal)
            .Order(StringComparer.Ordinal);
        var sources = sourcePaths.Select(path => new SourceRecord(path, Hash(path))).ToArray();
        var diagnostics = compilation.GetDiagnostics()
            .Where(item => item.Severity is DiagnosticSeverity.Error or DiagnosticSeverity.Warning)
            .Select(item => new DiagnosticRecord(
                item.Severity == DiagnosticSeverity.Error ? "error" : "warning",
                item.Id,
                item.GetMessage()))
            .Concat(workspaceDiagnostics)
            .OrderBy(item => item.Code, StringComparer.Ordinal)
            .ThenBy(item => item.Message, StringComparer.Ordinal)
            .ToArray();
        return new ExtractionResult(
            "1.0",
            sources,
            operations.OrderBy(item => item.Route).ThenBy(item => item.Method).ToArray(),
            types,
            diagnostics);
    }

    private static IEnumerable<INamedTypeSymbol> AllTypes(INamespaceSymbol root) =>
        root.GetNamespaceMembers().SelectMany(AllTypes).Concat(root.GetTypeMembers());

    private static bool IsController(INamedTypeSymbol type)
    {
        for (var current = type; current is not null; current = current.BaseType)
        {
            if (current.Name == "ControllerBase")
            {
                return true;
            }
        }
        return false;
    }

    private static bool IsAction(IMethodSymbol method) =>
        method.MethodKind == MethodKind.Ordinary &&
        method.DeclaredAccessibility == Accessibility.Public &&
        !method.IsStatic &&
        !HasAttribute(method.GetAttributes(), "NonAction");

    private static bool TryHttpMethod(string methodName, out string httpMethod)
    {
        httpMethod = methodName switch
        {
            "MapGet" => "GET",
            "MapPost" => "POST",
            "MapPut" => "PUT",
            "MapDelete" => "DELETE",
            "MapPatch" => "PATCH",
            _ => string.Empty
        };
        return httpMethod.Length > 0;
    }

    private static (string Method, string? Route)? SyntaxHttpAttribute(
        SyntaxList<AttributeListSyntax> lists)
    {
        foreach (var attribute in lists.SelectMany(list => list.Attributes))
        {
            var name = attribute.Name.ToString().Split('.').Last()
                .Replace("Attribute", string.Empty, StringComparison.Ordinal);
            if (name.StartsWith("Http", StringComparison.Ordinal) && name.Length > 4)
            {
                return (name[4..].ToUpperInvariant(), SyntaxFirstString(attribute));
            }
        }
        return null;
    }

    private static bool HasSyntaxAttribute(
        SyntaxList<AttributeListSyntax> lists,
        string expected) =>
        lists.SelectMany(list => list.Attributes).Any(attribute =>
            attribute.Name.ToString().Split('.').Last()
                .Replace("Attribute", string.Empty, StringComparison.Ordinal) == expected);

    private static string? SyntaxAttributeValue(
        SyntaxList<AttributeListSyntax> lists,
        string expected)
    {
        var attribute = lists.SelectMany(list => list.Attributes).FirstOrDefault(item =>
            item.Name.ToString().Split('.').Last()
                .Replace("Attribute", string.Empty, StringComparison.Ordinal) == expected);
        return attribute is null ? null : SyntaxFirstString(attribute);
    }

    private static string? SyntaxFirstString(AttributeSyntax attribute) =>
        attribute.ArgumentList?.Arguments.FirstOrDefault()?.Expression is LiteralExpressionSyntax literal &&
        literal.Token.Value is string value
            ? value
            : null;

    private static (string Method, string? Route)? HttpAttribute(ImmutableArray<AttributeData> attributes)
    {
        foreach (var attribute in attributes)
        {
            var name = attribute.AttributeClass?.Name;
            if (name is not null && name.StartsWith("Http", StringComparison.Ordinal) &&
                name.EndsWith("Attribute", StringComparison.Ordinal))
            {
                return (name[4..^9].ToUpperInvariant(), FirstString(attribute));
            }
        }
        return null;
    }

    private static ParameterRecord ToParameter(IParameterSymbol parameter)
    {
        var attributes = parameter.GetAttributes();
        var location = HasAttribute(attributes, "FromRoute") ? "route" :
            HasAttribute(attributes, "FromQuery") ? "query" :
            HasAttribute(attributes, "FromHeader") ? "header" :
            HasAttribute(attributes, "FromBody") ? "body" : "query";
        return new ParameterRecord(
            parameter.Name,
            Display(parameter.Type)!,
            location,
            parameter.NullableAnnotation != NullableAnnotation.Annotated && !parameter.HasExplicitDefaultValue);
    }

    private static IEnumerable<ResponseRecord> Responses(
        IMethodSymbol method,
        INamedTypeSymbol? viewModelType)
    {
        var found = false;
        foreach (var attribute in method.GetAttributes().Where(item =>
                     item.AttributeClass?.Name == "ProducesResponseTypeAttribute"))
        {
            found = true;
            var status = attribute.ConstructorArguments
                .FirstOrDefault(argument => argument.Value is int).Value as int? ?? 200;
            var type = attribute.AttributeClass?.TypeArguments.FirstOrDefault();
            yield return new ResponseRecord(status, Display(type));
        }
        if (!found)
        {
            yield return new ResponseRecord(
                200,
                Display(viewModelType ?? PayloadType(UnwrapActionResult(method.ReturnType))));
        }
    }

    private static INamedTypeSymbol? ViewModelType(
        MethodDeclarationSyntax method,
        Compilation compilation)
    {
        var semanticModel = compilation.GetSemanticModel(method.SyntaxTree);
        foreach (var invocation in method.DescendantNodes().OfType<InvocationExpressionSyntax>())
        {
            var invokedName = invocation.Expression switch
            {
                IdentifierNameSyntax identifier => identifier.Identifier.Text,
                MemberAccessExpressionSyntax member => member.Name.Identifier.Text,
                _ => string.Empty
            };
            if (invokedName != "View")
            {
                continue;
            }

            foreach (var argument in invocation.ArgumentList.Arguments.Reverse())
            {
                var candidate = PayloadType(semanticModel.GetTypeInfo(argument.Expression).Type);
                if (candidate is INamedTypeSymbol named && IsProjectType(named))
                {
                    return named;
                }
                var syntaxCandidate = SyntaxPayloadType(
                    argument.Expression,
                    method,
                    semanticModel,
                    compilation);
                if (syntaxCandidate is not null)
                {
                    return syntaxCandidate;
                }
            }
        }
        return null;
    }

    private static INamedTypeSymbol? SyntaxPayloadType(
        ExpressionSyntax expression,
        MethodDeclarationSyntax method,
        SemanticModel semanticModel,
        Compilation compilation)
    {
        if (expression is AwaitExpressionSyntax awaited)
        {
            return SyntaxPayloadType(awaited.Expression, method, semanticModel, compilation);
        }
        if (expression is ObjectCreationExpressionSyntax creation)
        {
            return ResolveProjectType(creation.Type, semanticModel, compilation);
        }
        if (expression is IdentifierNameSyntax identifier)
        {
            var parameter = method.ParameterList.Parameters.FirstOrDefault(item =>
                item.Identifier.Text == identifier.Identifier.Text);
            if (parameter?.Type is not null)
            {
                return ResolveProjectType(parameter.Type, semanticModel, compilation);
            }

            var variable = method.DescendantNodes().OfType<VariableDeclaratorSyntax>()
                .FirstOrDefault(item => item.Identifier.Text == identifier.Identifier.Text);
            if (variable?.Parent?.Parent is VariableDeclarationSyntax declaration &&
                declaration.Type is not IdentifierNameSyntax { Identifier.Text: "var" })
            {
                var declared = ResolveProjectType(declaration.Type, semanticModel, compilation);
                if (declared is not null)
                {
                    return declared;
                }
            }
            if (variable?.Initializer?.Value is { } initializer)
            {
                return SyntaxPayloadType(initializer, method, semanticModel, compilation);
            }
        }
        if (expression is InvocationExpressionSyntax invocation)
        {
            foreach (var argument in invocation.ArgumentList.Arguments)
            {
                if (argument.Expression is not ObjectCreationExpressionSyntax requestCreation)
                {
                    continue;
                }
                var requestType = ResolveProjectType(
                    requestCreation.Type,
                    semanticModel,
                    compilation);
                var responseType = RequestResponseType(requestType, compilation);
                if (responseType is not null)
                {
                    return responseType;
                }
            }
        }
        return null;
    }

    private static INamedTypeSymbol? RequestResponseType(
        INamedTypeSymbol? requestType,
        Compilation compilation)
    {
        if (requestType is null)
        {
            return null;
        }
        var semanticResponse = requestType.AllInterfaces.FirstOrDefault(item =>
            item.Name == "IRequest" && item.IsGenericType)?.TypeArguments.FirstOrDefault();
        var payload = PayloadType(semanticResponse);
        if (payload is INamedTypeSymbol named && IsProjectType(named))
        {
            return named;
        }

        foreach (var syntaxReference in requestType.DeclaringSyntaxReferences)
        {
            if (syntaxReference.GetSyntax() is not TypeDeclarationSyntax declaration ||
                declaration.BaseList is null)
            {
                continue;
            }
            var semanticModel = compilation.GetSemanticModel(declaration.SyntaxTree);
            foreach (var baseType in declaration.BaseList.Types)
            {
                var generic = baseType.Type.DescendantNodesAndSelf()
                    .OfType<GenericNameSyntax>()
                    .FirstOrDefault(item => item.Identifier.Text == "IRequest" &&
                        item.TypeArgumentList.Arguments.Count == 1);
                if (generic is null)
                {
                    continue;
                }
                var resolved = ResolveProjectType(
                    generic.TypeArgumentList.Arguments[0],
                    semanticModel,
                    compilation);
                if (resolved is not null)
                {
                    return resolved;
                }
            }
        }
        return null;
    }

    private static INamedTypeSymbol? ResolveProjectType(
        TypeSyntax type,
        SemanticModel semanticModel,
        Compilation compilation)
    {
        var payload = PayloadType(semanticModel.GetTypeInfo(type).Type);
        if (payload is INamedTypeSymbol named && IsProjectType(named))
        {
            return named;
        }

        foreach (var argument in type.DescendantNodesAndSelf().OfType<GenericNameSyntax>()
                     .SelectMany(item => item.TypeArgumentList.Arguments).Reverse())
        {
            var nested = ResolveProjectType(argument, semanticModel, compilation);
            if (nested is not null)
            {
                return nested;
            }
        }

        var simpleName = type.DescendantNodesAndSelf().OfType<SimpleNameSyntax>()
            .LastOrDefault()?.Identifier.Text;
        return simpleName is null
            ? null
            : AllTypes(compilation.Assembly.GlobalNamespace)
                .FirstOrDefault(item => item.Name == simpleName && IsProjectType(item));
    }

    private static ITypeSymbol? PayloadType(ITypeSymbol? type)
    {
        if (type is null)
        {
            return null;
        }
        var unwrapped = UnwrapActionResult(type);
        if (unwrapped is null)
        {
            return null;
        }
        return CollectionElement(unwrapped) ?? unwrapped;
    }

    private static ITypeSymbol? UnwrapActionResult(ITypeSymbol type)
    {
        while (type is INamedTypeSymbol { IsGenericType: true } named &&
               named.Name is "Task" or "ValueTask" or "ActionResult")
        {
            type = named.TypeArguments[0];
        }
        return type;
    }

    private static TypeRecord ToTypeRecord(INamedTypeSymbol type)
    {
        if (type.TypeKind == Microsoft.CodeAnalysis.TypeKind.Enum)
        {
            return new TypeRecord(
                type.Name, FullName(type), "enum", null, [],
                type.GetMembers().OfType<IFieldSymbol>().Where(field => field.HasConstantValue)
                    .Select(field => field.Name).Order(StringComparer.Ordinal).ToArray(),
                Location(type));
        }
        var properties = type.GetMembers().OfType<IPropertySymbol>()
            .Where(property => !property.IsStatic)
            .Select(property =>
            {
                var collection = CollectionElement(property.Type);
                return new PropertyRecord(
                    property.Name,
                    Display(property.Type)!,
                    property.NullableAnnotation == NullableAnnotation.Annotated,
                    collection is not null,
                    Display(collection),
                    property.GetAttributes().Select(ToAttribute).OrderBy(item => item.Name).ToArray(),
                    Location(property));
            })
            .OrderBy(property => property.Name, StringComparer.Ordinal)
            .ToArray();
        return new TypeRecord(
            type.Name,
            FullName(type),
            "class",
            type.BaseType is { SpecialType: SpecialType.None } ? FullName(type.BaseType) : null,
            properties,
            [],
            Location(type));
    }

    private static void ExpandReferencedTypes(HashSet<INamedTypeSymbol> types)
    {
        var queue = new Queue<INamedTypeSymbol>(types);
        while (queue.TryDequeue(out var type))
        {
            if (type.BaseType is { } baseType && IsProjectType(baseType) &&
                SymbolEqualityComparer.Default.Equals(baseType.ContainingAssembly, type.ContainingAssembly) &&
                types.Add(baseType))
            {
                queue.Enqueue(baseType);
            }
            foreach (var property in type.GetMembers().OfType<IPropertySymbol>())
            {
                var candidate = CollectionElement(property.Type) ?? property.Type;
                if (candidate is INamedTypeSymbol named && IsProjectType(named) &&
                    SymbolEqualityComparer.Default.Equals(named.ContainingAssembly, type.ContainingAssembly) &&
                    types.Add(named))
                {
                    queue.Enqueue(named);
                }
            }
        }
    }

    private static bool IsProjectType(INamedTypeSymbol type) =>
        type.SpecialType == SpecialType.None &&
        type.Locations.Any(location => location.IsInSource);

    private static bool IsRequestType(ITypeSymbol type) =>
        type is INamedTypeSymbol named && IsProjectType(named) &&
        !IsInjectedService(named) &&
        (named.Name.EndsWith("Request", StringComparison.Ordinal) || named.TypeKind != Microsoft.CodeAnalysis.TypeKind.Interface);

    private static bool IsInjectedService(ITypeSymbol type) =>
        type.TypeKind == Microsoft.CodeAnalysis.TypeKind.Interface &&
        !type.Name.EndsWith("Request", StringComparison.Ordinal);

    private static INamedTypeSymbol? ProducedType(
        InvocationExpressionSyntax mapInvocation,
        SemanticModel semanticModel)
    {
        var statement = mapInvocation.Ancestors().OfType<ExpressionStatementSyntax>().FirstOrDefault();
        var produces = statement?.DescendantNodes().OfType<GenericNameSyntax>()
            .FirstOrDefault(name => name.Identifier.Text == "Produces" && name.TypeArgumentList.Arguments.Count == 1);
        return produces is null
            ? null
            : semanticModel.GetTypeInfo(produces.TypeArgumentList.Arguments[0]).Type as INamedTypeSymbol;
    }

    private static ITypeSymbol? CollectionElement(ITypeSymbol type)
    {
        if (type is IArrayTypeSymbol array)
        {
            return array.ElementType;
        }
        if (type is not INamedTypeSymbol { IsGenericType: true } named)
        {
            return null;
        }
        var knownCollection = named.OriginalDefinition.SpecialType ==
            SpecialType.System_Collections_Generic_IEnumerable_T ||
            named.Name is "List" or "IList" or "ICollection" or "IReadOnlyList" or
                "IReadOnlyCollection" or "IEnumerable";
        var implementsCollection = named.AllInterfaces.Any(item =>
            item.OriginalDefinition.SpecialType ==
                SpecialType.System_Collections_Generic_IEnumerable_T);
        return knownCollection || implementsCollection ? named.TypeArguments[0] : null;
    }

    private static AttributeRecord ToAttribute(AttributeData attribute) => new(
        attribute.AttributeClass?.Name.Replace("Attribute", string.Empty, StringComparison.Ordinal) ?? "Unknown",
        attribute.ConstructorArguments.Select(argument => argument.Value?.ToString() ?? "null")
            .Concat(attribute.NamedArguments.Select(argument => $"{argument.Key}={argument.Value.Value}"))
            .ToArray());

    private static bool HasAttribute(ImmutableArray<AttributeData> attributes, string name) =>
        attributes.Any(attribute => attribute.AttributeClass?.Name is var value &&
            (value == name || value == $"{name}Attribute"));

    private static string? AttributeValue(ImmutableArray<AttributeData> attributes, string name) =>
        FirstString(attributes.FirstOrDefault(attribute => attribute.AttributeClass?.Name == $"{name}Attribute"));

    private static string? FirstString(AttributeData? attribute) =>
        attribute?.ConstructorArguments.FirstOrDefault().Value as string;

    private static string CombineRoute(string controllerRoute, string actionRoute, string controller, string action)
    {
        var route = $"{controllerRoute.TrimEnd('/')}/{actionRoute.TrimStart('/')}"
            .Replace("[controller]", controller.Replace("Controller", string.Empty, StringComparison.Ordinal), StringComparison.OrdinalIgnoreCase)
            .Replace("[action]", action, StringComparison.OrdinalIgnoreCase)
            .TrimEnd('/');
        return "/" + route.TrimStart('/');
    }

    private static LocationRecord Location(ISymbol symbol)
    {
        var location = symbol.Locations.First(item => item.IsInSource);
        var span = location.GetLineSpan();
        return new LocationRecord(
            Path.GetFullPath(span.Path).Replace('\\', '/'),
            span.StartLinePosition.Line + 1,
            span.EndLinePosition.Line + 1);
    }

    private static LocationRecord Location(SyntaxNode node)
    {
        var span = node.GetLocation().GetLineSpan();
        return new LocationRecord(
            Path.GetFullPath(span.Path).Replace('\\', '/'),
            span.StartLinePosition.Line + 1,
            span.EndLinePosition.Line + 1);
    }

    private static string Hash(string path) =>
        Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();

    private static string FullName(INamedTypeSymbol type) =>
        type.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat).Replace("global::", string.Empty, StringComparison.Ordinal);

    private static string? Display(ITypeSymbol? type) =>
        type is null ? null : type.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat).Replace("global::", string.Empty, StringComparison.Ordinal);

    private static INamedTypeSymbol? FindType(Compilation compilation, string? name) =>
        name is null ? null : compilation.GetTypeByMetadataName(name);
}
