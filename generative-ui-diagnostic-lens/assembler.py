"""Deterministic, rule-based assembler: request + field manifest -> spec | refusal.

No LLM call, no network, no randomness, no clock.  The same (request,
manifest) pair always produces the same result, byte for byte.

The assembler is given the run's *field manifest* only (names + units, see
``manifest.py``) - never the series values.  It therefore cannot diagnose
anything itself: it can only decide *which* of the six catalog primitives
should carry *which* declared fields.  Every decision is a keyword or
field-name match over the manifest, and every refusal is explicit.

Matching rules (all deterministic)
-----------------------------------

1.  The request is scanned for *trigger phrases* that name a catalog
    primitive (longest phrase wins, no overlap).
2.  Each trigger owns the text that follows it, up to the next trigger.
3.  Inside that text the request's significant words (stopwords removed)
    are matched against the manifest's field names: a field is *mentioned*
    when a window of significant words matches the field name's words
    (same count, same words, any order).  A bare "temperature" therefore
    never matches ``zone1_air_temperature``.
4.  Significant words that are **not** part of any mentioned field and are
    not generic words (``peak``, ``reference``, ``hour`` ...) are treated as
    a mention of a field the manifest does not have -> explicit refusal.
5.  A unit named in the request must match the unit of every field the
    request binds; otherwise the request is refused.  The unit vocabulary
    is the catalog's (``catalog.unit_spellings`` / ``catalog.normalize_unit``)
    - there is no second, shorter list of "recognised" units, because a
    catalog unit the assembler failed to recognise would silently bind the
    field's own unit instead of being checked.  A unit the catalog cannot
    check at all (``BTU/h``) is refused (``unknown_unit``).

Refusal codes
-------------

``empty_request``             the request is blank.
``mid_run_state_unavailable`` the request asks for live / mid-run solver state.
``run_mismatch``              the request names a run other than this one.
``different_run_requested``   the request asks for "another run" in words.
``no_known_intent``           no catalog primitive could be recognised.
``unknown_field``             the request names a field the manifest has not got.
``ambiguous_field``           the request names several fields equally well.
``unknown_unit``              the request names a unit the lens cannot check.
``unit_mismatch``             the request asks for a unit the field does not have.
``no_log_field``              the run has no log field for LogTail.
``no_zone_id``                a zone id cannot be derived from the field name.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import catalog
import manifest as manifest_mod
import uispec

# --------------------------------------------------------------------------
# vocabulary
# --------------------------------------------------------------------------

#: request words that carry no field meaning (they never break a match)
STOPWORDS = frozenset(
    """
    a an the of for in with and or show me please give all it its this that
    from by at to is are be was were vs versus than more less over under
    between against using use want need can do does did what which where when
    how why into out up down but not no yes so if then per each every some any
    same other others new old just also very much many few such there here we
    you your our their my
    """.split()
)

#: significant words that may appear without naming a field
GENERIC_WORDS = frozenset(
    """
    peak max maximum min minimum average mean last latest first final whole
    day hour hours minute minutes second seconds time times series data
    number numbers value values total
    sum summary comparison compare table card kpi zone zones log logs lines
    tail inputs input parameters parameter provenance settings configuration
    result results field fields name unit units reference range band case
    cases run runs state solver model models engine fluxion out and or with
    the a an of for in on at to from by is are be this that these those it
    its over under between against versus vs show plot chart graph trend
    highlight give please my our their what which where when how why can
    could would should do does did want need all any some each every more
    less than not no yes so if then per new old same other up down into only
    also just very much many few such there here we you both either neither
    add added adding include including display displaying showing give giving
    put bring bring up see look check inspect examine compare compared
    """.split()
)

#: spellings that are units, not field names (never counted as leftovers).
#: Shared with the catalog: the assembler recognises exactly the units the
#: catalog knows, so the two vocabularies cannot drift apart.
UNIT_WORDS = frozenset(catalog.unit_spellings())

#: request phrases that select a catalog primitive.  Longest match wins.
TRIGGERS: Tuple[Tuple[str, str], ...] = (
    ("time series", "chart"),
    ("zone highlight", "zone"),
    ("highlight zone", "zone"),
    ("which zone", "zone"),
    ("diff table", "table"),
    ("reference range", "table"),
    ("kpi card", "kpi"),
    ("scalar card", "kpi"),
    ("log tail", "log"),
    ("run log", "log"),
    ("chart", "chart"),
    ("plot", "chart"),
    ("graph", "chart"),
    ("trend", "chart"),
    ("compare", "table"),
    ("comparison", "table"),
    ("versus", "table"),
    ("kpi", "kpi"),
    ("highlight", "zone"),
    ("log", "log"),
    ("tail", "log"),
    ("inputs", "param"),
    ("input", "param"),
    ("parameters", "param"),
    ("provenance", "param"),
    ("settings", "param"),
)

#: which catalog primitive each trigger phrase selects
TRIGGER_TO_PRIMITIVE = {
    "chart": "TimeSeriesChart",
    "table": "DiffTable",
    "kpi": "KPICard",
    "zone": "ZoneHighlight",
    "log": "LogTail",
    "param": "ParamInspector",
}

#: phrases that mean "live / mid-run solver state" - never served
MID_RUN_PHRASES: Tuple[str, ...] = (
    "mid-run",
    "mid run",
    "solver state",
    "current solver",
    "live solver",
    "running solver",
    "in-progress",
    "in progress",
    "checkpoint",
    "partial run",
    "while running",
    "intermediate solver",
    "live state",
)

#: phrases that mean "some other run's data"
OTHER_RUN_PHRASES: Tuple[str, ...] = (
    "another run",
    "other run",
    "the other case",
    "a different run",
    "previous run",
)

#: tokens that may name a unit in free text: letters, digits, ``%``, ``°``
#: and the compound separators the catalog uses (``kg/s``, ``W/m2.K``)
UNIT_TOKEN_RE = re.compile(r"[A-Za-z%°][A-Za-z0-9%°]*(?:[./][A-Za-z0-9%°]+)*")

#: words that introduce a unit ("temperature in K", "power in kW")
UNIT_CONTEXT_WORDS = frozenset(
    """
    in using as unit units of expressed measured given
    """.split()
)

#: aggregation keywords (searched in the part of a segment not consumed by a
#: field-name match)
AGGREGATIONS: Tuple[Tuple[str, str], ...] = (
    ("peak", "max"),
    ("maximum", "max"),
    ("highest", "max"),
    ("average", "mean"),
    ("mean", "mean"),
    ("sum", "sum"),
    ("total", "sum"),
    ("last", "last"),
    ("latest", "last"),
    ("final", "last"),
)

#: how a zone id is derived from a field name (deterministic, name only)
ZONE_ID_RE = re.compile(r"^(zone[0-9]+|z[0-9]+|zone_[0-9]+|room[0-9]+)")

RUN_ID_RE = re.compile(r"\brun_[A-Za-z0-9_]+\b")
COUNT_RE = re.compile(r"last\s+(\d+)\s+lines", re.IGNORECASE)


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def _tokens(text: str) -> List[str]:
    """Lower-cased, punctuation-stripped word tokens."""
    cleaned = re.sub(r"[^0-9a-zA-Z%°/_.-]+", " ", text.lower())
    return [tok for tok in cleaned.split() if tok]


def _hard_tokens(text: str) -> List[str]:
    """Tokens with the stopwords removed."""
    return [tok for tok in _tokens(text) if tok not in STOPWORDS]


def _singular(token: str) -> str:
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _name_tokens(name: str) -> List[str]:
    """Token list of a manifest field name (``zone1_air_temperature``)."""
    out: List[str] = []
    for part in re.split(r"[_\-.]+", name):
        if not part:
            continue
        out.append(_singular(part.lower()))
    return out


def _detect_unit(
    text: str, field_tokens: Optional[Set[str]] = None
) -> Tuple[Optional[str], Optional[str]]:
    """The first unit named in ``text``.

    Returns ``(canonical_unit, unknown_unit_token)``.  The unit vocabulary
    is the catalog's: a token names a unit exactly when
    ``catalog.normalize_unit`` can canonicalise it.  There is deliberately no
    second, shorter list of "recognised" units - a unit the catalog knows
    but the assembler did not recognise would silently bind the field's own
    unit instead of being checked (the "in K" bug).

    ``unknown_unit_token`` is set when the request names something that looks
    like a unit (``BTU/h``) but that the catalog cannot check at all; such a
    request is refused rather than served with a guessed unit.
    """
    for match in UNIT_TOKEN_RE.finditer(text):
        token = match.group()
        lowered = token.lower()
        contextual = _in_unit_context(text, match.start())
        canonical = catalog.normalize_unit(token)
        if canonical is None:
            canonical = catalog.normalize_unit(lowered)
        if canonical is None:
            if _looks_like_unit(token) and contextual:
                return None, token
            continue
        if not catalog.is_detectable_unit(canonical):
            continue
        if not contextual:
            # an ordinary English word that also names a unit ("hours") is
            # only a unit mention when the request introduces it as one
            if lowered in GENERIC_WORDS:
                continue
            # a single letter only names a unit when it is written in the
            # canonical capitalisation ("K", "W") - "the run's log" is not a
            # request for seconds
            if len(token) == 1 and token.isalpha() and not token.isupper():
                continue
        # a part of a manifest field name ("zone1_heating_kw") is not a unit
        # mention unless the request introduces it as one ("in kW")
        if field_tokens and lowered in field_tokens and not contextual:
            continue
        return canonical, None
    return None, None


def _looks_symbolic(token: str) -> bool:
    """True if the token carries a unit symbol (``°C``, ``%RH``, ``kg/s``)."""
    return any(not char.isalpha() for char in token)


def _looks_like_unit(token: str) -> bool:
    """True if the token looks like a unit the catalog cannot check."""
    return _looks_symbolic(token) and any(char in token for char in "/%°")


def _in_unit_context(text: str, start: int) -> bool:
    """True if the token at ``start`` is introduced as a unit ("in K").

    The word right before the token must introduce it: "temperature in K",
    "power in kW", "units of kg/s".  A number in between ("the last 3
    hours") means the token is not a unit mention.
    """
    words = re.findall(r"[A-Za-z0-9]+", text[:start])
    if not words:
        return False
    return words[-1].lower() in UNIT_CONTEXT_WORDS


def _field_tokens(entries: Sequence[Dict[str, Any]]) -> Set[str]:
    """The lower-case parts of every manifest field name."""
    tokens: Set[str] = set()
    for entry in entries:
        for part in re.split(r"[_\-.]+", str(entry.get("name", ""))):
            if part:
                tokens.add(part.lower())
    return tokens


def _detect_aggregation(tokens: Sequence[str]) -> str:
    for keyword, how in AGGREGATIONS:
        if keyword in tokens:
            return how
    return "last"


def _title(name: str) -> str:
    return name.replace("_", " ")


def _zone_id_for(name: str) -> Optional[str]:
    match = ZONE_ID_RE.match(name.lower())
    if not match:
        return None
    return match.group(1).replace("_", "")


def match_fields(
    hard: Sequence[str], entries: Sequence[Dict[str, Any]]
) -> Tuple[List[Tuple[int, Dict[str, Any]]], List[bool]]:
    """Greedy left-to-right match of manifest field names in ``hard``.

    Returns the list of ``(start_index, manifest_entry)`` matches and a
    per-token "consumed" mask.  Longest field name wins at a position.
    """
    consumed = [False] * len(hard)
    matches: List[Tuple[int, Dict[str, Any]]] = []
    prepared = []
    for entry in entries:
        tokens = _name_tokens(entry["name"])
        prepared.append((sorted(_singular(t) for t in tokens), len(tokens), entry))
    for start in range(len(hard)):
        if consumed[start]:
            continue
        best = None
        for wanted, size, entry in prepared:
            if size == 0 or start + size > len(hard):
                continue
            if any(consumed[start:start + size]):
                continue
            window = sorted(_singular(t) for t in hard[start:start + size])
            if window == wanted:
                if best is None or size > best[0]:
                    best = (size, entry)
        if best is not None:
            size = best[0]
            for index in range(start, start + size):
                consumed[index] = True
            matches.append((start, best[1]))
    return matches, consumed


def _leftovers(hard: Sequence[str], consumed: Sequence[bool]) -> List[str]:
    """Significant words that no field name accounted for."""
    out = []
    for token, used in zip(hard, consumed):
        if used:
            continue
        if token in GENERIC_WORDS:
            continue
        if token in UNIT_WORDS:
            continue
        out.append(token)
    return out


# --------------------------------------------------------------------------
# request parsing
# --------------------------------------------------------------------------

class Trigger:
    """One recognised primitive intent and the text that follows it."""

    __slots__ = ("primitive", "phrase", "start", "end", "segment")

    def __init__(self, primitive: str, phrase: str, start: int, end: int, segment: str) -> None:
        self.primitive = primitive
        self.phrase = phrase
        self.start = start
        self.end = end
        self.segment = segment


def find_triggers(request: str) -> List[Trigger]:
    """Locate the primitive intents in ``request`` (longest match wins)."""
    text = request.lower()
    candidates: List[Tuple[int, int, str, str]] = []
    for phrase, primitive in TRIGGERS:
        pattern = r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(phrase)
        for match in re.finditer(pattern, text):
            candidates.append((match.start(), match.end(), phrase, primitive))
    candidates.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    chosen: List[Tuple[int, int, str, str]] = []
    for start, end, phrase, primitive in candidates:
        if any(not (end <= s or start >= e) for s, e, _p, _k in chosen):
            continue
        chosen.append((start, end, phrase, primitive))
    chosen.sort(key=lambda item: item[0])

    triggers: List[Trigger] = []
    for index, (start, end, phrase, primitive) in enumerate(chosen):
        stop = chosen[index + 1][0] if index + 1 < len(chosen) else len(text)
        triggers.append(Trigger(primitive, phrase, start, end, text[end:stop]))
    return triggers


def _entries_by_kind(entries: Sequence[Dict[str, Any]], kind: str) -> List[Dict[str, Any]]:
    return [e for e in entries if e.get("kind") == kind]


# --------------------------------------------------------------------------
# the assembler
# --------------------------------------------------------------------------

def assemble(
    request: str,
    manifest: Dict[str, Any],
    trace: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Assemble a UI spec (or an explicit refusal) for ``request``.

    ``manifest`` is a field manifest as produced by
    ``manifest.manifest_from_run`` - names and units only.
    """
    notes: List[str] = trace if trace is not None else []
    request = (request or "").strip()
    if not request:
        return uispec.make_refusal("empty_request", "the request is empty")

    lowered = request.lower()

    # 1. live / mid-run solver state is never served
    for phrase in MID_RUN_PHRASES:
        if phrase in lowered:
            notes.append("refused: mid-run phrase %r" % phrase)
            return uispec.make_refusal(
                "mid_run_state_unavailable",
                "this lens serves finished run outputs only; mid-run solver "
                "state is not available",
                matched_phrase=phrase,
            )

    # 2. another run's data
    run_id = manifest.get("run_id")
    for token in sorted(set(RUN_ID_RE.findall(request))):
        if token != run_id:
            notes.append("refused: run id %r != %r" % (token, run_id))
            return uispec.make_refusal(
                "run_mismatch",
                "the request names run %r; this lens is bound to run %r"
                % (token, run_id),
                requested_run=token,
                bound_run=run_id,
            )
    for phrase in OTHER_RUN_PHRASES:
        if phrase in lowered:
            notes.append("refused: other-run phrase %r" % phrase)
            return uispec.make_refusal(
                "different_run_requested",
                "the request asks for another run's data; this lens is bound "
                "to run %r" % run_id,
                matched_phrase=phrase,
                bound_run=run_id,
            )

    # 3. recognised intent
    triggers = find_triggers(request)
    entries = manifest.get("entries", [])

    # 4. unit named in the request.  The unit vocabulary is the catalog's,
    #    so a unit the catalog knows is always checked against the field.
    requested_unit, unknown_unit = _detect_unit(request, _field_tokens(entries))
    if unknown_unit is not None:
        notes.append("refused: uncheckable unit %r" % unknown_unit)
        return uispec.make_refusal(
            "unknown_unit",
            "the request names a unit the lens cannot check: %r" % unknown_unit,
            requested_unit=unknown_unit,
        )
    if requested_unit is not None:
        canonical = catalog.normalize_unit(requested_unit)
        if canonical is None:
            notes.append("refused: uncheckable unit %r" % requested_unit)
            return uispec.make_refusal(
                "unknown_unit",
                "the request names a unit the lens cannot check: %r"
                % requested_unit,
                requested_unit=requested_unit,
            )
        requested_unit = canonical

    components: List[Dict[str, Any]] = []
    if not triggers:
        notes.append("no recognised primitive intent - falling back to a single field")
        built = _build_generic(request, entries, requested_unit, notes)
        if isinstance(built, dict) and built.get("status") == "refused":
            return built
        components.extend(built)
    else:
        for trigger in triggers:
            built = _build_components(trigger, request, entries, requested_unit, notes)
            if isinstance(built, dict) and built.get("status") == "refused":
                return built
            components.extend(built)

    components = _dedupe(components)
    if not components:
        notes.append("refused: intent found but no component could be bound")
        return uispec.make_refusal(
            "no_bindable_component",
            "the request was recognised but nothing could be bound from the "
            "run's field manifest",
        )

    spec = uispec.make_spec(
        run_id=run_id,
        request=request,
        components=components,
        case_id=manifest.get("case_id"),
    )
    errors = uispec.validate_spec(spec, manifest)
    if errors:
        notes.append("refused: assembled spec failed validation: %s" % errors)
        return uispec.make_refusal(
            "internal_validation_failure",
            "the assembled spec did not validate against the field manifest",
            errors=errors,
        )
    notes.append("assembled %d component(s)" % len(components))
    return spec


def _dedupe(components: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop components that are identical in primitive and bindings."""
    seen = set()
    out = []
    for component in components:
        key = (
            component.get("primitive"),
            tuple(sorted((component.get("bindings") or {}).items())),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(component)
    return out


def _build_components(
    trigger: Trigger,
    request: str,
    entries: Sequence[Dict[str, Any]],
    requested_unit: Optional[str],
    notes: List[str],
) -> Any:
    """Build the components for one trigger (or return a refusal)."""
    if trigger.primitive == "chart":
        return _build_chart(trigger, entries, requested_unit, notes)
    if trigger.primitive == "table":
        return _build_table(trigger, request, entries, requested_unit, notes)
    if trigger.primitive == "kpi":
        return _build_kpi(trigger, entries, requested_unit, notes)
    if trigger.primitive == "zone":
        return _build_zone(trigger, entries, requested_unit, notes)
    if trigger.primitive == "log":
        return _build_log(trigger, request, entries, notes)
    if trigger.primitive == "param":
        return _build_param(trigger, entries, requested_unit, notes)
    return []


def _unknown_field(notes: List[str], segment: str, leftovers: Sequence[str]) -> Dict[str, Any]:
    notes.append("refused: unknown field mention %s" % (list(leftovers) or segment.strip()))
    return uispec.make_refusal(
        "unknown_field",
        "the request names a field that this run's field manifest does not "
        "have: %s" % (", ".join(leftovers) if leftovers else segment.strip()),
        unmatched=list(leftovers),
        segment=segment.strip(),
    )


def _unit_mismatch(
    entry: Dict[str, Any], requested_unit: Optional[str], notes: List[str]
) -> Optional[Dict[str, Any]]:
    if requested_unit is None:
        return None
    field_unit = catalog.normalize_unit(entry.get("unit"))
    if field_unit is None:
        return None
    if field_unit != requested_unit:
        notes.append(
            "refused: unit mismatch: field %r is %r, request asked for %r"
            % (entry["name"], field_unit, requested_unit)
        )
        return uispec.make_refusal(
            "unit_mismatch",
            "field %r is measured in %s; the request asked for %s"
            % (entry["name"], field_unit, requested_unit),
            field=entry["name"],
            field_unit=field_unit,
            requested_unit=requested_unit,
        )
    return None


def _free_tokens(segment: str, entries: Sequence[Dict[str, Any]], matches) -> List[str]:
    """Significant tokens of a segment that no field name consumed."""
    hard = _hard_tokens(segment)
    consumed = [False] * len(hard)
    for _start, entry in matches:
        size = len(_name_tokens(entry["name"]))
        for index in range(_start, min(_start + size, len(consumed))):
            consumed[index] = True
    return _leftovers(hard, consumed)


def _build_chart(
    trigger: Trigger,
    entries: Sequence[Dict[str, Any]],
    requested_unit: Optional[str],
    notes: List[str],
) -> Any:
    hard = _hard_tokens(trigger.segment)
    matches, consumed = match_fields(hard, entries)
    candidates = [entry for _start, entry in matches if entry.get("kind") != "log"]
    if not candidates:
        return _unknown_field(notes, trigger.segment, _leftovers(hard, consumed))
    leftovers = _leftovers(hard, consumed)
    if leftovers:
        return _unknown_field(notes, trigger.segment, leftovers)
    components = []
    for entry in candidates:
        mismatch = _unit_mismatch(entry, requested_unit, notes)
        if mismatch is not None:
            return mismatch
        unit = catalog.normalize_unit(entry.get("unit"))
        components.append(
            {
                "primitive": "TimeSeriesChart",
                "title": _title(entry["name"]),
                "bindings": {"series": entry["name"], "unit": unit},
                "props": {"title": _title(entry["name"]), "x_axis_label": "sample"},
            }
        )
    return components


def _build_table(
    trigger: Trigger,
    request: str,
    entries: Sequence[Dict[str, Any]],
    requested_unit: Optional[str],
    notes: List[str],
) -> Any:
    hard = _hard_tokens(trigger.segment)
    matches, consumed = match_fields(hard, entries)
    candidates = [entry for _start, entry in matches]
    if len(candidates) < 2:
        # the comparison partner may be named elsewhere in the request
        whole_hard = _hard_tokens(request)
        whole_matches, _whole_consumed = match_fields(whole_hard, entries)
        candidates = [entry for _start, entry in whole_matches]
    # the same field may be named twice in the request; count it once
    unique: List[Dict[str, Any]] = []
    seen_names = set()
    for entry in candidates:
        if entry["name"] in seen_names:
            continue
        seen_names.add(entry["name"])
        unique.append(entry)
    candidates = unique
    if not candidates:
        return _unknown_field(notes, trigger.segment, _leftovers(hard, consumed))
    leftovers = _leftovers(hard, consumed)
    if leftovers:
        return _unknown_field(notes, trigger.segment, leftovers)

    series = candidates[0]
    mismatch = _unit_mismatch(series, requested_unit, notes)
    if mismatch is not None:
        return mismatch
    unit = catalog.normalize_unit(series.get("unit"))

    # a same-unit comparison partner becomes the reference series
    reference = None
    for entry in candidates[1:]:
        if catalog.normalize_unit(entry.get("unit")) == unit:
            reference = entry
            break

    bindings: Dict[str, Any] = {"series": series["name"], "unit": unit}
    band = series.get("reference_range")
    if isinstance(band, dict) and band.get("min") is not None and band.get("max") is not None:
        bindings["reference_min"] = float(band["min"])
        bindings["reference_max"] = float(band["max"])
    if reference is not None:
        bindings["reference_series"] = reference["name"]

    consumed_tokens = set()
    for entry in candidates:
        for token in _name_tokens(entry["name"]):
            consumed_tokens.add(token)
    free = [t for t in hard if t not in consumed_tokens]
    aggregation = _detect_aggregation(free)

    return [
        {
            "primitive": "DiffTable",
            "title": _title(series["name"]),
            "bindings": bindings,
            "props": {"title": _title(series["name"]), "aggregation": aggregation},
        }
    ]


def _build_kpi(
    trigger: Trigger,
    entries: Sequence[Dict[str, Any]],
    requested_unit: Optional[str],
    notes: List[str],
) -> Any:
    hard = _hard_tokens(trigger.segment)
    matches, consumed = match_fields(hard, entries)
    candidates = [entry for _start, entry in matches if entry.get("kind") != "log"]
    if not candidates:
        return _unknown_field(notes, trigger.segment, _leftovers(hard, consumed))
    leftovers = _leftovers(hard, consumed)
    if leftovers:
        return _unknown_field(notes, trigger.segment, leftovers)
    scalars = [c for c in candidates if c.get("kind") == "scalar"]
    chosen = scalars[0] if scalars else candidates[0]
    mismatch = _unit_mismatch(chosen, requested_unit, notes)
    if mismatch is not None:
        return mismatch
    unit = catalog.normalize_unit(chosen.get("unit"))
    consumed_tokens = set()
    for entry in candidates:
        for token in _name_tokens(entry["name"]):
            consumed_tokens.add(token)
    free = [t for t in hard if t not in consumed_tokens]
    aggregation = _detect_aggregation(free)
    if chosen.get("kind") == "scalar":
        aggregation = "last"
    return [
        {
            "primitive": "KPICard",
            "title": _title(chosen["name"]),
            "bindings": {"field": chosen["name"], "unit": unit},
            "props": {"label": _title(chosen["name"]), "aggregation": aggregation},
        }
    ]


def _build_zone(
    trigger: Trigger,
    entries: Sequence[Dict[str, Any]],
    requested_unit: Optional[str],
    notes: List[str],
) -> Any:
    hard = _hard_tokens(trigger.segment)
    matches, consumed = match_fields(hard, entries)
    candidates = [entry for _start, entry in matches if entry.get("kind") != "log"]
    if not candidates:
        return _unknown_field(notes, trigger.segment, _leftovers(hard, consumed))
    leftovers = _leftovers(hard, consumed)
    if leftovers:
        return _unknown_field(notes, trigger.segment, leftovers)
    if len(candidates) > 1:
        units = {catalog.normalize_unit(c.get("unit")) for c in candidates}
        if len(units) == 1 and requested_unit is not None:
            same = [c for c in candidates if catalog.normalize_unit(c.get("unit")) == requested_unit]
            if len(same) == 1:
                candidates = same
        if len(candidates) > 1:
            notes.append(
                "refused: ambiguous field mention (%s)"
                % ", ".join(c["name"] for c in candidates)
            )
            return uispec.make_refusal(
                "ambiguous_field",
                "the request names several fields equally well: %s"
                % ", ".join(c["name"] for c in candidates),
                candidates=[c["name"] for c in candidates],
            )
    chosen = candidates[0]
    mismatch = _unit_mismatch(chosen, requested_unit, notes)
    if mismatch is not None:
        return mismatch
    zone_id = _zone_id_for(chosen["name"])
    if zone_id is None:
        notes.append("refused: no zone id derivable from %r" % chosen["name"])
        return uispec.make_refusal(
            "no_zone_id",
            "a zone id cannot be derived from field %r" % chosen["name"],
            field=chosen["name"],
        )
    unit = catalog.normalize_unit(chosen.get("unit"))
    heading = "%s - %s" % (zone_id, _title(chosen["name"]))
    return [
        {
            "primitive": "ZoneHighlight",
            "title": heading,
            "bindings": {
                "zone_id": zone_id,
                "series": chosen["name"],
                "unit": unit,
            },
            "props": {"title": heading},
        }
    ]


def _build_log(
    trigger: Trigger,
    request: str,
    entries: Sequence[Dict[str, Any]],
    notes: List[str],
) -> Any:
    logs = _entries_by_kind(entries, "log")
    if not logs:
        notes.append("refused: the run has no log field")
        return uispec.make_refusal(
            "no_log_field",
            "this run's field manifest has no log field to tail",
        )
    log_entry = sorted(logs, key=lambda e: e["name"])[0]
    match = COUNT_RE.search(request)
    count = int(match.group(1)) if match else 20
    heading = "run log (last %d lines)" % count
    return [
        {
            "primitive": "LogTail",
            "title": heading,
            "bindings": {"log_field": log_entry["name"], "count": count},
            "props": {"title": heading},
        }
    ]


def _build_param(
    trigger: Trigger,
    entries: Sequence[Dict[str, Any]],
    requested_unit: Optional[str],
    notes: List[str],
) -> Any:
    hard = _hard_tokens(trigger.segment)
    matches, consumed = match_fields(hard, entries)
    candidates = [entry for _start, entry in matches if entry.get("kind") != "log"]
    bindings: Dict[str, Any] = {}
    if candidates:
        chosen = candidates[0]
        mismatch = _unit_mismatch(chosen, requested_unit, notes)
        if mismatch is not None:
            return mismatch
        bindings["field"] = chosen["name"]
    section = "provenance" if "provenance" in trigger.segment.lower() else "inputs"
    return [
        {
            "primitive": "ParamInspector",
            "title": "run %s" % section,
            "bindings": bindings,
            "props": {"title": "run %s" % section, "section": section},
        }
    ]


def _build_generic(
    request: str,
    entries: Sequence[Dict[str, Any]],
    requested_unit: Optional[str],
    notes: List[str],
) -> Any:
    """Fallback for a request with no recognised primitive phrase.

    The request must name exactly one manifest field; the primitive is
    chosen from the field's kind (series -> chart, scalar -> card, log ->
    log tail).
    """
    hard = _hard_tokens(request)
    matches, consumed = match_fields(hard, entries)
    candidates = [entry for _start, entry in matches]
    if not candidates:
        leftovers = _leftovers(hard, consumed)
        if not leftovers:
            notes.append("refused: nothing field-like in the request")
            return uispec.make_refusal(
                "no_known_intent",
                "no catalog primitive could be recognised in the request",
            )
        return _unknown_field(notes, request, leftovers)
    leftovers = _leftovers(hard, consumed)
    if leftovers:
        return _unknown_field(notes, request, leftovers)
    if len(candidates) > 1:
        notes.append(
            "refused: ambiguous field mention (%s)"
            % ", ".join(c["name"] for c in candidates)
        )
        return uispec.make_refusal(
            "ambiguous_field",
            "the request names several fields equally well: %s"
            % ", ".join(c["name"] for c in candidates),
            candidates=[c["name"] for c in candidates],
        )
    entry = candidates[0]
    mismatch = _unit_mismatch(entry, requested_unit, notes)
    if mismatch is not None:
        return mismatch
    unit = catalog.normalize_unit(entry.get("unit"))
    kind = entry.get("kind")
    if kind == "log":
        return [
            {
                "primitive": "LogTail",
                "title": "run log (last 20 lines)",
                "bindings": {"log_field": entry["name"], "count": 20},
                "props": {"title": "run log (last 20 lines)"},
            }
        ]
    if kind == "scalar":
        return [
            {
                "primitive": "KPICard",
                "title": _title(entry["name"]),
                "bindings": {"field": entry["name"], "unit": unit},
                "props": {"label": _title(entry["name"]), "aggregation": "last"},
            }
        ]
    return [
        {
            "primitive": "TimeSeriesChart",
            "title": _title(entry["name"]),
            "bindings": {"series": entry["name"], "unit": unit},
            "props": {"title": _title(entry["name"]), "x_axis_label": "sample"},
        }
    ]


def assemble_for_run(request: str, run: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience: build the manifest of ``run`` and assemble against it."""
    return assemble(request, manifest_mod.manifest_from_run(run))
