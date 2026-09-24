using System.Collections.Concurrent;
using RegionalQuoteApi.Models;

namespace RegionalQuoteApi.Services;

public sealed class InMemoryQuoteService : IQuoteService
{
    private readonly ConcurrentDictionary<Guid, QuoteResponse> _quotes = new();

    public QuoteResponse Create(CreateQuoteRequest request)
    {
        var quote = new QuoteResponse
        {
            QuoteId = Guid.NewGuid(),
            Status = QuoteStatus.Offered,
            Premium = decimal.Round(request.CoverageAmount * 0.0125m, 2),
            ValidUntil = DateTimeOffset.UtcNow.AddDays(30)
        };

        _quotes[quote.QuoteId] = quote;
        return quote;
    }

    public QuoteResponse? Get(Guid quoteId) =>
        _quotes.GetValueOrDefault(quoteId);
}
