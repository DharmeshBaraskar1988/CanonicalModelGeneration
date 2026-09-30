using Fixture.Claims.Backends.Clients.CMS.Mappers;
using Fixture.Claims.Backends.Clients.CMS.Models;

namespace Fixture.Claims.Application.Commands;

public record CreateClaimRequestv1(IHeaderDictionary Headers, ClaimModel Content, string Operation)
    : IRequest<IActionResult>;

public class CreateClaimRequestHandlerv1 : IRequestHandler<CreateClaimRequestv1, IActionResult>
{
    private readonly ICMSClientv1 _cmsClient;
    private readonly IMapperFactory _mapperFactory;
    private readonly ClaimMapToIDIT _claimMapToIDIT;

    public CreateClaimRequestHandlerv1(
        IClientFactory<IAgoraClientv1> clientFactory,
        IClientFactory<ICMSClientv1> cmsClientFactory,
        IMapperFactory mapperFactory,
        IVLookupClient vlookupClient,
        ClaimMapToIDIT claimMapToIDIT)
    {
        _cmsClient = cmsClientFactory.GetClient();
        _mapperFactory = mapperFactory;
        _claimMapToIDIT = claimMapToIDIT;
    }

    public async Task<IActionResult> Handle(CreateClaimRequestv1 request, CancellationToken cancellationToken)
    {
        if (request.Content?.Claim?.PolicyInfo != null)
        {
            return await SendToIDIT(request.Content);
        }
        return await SendToCMS(request.Content);
    }

    public async Task<IActionResult> SendToIDIT(ClaimModel body)
    {
        ClaimIBO req = await _claimMapToIDIT.Map(body.Claim);
        var responseClaim = new LossEventModel_v3();
        return new OkObjectResult(new ClaimModel { Claim = responseClaim });
    }

    public async Task<IActionResult> SendToCMS(ClaimModel body)
    {
        var requestMapper = _mapperFactory.GetMapper<ClaimModel, SoapEnvelope>(new object());
        var soap = await requestMapper.Map(body);
        var responseMapper = _mapperFactory.GetMapper<RestResponse, ClaimModel>(new object());
        ClaimModel responsetoNexus = new ClaimModel();
        responsetoNexus = await responseMapper.Map(new RestResponse());
        return new OkObjectResult(responsetoNexus) { StatusCode = 200 };
    }
}
