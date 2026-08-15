from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class DividendPreview:
    retained_earnings_cny: Decimal
    requested_cny: Decimal
    warning: dict[str, object] | None
    warning_fingerprint: str

    def to_dict(self) -> dict[str, object]:
        return {
            'retained_earnings_cny': str(self.retained_earnings_cny),
            'requested_cny': str(self.requested_cny),
            'warning': self.warning,
            'warning_fingerprint': self.warning_fingerprint,
        }
