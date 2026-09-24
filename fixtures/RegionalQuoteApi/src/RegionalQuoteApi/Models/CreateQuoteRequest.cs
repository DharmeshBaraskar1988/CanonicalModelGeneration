using System.ComponentModel.DataAnnotations;

namespace RegionalQuoteApi.Models;

public sealed class CreateQuoteRequest
{
    [Required]
    [StringLength(80, MinimumLength = 2)]
    public required string ApplicantName { get; init; }

    [Required]
    public required AddressDto Address { get; init; }

    [Range(18, 100)]
    public int ApplicantAge { get; init; }

    public CoverageType CoverageType { get; init; }

    [Range(typeof(decimal), "1000", "1000000")]
    public decimal CoverageAmount { get; init; }

    [MinLength(1)]
    public IReadOnlyList<VehicleDto> Vehicles { get; init; } = [];
}

public sealed class AddressDto
{
    [Required]
    [StringLength(120)]
    public required string Line1 { get; init; }

    [Required]
    [RegularExpression("^[0-9]{5}$")]
    public required string PostalCode { get; init; }
}

public sealed class VehicleDto
{
    [Required]
    [StringLength(17, MinimumLength = 17)]
    public required string Vin { get; init; }

    [Range(1980, 2100)]
    public int ModelYear { get; init; }
}
