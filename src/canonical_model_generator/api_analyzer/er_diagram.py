"""Deterministic entity-relationship artifacts for API Analyzer output."""

from __future__ import annotations

import re
from html import escape

from canonical_model_generator.discovery_agent.model import DiscoveryModel, RelationshipKind


def render_er_mermaid(model: DiscoveryModel) -> str:
    """Render contract entities and their discovered structural relationships as Mermaid."""
    aliases = _aliases(model)
    lines = ["erDiagram"]
    for entity in sorted(model.entities, key=lambda item: (item.name.casefold(), item.id)):
        lines.append(f"    {aliases[entity.id]} {{")
        if entity.attributes:
            for attribute in sorted(
                entity.attributes, key=lambda item: (item.name.casefold(), item.id)
            ):
                type_name = _mermaid_token(_display_type(attribute.type))
                field_name = _mermaid_token(attribute.name)
                qualifier = "required" if attribute.required else "optional"
                lines.append(f'        {type_name} {field_name} "{qualifier}"')
        else:
            lines.append('        string empty "no discovered fields"')
        lines.append("    }")

    seen: set[tuple[str, str, str]] = set()
    for relationship in sorted(model.relationships, key=lambda item: item.id):
        if relationship.kind not in {RelationshipKind.CONTAINS, RelationshipKind.INHERITS}:
            continue
        source = aliases.get(relationship.source_id)
        target = aliases.get(relationship.target_id)
        if source is None or target is None:
            continue
        label = "contains" if relationship.kind == RelationshipKind.CONTAINS else "inherits"
        key = (source, target, label)
        if key not in seen:
            lines.append(f'    {source} ||--o{{ {target} : "{label}"')
            seen.add(key)
    return "\n".join(lines) + "\n"


def render_er_svg(model: DiscoveryModel) -> str:
    """Render a portable SVG view from the same deterministic ER inventory."""
    entities = sorted(model.entities, key=lambda item: (item.name.casefold(), item.id))
    width = 1100
    box_width = 500
    gap = 28
    x_positions = (30, 570)
    placements: dict[str, tuple[int, int, int]] = {}
    y_positions = [70, 70]
    boxes: list[str] = []
    for index, entity in enumerate(entities):
        column = index % 2
        x = x_positions[column]
        y = y_positions[column]
        height = max(90, 58 + 24 * max(1, len(entity.attributes)))
        placements[entity.id] = (x, y, height)
        y_positions[column] += height + gap
        boxes.append(
            f'<rect x="{x}" y="{y}" width="{box_width}" height="{height}" rx="8" '
            'fill="#f8fafc" stroke="#334155" stroke-width="2"/>'
        )
        boxes.append(
            f'<rect x="{x}" y="{y}" width="{box_width}" height="38" rx="8" '
            'fill="#dbeafe" stroke="#334155" stroke-width="2"/>'
        )
        boxes.append(f'<text x="{x + 14}" y="{y + 25}" class="title">{escape(entity.name)}</text>')
        if not entity.attributes:
            boxes.append(f'<text x="{x + 14}" y="{y + 62}" class="field">No fields</text>')
        for row, attribute in enumerate(
            sorted(entity.attributes, key=lambda item: (item.name.casefold(), item.id))
        ):
            required = "required" if attribute.required else "optional"
            label = f"{attribute.name}: {_display_type(attribute.type)} ({required})"
            boxes.append(
                f'<text x="{x + 14}" y="{y + 63 + row * 24}" class="field">{escape(label)}</text>'
            )

    relation_lines: list[str] = []
    for relationship in sorted(model.relationships, key=lambda item: item.id):
        if relationship.kind not in {RelationshipKind.CONTAINS, RelationshipKind.INHERITS}:
            continue
        if relationship.source_id not in placements or relationship.target_id not in placements:
            continue
        sx, sy, sh = placements[relationship.source_id]
        tx, ty, th = placements[relationship.target_id]
        x1, y1 = sx + box_width // 2, sy + sh // 2
        x2, y2 = tx + box_width // 2, ty + th // 2
        relation_lines.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            'stroke="#64748b" stroke-width="2" marker-end="url(#arrow)"/>'
        )
    height = max(y_positions, default=160) + 20
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="Entity relationship diagram">'
        '<defs><marker id="arrow" markerWidth="10" markerHeight="7" refX="9" refY="3.5" '
        'orient="auto"><polygon points="0 0, 10 3.5, 0 7" fill="#64748b"/></marker></defs>'
        "<style>.title{font:600 17px sans-serif;fill:#0f172a}"
        ".field{font:14px monospace;fill:#1e293b}"
        ".heading{font:700 24px sans-serif;fill:#0f172a}</style>"
        '<rect width="100%" height="100%" fill="white"/>'
        '<text x="30" y="38" class="heading">API Analyzer entity relationships</text>'
        + "".join(relation_lines)
        + "".join(boxes)
        + "</svg>\n"
    )


def _aliases(model: DiscoveryModel) -> dict[str, str]:
    aliases: dict[str, str] = {}
    used: set[str] = set()
    for entity in sorted(model.entities, key=lambda item: (item.name.casefold(), item.id)):
        base = _mermaid_token(entity.name)
        candidate = base
        suffix = 2
        while candidate in used:
            candidate = f"{base}_{suffix}"
            suffix += 1
        aliases[entity.id] = candidate
        used.add(candidate)
    return aliases


def _mermaid_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_]", "_", value).strip("_") or "Unknown"
    return f"T_{token}" if token[0].isdigit() else token


def _display_type(type_ref) -> str:
    value = type_ref.name or type_ref.kind.value
    if type_ref.collection:
        value += "[]"
    if type_ref.nullable:
        value += "?"
    return value
