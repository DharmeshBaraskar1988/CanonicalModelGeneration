namespace RegionalQuoteApi.Models;

public sealed class QuoteResponse
{
    public required Guid QuoteId { get; init; }

    public QuoteStatus Status { get; init; }

    public decimal Premium { get; init; }

    public DateTimeOffset ValidUntil { get; init; }
}

public enum CoverageType
{
    Liability,
    Collision,
    Comprehensive
}

public enum QuoteStatus
{
    Draft,
    Offered,
    Expired
}
