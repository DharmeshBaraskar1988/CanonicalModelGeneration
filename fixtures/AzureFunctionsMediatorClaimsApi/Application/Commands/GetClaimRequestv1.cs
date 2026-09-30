using Fixture.Claims.Backends.Clients.CMS.Mappers;
using Fixture.Claims.Backends.Clients.CMS.Models;

namespace Fixture.Claims.Application.Commands;

public record GetClaimRequestv1(IHeaderDictionary Headers, string Id, string Operation)
    : IRequest<IActionResult>;

public class GetClaimRequestHandlerv1 : IRequestHandler<GetClaimRequestv1, IActionResult>
{
    private readonly ClaimMapper _claimMapper;

    public GetClaimRequestHandlerv1(ClaimMapper claimMapper)
    {
        _claimMapper = claimMapper;
    }

    public async Task<IActionResult> Handle(GetClaimRequestv1 request, CancellationToken cancellationToken)
    {
        var result = await _claimMapper.Map(new RestResponse());
        return new OkObjectResult(result);
    }
}
