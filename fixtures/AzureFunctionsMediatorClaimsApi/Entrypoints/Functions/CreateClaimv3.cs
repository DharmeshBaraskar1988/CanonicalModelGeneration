using AppCommand = Fixture.Claims.Application.Commands;
using Fixture.Claims.Backends.Clients.CMS.Models;

namespace Fixture.Claims.Entrypoints.Functions;

/// <summary>Represents the root endpoint of a Service Azure Function App Operation.</summary>
public class CreateClaimv3 : ResponseBuilderFunctionRunner<CreateClaimv3>
{
    internal class OperationConstants
    {
        public const string OperationName = Constants.Operation.ServiceCreateClaim;
    }

    protected override string OperationName => OperationConstants.OperationName;

    private readonly IMediator _mediator;

    public CreateClaimv3(IMediator mediator)
    {
        _mediator = mediator;
    }

    [Function(OperationConstants.OperationName)]
    public async Task<IActionResult> Operation(
        [HttpTrigger(AuthorizationLevel.Anonymous, "POST", Route = "eu/cor01sh01/svc/claim/v3/service/claims")] HttpRequest request)
    {
        return await Handle<JObject, ClaimModel>(request, (body, req) =>
            _mediator.Send(new AppCommand.CreateClaimRequestv1(req.Headers, body, OperationName)));
    }
}
