#!/usr/bin/env bash
# Sourced by the backup scripts. Sets the restic repository, the storage credentials and the passphrase file.
# NOT executable on its own - source it. It never prints a secret value.
#
# Keys live in ${CCM_SECRETS_DIR}/restic.env (chmod 600; template: restic.env.template). Override the file: RESTIC_ENV_FILE.
#   backend b2 (default): B2_BUCKET, B2_ACCOUNT_ID, B2_ACCOUNT_KEY [, B2_PREFIX=/restic]   -> repo  b2:<bucket>:<prefix>
#   backend s3:           S3_BUCKET, S3_ENDPOINT, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY  -> repo  s3:<endpoint>/<bucket>
#   or set RESTIC_REPOSITORY yourself (any restic backend) and the matching credentials.
# Passphrase (the encryption key): file ${CCM_SECRETS_DIR}/backup-passphrase.txt (chmod 600) or RESTIC_PASSWORD_FILE.
# Secret files, all in CCM_SECRETS_DIR (0600): restic.env, backup-passphrase.txt.
# Old locations still work as a fallback, with a one-line warning: ~/.claude/secrets/s3-credentials.json (keys accessKey/
# secretKey/bucket/endpoint; RESTIC_S3_CREDS overrides) and ~/.claude/secrets/backup-passphrase.txt. Move them.

source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/backup-common.sh"

_fail() { echo "ERROR: $*" >&2; return 1 2>/dev/null || exit 1; }

ENV_FILE="${RESTIC_ENV_FILE:-$CCM_SECRETS_DIR/restic.env}"
LEGACY_JSON="${RESTIC_S3_CREDS:-$HOME/.claude/secrets/s3-credentials.json}"

if [[ -f "$ENV_FILE" ]]; then
    _mode=$(stat -c %a "$ENV_FILE" 2>/dev/null || stat -f %Lp "$ENV_FILE" 2>/dev/null || echo 600)
    [[ "$_mode" == *00 ]] || echo "WARNING: $ENV_FILE is readable by others - run: chmod 600 $ENV_FILE" >&2
    set -a; source "$ENV_FILE"; set +a
    if [[ -z "${RESTIC_REPOSITORY:-}" ]]; then
        case "${BACKUP_BACKEND:-b2}" in
            b2)
                [[ -n "${B2_BUCKET:-}" && -n "${B2_ACCOUNT_ID:-}" && -n "${B2_ACCOUNT_KEY:-}" ]] || { _fail "$ENV_FILE: B2_BUCKET, B2_ACCOUNT_ID and B2_ACCOUNT_KEY must all be set"; return 1 2>/dev/null || exit 1; }
                export B2_ACCOUNT_ID B2_ACCOUNT_KEY
                export RESTIC_REPOSITORY="b2:${B2_BUCKET}:${B2_PREFIX:-/restic}" ;;
            s3)
                [[ -n "${S3_BUCKET:-}" && -n "${S3_ENDPOINT:-}" && -n "${AWS_ACCESS_KEY_ID:-}" && -n "${AWS_SECRET_ACCESS_KEY:-}" ]] || { _fail "$ENV_FILE: S3_BUCKET, S3_ENDPOINT, AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must all be set"; return 1 2>/dev/null || exit 1; }
                export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
                export RESTIC_REPOSITORY="s3:${S3_ENDPOINT%/}/${S3_BUCKET}" ;;
            *) _fail "$ENV_FILE: BACKUP_BACKEND must be b2 or s3"; return 1 2>/dev/null || exit 1 ;;
        esac
    fi
elif [[ -f "$LEGACY_JSON" ]]; then
    echo "WARNING: using the old credentials file $LEGACY_JSON - move the keys into $ENV_FILE (template: restic.env.template)" >&2
    # the path goes in via argv, never spliced into the Python code; null / "" count as absent
    _s3() { python3 -c 'import json,sys; v=json.load(open(sys.argv[1])).get(sys.argv[2]); print(v if v not in (None, "") else sys.argv[3])' "$LEGACY_JSON" "$@"; }
    export AWS_ACCESS_KEY_ID=$(_s3 accessKey "")
    export AWS_SECRET_ACCESS_KEY=$(_s3 secretKey "")
    export RESTIC_REPOSITORY="s3:$(_s3 endpoint "https://s3.filebase.io" | sed 's#/*$##')/$(_s3 bucket "")"
    BACKUP_BACKEND=s3
else
    _fail "$ENV_FILE missing - copy restic.env.template there and fill it in"; return 1 2>/dev/null || exit 1
fi

export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
RESTIC_PASSWORD_FILE="${RESTIC_PASSWORD_FILE:-${RESTIC_PASSPHRASE_FILE:-$CCM_SECRETS_DIR/backup-passphrase.txt}}"
if [[ ! -f "$RESTIC_PASSWORD_FILE" && -f "$HOME/.claude/secrets/backup-passphrase.txt" ]]; then
    echo "WARNING: using the old passphrase file $HOME/.claude/secrets/backup-passphrase.txt - move it to $CCM_SECRETS_DIR/backup-passphrase.txt (chmod 600)" >&2
    RESTIC_PASSWORD_FILE="$HOME/.claude/secrets/backup-passphrase.txt"
fi
export RESTIC_PASSWORD_FILE
[[ -f "$RESTIC_PASSWORD_FILE" ]] || { _fail "passphrase file $RESTIC_PASSWORD_FILE missing"; return 1 2>/dev/null || exit 1; }
BACKUP_BACKEND="${BACKUP_BACKEND:-b2}"
