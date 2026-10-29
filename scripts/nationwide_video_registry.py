"""Research-only multivenue video source registry. No media fetching or forecasts."""
from __future__ import annotations
from dataclasses import dataclass
from urllib.parse import urlsplit
from scripts.venue_profiles import VENUE_PROFILES

EXCLUDED_VENUES = frozenset({"03"})
REQUIRED_STAGES = ("provider_verified", "terms_verified", "permission_verified", "playback_verified")

@dataclass(frozen=True)
class VideoVenue:
    code: str
    name: str
    status: str = "NOT_CONFIGURED"
    provider_name: str | None = None
    approved_host: str | None = None
    # Separate approval gates: never infer rights from a venue's oral permission.
    provider_verified: bool = False
    terms_verified: bool = False
    permission_verified: bool = False
    playback_verified: bool = False

    @property
    def ready(self) -> bool:
        return (self.code not in EXCLUDED_VENUES and self.status == "READY"
                and bool(self.provider_name and self.approved_host)
                and all(getattr(self, flag) for flag in REQUIRED_STAGES))

REGISTRY = {
    code: VideoVenue(code=code, name=profile["name"],
        status="EXCLUDED_BY_PROJECT_POLICY" if code in EXCLUDED_VENUES else "NOT_CONFIGURED")
    for code, profile in VENUE_PROFILES.items()
}

def active_codes() -> list[str]:
    return sorted(code for code in REGISTRY if code not in EXCLUDED_VENUES)

def validate_candidate(venue_code: str, candidate_url: str, venue: VideoVenue | None = None) -> dict:
    """Validate metadata only; neither fetch nor navigate to candidate_url."""
    code = str(venue_code).zfill(2)
    if code not in REGISTRY:
        return {"allowed": False, "reason": "UNKNOWN_VENUE"}
    if code in EXCLUDED_VENUES:
        return {"allowed": False, "reason": "EXCLUDED_VENUE"}
    setting = venue if venue is not None else REGISTRY[code]
    if setting.code != code or not setting.ready:
        return {"allowed": False, "reason": "PROVIDER_APPROVAL_OR_PLAYBACK_UNVERIFIED"}
    try:
        parts = urlsplit(candidate_url)
        host = parts.hostname
        # Exact hostname only: reject userinfo, IP, plaintext, custom port.
        valid = (parts.scheme == "https" and parts.port in (None, 443)
                 and not parts.username and not parts.password
                 and host == setting.approved_host and
                 bool(host) and not host.replace(".", "").isdigit()
                 and all(label and label.isascii() for label in host.split(".")))
    except ValueError:
        valid = False
    return {"allowed": bool(valid), "reason": "APPROVED_SOURCE" if valid else "SOURCE_HOST_REJECTED"}

def coverage() -> dict:
    return {"registered": len(REGISTRY), "eligible": len(active_codes()),
            "excluded": sorted(EXCLUDED_VENUES),
            "approved_sources": sum(v.ready for v in REGISTRY.values()),
            "unverified_sources": sum(not v.ready for k,v in REGISTRY.items() if k not in EXCLUDED_VENUES),
            "video_races_captured": 0, "six_boat_tracks_verified": 0,
            "formal_forecast_modified": False}
