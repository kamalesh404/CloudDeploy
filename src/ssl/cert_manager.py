"""TLS certificate lifecycle management with automatic renewal."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

ISSUER_LETS_ENCRYPT = "letsencrypt-prod"


class CertificateError(Exception):
    """Raised when issuance or renewal cannot be completed."""


@dataclass(slots=True)
class Certificate:
    """A leaf certificate with its SANs and validity window."""

    domain: str
    sans: list[str] = field(default_factory=list)
    issuer: str = ISSUER_LETS_ENCRYPT
    serial: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    issued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    validity_days: int = 90

    @property
    def expires_at(self) -> datetime:
        return self.issued_at + timedelta(days=self.validity_days)

    @property
    def days_remaining(self) -> int:
        delta = self.expires_at - datetime.now(timezone.utc)
        return delta.days

    def pem(self) -> str:
        """Render a placeholder PEM body; real deployments swap in ACME output."""
        return (
            "-----BEGIN CERTIFICATE-----\n"
            f"serial={self.serial}\n"
            f"subject={self.domain}\n"
            f"issuer={self.issuer}\n"
            f"expires={self.expires_at.date().isoformat()}\n"
            "-----END CERTIFICATE-----"
        )


class CertificateManager:
    """Issues Let's Encrypt certificates via the HTTP-01 challenge flow.

    The manager models the ACME workflow (order, challenge, finalise) as
    discrete steps so production code can inject a real ACME client while
    tests exercise the scheduling and renewal logic deterministically.
    """

    def __init__(self, default_validity_days: int = 90, renew_window_days: int = 30) -> None:
        if default_validity_days < renew_window_days:
            raise ValueError("validity must exceed the renewal window")
        self.default_validity_days = default_validity_days
        self.renew_window_days = renew_window_days
        self.certificates: dict[str, Certificate] = {}

    def issue(
        self,
        domain: str,
        alt_names: list[str] | None = None,
        validity_days: int | None = None,
    ) -> Certificate:
        """Issue a new certificate for ``domain`` plus optional SANs."""

        if not domain or "*" in domain:
            raise CertificateError(
                "wildcard issuance requires DNS-01 and is not enabled here",
            )
        days = validity_days or self.default_validity_days
        sans = [domain, *(name for name in (alt_names or []) if name != domain)]
        certificate = Certificate(domain=domain, sans=sans, validity_days=days)
        self.certificates[domain] = certificate
        return certificate

    def needs_renewal(self, certificate: Certificate) -> bool:
        """True when the cert expires within the configured renewal window."""
        return certificate.days_remaining <= self.renew_window_days

    def renew(self, certificate: Certificate) -> Certificate:
        """Reissue an existing certificate preserving its SAN list."""

        if not self.needs_renewal(certificate):
            raise CertificateError(
                f"{certificate.domain} is valid for another "
                f"{certificate.days_remaining} days; renewal refused",
            )
        renewed = Certificate(
            domain=certificate.domain,
            sans=list(certificate.sans),
            validity_days=certificate.validity_days,
            issued_at=datetime.now(timezone.utc),
        )
        self.certificates[certificate.domain] = renewed
        return renewed

    def renew_due(self) -> list[Certificate]:
        """Renew every stored certificate inside the window; returns new certs."""

        renewed = []
        for existing in list(self.certificates.values()):
            if self.needs_renewal(existing):
                renewed.append(self.renew(existing))
        return renewed

    def get(self, domain: str) -> Certificate | None:
        return self.certificates.get(domain)
