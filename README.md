# OpsClaw

OpsClaw is a production-oriented OpenClaw deployment package for turning a fresh agent runtime into a business operations assistant. Phase 1 provides the core infrastructure: workspace instructions, state schemas, reliability utilities, client templates, setup tooling, and deployment documentation.

## What Phase 1 Includes
- Workspace operating documents for persona, policy, heartbeat, identity, and tool boundaries
- Versioned state files for ops status, client records, and heartbeat telemetry
- Python utilities for retries, idempotency, dead-letter capture, action classification, and structured logging
- Five client-type JSON5 templates for common deployment profiles
- Cross-platform setup and configuration scripts
- Docker Compose runtime for always-on deployments
- Security and setup documentation aligned to the Phase 1 acceptance criteria

## Architecture

```text
Inbound channels -> OpenClaw Gateway -> Ops Agent -> Skills Layer
                                            |
                                            +-> Email Intel
                                            +-> Calendar Ops
                                            +-> CRM Sync
                                            +-> Task Tracker
                                            +-> Ops Reporting
                                            |
                                            +-> Workspace memory + state
                                            +-> Heartbeat + reconciliation jobs
```

## Repository Layout
- `workspace/` contains the deployment persona, operating rules, and state files.
- `scripts/` contains reliability and policy helpers used by skills and automation.
- `templates/` contains JSON5 profiles for common customer types.
- `docs/` contains operator-facing setup and security guidance.
- `skills/` is reserved for skill implementations introduced in later phases.

## Quick Start
1. Run `./setup.sh`.
2. Run `./config-wizard.sh`.
3. Add secrets through `.env` or your secret manager.
4. Run `openclaw security audit --deep`.
5. Start the runtime with `openclaw gateway start` or `docker compose up -d`.

## Phase 1 Acceptance Alignment
- Setup tooling targets macOS and Ubuntu 22.04+.
- Heartbeat policy, reconciliation, and observability are documented in the workspace and scripts.
- Security hardening guidance is included in [docs/security-guide.md](/Users/austin/Desktop/opsclaw/docs/security-guide.md).
- Guided setup is documented in [docs/setup-guide.md](/Users/austin/Desktop/opsclaw/docs/setup-guide.md).

## Notes
- External messages, calendar writes, and CRM deal changes are approval-gated.
- Financial actions are always blocked.
- Credentials belong in environment variables or a secret manager, never in git.

## License
MIT, 2026 Austin Mander. See [LICENSE](/Users/austin/Desktop/opsclaw/LICENSE).
