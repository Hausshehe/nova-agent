"""Bounded entity and state representation for Nova's 185 internal world model phase."""

from __future__ import annotations

from dataclasses import dataclass


_MAX_TEXT = 512
_MAX_ENTITIES = 16


@dataclass(frozen=True)
class EntityState:
    """One bounded entity with an explicit current state."""

    entity_id: str
    entity_type: str
    state: str
    confidence: int = 100

    def __post_init__(self) -> None:
        for value, label in (
            (self.entity_id, "Entity id"),
            (self.entity_type, "Entity type"),
            (self.state, "State"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} cannot be empty.")
            if len(value.strip()) > _MAX_TEXT:
                raise ValueError(f"{label} is too long.")
        if isinstance(self.confidence, bool) or not isinstance(self.confidence, int):
            raise ValueError("Confidence must be an integer from 0 to 100.")
        if not 0 <= self.confidence <= 100:
            raise ValueError("Confidence must be between 0 and 100.")

    def snapshot(self) -> dict[str, object]:
        return {
            "entity_id": self.entity_id.strip(),
            "entity_type": self.entity_type.strip(),
            "state": self.state.strip(),
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class WorldModel:
    """Bounded collection of distinct entity/state representations."""

    entities: tuple[EntityState, ...]

    def __post_init__(self) -> None:
        if not self.entities:
            raise ValueError("World model cannot be empty.")
        if len(self.entities) > _MAX_ENTITIES:
            raise ValueError(f"World model cannot contain more than {_MAX_ENTITIES} entities.")
        ids = [entity.entity_id.strip() for entity in self.entities]
        if len(ids) != len(set(ids)):
            raise ValueError("Entity ids must be unique.")

    def snapshot(self) -> dict[str, object]:
        return {
            "entities": [entity.snapshot() for entity in self.entities],
            "count": len(self.entities),
        }


def represent_entity_states(entities: str) -> str:
    """Represent bounded entities and their current states without changing reality.

    Each entity is supplied as:
        entity_id | entity_type | state | confidence
    """
    if not isinstance(entities, str) or not entities.strip():
        raise ValueError("Entities cannot be empty.")

    entries = [line.strip() for line in entities.strip().splitlines() if line.strip()]
    if not entries:
        raise ValueError("World model cannot be empty.")
    if len(entries) > _MAX_ENTITIES:
        raise ValueError(f"World model cannot contain more than {_MAX_ENTITIES} entities.")

    parsed: list[EntityState] = []
    for entry in entries:
        parts = [part.strip() for part in entry.split("|")]
        if len(parts) != 4:
            raise ValueError(
                "Each entity must use: entity_id | entity_type | state | confidence"
            )
        try:
            confidence = int(parts[3])
        except ValueError as exc:
            raise ValueError("Confidence must be an integer from 0 to 100.") from exc
        parsed.append(EntityState(parts[0], parts[1], parts[2], confidence))

    model = WorldModel(tuple(parsed))
    lines = [
        "Entity and state representation (read-only):",
        f"Entity count: {model.snapshot()['count']}",
    ]
    for entity in model.entities:
        lines.extend([
            f"- Entity id: {entity.entity_id.strip()}",
            f"  Type: {entity.entity_type.strip()}",
            f"  State: {entity.state.strip()}",
            f"  Confidence: {entity.confidence}",
        ])
    lines.extend([
        "Boundary: entities and their supplied current states were represented without inferring relationships or changing state.",
        "No action was executed and no device state was changed.",
    ])
    return "\n".join(lines)
