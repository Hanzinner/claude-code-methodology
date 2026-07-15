# offsite-backup — encrypted incremental VM backup

Your Claude Code setup grows over time — memory files, sessions, custom
scripts, mobile bot config, SSH keys, per-user CLAUDE.md. All of it lives
on one machine. If that machine dies (hardware failure, theft, fire), the
loss isn't just files — it's the accumulated context that made Claude
useful to you specifically.

This addon backs the whole thing up nightly to any S3-compatible object
storage using restic. Encrypted with a passphrase you memorize.

## What you get

- **Nightly cron** pushes an incremental snapshot (~5-20 MB per day after
  the first backup). Full base is 1-3 GB depending on how much sit on disk.
- **AES-256 encryption** with a passphrase you type once during setup
  (stored in a chmod-600 file on disk so cron can read it, plus in your
  head as the ultimate fallback).
- **Deduplication + zstd compression** via restic — same file across many
  commits stored once. Typical compression ratio 1.4-2x.
- **Recovery script for a fresh Claude on a new machine** — it's included
  in the archive itself, so a new machine only needs the passphrase and
  cloud credentials to bootstrap the entire setup.

## Why restic + S3 (and not tar+gpg or rsync)

- `tar+gpg` re-sends the full archive every night. Even a 500 MB archive
  = 15 GB/month upload. Restic sends only changed chunks.
- `rsync` doesn't encrypt at rest. Object storage inherits provider trust.
  Restic's chunk-level AES-256 makes the storage provider blind to
  contents.
- Any S3-compatible provider works — Filebase (5 GB free), Cloudflare R2
  (10 GB free), Wasabi, Backblaze B2, MinIO self-hosted. Just swap the
  endpoint URL.

## Setup

1. Sign up for an S3-compatible storage provider. Get: bucket name,
   Access Key, Secret Key, endpoint URL.

2. Install restic:
   ```bash
   sudo apt-get install restic     # or brew install restic on macOS
   ```

3. Create credentials file (root:root, chmod 600) at
   `~/.claude/secrets/s3-credentials.json`:
   ```json
   {"accessKey": "...", "secretKey": "...",
    "bucket": "your-bucket", "endpoint": "https://s3.filebase.io"}
   ```

4. Create passphrase file at `~/.claude/secrets/backup-passphrase.txt`
   (chmod 600). **Also memorize it** — it's the ultimate decryption key,
   losing both means losing the archive.

5. Copy scripts from this addon to `~/.claude/scripts/backup/`:
   ```bash
   cp scripts/*.sh scripts/*.txt ~/.claude/scripts/backup/
   chmod +x ~/.claude/scripts/backup/*.sh
   ```

6. Edit `restic-env.sh` if your creds path differs from default.

7. Initialize the repo (first time only):
   ```bash
   source ~/.claude/scripts/backup/restic-env.sh
   restic init
   ```

8. Run the first backup manually to verify:
   ```bash
   bash ~/.claude/scripts/backup/backup-restic.sh
   ```

9. Install cron:
   ```bash
   ( crontab -l 2>/dev/null; \
     echo "17 2 * * * /root/.claude/scripts/backup/backup-restic.sh >> /var/log/restic-backup.log 2>&1" \
   ) | crontab -
   ```

## Recovery drill

Run this **monthly**. Otherwise you'll discover the backup is broken
only when you actually need it — which is the worst possible time.

```bash
source ~/.claude/scripts/backup/restic-env.sh
restic restore latest --target /var/tmp/recovery-test    # NOT /tmp — tmpfs too small
# Sanity check: does memory index parse? do jsonl files exist?
head /var/tmp/recovery-test/home/*/claude-projects/.claude/memory/MEMORY.md
find /var/tmp/recovery-test -name '*.jsonl' | wc -l
rm -rf /var/tmp/recovery-test
```

If restore fails or files are missing — fix the exclude patterns and
re-backup before you rely on it.

## What NOT to back up

Look at `restic-exclude.txt` — the default excludes cover the common
regenerable-heavy paths:

- Docs corpora cloned from GitHub (git clone reproduces them)
- Language toolchains (rustup, cargo, node_modules)
- VS Code Remote server install
- Build outputs (cargo target/, cached artifacts via `--exclude-caches`)
- Trash directories

Don't back up files you can re-download in 30 seconds — they double
your restore time and eat your free tier.

## The `.git/objects` decision

If you have a **local-only** git repo (no remote), its history exists
only in `.git/objects/`. Excluding this from backup means restoring the
working tree but losing all commits.

The default exclude does NOT skip `.git/objects/` — the file is included.
If your repo has a remote (GitHub, GitLab), you can safely add
`**/.git/objects` back to `restic-exclude.txt` and rely on the remote for
history restore.

Trade-off: including `.git/objects/` can add 500 MB - 3 GB depending on
repo age. Compressed and deduplicated by restic, but still nontrivial.

## Where the recovery instructions live

`RECOVERY.md` in this addon is a template. Customize it for your setup
(paths, user names, systemd services you run) and copy it to
`~/.claude/scripts/backup/RECOVERY.md`. The backup script copies this
file **into the archive itself** every run — a fresh Claude on a new
machine reads the copy from the restored archive and follows the steps.

That's the trick: the backup carries its own recovery instructions,
which means the only prerequisite knowledge on a new machine is
**passphrase + cloud credentials**. Everything else is in the archive.

## Costs

Filebase 5 GB free covers a typical Claude Code setup (~1-2 GB base +
month of daily deltas). If you outgrow it, paid tiers start at $6-10/mo
for 100+ GB. Cloudflare R2 offers 10 GB free with zero egress fees —
better long-term if you plan restores from anywhere.
