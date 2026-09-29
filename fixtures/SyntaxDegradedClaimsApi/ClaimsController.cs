using Missing.AspNetCore.Mvc;

namespace SyntaxDegradedClaimsApi;

[ApiController]
[Route("api/[controller]")]
public class ClaimsController : ControllerBase
{
    [HttpPost]
    public Task<ActionResult<InsuranceClaim>> SubmitClaim([FromBody] ClaimDto claimDto) =>
        throw new NotImplementedException();

    [HttpGet]
    public Task<ActionResult<List<InsuranceClaim>>> GetAllClaims() =>
        throw new NotImplementedException();
}

public sealed class ClaimDto
{
    public string PolicyNumber { get; set; } = string.Empty;
    public ClaimAddress Address { get; set; } = new();
}

public sealed class ClaimAddress
{
    public string PostalCode { get; set; } = string.Empty;
}

public sealed class InsuranceClaim
{
    public int Id { get; set; }
    public string PolicyNumber { get; set; } = string.Empty;
}
