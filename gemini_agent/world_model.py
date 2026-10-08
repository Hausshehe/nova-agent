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

@dataclass(frozen=True)
class EntityRelationship:
    """One explicit relationship between two represented entities."""

    source_id: str
    relationship: str
    target_id: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.source_id, "Source entity id"),
            (self.relationship, "Relationship"),
            (self.target_id, "Target entity id"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} cannot be empty.")
            if len(value.strip()) > _MAX_TEXT:
                raise ValueError(f"{label} is too long.")

    def snapshot(self) -> dict[str, str]:
        return {
            "source_id": self.source_id.strip(),
            "relationship": self.relationship.strip(),
            "target_id": self.target_id.strip(),
        }


def represent_entity_relationships(entities: str, relationships: str) -> str:
    """Represent supplied entity relationships without inferring missing links."""
    if not isinstance(entities, str) or not entities.strip():
        raise ValueError("Entities cannot be empty.")
    if not isinstance(relationships, str) or not relationships.strip():
        raise ValueError("Relationships cannot be empty.")

    entity_entries = [line.strip() for line in entities.strip().splitlines() if line.strip()]
    relationship_entries = [line.strip() for line in relationships.strip().splitlines() if line.strip()]
    if not entity_entries:
        raise ValueError("World model cannot be empty.")
    if not relationship_entries:
        raise ValueError("Relationships cannot be empty.")
    if len(entity_entries) > _MAX_ENTITIES:
        raise ValueError(f"World model cannot contain more than {_MAX_ENTITIES} entities.")
    if len(relationship_entries) > _MAX_ENTITIES * 2:
        raise ValueError(f"World model cannot contain more than {_MAX_ENTITIES * 2} relationships.")

    parsed_entities: list[EntityState] = []
    for entry in entity_entries:
        parts = [part.strip() for part in entry.split("|")]
        if len(parts) != 4:
            raise ValueError(
                "Each entity must use: entity_id | entity_type | state | confidence"
            )
        try:
            confidence = int(parts[3])
        except ValueError as exc:
            raise ValueError("Confidence must be an integer from 0 to 100.") from exc
        parsed_entities.append(EntityState(parts[0], parts[1], parts[2], confidence))

    model = WorldModel(tuple(parsed_entities))
    entity_ids = {entity.entity_id.strip() for entity in model.entities}
    parsed_relationships: list[EntityRelationship] = []
    seen: set[tuple[str, str, str]] = set()
    for entry in relationship_entries:
        parts = [part.strip() for part in entry.split("|")]
        if len(parts) != 3:
            raise ValueError(
                "Each relationship must use: source_entity_id | relationship | target_entity_id"
            )
        relationship = EntityRelationship(parts[0], parts[1], parts[2])
        key = (
            relationship.source_id.strip(),
            relationship.relationship.strip(),
            relationship.target_id.strip(),
        )
        if key in seen:
            raise ValueError("Relationships must be unique.")
        if relationship.source_id.strip() not in entity_ids:
            raise ValueError(f"Unknown source entity id: {relationship.source_id.strip()}.")
        if relationship.target_id.strip() not in entity_ids:
            raise ValueError(f"Unknown target entity id: {relationship.target_id.strip()}.")
        seen.add(key)
        parsed_relationships.append(relationship)

    lines = [
        "Entity relationship representation (read-only):",
        f"Entity count: {len(model.entities)}",
        f"Relationship count: {len(parsed_relationships)}",
    ]
    for relationship in parsed_relationships:
        lines.append(
            f"- {relationship.source_id.strip()} | {relationship.relationship.strip()} | "
            f"{relationship.target_id.strip()}"
        )
    lines.extend([
        "Boundary: relationships were represented only when explicitly supplied; no missing relationship was inferred.",
        "No entity state, relationship, action, or device state was changed.",
    ])
    return "\n".join(lines)


@dataclass(frozen=True)
class EvidenceRecord:
    """One explicit evidence record with bounded provenance."""

    subject_id: str
    claim: str
    source: str
    confidence: int = 100

    def __post_init__(self) -> None:
        for value, label in (
            (self.subject_id, "Subject entity id"),
            (self.claim, "Claim"),
            (self.source, "Evidence source"),
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
            "subject_id": self.subject_id.strip(),
            "claim": self.claim.strip(),
            "source": self.source.strip(),
            "confidence": self.confidence,
        }


def represent_world_evidence(entities: str, evidence: str) -> str:
    """Represent explicit evidence and provenance for known entities only."""
    if not isinstance(entities, str) or not entities.strip():
        raise ValueError("Entities cannot be empty.")
    if not isinstance(evidence, str) or not evidence.strip():
        raise ValueError("Evidence cannot be empty.")

    entity_entries = [line.strip() for line in entities.strip().splitlines() if line.strip()]
    evidence_entries = [line.strip() for line in evidence.strip().splitlines() if line.strip()]
    if not entity_entries:
        raise ValueError("World model cannot be empty.")
    if not evidence_entries:
        raise ValueError("Evidence cannot be empty.")
    if len(entity_entries) > _MAX_ENTITIES:
        raise ValueError(f"World model cannot contain more than {_MAX_ENTITIES} entities.")
    if len(evidence_entries) > _MAX_ENTITIES * 2:
        raise ValueError(f"World model cannot contain more than {_MAX_ENTITIES * 2} evidence records.")

    parsed_entities: list[EntityState] = []
    for entry in entity_entries:
        parts = [part.strip() for part in entry.split("|")]
        if len(parts) != 4:
            raise ValueError(
                "Each entity must use: entity_id | entity_type | state | confidence"
            )
        try:
            confidence = int(parts[3])
        except ValueError as exc:
            raise ValueError("Confidence must be an integer from 0 to 100.") from exc
        parsed_entities.append(EntityState(parts[0], parts[1], parts[2], confidence))

    model = WorldModel(tuple(parsed_entities))
    entity_ids = {entity.entity_id.strip() for entity in model.entities}
    parsed_evidence: list[EvidenceRecord] = []
    seen: set[tuple[str, str, str, int]] = set()
    for entry in evidence_entries:
        parts = [part.strip() for part in entry.split("|")]
        if len(parts) != 4:
            raise ValueError(
                "Each evidence record must use: entity_id | claim | source | confidence"
            )
        try:
            confidence = int(parts[3])
        except ValueError as exc:
            raise ValueError("Confidence must be an integer from 0 to 100.") from exc
        record = EvidenceRecord(parts[0], parts[1], parts[2], confidence)
        key = (
            record.subject_id.strip(),
            record.claim.strip(),
            record.source.strip(),
            record.confidence,
        )
        if key in seen:
            raise ValueError("Evidence records must be unique.")
        if record.subject_id.strip() not in entity_ids:
            raise ValueError(f"Unknown evidence subject entity id: {record.subject_id.strip()}.")
        seen.add(key)
        parsed_evidence.append(record)

    lines = [
        "World evidence and provenance representation (read-only):",
        f"Entity count: {len(model.entities)}",
        f"Evidence count: {len(parsed_evidence)}",
    ]
    for record in parsed_evidence:
        lines.append(
            f"- {record.subject_id.strip()} | claim: {record.claim.strip()} | "
            f"source: {record.source.strip()} | confidence: {record.confidence}"
        )
    lines.extend([
        "Boundary: evidence and provenance were represented only when explicitly supplied; no claim, source, relationship, or state was inferred.",
        "No entity state, evidence, relationship, action, or device state was changed.",
    ])
    return "\n".join(lines)


@dataclass(frozen=True)
class TemporalState:
    """One explicit state observation anchored to a supplied time marker."""

    entity_id: str
    state: str
    observed_at: str
    confidence: int = 100

    def __post_init__(self) -> None:
        for value, label in (
            (self.entity_id, "Entity id"),
            (self.state, "State"),
            (self.observed_at, "Observed time"),
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
            "state": self.state.strip(),
            "observed_at": self.observed_at.strip(),
            "confidence": self.confidence,
        }


def represent_temporal_states(entities: str, observations: str) -> str:
    """Represent explicit entity states at supplied times without inventing history."""
    if not isinstance(entities, str) or not entities.strip():
        raise ValueError("Entities cannot be empty.")
    if not isinstance(observations, str) or not observations.strip():
        raise ValueError("Temporal observations cannot be empty.")

    entity_entries = [line.strip() for line in entities.strip().splitlines() if line.strip()]
    observation_entries = [line.strip() for line in observations.strip().splitlines() if line.strip()]
    if not entity_entries:
        raise ValueError("World model cannot be empty.")
    if not observation_entries:
        raise ValueError("Temporal observations cannot be empty.")
    if len(entity_entries) > _MAX_ENTITIES:
        raise ValueError(f"World model cannot contain more than {_MAX_ENTITIES} entities.")
    if len(observation_entries) > _MAX_ENTITIES * 2:
        raise ValueError(
            f"World model cannot contain more than {_MAX_ENTITIES * 2} temporal observations."
        )

    entity_ids: set[str] = set()
    for entry in entity_entries:
        parts = [part.strip() for part in entry.split("|")]
        if len(parts) != 4:
            raise ValueError(
                "Each entity must use: entity_id | entity_type | state | confidence"
            )
        try:
            confidence = int(parts[3])
        except ValueError as exc:
            raise ValueError("Confidence must be an integer from 0 to 100.") from exc
        entity = EntityState(parts[0], parts[1], parts[2], confidence)
        entity_ids.add(entity.entity_id.strip())
    if len(entity_ids) != len(entity_entries):
        raise ValueError("Entity ids must be unique.")

    parsed: list[TemporalState] = []
    seen: set[tuple[str, str, str, int]] = set()
    for entry in observation_entries:
        parts = [part.strip() for part in entry.split("|")]
        if len(parts) != 4:
            raise ValueError(
                "Each temporal observation must use: entity_id | state | observed_at | confidence"
            )
        try:
            confidence = int(parts[3])
        except ValueError as exc:
            raise ValueError("Confidence must be an integer from 0 to 100.") from exc
        observation = TemporalState(parts[0], parts[1], parts[2], confidence)
        key = (
            observation.entity_id.strip(),
            observation.state.strip(),
            observation.observed_at.strip(),
            observation.confidence,
        )
        if key in seen:
            raise ValueError("Temporal observations must be unique.")
        if observation.entity_id.strip() not in entity_ids:
            raise ValueError(
                f"Unknown temporal observation entity id: {observation.entity_id.strip()}."
            )
        seen.add(key)
        parsed.append(observation)

    lines = [
        "Temporal state representation (read-only):",
        f"Entity count: {len(entity_ids)}",
        f"Observation count: {len(parsed)}",
    ]
    for observation in parsed:
        lines.append(
            f"- {observation.entity_id.strip()} | state: {observation.state.strip()} | "
            f"observed_at: {observation.observed_at.strip()} | confidence: {observation.confidence}"
        )
    lines.extend([
        "Boundary: temporal states were represented only at the explicitly supplied times; no prior, current, or future state was inferred.",
        "No entity state, temporal observation, relationship, action, or device state was changed.",
    ])
    return "\n".join(lines)
