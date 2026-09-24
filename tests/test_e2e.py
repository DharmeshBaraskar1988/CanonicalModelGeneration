import json
import subprocess
import sys
from hashlib import sha256
from pathlib import Path


def test_quote_fixture_matches_golden_discovery(tmp_path: Path) -> None:
    repository = Path("fixtures/RegionalQuoteApi").resolve()
    output = tmp_path / "discovery"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "canonical_model_generator.cli",
            "--region",
            "IN",
            "--system",
            "regional-quote-api-fixture",
            "--repository",
            str(repository),
            "--project",
            str(repository / "src/RegionalQuoteApi/RegionalQuoteApi.csproj"),
            "--openapi",
            str(repository / "openapi/quote-api.yaml"),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr

    golden = json.loads(
        Path("tests/golden/discovery-output.sha256.json").read_text(encoding="utf-8")
    )
    actual_hashes = {
        path.name: sha256(path.read_bytes()).hexdigest() for path in sorted(output.iterdir())
    }
    assert actual_hashes == golden["files"]

    model = json.loads((output / "discovery-model.json").read_text(encoding="utf-8"))
    actual_counts = {
        "operations": len(model["operations"]),
        "entities": len(model["entities"]),
        "enums": len(model["enums"]),
        "relationships": len(model["relationships"]),
        "validations": len(model["validations"]),
        "evidence": len(model["evidence"]),
        "lineage": len(model["lineage"]),
        "diagnostics": len(model["diagnostics"]),
    }
    assert actual_counts == golden["counts"]
