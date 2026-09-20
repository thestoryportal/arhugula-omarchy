"""Pure synthetic voice-candidate metadata; never policy, storage, or activation."""
from dataclasses import dataclass
from enum import Enum


class AuthorityState(Enum):
    SYNTHETIC_AUTHORIZED = "synthetic-authorized"
    DENIED = "denied"
    UNKNOWN = "unknown"


class QualityState(Enum):
    SYNTHETIC_ACCEPTED = "synthetic-accepted"
    REJECTED = "rejected"
    INCOMPLETE = "incomplete"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CandidateVersion:
    """One candidate identity and optional prior version in its same identity line."""

    candidate_id: str
    version: int
    parent: "CandidateVersion | None" = None

    def __post_init__(self):
        # [LAW:parse-dont-validate] Construction is the sole raw-metadata boundary.
        if type(self.candidate_id) is not str or not self.candidate_id:
            raise ValueError("candidate ID must be nonempty text")
        if type(self.version) is not int or self.version < 1:
            raise ValueError("candidate version must be a positive integer")
        if self.parent is not None and type(self.parent) is not CandidateVersion:
            raise ValueError("candidate lineage must use a candidate version")
        if self.parent is not None and (self.parent.candidate_id != self.candidate_id
                                        or self.parent.version >= self.version):
            raise ValueError("candidate lineage contradicts identity or version order")


@dataclass(frozen=True)
class Provenance:
    """Stable fixture provenance reference, deliberately excluding source content."""

    reference_id: str
    digest: str

    def __post_init__(self):
        if (type(self.reference_id) is not str or not self.reference_id
                or type(self.digest) is not str or not self.digest):
            raise ValueError("provenance requires nonempty reference and digest")


@dataclass(frozen=True)
class CandidateBinding:
    """The one immutable binding shared by a request and both evidence inputs."""

    version: CandidateVersion
    provenance: Provenance

    def __post_init__(self):
        # [LAW:types-are-the-program] A binding cannot carry unparsed identity or provenance.
        if type(self.version) is not CandidateVersion or type(self.provenance) is not Provenance:
            raise ValueError("candidate binding requires candidate version and provenance")


@dataclass(frozen=True)
class CandidateRequest:
    binding: CandidateBinding

    def __post_init__(self):
        if type(self.binding) is not CandidateBinding:
            raise ValueError("candidate request requires a binding")


@dataclass(frozen=True)
class AuthorityEvidence:
    binding: CandidateBinding
    state: AuthorityState

    def __post_init__(self):
        if type(self.binding) is not CandidateBinding or type(self.state) is not AuthorityState:
            raise ValueError("authority evidence requires a binding and closed state")


@dataclass(frozen=True)
class QualityEvidence:
    binding: CandidateBinding
    state: QualityState

    def __post_init__(self):
        if type(self.binding) is not CandidateBinding or type(self.state) is not QualityState:
            raise ValueError("quality evidence requires a binding and closed state")


@dataclass(frozen=True)
class VoiceCandidate:
    """A representable synthetic candidate, not a consent or activation grant."""

    binding: CandidateBinding


@dataclass(frozen=True)
class CandidateRejection:
    """Explicit non-candidate result for semantically insufficient supplied evidence."""

    reasons: tuple[str, ...]

    def __post_init__(self):
        if not self.reasons or any(type(reason) is not str or not reason for reason in self.reasons):
            raise ValueError("rejection requires explicit reasons")


def _match(request: CandidateRequest, evidence: AuthorityEvidence | QualityEvidence) -> None:
    # [LAW:single-enforcer] One boundary rejects contradictory evidence bindings.
    if request.binding != evidence.binding:
        raise ValueError("candidate evidence binding contradicts request")


def represent_candidate(
    request: CandidateRequest,
    authority: AuthorityEvidence | None,
    quality: QualityEvidence | None,
) -> VoiceCandidate | CandidateRejection:
    """Represent only qualifying synthetic fixture metadata; perform no external effects."""
    # [LAW:effects-at-boundaries] This pure function accepts every fact it needs as data.
    if type(request) is not CandidateRequest:
        raise ValueError("candidate request is required")
    if authority is not None and type(authority) is not AuthorityEvidence:
        raise ValueError("authority evidence is malformed")
    if quality is not None and type(quality) is not QualityEvidence:
        raise ValueError("quality evidence is malformed")
    if authority is not None:
        _match(request, authority)
    if quality is not None:
        _match(request, quality)
    if authority is None:
        return CandidateRejection(("authority-missing",))
    if authority.state is AuthorityState.UNKNOWN:
        return CandidateRejection(("authority-unknown",))
    if authority.state is AuthorityState.DENIED:
        return CandidateRejection(("authority-denied",))
    if quality is None:
        return CandidateRejection(("quality-missing",))
    if quality.state is QualityState.UNKNOWN:
        return CandidateRejection(("quality-unknown",))
    if quality.state is QualityState.REJECTED:
        return CandidateRejection(("quality-rejected",))
    if quality.state is QualityState.INCOMPLETE:
        return CandidateRejection(("quality-incomplete",))
    # [LAW:types-are-the-program] The closed states leave one eligible combination.
    return VoiceCandidate(request.binding)
