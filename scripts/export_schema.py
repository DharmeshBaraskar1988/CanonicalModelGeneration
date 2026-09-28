"""Export the checked DiscoveryModel JSON Schema deterministically."""

import json
from pathlib import Path

from canonical_model_generator.discovery_agent.model import DiscoveryModel
from canonical_model_generator.normalization import NormalizedDiscoveryPortfolio


def main() -> None:
    schemas = {
        Path("schemas/discovery-model-v1.schema.json"): DiscoveryModel,
        Path("schemas/normalized-discovery-v1.schema.json"): NormalizedDiscoveryPortfolio,
    }
    for target, contract in schemas.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(contract.model_json_schema(by_alias=True), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
