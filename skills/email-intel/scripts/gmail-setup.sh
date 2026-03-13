#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  gmail-setup.sh --project-id PROJECT --topic TOPIC --subscription SUB \
    --webhook-url URL --email ADDRESS [--service-account EMAIL] [--region REGION]

Required:
  --project-id       Google Cloud project ID
  --topic            Pub/Sub topic name for Gmail watch events
  --subscription     Pub/Sub push subscription name
  --webhook-url      OpenClaw Gmail webhook URL, e.g. https://host/hooks/gmail
  --email            Gmail account to watch

Optional:
  --service-account  Push auth service account email for Pub/Sub push delivery
  --region           Location hint for future resources (default: global)

This script enables required APIs, creates Pub/Sub resources, grants Gmail publish
permissions, and prints the remaining watch / OpenClaw commands.
EOF
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

PROJECT_ID=""
TOPIC=""
SUBSCRIPTION=""
WEBHOOK_URL=""
EMAIL=""
SERVICE_ACCOUNT=""
REGION="global"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-id)
      PROJECT_ID="$2"
      shift 2
      ;;
    --topic)
      TOPIC="$2"
      shift 2
      ;;
    --subscription)
      SUBSCRIPTION="$2"
      shift 2
      ;;
    --webhook-url)
      WEBHOOK_URL="$2"
      shift 2
      ;;
    --email)
      EMAIL="$2"
      shift 2
      ;;
    --service-account)
      SERVICE_ACCOUNT="$2"
      shift 2
      ;;
    --region)
      REGION="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$PROJECT_ID" || -z "$TOPIC" || -z "$SUBSCRIPTION" || -z "$WEBHOOK_URL" || -z "$EMAIL" ]]; then
  usage
  exit 1
fi

require_cmd gcloud
require_cmd jq

echo "Configuring project $PROJECT_ID"
gcloud config set project "$PROJECT_ID" >/dev/null

echo "Enabling required APIs"
gcloud services enable gmail.googleapis.com pubsub.googleapis.com iam.googleapis.com >/dev/null

echo "Ensuring Pub/Sub topic exists: $TOPIC"
if ! gcloud pubsub topics describe "$TOPIC" >/dev/null 2>&1; then
  gcloud pubsub topics create "$TOPIC" >/dev/null
fi

TOPIC_RESOURCE=$(gcloud pubsub topics describe "$TOPIC" --format='value(name)')
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
GMAIL_PUBLISHER="serviceAccount:gmail-api-push@system.gserviceaccount.com"

echo "Granting Gmail publisher access to topic"
gcloud pubsub topics add-iam-policy-binding "$TOPIC" \
  --member="$GMAIL_PUBLISHER" \
  --role="roles/pubsub.publisher" >/dev/null

echo "Ensuring push subscription exists: $SUBSCRIPTION"
if ! gcloud pubsub subscriptions describe "$SUBSCRIPTION" >/dev/null 2>&1; then
  CREATE_ARGS=(
    "$SUBSCRIPTION"
    "--topic=$TOPIC"
    "--push-endpoint=$WEBHOOK_URL"
    "--ack-deadline=30"
    "--message-retention-duration=1d"
  )

  if [[ -n "$SERVICE_ACCOUNT" ]]; then
    CREATE_ARGS+=("--push-auth-service-account=$SERVICE_ACCOUNT")
  fi

  gcloud pubsub subscriptions create "${CREATE_ARGS[@]}" >/dev/null
else
  echo "Updating push endpoint on existing subscription"
  UPDATE_ARGS=("$SUBSCRIPTION" "--push-endpoint=$WEBHOOK_URL")
  if [[ -n "$SERVICE_ACCOUNT" ]]; then
    UPDATE_ARGS+=("--push-auth-service-account=$SERVICE_ACCOUNT")
  fi
  gcloud pubsub subscriptions update "${UPDATE_ARGS[@]}" >/dev/null
fi

SUBSCRIPTION_RESOURCE=$(gcloud pubsub subscriptions describe "$SUBSCRIPTION" --format='value(name)')

WATCH_PAYLOAD=$(jq -n --arg topic "$TOPIC_RESOURCE" '{labelIds:["INBOX"], topicName:$topic}')

cat <<EOF

Gmail Pub/Sub setup complete.

Project:
  ID: $PROJECT_ID
  Number: $PROJECT_NUMBER
Region hint:
  $REGION
Topic:
  $TOPIC_RESOURCE
Subscription:
  $SUBSCRIPTION_RESOURCE
Webhook:
  $WEBHOOK_URL
Watched mailbox:
  $EMAIL

Next steps
1. Authorize Gmail API access for the mailbox.
2. Register the Gmail watch:

   curl -sS -X POST \\
     -H "Authorization: Bearer \$(gcloud auth print-access-token)" \\
     -H "Content-Type: application/json" \\
     "https://gmail.googleapis.com/gmail/v1/users/$EMAIL/watch" \\
     -d '$WATCH_PAYLOAD'

3. If you prefer a local bridge, run:

   gog gmail watch serve \\
     --project $PROJECT_ID \\
     --subscription $SUBSCRIPTION \\
     --forward-to $WEBHOOK_URL

4. Confirm your OpenClaw config contains the Gmail preset and mapping:

   hooks: {
     enabled: true,
     token: "\${OPSCLAW_HOOKS_TOKEN}",
     path: "/hooks",
     presets: ["gmail"],
     mappings: [{
       match: { path: "gmail" },
       action: "agent",
       wakeMode: "now",
       name: "Gmail",
       sessionKey: "hook:gmail:{{messages[0].id}}",
       messageTemplate: "New email from {{messages[0].from}}\\nSubject: {{messages[0].subject}}\\n\\n{{messages[0].body}}",
       deliver: true,
       channel: "last"
     }]
   }

5. Send a test email and confirm OpsClaw receives it within 60 seconds.

Operational note:
  Gmail watches expire and should be renewed periodically. Schedule a daily or weekly refresh of the watch call above.
EOF
