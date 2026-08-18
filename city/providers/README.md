# Provider contracts

`city.toml` declares the portable provider names. The Copilot providers
delegate one ACP session directly to `d2b-gascity-copilot-provider`; the
wrapper owns only the process boundary and fixed profile arguments.

The `copilot-review` provider reads the machine-local readiness selection.
The explicit `copilot-planning-grok`, `copilot-review-grok`, and
`copilot-review-luna` names remain available for direct diagnostics. The
d2b publisher is the official pack `gc.publisher` role on
`copilot-code-luna`. No provider declaration copies imported agents or
formulas.
