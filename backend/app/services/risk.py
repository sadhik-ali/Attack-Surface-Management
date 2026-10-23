"""Composite risk scoring.

The score is deliberately explainable. Every input contributes a named factor,
and the API returns those factors so an analyst can see *why* an asset is rated
9.1 rather than being handed an opaque number.

Model (version 2026.10):

    finding_risk = severity_base
                 x exploitability
                 x exposure
                 x asset_criticality
                 + 0.5 if a verified CVE has a public exploit
                 (clamped to 0..10)

    asset_risk   = weighted mean of its five highest open finding risks
                   weights 0.40 / 0.25 / 0.15 / 0.10 / 0.10

    company_risk = 0.5 x highest asset risk + 0.5 x mean of top ten asset risks

Rationale for the two aggregation steps: taking only the maximum hides breadth
(one bad host in an otherwise clean estate scores the same as fifty), while a
plain mean lets a single critical host vanish among hundreds of low-value ones.
The blend is stable under both conditions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.enums import (
    AssetType,
    CriticalityTier,
    ExposureClass,
    SEVERITY_WEIGHT,
    Severity,
    classify,
)

SEVERITY_BASE: dict[str, float] = {
    Severity.CRITICAL.value: 9.5,
    Severity.HIGH.value: 8.0,
    Severity.MEDIUM.value: 5.5,
    Severity.LOW.value: 2.5,
    Severity.INFORMATIONAL.value: 0.5,
}

EXPOSURE_MULTIPLIER: dict[str, float] = {
    ExposureClass.INTERNET_FACING.value: 1.0,
    ExposureClass.PARTNER_FACING.value: 0.92,
    ExposureClass.INTERNAL.value: 0.72,
    ExposureClass.UNKNOWN.value: 0.85,
}

CRITICALITY_MULTIPLIER: dict[str, float] = {
    CriticalityTier.BUSINESS_CRITICAL.value: 1.0,
    CriticalityTier.HIGH.value: 0.95,
    CriticalityTier.MEDIUM.value: 0.85,
    CriticalityTier.LOW.value: 0.70,
    CriticalityTier.UNKNOWN.value: 0.80,
}

#: Some asset classes are exposed by definition, which lifts an otherwise
#: unremarkable finding on them.
TYPE_MULTIPLIER: dict[str, float] = {
    AssetType.WEB_APPLICATION.value: 1.0,
    AssetType.API_ENDPOINT.value: 1.0,
    AssetType.DOMAIN.value: 0.97,
    AssetType.SUBDOMAIN.value: 0.95,
    AssetType.IP_ADDRESS.value: 0.95,
    AssetType.CLOUD_RESOURCE.value: 0.93,
    AssetType.NETWORK_SERVICE.value: 0.9,
}

TOP_FINDING_WEIGHTS = (0.40, 0.25, 0.15, 0.10, 0.10)


@dataclass(slots=True)
class RiskFactor:
    key: str
    label: str
    value: float
    weight: float
    contribution: float
    description: str = ""

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "weight": round(self.weight, 3),
            "contribution": round(self.contribution, 2),
            "description": self.description,
        }


@dataclass(slots=True)
class FindingRisk:
    score: float
    classification: str
    factors: list[RiskFactor] = field(default_factory=list)
    driver_summary: str = ""

    def factors_dict(self) -> dict:
        return {f.key: {"weight": round(f.weight, 3), "contribution": round(f.contribution, 2), "label": f.label} for f in self.factors}


def assess_finding(
    *,
    severity: str,
    asset_type: str = AssetType.DOMAIN.value,
    exposure: str = ExposureClass.UNKNOWN.value,
    criticality: str = CriticalityTier.UNKNOWN.value,
    confidence: str = "confirmed",
    cvss: float | None = None,
    has_known_exploit: bool = False,
    cve_count: int = 0,
) -> FindingRisk:
    base = SEVERITY_BASE.get(severity, 5.0)

    # Confidence: a potential issue scores below a verified one. The UI labels
    # them separately; the score must not imply the same certainty.
    confidence_mult = 0.75 if confidence == "potential" else 1.0

    # Exploitability: CVSS overrides the coarse severity hint when available.
    if cvss is not None:
        cvss_component = max(0.0, min(1.0, (cvss - 1.0) / 9.0))
        exploit_mult = 0.65 + 0.45 * cvss_component
        exploit_desc = f"CVSS {cvss:.1f} base score"
    else:
        exploit_mult = 0.7 if severity in {Severity.INFORMATIONAL.value, Severity.LOW.value} else 0.9
        exploit_desc = "Derived from severity (no CVSS supplied)"

    exposure_mult = EXPOSURE_MULTIPLIER.get(exposure, 0.85)
    criticality_mult = CRITICALITY_MULTIPLIER.get(criticality, 0.80)
    type_mult = TYPE_MULTIPLIER.get(asset_type, 0.9)

    raw = base * confidence_mult * exploit_mult * exposure_mult * criticality_mult * type_mult
    if has_known_exploit:
        raw += 0.5
    if cve_count >= 3:
        raw += 0.2
    score = round(max(0.0, min(10.0, raw)), 1)

    factors = [
        RiskFactor("severity", "Severity", base, 1.0, base, f"{severity.title()} base weight"),
        RiskFactor("confidence", "Confidence", confidence_mult, 1.0, base * (confidence_mult - 1), "Potential findings are discounted"),
        RiskFactor("exploitability", "Exploitability", exploit_mult, 1.0, base * (exploit_mult - 1), exploit_desc),
        RiskFactor("exposure", "Exposure", exposure_mult, 1.0, base * (exposure_mult - 1), f"{exposure.replace('_', ' ')} exposure"),
        RiskFactor("criticality", "Business criticality", criticality_mult, 1.0, base * (criticality_mult - 1), f"{criticality.replace('_', ' ')} asset"),
        RiskFactor("asset_type", "Asset class", type_mult, 1.0, base * (type_mult - 1), f"{asset_type.replace('_', ' ')} exposure profile"),
    ]
    if has_known_exploit:
        factors.append(RiskFactor("known_exploit", "Known public exploit", 0.5, 1.0, 0.5, "A public exploit exists for this issue"))

    driver = _driver_summary(severity, exposure, criticality, confidence)
    return FindingRisk(score=score, classification=classify(score), factors=factors, driver_summary=driver)


def _driver_summary(severity: str, exposure: str, criticality: str, confidence: str) -> str:
    parts = [f"{severity.title()} severity on a {exposure.replace('_', ' ')} asset"]
    if criticality in {CriticalityTier.BUSINESS_CRITICAL.value, CriticalityTier.HIGH.value}:
        parts.append(f"rated {criticality.replace('_', ' ')} for the business")
    if confidence == "potential":
        parts.append("not yet confirmed (potential)")
    return "; ".join(parts)


def aggregate_asset_risk(finding_scores: list[float]) -> float:
    """Weighted top-five blend; see module docstring."""
    if not finding_scores:
        return 0.0
    top = sorted(finding_scores, reverse=True)[: len(TOP_FINDING_WEIGHTS)]
    total_weight = sum(TOP_FINDING_WEIGHTS[: len(top)])
    blended = sum(score * weight for score, weight in zip(top, TOP_FINDING_WEIGHTS)) / total_weight
    return round(min(10.0, blended), 1)


def aggregate_company_risk(asset_scores: list[float]) -> float:
    if not asset_scores:
        return 0.0
    ordered = sorted(asset_scores, reverse=True)
    peak = ordered[0]
    top_ten_mean = sum(ordered[:10]) / len(ordered[:10])
    return round(min(10.0, 0.5 * peak + 0.5 * top_ten_mean), 1)


def severity_from_cvss(score: float | None) -> str:
    if score is None:
        return Severity.INFORMATIONAL.value
    if score >= 9.0:
        return Severity.CRITICAL.value
    if score >= 7.0:
        return Severity.HIGH.value
    if score >= 4.0:
        return Severity.MEDIUM.value
    if score > 0:
        return Severity.LOW.value
    return Severity.INFORMATIONAL.value


def severity_weight(severity: str) -> int:
    return SEVERITY_WEIGHT.get(severity, 1)
