# Troubleshooting

This guide covers the most common setup and runtime issues in OpsClaw deployments. Use it alongside [docs/setup-guide.md](/Users/austin/Desktop/opsclaw/docs/setup-guide.md) and [docs/security-guide.md](/Users/austin/Desktop/opsclaw/docs/security-guide.md).

## Setup Issues

### `node` or `npm` not found

Install Node.js 20 or newer and make sure both `node` and `npm` are in `PATH`.

Check:

```bash
node --version
npm --version
```

### `python3` not found

Install Python 3.11 or newer if possible. Re-run:

```bash
python3 --version
```

### `openclaw` command not found after setup

The global npm bin path is likely missing from `PATH`.

Check:

```bash
npm bin -g
which openclaw
```

Restart the shell or add the npm global bin directory to your shell profile.

### `setup.sh` fails while copying files

Common causes:

- insufficient permissions on `~/.openclaw/`
- interrupted previous install
- missing source directories in a partial clone

Fix by checking ownership and rerunning from a clean local clone.

## Configuration Issues

### `config-wizard.sh` writes the wrong values into `workspace/USER.md`

The wizard performs placeholder replacement against the starter file. If the placeholders were already edited manually, replacement may become incomplete. Restore the original placeholders or update the file manually after running the wizard.

### Webhook token was generated but not stored securely

Move it into your secret store or `~/.openclaw/opsclaw/.env` and remove it from any temporary notes or shell history.

### Skill is enabled but not doing anything

Check:

- the skill is enabled in `workspace/config.json5`
- the required provider credentials are exported
- the provider config file under `skills/<name>/config/` is complete
- the runtime or hook actually invokes the skill

## Integration Issues

### Gmail notifications are not arriving

Check:

- Gmail API and Pub/Sub are enabled in Google Cloud
- the Pub/Sub topic and subscription exist
- Gmail watch registration is active
- the webhook endpoint matches the configured push target
- `OPSCLAW_HOOKS_TOKEN` is set correctly

Use the setup helper in [skills/email-intel/scripts/gmail-setup.sh](/Users/austin/Desktop/opsclaw/skills/email-intel/scripts/gmail-setup.sh) and confirm the watch flow end to end.

### Google Calendar auth expires or fails

Regenerate or refresh the token with:

```bash
python3 skills/calendar-ops/scripts/gcal-auth.py status \
  --token-path skills/calendar-ops/config/google-token.json
```

If needed, rerun the `auth` command with a valid OAuth client JSON file.

### HubSpot or Pipedrive requests fail

Check:

- provider selection in `skills/crm-sync/config/crm-config.json`
- correct base URL
- token environment variable is exported
- token scopes include the required CRM objects

For rate-limit errors, retry after the provider cool-down and inspect logs for repeated failures.

### Linear, Notion, or Asana commands fail authentication

Verify the correct environment variable is exported:

- `LINEAR_API_KEY`
- `NOTION_API_TOKEN`
- `ASANA_ACCESS_TOKEN`

Then run the provider CLI directly to isolate whether the issue is in credentials, provider config, or the broader workflow.

## Runtime Issues

### Heartbeat checks are not running

Check the active config and scheduler setup. If the deployment relies on cron or OpenClaw scheduled jobs, verify those jobs exist and point to the intended workspace.

### Duplicate actions appear after retries

Review idempotency handling and correlation IDs. OpsClaw includes helper modules in [scripts/idempotency.py](/Users/austin/Desktop/opsclaw/scripts/idempotency.py) and retry logic in [scripts/retry.py](/Users/austin/Desktop/opsclaw/scripts/retry.py). Confirm the event key is stable across retries.

### Actions are stuck waiting for approval

That usually means the approval gate is working correctly. Check:

- approval policy in the template or config
- owner notification channel
- `workspace/ops-state.json` for pending approvals

### Dead letters are growing

Inspect `workspace/memory/dead-letters/` and look for repeated causes:

- missing credentials
- bad payload shape
- provider rate limiting
- expired OAuth tokens
- malformed config

Fix the root cause before replaying or deleting dead-letter events.

## System Issues

### Disk space is low

Run:

```bash
./scripts/health-check.sh
```

Then inspect backups, logs, cached dependencies, and large export files. Backups should be rotated regularly.

### The deployment was upgraded and something drifted

Use:

```bash
./scripts/migrate.sh --dry-run
```

Review the proposed file sync before applying the migration.

### Need to move the deployment to a new machine

Use:

```bash
./scripts/backup.sh
```

Restore the archive, then rerun setup and migration checks on the target host.

## When To Escalate

Escalate to manual review when:

- external writes behave differently from the approval policy
- financial actions appear anywhere in an automated path
- logs suggest data corruption in `workspace/ops-state.json`
- API credentials may be exposed
- a restore test fails after a backup
