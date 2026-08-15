# Copilot ACP provider contract

`city.toml` declares the portable provider names. Each provider delegates one
ACP session directly to `d2b-gascity-copilot-provider`; the wrapper owns only
the process boundary and fixed profile arguments.

The `copilot-review` provider reads the machine-local readiness selection.
Explicit `copilot-review-sol` and `copilot-review-luna` names remain available
for diagnostics. No provider declaration copies imported agents or formulas.
