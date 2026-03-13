---
name: Bug report
about: Report a defect, regression, or deployment issue in OpsClaw
title: "[Bug] "
labels: bug
assignees: ''
---

## Summary

Describe the problem in one or two sentences.

## Environment

- OpsClaw version or phase:
- Deployment mode: client machine / VPS / Docker Compose
- OS and version:
- OpenClaw version:
- Active skills:

## Steps To Reproduce

1. 
2. 
3. 

## Expected Behavior

Describe what should have happened.

## Actual Behavior

Describe what happened instead.

## Logs And Evidence

Include relevant excerpts from:

- `workspace/ops-state.json`
- `workspace/memory/dead-letters/`
- terminal output
- provider API error responses

Redact secrets before posting.

## Impact

Describe whether this blocks setup, affects one skill, or creates a production risk.

## Verification Attempted

List any checks already run, such as:

- `./scripts/health-check.sh`
- `openclaw security audit --deep`
- provider CLI tests
