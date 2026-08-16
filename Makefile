SHELL := /bin/sh

PYTHON ?= python3
NIX ?= nix
SYSTEM ?= x86_64-linux
RUNNER := $(PYTHON) tests/run.py

.DEFAULT_GOAL := check

.PHONY: check test-python test-policy test-fixtures test-ingress test-generated \
	test-privacy test-workflow check-nix test-nix test-vm update-generated \
	manual-acp-feasibility

check:
	$(RUNNER) check
	$(MAKE) check-nix

test-python: test-policy test-fixtures

test-policy:
	$(RUNNER) policy

test-fixtures:
	$(RUNNER) fixtures

test-ingress:
	$(RUNNER) ingress

test-generated:
	$(RUNNER) generated

test-privacy:
	$(RUNNER) privacy

test-workflow:
	$(RUNNER) workflow

check-nix:
	$(NIX) flake check --no-write-lock-file

test-nix: check-nix

test-vm:
	$(NIX) build .#vmChecks.$(SYSTEM).d2b-gascity --no-link --no-write-lock-file

update-generated:
	$(RUNNER) update-generated
	git diff --check -- tests/generated/repository-inventory.json

manual-acp-feasibility:
	@echo "Manual credential-backed ACP feasibility is documented in docs/feasibility/copilot-acp.md"
	@echo "Use the exact runtime and evidence-repository command from that document."
