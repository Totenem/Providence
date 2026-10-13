# GNU Make on Windows. Without make, use scripts/release.ps1 directly.
.DEFAULT_GOAL := help
POWERSHELL ?= powershell.exe
VERSION ?=
REPO ?= Totenem/Providence
CONFIRM_BUILD ?= 0
CONFIRM_PUBLISH ?= 0
RELEASE = $(POWERSHELL) -NoProfile -ExecutionPolicy Bypass -File scripts/release.ps1 -Version "$(VERSION)" -Repo "$(REPO)"

.PHONY: help test release-check release-plan tag release-build release release-status
help:
	@$(RELEASE) -Action help

test:
	@$(RELEASE) -Action test

release-check:
	@$(RELEASE) -Action check

release-plan:
	@$(RELEASE) -Action release -DryRun

tag:
	@$(RELEASE) -Action tag

release-build:
	@$(RELEASE) -Action build -ConfirmBuild "$(CONFIRM_BUILD)"

release:
	@$(RELEASE) -Action release -ConfirmBuild "$(CONFIRM_BUILD)" -ConfirmPublish "$(CONFIRM_PUBLISH)"

release-status:
	@$(RELEASE) -Action status
