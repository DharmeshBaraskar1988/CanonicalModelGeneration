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
    public static async Task<ExtractionResult> ExtractAsync(
        string projectPath,
        IReadOnlyCollection<string>? hintTypes = null)
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

        // Azure Functions Isolated Worker: detect [Function]-decorated methods.
        var flowDiagnostics = new List<DiagnosticRecord>();
        var sourceTypes = new Lazy<IReadOnlyList<INamedTypeSymbol>>(() =>
            AllSourceTypes(compilation).Where(IsProjectType).ToArray());
        foreach (var tree in compilation.SyntaxTrees)
        {
            foreach (var typeDecl in tree.GetRoot().DescendantNodes().OfType<ClassDeclarationSyntax>())
            {
                foreach (var method in typeDecl.Members.OfType<MethodDeclarationSyntax>())
                {
                    var semanticModel = compilation.GetSemanticModel(method.SyntaxTree);
                    var functionName = AzureFunctionName(method.AttributeLists, semanticModel);
                    if (functionName is null)
                    {
                        continue;
                    }

                    // For now, only HTTP triggers produce operations.
                    // Non-HTTP triggers (Queue, Blob, Timer, CosmosDB, …) are skipped.
                    var httpTrigger = AzureHttpTrigger(method.ParameterList, semanticModel);
                    if (httpTrigger is null)
                    {
                        continue;
                    }

                    var (httpMethods, triggerRoute) = httpTrigger.Value;
                    var route = triggerRoute is not null
                        ? "/" + triggerRoute.TrimStart('/')
                        : $"/api/{functionName}";

                    // Request type: prefer [FromBody] parameter; fall back to first
                    // non-framework body parameter on mutating verbs.
                    INamedTypeSymbol? requestType = null;
                    var fromBodyParam = method.ParameterList.Parameters.FirstOrDefault(p =>
                        HasSyntaxAttribute(p.AttributeLists, "FromBody"));
                    if (fromBodyParam?.Type is not null)
                    {
                        requestType = ResolveProjectType(fromBodyParam.Type, semanticModel, compilation);
                        if (requestType is not null) referencedTypes.Add(requestType);
                    }

                    if (requestType is null &&
                        httpMethods.Any(m => m.Equals("post", StringComparison.OrdinalIgnoreCase) ||
                                            m.Equals("put", StringComparison.OrdinalIgnoreCase) ||
                                            m.Equals("patch", StringComparison.OrdinalIgnoreCase)))
                    {
                        var candidateParam = method.ParameterList.Parameters.FirstOrDefault(p =>
                            p.Type is not null &&
                            !HasSyntaxAttribute(p.AttributeLists, "HttpTrigger") &&
                            !IsAzureFunctionsFrameworkParam(p));
                        if (candidateParam?.Type is not null)
                        {
                            var candidate = ResolveProjectType(candidateParam.Type, semanticModel, compilation);
                            if (candidate is not null && IsRequestType(candidate))
                            {
                                requestType = candidate;
                                referencedTypes.Add(requestType);
                            }
                        }
                    }

                    // Response type: resolved return type when it is not an AF framework type.
                    INamedTypeSymbol? responseType = null;
                    var returnTypeName = method.ReturnType.ToString().Split('.').Last().TrimEnd('?');
                    if (returnTypeName is not "HttpResponseData" and not "Task" and not "void")
                    {
                        var resolved = ResolveProjectType(method.ReturnType, semanticModel, compilation);
                        if (resolved is not null &&
                            resolved.Name is not ("IActionResult" or "ActionResult" or "IResult"))
                        {
                            responseType = resolved;
                            referencedTypes.Add(responseType);
                        }
                    }

                    // Command/handler code behind the function: `_mediator.Send(new Cmd(...))`.
                    var flow = TraceMediatorFlow(
                        method, semanticModel, compilation, sourceTypes.Value, flowDiagnostics);
                    if (flow is not null)
                    {
                        if (requestType is null && flow.RequestModel is not null)
                        {
                            requestType = flow.RequestModel;
                            referencedTypes.Add(requestType);
                        }
                        if (responseType is null && flow.ResponseModel is not null)
                        {
                            responseType = flow.ResponseModel;
                            referencedTypes.Add(responseType);
                        }
                        foreach (var related in flow.Related)
                        {
                            referencedTypes.Add(related);
                        }
                    }

                    var declaredParameters = method.ParameterList.Parameters
                        .Where(p => !HasSyntaxAttribute(p.AttributeLists, "HttpTrigger") &&
                                    !IsAzureFunctionsFrameworkParam(p))
                        .Select(p =>
                        {
                            var name = p.Identifier.Text;
                            var loc = route.Contains($"{{{name}}}", StringComparison.OrdinalIgnoreCase)
                                ? "route"
                                : HasSyntaxAttribute(p.AttributeLists, "FromBody") ? "body" : "query";
                            var resolvedType = p.Type is null
                                ? null
                                : ResolveProjectType(p.Type, semanticModel, compilation);
                            return new ParameterRecord(
                                name,
                                Display(resolvedType) ?? p.Type?.ToString() ?? "unknown",
                                loc,
                                p.Default is null && p.Type is not NullableTypeSyntax);
                        }).ToList();

                    // Inputs the signature does not show: `{id}` route-template segments and the
                    // scalar properties of the mediator command.
                    var commandTypes = (flow?.CommandParameters ?? [])
                        .ToDictionary(item => item.Name, item => item.Type, StringComparer.OrdinalIgnoreCase);
                    foreach (System.Text.RegularExpressions.Match segment in RouteSegmentPattern.Matches(route))
                    {
                        var segmentName = segment.Groups["name"].Value;
                        if (declaredParameters.Any(item =>
                                item.Name.Equals(segmentName, StringComparison.OrdinalIgnoreCase)))
                        {
                            continue;
                        }
                        declaredParameters.Add(new ParameterRecord(
                            segmentName,
                            commandTypes.TryGetValue(segmentName, out var commandType)
                                ? commandType
                                : RouteConstraintType(segment.Groups["constraint"].Value),
                            "route",
                            !segment.Groups["optional"].Success));
                    }
                    foreach (var (commandName, commandType) in flow?.CommandParameters ?? [])
                    {
                        if (!declaredParameters.Any(item =>
                                item.Name.Equals(commandName, StringComparison.OrdinalIgnoreCase)))
                        {
                            declaredParameters.Add(new ParameterRecord(commandName, commandType, "query", false));
                        }
                    }
                    var parameters = declaredParameters.ToArray();

                    foreach (var httpMethod in httpMethods)
                    {
                        var methodUpper = httpMethod.ToUpperInvariant();
                        var key = $"{methodUpper}:{route}";
                        if (!operationKeys.Add(key)) continue;

                        operations.Add(new OperationRecord(
                            functionName,
                            methodUpper,
                            route,
                            Display(requestType),
                            parameters,
                            [new ResponseRecord(200, Display(responseType))],
                            Location(method),
                            flow?.Record));
                    }
                }
            }
        }

        // Names taken from the OpenAPI document: a project model with the same name is part of the
        // contract even when no endpoint trace reached it.
        var hintSet = new HashSet<string>(hintTypes ?? [], StringComparer.OrdinalIgnoreCase);
        var hinted = hintSet.Count == 0
            ? []
            : sourceTypes.Value
                .Where(type => IsModelType(type) && hintSet.Contains(type.Name))
                .OrderBy(type => FullName(type), StringComparer.Ordinal)
                .ToArray();
        foreach (var type in hinted)
        {
            referencedTypes.Add(type);
        }

        ExpandReferencedTypes(referencedTypes);
        var types = referencedTypes
            .Where(type => type.Locations.Any(location => location.IsInSource))
            .Select(ToTypeRecord)
            .OrderBy(type => type.FullName, StringComparer.Ordinal)
            .ToArray();
        var sourcePaths = operations.Select(item => item.Location.Path)
            .Concat(operations.Where(item => item.Flow is not null)
                .Select(item => item.Flow!.Location.Path))
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
            .Concat(flowDiagnostics)
            .OrderBy(item => item.Code, StringComparer.Ordinal)
            .ThenBy(item => item.Message, StringComparer.Ordinal)
            .ToArray();
        return new ExtractionResult(
            "1.0",
            sources,
            operations.OrderBy(item => item.Route).ThenBy(item => item.Method).ToArray(),
            types,
            diagnostics,
            hinted.Select(FullName).ToArray());
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

    private static string? SyntaxFirstString(AttributeSyntax attribute)
    {
        var firstArg = attribute.ArgumentList?.Arguments.FirstOrDefault();
        if (firstArg is null) return null;
        // String literal: [Attr("value")]
        if (firstArg.Expression is LiteralExpressionSyntax literal &&
            literal.Token.Value is string literalValue)
        {
            return literalValue;
        }
        // nameof expression: [Attr(nameof(Identifier))]
        if (firstArg.Expression is InvocationExpressionSyntax invocation &&
            invocation.Expression is IdentifierNameSyntax { Identifier.Text: "nameof" } &&
            invocation.ArgumentList.Arguments.Count == 1 &&
            invocation.ArgumentList.Arguments[0].Expression is SimpleNameSyntax nameofArg)
        {
            return nameofArg.Identifier.Text;
        }
        return null;
    }

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

    // ------------------------------------------------------------------
    // Azure Functions Isolated Worker helpers
    // ------------------------------------------------------------------

    /// <summary>
    /// Returns the function name from a [Function("name")] or [Function(nameof(X))] attribute,
    /// or null if the method is not an Azure Function.
    /// </summary>
    private static string? AzureFunctionName(
        SyntaxList<AttributeListSyntax> lists,
        SemanticModel semanticModel)
    {
        foreach (var attribute in lists.SelectMany(l => l.Attributes))
        {
            var attrName = attribute.Name.ToString().Split('.').Last()
                .Replace("Attribute", string.Empty, StringComparison.Ordinal);
            if (attrName == "Function")
            {
                // Try string literal or nameof() first.
                var name = SyntaxFirstString(attribute);
                if (name is not null) return name;
                // Constant references such as OperationConstants.OperationName resolve to their value.
                var firstArg = attribute.ArgumentList?.Arguments.FirstOrDefault();
                var constant = firstArg is null ? null : ConstantString(firstArg.Expression, semanticModel);
                if (constant is not null) return constant;
                var fallback = firstArg?.Expression.ToString().Split('.').Last();
                return string.IsNullOrEmpty(fallback) ? "UnknownFunction" : fallback;
            }
        }
        return null;
    }

    /// <summary>
    /// Finds the [HttpTrigger] parameter and returns the declared HTTP methods and route.
    /// Returns null for non-HTTP triggers (queue, blob, timer, cosmos, etc.).
    /// </summary>
    private static (string[] Methods, string? Route)? AzureHttpTrigger(
        ParameterListSyntax paramList,
        SemanticModel semanticModel)
    {
        foreach (var parameter in paramList.Parameters)
        {
            foreach (var attribute in parameter.AttributeLists.SelectMany(l => l.Attributes))
            {
                var attrName = attribute.Name.ToString().Split('.').Last()
                    .Replace("Attribute", string.Empty, StringComparison.Ordinal);
                if (attrName != "HttpTrigger") continue;

                // [HttpTrigger(AuthorizationLevel.xxx, "get", "post", Route = "...")]
                // First positional arg is AuthorizationLevel (skip).
                // Remaining positional string args are the HTTP methods.
                var args = attribute.ArgumentList?.Arguments ?? default;
                var methods = args
                    .Where(a => a.NameEquals is null &&
                        !a.Expression.ToString().Contains("AuthorizationLevel", StringComparison.Ordinal))
                    .Select(a => ConstantString(a.Expression, semanticModel))
                    .Where(m => m is not null)
                    .Select(m => m!)
                    .ToArray();

                var routeArg = args.FirstOrDefault(a =>
                    a.NameEquals?.Name.Identifier.Text == "Route");
                var route = routeArg is null ? null : ConstantString(routeArg.Expression, semanticModel);

                return (methods.Length > 0 ? methods : ["GET", "POST"], route);
            }
        }
        return null;
    }

    /// <summary>
    /// Returns true for Azure Functions framework parameter types that should not be
    /// treated as domain model parameters.
    /// </summary>
    private static bool IsAzureFunctionsFrameworkParam(ParameterSyntax parameter)
    {
        var typeName = parameter.Type?.ToString().Split('.').Last()
            .TrimEnd('?') ?? string.Empty;
        return typeName is "FunctionContext" or "HttpRequestData" or "HttpResponseData" or
            "HttpRequest" or "HttpRequestMessage";
    }

    /// <summary>Literal, nameof(), or compile-time constant string (including const chains).</summary>
    private static string? ConstantString(
        ExpressionSyntax expression,
        SemanticModel semanticModel,
        int depth = 0)
    {
        if (expression is LiteralExpressionSyntax { Token.Value: string literal })
        {
            return literal;
        }
        if (expression is InvocationExpressionSyntax
            {
                Expression: IdentifierNameSyntax { Identifier.Text: "nameof" },
                ArgumentList.Arguments: [{ Expression: var argument }]
            })
        {
            return (argument as SimpleNameSyntax)?.Identifier.Text ??
                (argument as MemberAccessExpressionSyntax)?.Name.Identifier.Text;
        }
        var constant = semanticModel.GetConstantValue(expression);
        if (constant.HasValue)
        {
            return constant.Value as string;
        }

        // Unresolved compilation: follow `Owner.Name` const declarations by syntax.
        var segments = NameSegments(expression);
        if (segments is null || depth > 8)
        {
            return null;
        }
        var qualifier = segments[..^1];
        foreach (var tree in semanticModel.Compilation.SyntaxTrees)
        {
            foreach (var field in tree.GetRoot().DescendantNodes().OfType<FieldDeclarationSyntax>()
                         .Where(item => item.Modifiers.Any(modifier =>
                             modifier.IsKind(Microsoft.CodeAnalysis.CSharp.SyntaxKind.ConstKeyword))))
            {
                var owners = field.Ancestors().OfType<TypeDeclarationSyntax>()
                    .Select(item => item.Identifier.Text).Reverse().ToArray();
                if (qualifier.Length > owners.Length ||
                    !owners.TakeLast(qualifier.Length).SequenceEqual(qualifier))
                {
                    continue;
                }
                foreach (var variable in field.Declaration.Variables.Where(item =>
                             item.Identifier.Text == segments[^1] && item.Initializer is not null))
                {
                    var value = ConstantString(
                        variable.Initializer!.Value,
                        semanticModel.Compilation.GetSemanticModel(tree),
                        depth + 1);
                    if (value is not null)
                    {
                        return value;
                    }
                }
            }
        }
        return null;
    }

    private static string[]? NameSegments(ExpressionSyntax expression) => expression switch
    {
        IdentifierNameSyntax identifier => [identifier.Identifier.Text],
        MemberAccessExpressionSyntax member when NameSegments(member.Expression) is { } head =>
            [.. head, member.Name.Identifier.Text],
        _ => null
    };

    // ------------------------------------------------------------------
    // MediatR command/handler flow behind an endpoint
    // ------------------------------------------------------------------

    private static readonly System.Text.RegularExpressions.Regex RouteSegmentPattern = new(
        @"\{\*?(?<name>[A-Za-z_]\w*)(?::(?<constraint>[^}?=]+))?(?<optional>\?)?[^}]*\}",
        System.Text.RegularExpressions.RegexOptions.Compiled);

    private static string RouteConstraintType(string constraint) => constraint.ToLowerInvariant() switch
    {
        "int" => "int",
        "long" => "long",
        "guid" => "System.Guid",
        "bool" => "bool",
        "datetime" => "System.DateTime",
        _ => "string"
    };

    private sealed record MediatorFlow(
        INamedTypeSymbol Command,
        IReadOnlyList<(string Name, string Type)> CommandParameters,
        INamedTypeSymbol? RequestModel,
        INamedTypeSymbol? ResponseModel,
        IReadOnlyList<INamedTypeSymbol> Related,
        FlowRecord Record);

    private static readonly HashSet<string> ResultPayloadTypes =
    [
        "OkObjectResult", "ObjectResult", "CreatedResult", "CreatedAtActionResult",
        "CreatedAtRouteResult", "AcceptedResult"
    ];

    private static readonly HashSet<string> ResultHelpers = ["Ok", "Created", "CreatedAtAction", "Accepted"];

    private static IEnumerable<INamedTypeSymbol> AllSourceTypes(Compilation compilation)
    {
        foreach (var type in AllTypes(compilation.Assembly.GlobalNamespace))
        {
            yield return type;
        }
        foreach (var reference in compilation.References.OfType<CompilationReference>())
        {
            if (compilation.GetAssemblyOrModuleSymbol(reference) is not IAssemblySymbol assembly)
            {
                continue;
            }
            foreach (var type in AllTypes(assembly.GlobalNamespace))
            {
                yield return type;
            }
        }
    }

    /// <summary>
    /// Follows `mediator.Send(new Command(...))` from an endpoint to the command's model,
    /// its IRequestHandler, the payload the handler returns, and the mappers/backend clients it uses.
    /// </summary>
    private static MediatorFlow? TraceMediatorFlow(
        MethodDeclarationSyntax method,
        SemanticModel semanticModel,
        Compilation compilation,
        IReadOnlyList<INamedTypeSymbol> sourceTypes,
        List<DiagnosticRecord> diagnostics)
    {
        INamedTypeSymbol? command = null;
        foreach (var invocation in method.DescendantNodes().OfType<InvocationExpressionSyntax>())
        {
            var name = invocation.Expression switch
            {
                MemberAccessExpressionSyntax member => member.Name.Identifier.Text,
                IdentifierNameSyntax identifier => identifier.Identifier.Text,
                _ => string.Empty
            };
            if (name != "Send" || invocation.ArgumentList.Arguments.Count == 0)
            {
                continue;
            }
            var candidate = SyntaxPayloadType(
                invocation.ArgumentList.Arguments[0].Expression, method, semanticModel, compilation);
            if (candidate is not null && IsProjectType(candidate))
            {
                command = candidate;
                break;
            }
        }
        if (command is null)
        {
            return null;
        }

        var requestModel = command.GetMembers().OfType<IPropertySymbol>()
            .Where(property => !property.IsStatic)
            .Select(property => PayloadType(property.Type))
            .OfType<INamedTypeSymbol>()
            .FirstOrDefault(type => IsProjectType(type) &&
                type.TypeKind is Microsoft.CodeAnalysis.TypeKind.Class or Microsoft.CodeAnalysis.TypeKind.Struct &&
                !SymbolEqualityComparer.Default.Equals(type, command));

        // Scalar command properties (ids, filters, ...) are the endpoint's route/query inputs.
        var commandParameters = command.GetMembers().OfType<IPropertySymbol>()
            .Where(property => !property.IsStatic &&
                property.DeclaredAccessibility == Accessibility.Public &&
                property.Name is not ("Headers" or "Operation" or "EqualityContract") &&
                property.Type.Name is not ("IHeaderDictionary" or "CancellationToken" or "HttpRequest") &&
                !(PayloadType(property.Type) is INamedTypeSymbol modelType && IsProjectType(modelType)))
            .Select(property => (property.Name, Display(property.Type) ?? property.Type.Name))
            .ToArray();

        var handler = sourceTypes
            .Where(type => type.TypeKind == Microsoft.CodeAnalysis.TypeKind.Class &&
                ImplementsHandler(type, command))
            .OrderBy(type => FullName(type), StringComparer.Ordinal)
            .FirstOrDefault();
        if (handler is null)
        {
            diagnostics.Add(new DiagnosticRecord(
                "warning", "FLOW001", $"No IRequestHandler found for command {command.Name}."));
            return new MediatorFlow(
                command, commandParameters, requestModel, null, [],
                new FlowRecord("mediator", FullName(command), null, [], [], [], Location(command)));
        }

        var declarations = handler.DeclaringSyntaxReferences
            .Select(reference => reference.GetSyntax())
            .OfType<TypeDeclarationSyntax>()
            .ToArray();
        var responseModel = declarations
            .SelectMany(declaration => declaration.DescendantNodes())
            .Select(node => HandlerPayload(node, sourceTypes))
            .FirstOrDefault(type => type is not null);

        var mappings = new List<MappingRecord>();
        foreach (var generic in declarations.SelectMany(item => item.DescendantNodes())
                     .OfType<GenericNameSyntax>()
                     .Where(item => item.Identifier.Text == "GetMapper" &&
                         item.TypeArgumentList.Arguments.Count == 2))
        {
            mappings.Add(new MappingRecord(
                TypeName(generic.TypeArgumentList.Arguments[0], sourceTypes),
                TypeName(generic.TypeArgumentList.Arguments[1], sourceTypes),
                "GetMapper"));
        }
        var constructorParameters = declarations
            .SelectMany(item => item.Members.OfType<ConstructorDeclarationSyntax>())
            .SelectMany(item => item.ParameterList.Parameters)
            .Where(parameter => parameter.Type is not null)
            .ToArray();
        foreach (var parameter in constructorParameters)
        {
            var injected = TypeByName(parameter.Type!, sourceTypes);
            if (injected is null || injected.TypeKind != Microsoft.CodeAnalysis.TypeKind.Class)
            {
                continue;
            }
            var mapper = injected.AllInterfaces.FirstOrDefault(item =>
                item.Name == "IMapper" && item.TypeArguments.Length == 2);
            if (mapper is not null)
            {
                mappings.Add(new MappingRecord(
                    Display(mapper.TypeArguments[0])!, Display(mapper.TypeArguments[1])!, injected.Name));
                continue;
            }
            var map = injected.GetMembers("Map").OfType<IMethodSymbol>()
                .FirstOrDefault(item => item.Parameters.Length > 0);
            if (map is not null && PayloadType(map.ReturnType) is { } mapped &&
                PayloadType(map.Parameters[0].Type) is { } source)
            {
                mappings.Add(new MappingRecord(Display(source)!, Display(mapped)!, injected.Name));
            }
        }

        var backends = constructorParameters
            .SelectMany(parameter => parameter.Type!.DescendantNodesAndSelf().OfType<SimpleNameSyntax>())
            .Select(name => name.Identifier.Text)
            .Where(name => System.Text.RegularExpressions.Regex.IsMatch(name, @"Client(v\d+)?$"))
            .Distinct(StringComparer.Ordinal)
            .Order(StringComparer.Ordinal)
            .ToArray();

        var orderedMappings = mappings
            .DistinctBy(item => (item.From, item.To, item.Via))
            .OrderBy(item => item.Via, StringComparer.Ordinal)
            .ThenBy(item => item.From, StringComparer.Ordinal)
            .ThenBy(item => item.To, StringComparer.Ordinal)
            .ToArray();

        // Every model the flow touches: mapper endpoints, then models used by the handler, the
        // mapper implementations, and the backend client contracts.
        var byFullName = sourceTypes.ToLookup(item => FullName(item), StringComparer.Ordinal);
        var related = new List<(INamedTypeSymbol Type, string Role)>();
        foreach (var mapping in orderedMappings)
        {
            if (byFullName[mapping.From].FirstOrDefault() is { } from)
            {
                related.Add((from, "mapping-source"));
            }
            if (byFullName[mapping.To].FirstOrDefault() is { } to)
            {
                related.Add((to, "mapping-target"));
            }
        }
        related.AddRange(ModelsIn(declarations, sourceTypes).Select(item => (item, "handler")));

        var mapperTypes = new List<INamedTypeSymbol>();
        foreach (var mapping in orderedMappings)
        {
            mapperTypes.AddRange(mapping.Via == "GetMapper"
                ? sourceTypes.Where(item => item.TypeKind == Microsoft.CodeAnalysis.TypeKind.Class &&
                    ImplementsMapper(item, SimpleName(mapping.From), SimpleName(mapping.To)))
                : sourceTypes.Where(item => item.Name == mapping.Via));
        }
        related.AddRange(ModelsIn(TypeDeclarations(mapperTypes), sourceTypes)
            .Select(item => (item, "mapper")));

        var clientTypes = sourceTypes.Where(item => backends.Any(backend =>
            item.Name == backend ||
            (backend.Length > 1 && backend[0] == 'I' && char.IsUpper(backend[1]) &&
                item.Name == backend[1..])));
        related.AddRange(ModelsIn(TypeDeclarations(clientTypes), sourceTypes)
            .Select(item => (item, "client")));

        var roleRank = new[] { "mapping-source", "mapping-target", "handler", "mapper", "client" };
        var relatedTypes = related
            .Where(item => !SymbolEqualityComparer.Default.Equals(item.Type, command))
            .OrderBy(item => Array.IndexOf(roleRank, item.Role))
            .ThenBy(item => FullName(item.Type), StringComparer.Ordinal)
            .DistinctBy(item => FullName(item.Type))
            .ToArray();

        return new MediatorFlow(
            command,
            commandParameters,
            requestModel,
            responseModel,
            relatedTypes.Select(item => item.Type).ToArray(),
            new FlowRecord(
                "mediator",
                FullName(command),
                FullName(handler),
                orderedMappings,
                backends,
                relatedTypes
                    .Select(item => new RelatedTypeRecord(FullName(item.Type), item.Role))
                    .ToArray(),
                Location(handler)));
    }

    private static readonly string[] NonModelSuffixes =
    [
        "Exception", "Helper", "Client", "Mapper", "Factory", "Formatter", "Handler",
        "Options", "Settings", "Utils", "Constants"
    ];

    private static bool IsModelType(INamedTypeSymbol type) =>
        type.TypeKind is Microsoft.CodeAnalysis.TypeKind.Class or Microsoft.CodeAnalysis.TypeKind.Struct &&
        !type.IsStatic && !ResultPayloadTypes.Contains(type.Name) &&
        !NonModelSuffixes.Any(suffix => type.Name.EndsWith(suffix, StringComparison.Ordinal)) &&
        type.GetMembers().OfType<IPropertySymbol>().Any(property =>
            !property.IsStatic && property.DeclaredAccessibility == Accessibility.Public);

    private static string SimpleName(string fullName) => fullName.Split('.').Last();

    private static IEnumerable<TypeDeclarationSyntax> TypeDeclarations(IEnumerable<INamedTypeSymbol> types) =>
        types.SelectMany(type => type.DeclaringSyntaxReferences)
            .Select(reference => reference.GetSyntax())
            .OfType<TypeDeclarationSyntax>();

    private static bool ImplementsMapper(INamedTypeSymbol type, string from, string to) =>
        type.DeclaringSyntaxReferences.Select(reference => reference.GetSyntax())
            .OfType<TypeDeclarationSyntax>()
            .Any(declaration => declaration.BaseList?.Types.Any(baseType =>
                baseType.Type.DescendantNodesAndSelf().OfType<GenericNameSyntax>().Any(generic =>
                    generic.Identifier.Text == "IMapper" &&
                    generic.TypeArgumentList.Arguments.Count == 2 &&
                    SimpleTypeName(generic.TypeArgumentList.Arguments[0]) == from &&
                    SimpleTypeName(generic.TypeArgumentList.Arguments[1]) == to)) == true);

    private static string? SimpleTypeName(TypeSyntax type) =>
        type.DescendantNodesAndSelf().OfType<SimpleNameSyntax>().LastOrDefault()?.Identifier.Text;

    /// <summary>Project model types named by object creations, locals, parameters, returns and properties.</summary>
    private static IEnumerable<INamedTypeSymbol> ModelsIn(
        IEnumerable<SyntaxNode> roots,
        IReadOnlyList<INamedTypeSymbol> sourceTypes)
    {
        var byName = sourceTypes.Where(IsModelType).ToLookup(item => item.Name, StringComparer.Ordinal);
        foreach (var node in roots.SelectMany(root => root.DescendantNodesAndSelf()))
        {
            TypeSyntax? type = node switch
            {
                ObjectCreationExpressionSyntax creation => creation.Type,
                VariableDeclarationSyntax variable => variable.Type,
                ParameterSyntax parameter => parameter.Type,
                MethodDeclarationSyntax method => method.ReturnType,
                PropertyDeclarationSyntax property => property.Type,
                _ => null
            };
            if (type is null)
            {
                continue;
            }
            foreach (var name in type.DescendantNodesAndSelf().OfType<SimpleNameSyntax>())
            {
                var model = byName[name.Identifier.Text]
                    .OrderBy(item => FullName(item), StringComparer.Ordinal)
                    .FirstOrDefault();
                if (model is not null)
                {
                    yield return model;
                }
            }
        }
    }

    private static bool ImplementsHandler(INamedTypeSymbol type, INamedTypeSymbol command) =>
        type.AllInterfaces.Any(item => item.Name == "IRequestHandler" &&
            item.TypeArguments.Length > 0 &&
            SymbolEqualityComparer.Default.Equals(item.TypeArguments[0], command)) ||
        type.DeclaringSyntaxReferences.Select(reference => reference.GetSyntax())
            .OfType<TypeDeclarationSyntax>()
            .Any(declaration => declaration.BaseList?.Types.Any(baseType =>
                baseType.Type.DescendantNodesAndSelf().OfType<GenericNameSyntax>().Any(generic =>
                    generic.Identifier.Text == "IRequestHandler" &&
                    generic.TypeArgumentList.Arguments.Count > 0 &&
                    generic.TypeArgumentList.Arguments[0].DescendantNodesAndSelf()
                        .OfType<SimpleNameSyntax>().LastOrDefault()?.Identifier.Text == command.Name)) == true);

    /// <summary>Payload of `new OkObjectResult(x)` / `Ok(x)` style results, resolved syntactically.</summary>
    private static INamedTypeSymbol? HandlerPayload(
        SyntaxNode node,
        IReadOnlyList<INamedTypeSymbol> sourceTypes)
    {
        ArgumentListSyntax? arguments = null;
        if (node is ObjectCreationExpressionSyntax creation &&
            creation.Type.DescendantNodesAndSelf().OfType<SimpleNameSyntax>().LastOrDefault()
                ?.Identifier.Text is { } created && ResultPayloadTypes.Contains(created))
        {
            arguments = creation.ArgumentList;
        }
        else if (node is InvocationExpressionSyntax invocation)
        {
            var helper = invocation.Expression switch
            {
                IdentifierNameSyntax identifier => identifier.Identifier.Text,
                MemberAccessExpressionSyntax member => member.Name.Identifier.Text,
                _ => string.Empty
            };
            if (ResultHelpers.Contains(helper))
            {
                arguments = invocation.ArgumentList;
            }
        }
        var payload = arguments?.Arguments.LastOrDefault()?.Expression;
        return payload is null
            ? null
            : SyntaxExpressionType(
                payload,
                node.Ancestors().OfType<MethodDeclarationSyntax>().FirstOrDefault(),
                sourceTypes,
                0);
    }

    private static INamedTypeSymbol? SyntaxExpressionType(
        ExpressionSyntax expression,
        MethodDeclarationSyntax? scope,
        IReadOnlyList<INamedTypeSymbol> sourceTypes,
        int depth)
    {
        if (depth > 4)
        {
            return null;
        }
        switch (expression)
        {
            case AwaitExpressionSyntax awaited:
                return SyntaxExpressionType(awaited.Expression, scope, sourceTypes, depth + 1);
            case ObjectCreationExpressionSyntax creation:
                return TypeByName(creation.Type, sourceTypes);
            case InvocationExpressionSyntax invocation:
                return InvocationResultType(invocation, scope, sourceTypes, depth);
            case IdentifierNameSyntax identifier when scope is not null:
                var parameter = scope.ParameterList.Parameters.FirstOrDefault(item =>
                    item.Identifier.Text == identifier.Identifier.Text);
                if (parameter?.Type is not null)
                {
                    return TypeByName(parameter.Type, sourceTypes);
                }
                var variable = scope.DescendantNodes().OfType<VariableDeclaratorSyntax>()
                    .FirstOrDefault(item => item.Identifier.Text == identifier.Identifier.Text);
                if (variable?.Parent is VariableDeclarationSyntax declaration)
                {
                    return TypeByName(declaration.Type, sourceTypes) ??
                        (variable.Initializer?.Value is { } value
                            ? SyntaxExpressionType(value, scope, sourceTypes, depth + 1)
                            : null);
                }
                return null;
            default:
                return null;
        }
    }

    private static readonly HashSet<string> GenericResultMethods =
    [
        "Map", "Deserialize", "DeserializeObject", "ReadFromJsonAsync", "ReadAsAsync",
        "GetFromJsonAsync", "ToObject", "Convert"
    ];

    private static GenericNameSyntax? GenericNameOf(InvocationExpressionSyntax invocation) =>
        (invocation.Expression as MemberAccessExpressionSyntax)?.Name as GenericNameSyntax ??
        invocation.Expression as GenericNameSyntax;

    /// <summary>Type produced by `Map<T>(..)`, `Deserialize<T>(..)`, a factory mapper, or a mapper/client method.</summary>
    private static INamedTypeSymbol? InvocationResultType(
        InvocationExpressionSyntax invocation,
        MethodDeclarationSyntax? scope,
        IReadOnlyList<INamedTypeSymbol> sourceTypes,
        int depth)
    {
        if (GenericNameOf(invocation) is { TypeArgumentList.Arguments.Count: 1 } generic &&
            GenericResultMethods.Contains(generic.Identifier.Text))
        {
            return TypeByName(generic.TypeArgumentList.Arguments[0], sourceTypes);
        }
        if (invocation.Expression is not MemberAccessExpressionSyntax { Expression: var receiver } member)
        {
            return null;
        }

        var methodName = member.Name.Identifier.Text;
        if (receiver is IdentifierNameSyntax variable && scope is not null && methodName == "Map")
        {
            // var mapper = factory.GetMapper<TIn, TOut>(..); mapper.Map(x) => TOut
            var initializer = scope.DescendantNodes().OfType<VariableDeclaratorSyntax>()
                .FirstOrDefault(item => item.Identifier.Text == variable.Identifier.Text)
                ?.Initializer?.Value;
            while (initializer is AwaitExpressionSyntax awaited)
            {
                initializer = awaited.Expression;
            }
            if (initializer is InvocationExpressionSyntax created &&
                GenericNameOf(created) is { Identifier.Text: "GetMapper", TypeArgumentList.Arguments.Count: 2 } mapper)
            {
                return TypeByName(mapper.TypeArgumentList.Arguments[1], sourceTypes);
            }
        }

        var receiverType = ReceiverType(receiver, scope, sourceTypes, depth);
        var method = receiverType?.GetMembers(methodName).OfType<IMethodSymbol>().FirstOrDefault();
        return method is not null && PayloadType(method.ReturnType) is INamedTypeSymbol result &&
            IsProjectType(result) && result.TypeKind is Microsoft.CodeAnalysis.TypeKind.Class
                or Microsoft.CodeAnalysis.TypeKind.Struct
            ? result
            : null;
    }

    private static INamedTypeSymbol? ReceiverType(
        ExpressionSyntax receiver,
        MethodDeclarationSyntax? scope,
        IReadOnlyList<INamedTypeSymbol> sourceTypes,
        int depth)
    {
        if (receiver is not IdentifierNameSyntax identifier || scope is null)
        {
            return null;
        }
        var name = identifier.Identifier.Text;
        var parameter = scope.ParameterList.Parameters.FirstOrDefault(item => item.Identifier.Text == name);
        if (parameter?.Type is not null)
        {
            return TypeByName(parameter.Type, sourceTypes, anyKind: true);
        }
        var local = scope.DescendantNodes().OfType<VariableDeclaratorSyntax>()
            .FirstOrDefault(item => item.Identifier.Text == name);
        if (local?.Parent is VariableDeclarationSyntax declaration)
        {
            return TypeByName(declaration.Type, sourceTypes, anyKind: true) ??
                (local.Initializer?.Value is { } value
                    ? SyntaxExpressionType(value, scope, sourceTypes, depth + 1)
                    : null);
        }
        var field = scope.Ancestors().OfType<TypeDeclarationSyntax>().FirstOrDefault()
            ?.Members.OfType<FieldDeclarationSyntax>()
            .FirstOrDefault(item => item.Declaration.Variables.Any(variable => variable.Identifier.Text == name));
        return field is null ? null : TypeByName(field.Declaration.Type, sourceTypes, anyKind: true);
    }

    private static INamedTypeSymbol? TypeByName(
        TypeSyntax type,
        IReadOnlyList<INamedTypeSymbol> sourceTypes,
        bool anyKind = false)
    {
        var name = type.DescendantNodesAndSelf().OfType<SimpleNameSyntax>().LastOrDefault()?.Identifier.Text;
        return name is null
            ? null
            : sourceTypes
                .Where(item => item.Name == name && (anyKind ||
                    item.TypeKind is Microsoft.CodeAnalysis.TypeKind.Class or Microsoft.CodeAnalysis.TypeKind.Struct))
                .OrderBy(item => FullName(item), StringComparer.Ordinal)
                .FirstOrDefault();
    }

    private static string TypeName(TypeSyntax type, IReadOnlyList<INamedTypeSymbol> sourceTypes) =>
        TypeByName(type, sourceTypes) is { } resolved ? FullName(resolved) : type.ToString();

}
