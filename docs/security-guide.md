# Security Guide

OpsClaw handles customer communications, meeting data, CRM records, and operational metadata. Phase 1 is designed so the platform is safe by default and only becomes more capable when explicit credentials and policies are added.

## Security Principles
- Default-deny external writes.
- Keep secrets out of git and out of logs.
- Run on private infrastructure where possible.
- Prefer environment variables or a secret manager over static config values.
- Preserve evidence for approvals, retries, and failures.

## Hardening Checklist
- Set a gateway token before exposing the OpenClaw gateway.
- Set `OPSCLAW_HOOKS_TOKEN` before enabling webhooks.
- Restrict owner messaging to an allowlist.
- Enable sandboxing for production deployments.
- Use Tailscale, WireGuard, or another private overlay instead of exposing admin ports publicly.
- Back up `workspace/` daily, including memory and state files.
- Run `openclaw security audit --deep` after onboarding credentials.
- Rotate webhook tokens and channel credentials on handover or suspicion of compromise.

## Secret Management
- Store secrets in `.env`, systemd environment files, Docker secrets, or a managed secret store.
- Never commit API keys, OAuth refresh tokens, bot tokens, or webhook secrets.
- Redact secret-like fields from structured logs and human summaries.
- Scope credentials narrowly: read-only for systems that do not need write access.

## Network Exposure
- Prefer running behind Tailscale or another VPN.
- If a reverse proxy is required, terminate TLS and restrict inbound paths to only the webhook endpoint.
- Avoid exposing shell access or admin dashboards publicly.

## Approval Controls
- External email and messages require explicit owner approval.
- Calendar modifications require approval.
- CRM pipeline changes require approval.
- Financial actions are always blocked.

## Logging And Audit
- Use structured JSON logs for automation paths.
- Keep dead-letter events for failed processing in `workspace/memory/dead-letters/`.
- Maintain approval history in `ops-state.json` or the external system of record.
- Review heartbeat consecutive error counters during weekly operations checks.

## Data Protection
- Redact payment-card numbers, passwords, tax IDs, and national IDs from logs and summaries.
- Limit workspace access to operators who need it.
- If storing backups off-machine, encrypt them at rest.
- Treat CRM exports and memory files as confidential client data.

## Incident Response
1. Pause affected integrations.
2. Rotate exposed credentials.
3. Review logs, state files, and dead letters to understand scope.
4. Notify the owner with concrete impact, affected systems, and next steps.
5. Restore service only after credentials, policies, and root cause are addressed.

## Operational Reviews
- Weekly: review error rates, dead letters, and webhook health.
- Monthly: rotate or validate tokens, audit access, and verify backups restore cleanly.
- On every new client deployment: rerun the hardening checklist before go-live.
