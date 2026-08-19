SHELL := /bin/sh

PYTHON ?= python3

.DEFAULT_GOAL := check

.PHONY: check

check:
	$(PYTHON) tests/test_city.py
