"""Small persistent experience memory for verified Android mechanism selection."""

import datetime as dt
import json
import os
import re
import tempfile
from pathlib import Path


_MAX_EXPERIENCES = 128
_MAX_TEXT = 4096
_GENERIC_TERMS = {
    "the", "a", "an", "to", "for", "of", "and", "or", "with", "without",
    "use", "execute", "run", "verify", "test", "device", "android",
    "capability", "request", "mechanism",
}


def _experience_path() -> Path:
    configured = os.environ.get("NOVA_ANDROID_EXPERIENCE_STORE", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / ".nova-agent-android-experiences.json"


def _tokens(text: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9_]+", str(text).lower())
        if token not in _GENERIC_TERMS
    }



def record_verified_experience(request: str, strategy: str, verification: str, domain: str = "general") -> str:
    """Persist one explicitly verified experience for conservative future reuse."""
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Request cannot be empty.")
    if not isinstance(strategy, str) or not strategy.strip():
        raise ValueError("Strategy cannot be empty.")
    if not isinstance(verification, str) or not verification.strip():
        raise ValueError("Verification evidence cannot be empty.")
    if not isinstance(domain, str) or not domain.strip():
        raise ValueError("Experience domain cannot be empty.")
    if not re.search(r"(?:Post-action verification|Verification|Postcondition)\s*:\s*VERIFIED\b", verification, re.IGNORECASE):
        return "Experience not learned: verification is not explicitly VERIFIED."
    event = {
        "request": request.strip()[:_MAX_TEXT],
        "strategy": strategy.strip()[:_MAX_TEXT],
        "domain": domain.strip().lower()[:128],
        "status": "VERIFIED",
        "evidence": verification.strip()[:_MAX_TEXT],
        "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    path = Path(os.environ.get("NOVA_EXPERIENCE_STORE", "").strip()).expanduser() if os.environ.get("NOVA_EXPERIENCE_STORE", "").strip() else Path.home() / ".nova-agent-experiences.json"
    entries = []
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return f"Experience not learned: experience store could not be read: {exc}"
        if not isinstance(loaded, list):
            return "Experience not learned: experience store is not a JSON list."
        entries = loaded
    entries.append(event)
    entries = entries[-_MAX_EXPERIENCES:]
    temp_path = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as temp_file:
            json.dump(entries, temp_file, ensure_ascii=False, indent=2)
            temp_file.write("\n")
            temp_path = Path(temp_file.name)
        os.replace(temp_path, path)
    except (OSError, TypeError, ValueError) as exc:
        if temp_path is not None:
            try: temp_path.unlink(missing_ok=True)
            except OSError: pass
        return f"Experience not learned: store write failed: {exc}"
    return ("Verified experience learned.\n"
            f"Request: {event['request']}\n"
            f"Strategy: {event['strategy']}\n"
            f"Domain: {event['domain']}\n"
            "Status: VERIFIED\n"
            "Future ranking may prefer this strategy only for sufficiently similar requests.")



def record_verified_failure(request: str, strategy: str, failure: str, domain: str = "general") -> str:
    """Persist one explicitly verified failed strategy for conservative future avoidance."""
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Request cannot be empty.")
    if not isinstance(strategy, str) or not strategy.strip():
        raise ValueError("Strategy cannot be empty.")
    if not isinstance(failure, str) or not failure.strip():
        raise ValueError("Failure evidence cannot be empty.")
    if not isinstance(domain, str) or not domain.strip():
        raise ValueError("Experience domain cannot be empty.")
    if not re.search(r"(?:Postcondition|Verification|Post-action verification|Outcome)\s*:\s*FAILED\b", failure, re.IGNORECASE):
        return "Failure not learned: failure is not explicitly VERIFIED."
    event = {
        "request": request.strip()[:_MAX_TEXT],
        "strategy": strategy.strip()[:_MAX_TEXT],
        "domain": domain.strip().lower()[:128],
        "status": "FAILED",
        "evidence": failure.strip()[:_MAX_TEXT],
        "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    configured = os.environ.get("NOVA_EXPERIENCE_STORE", "").strip()
    path = Path(configured).expanduser() if configured else Path.home() / ".nova-agent-experiences.json"
    entries = []
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return f"Failure not learned: experience store could not be read: {exc}"
        if not isinstance(loaded, list):
            return "Failure not learned: experience store is not a JSON list."
        entries = loaded
    entries.append(event)
    entries = entries[-_MAX_EXPERIENCES:]
    temp_path = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as temp_file:
            json.dump(entries, temp_file, ensure_ascii=False, indent=2)
            temp_file.write("\n")
            temp_path = Path(temp_file.name)
        os.replace(temp_path, path)
    except (OSError, TypeError, ValueError) as exc:
        if temp_path is not None:
            try: temp_path.unlink(missing_ok=True)
            except OSError: pass
        return f"Failure not learned: store write failed: {exc}"
    return ("Verified failed experience learned.\n"
            f"Request: {event['request']}\n"
            f"Strategy: {event['strategy']}\n"
            f"Domain: {event['domain']}\n"
            "Status: FAILED\n"
            "Future ranking will conservatively demote this strategy for sufficiently similar requests.")


def rank_with_verified_experience(request: str, candidates: list[str], domain: str = "general") -> list[str]:
    """Conservatively boost verified strategies for sufficiently similar requests."""
    if not isinstance(request, str) or not request.strip() or not candidates:
        return list(candidates)
    configured = os.environ.get("NOVA_EXPERIENCE_STORE", "").strip()
    path = Path(configured).expanduser() if configured else Path.home() / ".nova-agent-experiences.json"
    if not path.exists():
        return list(candidates)
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return list(candidates)
    if not isinstance(entries, list):
        return list(candidates)
    request_tokens = _tokens(request)
    if not request_tokens:
        return list(candidates)
    scores = {candidate: 0.0 for candidate in candidates}
    for entry in entries:
        status = str(entry.get("status", "")).upper()
        if status not in {"VERIFIED", "FAILED"}:
            continue
        if str(entry.get("domain", domain)).strip().lower() != domain.strip().lower():
            continue
        prior_tokens = _tokens(str(entry.get("request", "")))
        strategy = str(entry.get("strategy", "")).strip()
        if strategy not in scores or not prior_tokens:
            continue
        similarity = len(request_tokens & prior_tokens) / len(request_tokens | prior_tokens)
        if similarity < 0.80:
            continue
        if status == "VERIFIED":
            scores[strategy] = max(scores[strategy], similarity)
        else:
            scores[strategy] = min(scores[strategy], -similarity)
    return [candidate for _, candidate in sorted(enumerate(candidates), key=lambda item: (-scores[item[1]], item[0]))]


def select_verified_strategy(request: str, candidates: list[str], domain: str = "general") -> str:
    """Select the highest-ranked candidate using only existing verified experience."""
    ranked = rank_with_verified_experience(request, candidates, domain)
    if not ranked:
        return ("Verified strategy selection: NONE\n"
                "Basis: no strategy candidates were supplied.\n"
                "No strategy execution or device state change was performed.")
    selected = ranked[0]
    changed = bool(candidates) and selected != candidates[0]
    return (f"Verified strategy selection: {selected}\n"
            f"Candidates: {ranked}\n"
            f"Selection basis: {'verified experience ranking changed the preferred candidate' if changed else 'verified experience ranking preserved the existing candidate order'}\n"
            "Safety boundary: selection is a preference only; validation and execution verification remain authoritative.\n"
            "No strategy execution or device state change was performed.")


def record_verified_android_experience(
    request: str,
    mechanism: str,
    verification: str,
) -> str:
    """Persist one verified Android mechanism experience for future ranking."""
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Request cannot be empty.")
    if not isinstance(mechanism, str) or not mechanism.strip():
        raise ValueError("Mechanism cannot be empty.")
    if not isinstance(verification, str) or not verification.strip():
        raise ValueError("Verification evidence cannot be empty.")
    if not re.fullmatch(r"(?:intent|ui|ui-text):.+", mechanism.strip(), re.IGNORECASE):
        raise ValueError("Mechanism must use a bounded Android mechanism form.")
    if not re.search(
        r"(?:Post-action verification|Verification)\s*:\s*VERIFIED\b",
        verification,
        re.IGNORECASE,
    ):
        return "Android experience not learned: verification is not explicitly VERIFIED."

    event = {
        "request": request.strip()[:_MAX_TEXT],
        "mechanism": mechanism.strip()[:_MAX_TEXT],
        "status": "VERIFIED",
        "evidence": verification.strip()[:_MAX_TEXT],
        "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    path = _experience_path()
    entries = []
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return f"Android experience not learned: experience store could not be read: {exc}"
        if not isinstance(loaded, list):
            return "Android experience not learned: experience store is not a JSON list."
        entries = loaded

    entries.append(event)
    entries = entries[-_MAX_EXPERIENCES:]
    temp_path = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as temp_file:
            json.dump(entries, temp_file, ensure_ascii=False, indent=2)
            temp_file.write("\n")
            temp_path = Path(temp_file.name)
        os.replace(temp_path, path)
    except (OSError, TypeError, ValueError) as exc:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
        return f"Android experience not learned: store write failed: {exc}"

    return (
        "Verified Android experience learned.\n"
        f"Request: {event['request']}\n"
        f"Mechanism: {event['mechanism']}\n"
        "Status: VERIFIED\n"
        "Future ranking may prefer this mechanism only for sufficiently similar requests."
    )


def rank_with_verified_android_experience(
    request: str,
    candidates: list[str],
) -> list[str]:
    """Conservatively boost mechanisms proven successful for similar requests."""
    if not isinstance(request, str) or not request.strip() or not candidates:
        return list(candidates)
    path = _experience_path()
    if not path.exists():
        return list(candidates)
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return list(candidates)
    if not isinstance(entries, list):
        return list(candidates)

    request_tokens = _tokens(request)
    if not request_tokens:
        return list(candidates)

    scores = {candidate: 0.0 for candidate in candidates}
    for entry in entries:
        if not isinstance(entry, dict) or str(entry.get("status", "")).upper() != "VERIFIED":
            continue
        prior_request = str(entry.get("request", ""))
        mechanism = str(entry.get("mechanism", "")).strip()
        if mechanism not in scores:
            continue
        prior_tokens = _tokens(prior_request)
        if not prior_tokens:
            continue
        similarity = len(request_tokens & prior_tokens) / len(request_tokens | prior_tokens)
        if similarity >= 0.80:
            scores[mechanism] = max(scores[mechanism], similarity)

    return [
        candidate
        for _, candidate in sorted(
            enumerate(candidates),
            key=lambda item: (-scores[item[1]], item[0]),
        )
    ]
