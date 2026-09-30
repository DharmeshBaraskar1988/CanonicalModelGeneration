using Fixture.Claims.Backends.Clients.CMS.Models;

namespace Fixture.Claims.Backends.Clients.CMS.Mappers;

public class CreateClaimDataResponseToClaimv1Mapper : IMapper<RestResponse, ClaimModel>
{
    public Task<ClaimModel> Map(RestResponse response) => Task.FromResult(new ClaimModel());
}

public class ClaimMapToIDIT
{
    public Task<ClaimIBO> Map(LossEventModel_v3 claim) => Task.FromResult(new ClaimIBO());
}
