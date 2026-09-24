using RegionalQuoteApi.Models;

namespace RegionalQuoteApi.Services;

public interface IQuoteService
{
    QuoteResponse Create(CreateQuoteRequest request);

    QuoteResponse? Get(Guid quoteId);
}
