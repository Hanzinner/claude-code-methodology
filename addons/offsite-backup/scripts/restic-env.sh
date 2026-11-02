#!/usr/bin/env bash
# Sourced by all restic wrapper scripts. Sets repo + credentials + passphrase.
# NOT executable on its own — source it.
#
# S3 creds (chmod 600) — default ~/.claude/secrets/s3-credentials.json:
#   { "accessKey": "...", "secretKey": "...", "bucket": "your-bucket",
#     "endpoint": "https://s3.filebase.io" }       # endpoint optional, Filebase if absent
# Passphrase (encryption key) — default ~/.claude/secrets/backup-passphrase.txt
# — chmod 600, read only by scripts. NEVER printed / logged / echoed.
# Override either path: RESTIC_S3_CREDS=... RESTIC_PASSPHRASE_FILE=...

S3_CREDS="${RESTIC_S3_CREDS:-$HOME/.claude/secrets/s3-credentials.json}"
PASSPHRASE_FILE="${RESTIC_PASSPHRASE_FILE:-$HOME/.claude/secrets/backup-passphrase.txt}"

[[ -f "$S3_CREDS" ]] || { echo "ERROR: $S3_CREDS missing" >&2; exit 1; }
[[ -f "$PASSPHRASE_FILE" ]] || { echo "ERROR: $PASSPHRASE_FILE missing" >&2; exit 1; }

# The path goes in via argv, never spliced into the Python code.
# null / "" count as absent, so the default applies.
_s3() { python3 -c 'import json,sys; v=json.load(open(sys.argv[1])).get(sys.argv[2]); print(v if v not in (None, "") else sys.argv[3])' "$S3_CREDS" "$@"; }
export AWS_ACCESS_KEY_ID=$(_s3 accessKey "")
export AWS_SECRET_ACCESS_KEY=$(_s3 secretKey "")
BUCKET=$(_s3 bucket "")
ENDPOINT=$(_s3 endpoint "https://s3.filebase.io")

export RESTIC_REPOSITORY="s3:${ENDPOINT%/}/$BUCKET"
export AWS_DEFAULT_REGION=us-east-1
export RESTIC_PASSWORD_FILE="$PASSPHRASE_FILE"
