"""Bounded evidence-driven belief revision for Nova's 185 internal world model phase."""

from __future__ import annotations

from dataclasses import dataclass


_MAX_TEXT = 512
_MAX_ENTITIES = 16
_MAX_RECORDS = _MAX_ENTITIES * 2
_STANCES = {"SUPPORTS", "CONTRADICTS"}


@dataclass(frozen=True)
class WorldBelief:
    """One explicit belief about a represented entity."""

    entity_id: str
    claim: str
    confidence: int = 100

    def __post_init__(self) -> None:
        for value, label in (
            (self.entity_id, "Entity id"),
            (self.claim, "Belief claim"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} cannot be empty.")
            if len(value.strip()) > _MAX_TEXT:
                raise ValueError(f"{label} is too long.")
        if isinstance(self.confidence, bool) or not isinstance(self.confidence, int):
            raise ValueError("Confidence must be an integer from 0 to 100.")
        if not 0 <= self.confidence <= 100:
            raise ValueError("Confidence must be between 0 and 100.")


@dataclass(frozen=True)
class RevisionEvidence:
    """One explicit piece of evidence and its declared relationship to a belief."""

    entity_id: str
    claim: str
    source: str
    confidence: int
    stance: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.entity_id, "Entity id"),
            (self.claim, "Evidence claim"),
            (self.source, "Evidence source"),
            (self.stance, "Evidence stance"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} cannot be empty.")
            if len(value.strip()) > _MAX_TEXT:
                raise ValueError(f"{label} is too long.")
        if isinstance(self.confidence, bool) or not isinstance(self.confidence, int):
            raise ValueError("Confidence must be an integer from 0 to 100.")
        if not 0 <= self.confidence <= 100:
            raise ValueError("Confidence must be between 0 and 100.")
        if self.stance.strip().upper() not in _STANCES:
            raise ValueError("Evidence stance must be SUPPORTS or CONTRADICTS.")


def revise_world_beliefs(entities: str, beliefs: str, evidence: str) -> str:
    """Revise explicit beliefs only when supplied evidence supports a bounded decision.

    Entity format:
        entity_id | entity_type | state | confidence

    Belief format:
        entity_id | claim | confidence

    Evidence format:
        entity_id | claim | source | confidence | SUPPORTS|CONTRADICTS

    Revision is conservative:
    - matching SUPPORTS evidence raises confidence to the stronger supplied value;
    - higher-confidence CONTRADICTS evidence replaces the belief claim;
    - equal-confidence contradiction requires human input;
    - weaker contradiction does not revise the belief;
    - no evidence is inferred or treated as stronger than supplied.
    """
    for value, label in (
        (entities, "Entities"),
        (beliefs, "Beliefs"),
        (evidence, "Evidence"),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} cannot be empty.")

    entity_entries = [line.strip() for line in entities.strip().splitlines() if line.strip()]
    belief_entries = [line.strip() for line in beliefs.strip().splitlines() if line.strip()]
    evidence_entries = [line.strip() for line in evidence.strip().splitlines() if line.strip()]

    if len(entity_entries) > _MAX_ENTITIES:
        raise ValueError(f"World model cannot contain more than {_MAX_ENTITIES} entities.")
    if len(belief_entries) > _MAX_RECORDS or len(evidence_entries) > _MAX_RECORDS:
        raise ValueError(f"World model cannot contain more than {_MAX_RECORDS} beliefs or evidence records.")

    entity_ids: set[str] = set()
    for entry in entity_entries:
        parts = [part.strip() for part in entry.split("|")]
        if len(parts) != 4:
            raise ValueError("Each entity must use: entity_id | entity_type | state | confidence")
        try:
            confidence = int(parts[3])
        except ValueError as exc:
            raise ValueError("Confidence must be an integer from 0 to 100.") from exc
        if isinstance(confidence, bool) or not 0 <= confidence <= 100:
            raise ValueError("Confidence must be between 0 and 100.")
        if not parts[0] or not parts[1] or not parts[2]:
            raise ValueError("Entity id, type, and state cannot be empty.")
        entity_id = parts[0]
        if entity_id in entity_ids:
            raise ValueError("Entity ids must be unique.")
        entity_ids.add(entity_id)

    parsed_beliefs: list[WorldBelief] = []
    seen_beliefs: set[tuple[str, str]] = set()
    for entry in belief_entries:
        parts = [part.strip() for part in entry.split("|")]
        if len(parts) != 3:
            raise ValueError("Each belief must use: entity_id | claim | confidence")
        try:
            confidence = int(parts[2])
        except ValueError as exc:
            raise ValueError("Confidence must be an integer from 0 to 100.") from exc
        belief = WorldBelief(parts[0], parts[1], confidence)
        key = (belief.entity_id.strip(), belief.claim.strip())
        if key in seen_beliefs:
            raise ValueError("Beliefs must be unique.")
        if belief.entity_id.strip() not in entity_ids:
            raise ValueError(f"Unknown belief entity id: {belief.entity_id.strip()}.")
        seen_beliefs.add(key)
        parsed_beliefs.append(belief)

    parsed_evidence: list[RevisionEvidence] = []
    seen_evidence: set[tuple[str, str, str, int, str]] = set()
    for entry in evidence_entries:
        parts = [part.strip() for part in entry.split("|")]
        if len(parts) != 5:
            raise ValueError(
                "Each evidence record must use: entity_id | claim | source | confidence | SUPPORTS|CONTRADICTS"
            )
        try:
            confidence = int(parts[3])
        except ValueError as exc:
            raise ValueError("Confidence must be an integer from 0 to 100.") from exc
        record = RevisionEvidence(parts[0], parts[1], parts[2], confidence, parts[4].upper())
        key = (
            record.entity_id.strip(),
            record.claim.strip(),
            record.source.strip(),
            record.confidence,
            record.stance.strip().upper(),
        )
        if key in seen_evidence:
            raise ValueError("Evidence records must be unique.")
        if record.entity_id.strip() not in entity_ids:
            raise ValueError(f"Unknown evidence entity id: {record.entity_id.strip()}.")
        seen_evidence.add(key)
        parsed_evidence.append(record)

    lines = [
        "Belief revision (read-only):",
        f"Entity count: {len(entity_ids)}",
        f"Belief count: {len(parsed_beliefs)}",
        f"Evidence count: {len(parsed_evidence)}",
    ]

    for belief in parsed_beliefs:
        related = [
            item for item in parsed_evidence
            if item.entity_id.strip() == belief.entity_id.strip()
        ]
        if not related:
            lines.append(
                f"- {belief.entity_id.strip()} | belief: {belief.claim.strip()} | "
                f"confidence: {belief.confidence} | decision: UNCHANGED | basis: no supplied evidence"
            )
            continue

        exact_support = [
            item for item in related
            if item.stance.strip().upper() == "SUPPORTS"
            and item.claim.strip() == belief.claim.strip()
        ]
        contradictions = [
            item for item in related
            if item.stance.strip().upper() == "CONTRADICTS"
        ]

        if exact_support:
            strongest = max(exact_support, key=lambda item: item.confidence)
            new_confidence = max(belief.confidence, strongest.confidence)
            lines.append(
                f"- {belief.entity_id.strip()} | belief: {belief.claim.strip()} | "
                f"confidence: {new_confidence} | decision: CONFIRMED | "
                f"basis: supporting evidence from {strongest.source.strip()}"
            )
        elif contradictions:
            strongest = max(contradictions, key=lambda item: item.confidence)
            if strongest.confidence > belief.confidence:
                lines.append(
                    f"- {belief.entity_id.strip()} | belief: {belief.claim.strip()} | "
                    f"revised_to: {strongest.claim.strip()} | confidence: {strongest.confidence} | "
                    f"decision: REVISED | basis: higher-confidence contradictory evidence from "
                    f"{strongest.source.strip()}"
                )
            elif strongest.confidence == belief.confidence:
                lines.append(
                    f"- {belief.entity_id.strip()} | belief: {belief.claim.strip()} | "
                    f"decision: HUMAN INPUT REQUIRED | basis: contradictory evidence has equal confidence"
                )
            else:
                lines.append(
                    f"- {belief.entity_id.strip()} | belief: {belief.claim.strip()} | "
                    f"confidence: {belief.confidence} | decision: UNCHANGED | "
                    f"basis: contradictory evidence is weaker than the current belief"
                )
        else:
            lines.append(
                f"- {belief.entity_id.strip()} | belief: {belief.claim.strip()} | "
                f"confidence: {belief.confidence} | decision: UNCHANGED | "
                f"basis: supplied evidence does not explicitly support or contradict this claim"
            )

    lines.extend([
        "Boundary: beliefs were revised only from explicitly supplied evidence and confidence; no missing evidence, claim, source, or state was inferred.",
        "No entity state, belief store, relationship, action, or device state was changed.",
    ])
    return "\n".join(lines)
