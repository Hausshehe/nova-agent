"""Read-only queries over Nova's supplied internal world-model facts."""

from __future__ import annotations

_MAX_TEXT = 512
_MAX_RECORDS = 32
_KINDS = {"ENTITY", "RELATIONSHIP", "EVIDENCE", "TEMPORAL", "BELIEF"}


def _field(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} cannot be empty.")
    value = value.strip()
    if len(value) > _MAX_TEXT:
        raise ValueError(f"{label} is too long.")
    return value


def query_world_model(
    entities: str,
    relationships: str,
    evidence: str,
    temporal_states: str,
    beliefs: str,
    query: str,
) -> str:
    """Answer a bounded query using only explicitly supplied world-model records.

    Records use:
      entities: entity_id | entity_type | state | confidence
      relationships: source_entity_id | relationship | target_entity_id
      evidence: entity_id | claim | source | confidence
      temporal_states: entity_id | state | observed_at | confidence
      beliefs: entity_id | claim | confidence

    The query is intentionally conservative: it matches explicit entity ids and
    exact/substring terms against supplied records. It never infers missing
    relationships, history, causality, or claims.
    """
    query = _field(query, "Query")
    sources = {
        "ENTITY": entities,
        "RELATIONSHIP": relationships,
        "EVIDENCE": evidence,
        "TEMPORAL": temporal_states,
        "BELIEF": beliefs,
    }

    parsed: dict[str, list[str]] = {}
    total = 0
    for kind, raw in sources.items():
        if not isinstance(raw, str):
            raise ValueError(f"{kind.title()} records must be strings.")
        lines = [line.strip() for line in raw.strip().splitlines() if line.strip()]
        if len(lines) > _MAX_RECORDS:
            raise ValueError(f"{kind.title()} records exceed the bounded limit.")
        parsed[kind] = lines
        total += len(lines)

    terms = [term.strip().lower() for term in query.split() if term.strip()]
    if not terms:
        raise ValueError("Query cannot be empty.")
    needle = query.lower()

    matches: list[tuple[str, str]] = []
    for kind in _KINDS:
        for record in parsed[kind]:
            if needle in record.lower() or all(term in record.lower() for term in terms):
                matches.append((kind, record))

    # Do not broaden a query merely because it mentions a known entity. A known
    # entity does not support arbitrary claims about that entity. Only records
    # whose own fields explicitly match the query can support the answer.

    # Deterministic ordering keeps this a query over supplied facts, not a
    # provider-generated interpretation.
    matches.sort(key=lambda item: (_KINDS_ORDER[item[0]], item[1]))
    lines = [
        "World-model query (read-only):",
        f"Query: {query}",
        f"Supplied record count: {total}",
        f"Match count: {len(matches)}",
    ]
    if matches:
        lines.append("Explicitly supported records:")
        for kind, record in matches:
            lines.append(f"- {kind}: {record}")
        lines.append("Answer status: SUPPORTED_BY_SUPPLIED_RECORDS")
    else:
        lines.extend([
            "Explicitly supported records: none.",
            "Answer status: UNKNOWN_OR_UNSUPPORTED",
            "No supplied record supports the requested fact; no missing fact was inferred.",
        ])
    lines.extend([
        "Boundary: the query used only explicitly supplied world-model records.",
        "No entity state, relationship, evidence, temporal observation, belief, action, or device state was changed.",
    ])
    return "\n".join(lines)


_KINDS_ORDER = {
    "ENTITY": 0,
    "RELATIONSHIP": 1,
    "EVIDENCE": 2,
    "TEMPORAL": 3,
    "BELIEF": 4,
}
