import json
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from canonical_model_generator.intake import (
    IntakeError,
    build_intake_manifest,
    inspect_repository_zip,
    validate_openapi,
)


def make_zip(files: dict[str, str]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_inventory_finds_dotnet_discovery_inputs() -> None:
    archive = make_zip(
        {
            "QuoteApi.sln": "solution",
            "src/QuoteApi/QuoteApi.csproj": "<Project />",
            "src/QuoteApi/Controllers/QuotesController.cs": "class QuotesController {}",
            "docs/openapi.yaml": "openapi: 3.0.3",
            "src/QuoteApi/obj/GeneratedController.cs": "ignored",
        }
    )

    inventory = inspect_repository_zip(archive)

    assert inventory.ready_for_discovery
    assert inventory.solutions == ("QuoteApi.sln",)
    assert inventory.controllers == ("src/QuoteApi/Controllers/QuotesController.cs",)
    assert inventory.openapi_candidates == ("docs/openapi.yaml",)


def test_inventory_rejects_path_traversal() -> None:
    archive = make_zip({"../secret.txt": "not allowed"})

    with pytest.raises(IntakeError, match="Unsafe archive path"):
        inspect_repository_zip(archive)


def test_invalid_zip_has_useful_error() -> None:
    with pytest.raises(IntakeError, match="not a valid ZIP"):
        inspect_repository_zip(b"not-a-zip")


def test_openapi_summary_supports_json() -> None:
    document = json.dumps(
        {
            "openapi": "3.0.3",
            "paths": {"/quotes": {}},
            "components": {"schemas": {"Quote": {"type": "object"}}},
        }
    ).encode()

    summary = validate_openapi(document, "openapi.json")

    assert summary["openapi_version"] == "3.0.3"
    assert summary["path_count"] == 1
    assert summary["schema_count"] == 1


def test_manifest_is_stable_and_records_next_stage() -> None:
    inventory = inspect_repository_zip(
        make_zip(
            {
                "QuoteApi.csproj": "<Project />",
                "QuotesController.cs": "class QuotesController {}",
            }
        )
    )

    first = build_intake_manifest(
        region=" IN ",
        system=" quote-api ",
        archive_name="repo.zip",
        inventory=inventory,
        openapi=None,
    )
    second = build_intake_manifest(
        region=" IN ",
        system=" quote-api ",
        archive_name="repo.zip",
        inventory=inventory,
        openapi=None,
    )

    assert first == second
    assert first["region"] == "IN"
    assert first["status"] == "ready"
    assert first["nextStage"] == "DiscoveryModel v1 contract (M1)"
