# Provider contracts

`city.toml` declares the portable provider names. The Copilot providers
delegate one ACP session directly to `d2b-gascity-copilot-provider`; the
wrapper owns only the process boundary and fixed profile arguments.

The `copilot-review` provider reads the machine-local readiness selection.
Explicit `copilot-review-sol` and `copilot-review-luna` names remain available
for diagnostics. The `publication-worker` provider is deliberately different:
it is non-ACP, uses `prompt_mode = "none"`, and starts the packaged
`d2b-gascity-publication-worker` one-shot subprocess. It never invokes a model
or receives a model-provided executable path. No provider declaration copies
imported agents or formulas.
