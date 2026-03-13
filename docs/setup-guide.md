# Setup Guide

This guide turns a fresh machine into a Phase 1 OpsClaw deployment. It assumes the repo has been cloned locally and that onboarding credentials will be added after the infrastructure is in place.

## Supported Platforms
- macOS with Homebrew-installed Node.js and Python 3
- Ubuntu 22.04+ with Node.js 20+ and Python 3.11+

## Prerequisites
- `node` and `npm`
- `python3`
- `git`
- Optional for container deployments: Docker Engine and Docker Compose plugin

## Fast Path
Run:

```bash
./setup.sh
```

The script:
- validates prerequisites,
- creates `~/.openclaw/workspace`,
- copies the workspace, templates, docs, skills, and utility scripts,
- installs OpenClaw globally if missing,
- generates a starter `.env.example`,
- points you to `./config-wizard.sh` for client-specific setup.

## Guided Configuration
Run:

```bash
./config-wizard.sh
```

The wizard captures:
- client name and timezone,
- deployment mode,
- primary owner channel,
- enabled skills,
- briefing schedule,
- webhook token generation,
- template selection.

It writes `workspace/config.json5` and updates `workspace/USER.md` placeholders for the deployment.

## Recommended Production Flow
1. Clone the repo onto the target machine or VPS.
2. Run `./setup.sh`.
3. Run `./config-wizard.sh`.
4. Add channel and API credentials through environment variables or your secret store.
5. Run `openclaw security audit --deep`.
6. Start the gateway with `openclaw gateway start`.
7. Verify the heartbeat schedule and webhook endpoint.

## Docker Compose Deployment
If the target environment prefers Docker:

```bash
docker compose up -d
```

Then exec into the container for onboarding tasks if needed:

```bash
docker compose exec opsclaw bash
```

## Verification Checklist
- `openclaw --help` returns successfully.
- Workspace files exist under `~/.openclaw/workspace`.
- `workspace/ops-state.json` validates as JSON.
- `python3 -m compileall scripts` passes.
- `openclaw security audit --deep` reports no critical issues once credentials are present.

## Troubleshooting
- If `npm i -g openclaw` fails, verify Node.js version and network access.
- If `openclaw` is not in `PATH`, restart the shell or add npm global bin to `PATH`.
- If Docker cannot start the service, confirm the image can access the mounted repository path and `.env`.
- If the wizard cannot write config files, check repository permissions.
