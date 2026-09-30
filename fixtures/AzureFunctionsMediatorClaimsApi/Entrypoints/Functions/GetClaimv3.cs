using AppCommand = Fixture.Claims.Application.Commands;
using Fixture.Claims.Backends.Clients.CMS.Models;

namespace Fixture.Claims.Entrypoints.Functions;

/// <summary>GET endpoint that exists in code only; its inputs come from the route template.</summary>
public class GetClaimv3 : ResponseBuilderFunctionRunner<GetClaimv3>
{
    protected override string OperationName => Constants.Operation.ServiceGetClaim;

    private readonly IMediator _mediator;

    public GetClaimv3(IMediator mediator)
    {
        _mediator = mediator;
    }

    [Function(Constants.Operation.ServiceGetClaim)]
    public async Task<IActionResult> Operation(
        [HttpTrigger(AuthorizationLevel.Anonymous, "GET", Route = "eu/cor01sh01/svc/claim/v3/service/claims/{id:int}")] HttpRequest request)
    {
        return await Handle<JObject, ClaimModel>(request, (body, req) =>
            _mediator.Send(new AppCommand.GetClaimRequestv1(req.Headers, null, OperationName)));
    }
}
