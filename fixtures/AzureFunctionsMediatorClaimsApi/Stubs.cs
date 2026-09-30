namespace Fixture.Claims;

// Minimal stand-ins for framework/package types so the fixture compiles offline.
public enum AuthorizationLevel { Anonymous, Function }

[AttributeUsage(AttributeTargets.Method)]
public sealed class FunctionAttribute(string name) : Attribute
{
    public string Name { get; } = name;
}

[AttributeUsage(AttributeTargets.Parameter)]
public sealed class HttpTriggerAttribute(AuthorizationLevel level, params string[] methods) : Attribute
{
    public string Route { get; set; }
}

public interface IHeaderDictionary { }

public class HttpRequest
{
    public IHeaderDictionary Headers { get; }
}

public interface IActionResult { }

public class OkObjectResult(object value) : IActionResult
{
    public object Value { get; } = value;
    public int? StatusCode { get; set; }
}

public class JObject { }

public interface IRequest<TResponse> { }

public interface IRequestHandler<TRequest, TResponse> where TRequest : IRequest<TResponse>
{
    Task<TResponse> Handle(TRequest request, CancellationToken cancellationToken);
}

public interface IMediator
{
    Task<TResponse> Send<TResponse>(IRequest<TResponse> request, CancellationToken cancellationToken = default);
}

public abstract class ResponseBuilderFunctionRunner<T>
{
    protected abstract string OperationName { get; }

    protected Task<IActionResult> Handle<TIn, TOut>(
        HttpRequest request,
        Func<TOut, HttpRequest, Task<IActionResult>> action) => action(default, request);
}

public interface IMapper<TIn, TOut>
{
    Task<TOut> Map(TIn input);
}

public interface IMapperFactory
{
    IMapper<TIn, TOut> GetMapper<TIn, TOut>(object options);
}

public interface IClientFactory<T> { T GetClient(); }
public interface IAgoraClientv1 { }
public interface ICMSClientv1 { }
public interface IVLookupClient { }

public static class Constants
{
    public static class Operation
    {
        public const string ServiceCreateClaim = "CreateClaim";
    }
}
