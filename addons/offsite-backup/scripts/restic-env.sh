#!/usr/bin/env bash
# Sourced by all restic wrapper scripts. Sets repo + credentials + passphrase.
# NOT executable on its own — source it.
#
# Filebase creds live in /home/<user>/.claude/secrets/filebase-credentials.json:
#   { "accessKey": "...", "secretKey": "...", "bucket": "your-bucket" }
# Passphrase (encryption key) in /home/<user>/.claude/secrets/backup-passphrase.txt
# — chmod 600, read only by scripts. NEVER printed / logged / echoed.

FILEBASE_CREDS=/home/<user>/.claude/secrets/filebase-credentials.json
PASSPHRASE_FILE=/home/<user>/.claude/secrets/backup-passphrase.txt

[[ -f "$FILEBASE_CREDS" ]] || { echo "ERROR: $FILEBASE_CREDS missing" >&2; exit 1; }
[[ -f "$PASSPHRASE_FILE" ]] || { echo "ERROR: $PASSPHRASE_FILE missing" >&2; exit 1; }

export AWS_ACCESS_KEY_ID=$(python3 -c "import json; print(json.load(open('$FILEBASE_CREDS'))['accessKey'])")
export AWS_SECRET_ACCESS_KEY=$(python3 -c "import json; print(json.load(open('$FILEBASE_CREDS'))['secretKey'])")
BUCKET=$(python3 -c "import json; print(json.load(open('$FILEBASE_CREDS'))['bucket'])")

export RESTIC_REPOSITORY="s3:https://s3.filebase.io/$BUCKET"
export AWS_DEFAULT_REGION=us-east-1
export RESTIC_PASSWORD_FILE="$PASSPHRASE_FILE"
