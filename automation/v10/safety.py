from dataclasses import dataclass


@dataclass(frozen=True)
class SafetyConstitution:
    paper_only: bool = True
    broker_order_submission_enabled: bool = False
    real_money_trading_enabled: bool = False
    historical_rewrite_allowed: bool = False
    production_execution_available: bool = False
    long_only: bool = True
    margin_enabled: bool = False
    short_enabled: bool = False

    def assert_safe(self) -> None:
        if not self.paper_only:
            raise RuntimeError("V10 must remain paper-only")
        if any((self.broker_order_submission_enabled, self.real_money_trading_enabled,
                self.historical_rewrite_allowed, self.production_execution_available,
                self.margin_enabled, self.short_enabled)):
            raise RuntimeError("V10 safety constitution violated")


SAFETY = SafetyConstitution()
SAFETY.assert_safe()
