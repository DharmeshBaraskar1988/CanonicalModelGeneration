using RegionalQuoteApi.Services;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddControllers();
builder.Services.AddSingleton<IQuoteService, InMemoryQuoteService>();

var app = builder.Build();

app.MapControllers();

app.Run();

public partial class Program;
