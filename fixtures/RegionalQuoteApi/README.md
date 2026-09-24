# Regional Quote API fixture

This synthetic, non-production fixture is the initial Discovery MVP input. It contains no confidential, personal, or regulated data.

## Source descriptor

- Region: `IN`
- System: `regional-quote-api-fixture`
- Solution: `fixtures/RegionalQuoteApi/RegionalQuoteApi.sln`
- Project: `fixtures/RegionalQuoteApi/src/RegionalQuoteApi/RegionalQuoteApi.csproj`
- Target framework: `.NET 8` (`net8.0`)
- Required SDK: a .NET SDK capable of targeting `net8.0`; .NET 8 is the project baseline, with major-version runtime roll-forward enabled for local verification
- OpenAPI: `fixtures/RegionalQuoteApi/openapi/quote-api.yaml` (OpenAPI 3.0.3)
- Source exclusions: `bin/`, `obj/`

## Discovery surface

- `POST /api/v1/quotes` creates a quote from nested request DTOs, validation attributes, an enum, and a collection.
- `GET /api/v1/quotes/{quoteId}` returns the quote or a 404 response.
- The OpenAPI document mirrors the controller contract and provides local component references and constraints.

## Verification

```powershell
dotnet restore fixtures/RegionalQuoteApi/RegionalQuoteApi.sln
dotnet build fixtures/RegionalQuoteApi/RegionalQuoteApi.sln --no-restore
```
