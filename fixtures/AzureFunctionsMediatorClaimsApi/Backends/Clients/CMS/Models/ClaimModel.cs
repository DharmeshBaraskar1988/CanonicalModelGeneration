namespace Fixture.Claims.Backends.Clients.CMS.Models;

public class ClaimModel
{
    public LossEventModel_v3 Claim { get; set; }
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
