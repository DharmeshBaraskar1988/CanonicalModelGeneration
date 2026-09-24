using Microsoft.AspNetCore.Mvc;
using RegionalQuoteApi.Models;
using RegionalQuoteApi.Services;

namespace RegionalQuoteApi.Controllers;

[ApiController]
[Route("api/v1/quotes")]
public sealed class QuotesController(IQuoteService quoteService) : ControllerBase
{
    [HttpPost]
    [ProducesResponseType<QuoteResponse>(StatusCodes.Status201Created)]
    [ProducesResponseType<ValidationProblemDetails>(StatusCodes.Status400BadRequest)]
    public ActionResult<QuoteResponse> CreateQuote([FromBody] CreateQuoteRequest request)
    {
        var quote = quoteService.Create(request);
        return CreatedAtAction(nameof(GetQuote), new { quoteId = quote.QuoteId }, quote);
    }

    [HttpGet("{quoteId:guid}")]
    [ProducesResponseType<QuoteResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<QuoteResponse> GetQuote([FromRoute] Guid quoteId)
    {
        var quote = quoteService.Get(quoteId);
        return quote is null ? NotFound() : Ok(quote);
    }
}
