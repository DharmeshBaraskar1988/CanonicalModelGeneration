namespace Fixture.Claims.Backends.Clients.CMS.Models;

public class ClaimModel
{
    public LossEventModel_v3 Claim { get; set; }
    public GeneralPartyModel_v3 Allocate { get; set; }
    public GeneralPartyModel_v3 Broker { get; set; }
    public GeneralPartyModel_v3 Claimant { get; set; }
    public GeneralPartyModel_v3 Supervisor { get; set; }
    public GeneralPartyModel_v3 Expert { get; set; }
    public GeneralPartyModel_v3 Insured { get; set; }
}

public class GeneralPartyModel_v3
{
    public ItemIdInfoModel_v3 IdInfo { get; set; }
}

// Not reachable from any traced endpoint; only the OpenAPI document names it.
public class SearchModel_v3
{
    public string PolicyNumber { get; set; }
}

public class LossEventModel_v3
{
    public ItemIdInfoModel_v3 IdInfo { get; set; }
    public ItemIdInfoModel_v3 PolicyInfo { get; set; }
}

public class ItemIdInfoModel_v3
{
    public string SystemId { get; set; }
}

public class SoapEnvelope
{
    public string Body { get; set; }
}

public class RestResponse
{
    public string Content { get; set; }
    public int StatusCode { get; set; }
}

public class ClaimIBO
{
    public string Id { get; set; }
}
