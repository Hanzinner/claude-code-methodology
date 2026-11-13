#!/usr/bin/env bash
# Quota supervisor check: the status file is fresh (<10 min) AND the number is real (source=api) AND the real reading
# is not older than MAX_REAL_MIN. Why: a transcript estimate once overstated the quota up to 2x (72% vs a real 35%) -
# "the file exists" cannot see that. Exit 0 = ok (or quiet), 1 = problem, 3 = no/broken file. One line of text on stdout.
#
# Quiet case (added after 3 false alarms, all right after a machine reboot): after downtime the OAuth token is
# expired, and only a live CLI renews it (quota_status.py never refreshes - the refresh token is single-use). While no
# agent works, no quota is spent, so that is not an incident. Agents ARE working (a transcript changed within
# IDLE_MIN minutes) and the token is still expired -> red: the CLI is not renewing the login.
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
F=${F:-$HOME/.claude/quota-status.json}; MAX_REAL_MIN=${MAX_REAL_MIN:-60}
[[ -s $F ]] || { echo "no $F"; exit 3; }
age=$(( ($(date +%s) - $(stat -c %Y "$F")) / 60 ))
read -r src real_age pct < <(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('source','?'), d.get('real_age_min') if d.get('real_age_min') is not None else -1, d.get('pct'))" "$F" 2>/dev/null) || { echo "broken JSON $F"; exit 3; }
echo "file ${age} min old; source ${src}; real reading ${real_age} min old; session ${pct}%"
(( age < 10 )) || { echo "quota file is not updating - the cron job is stopped"; exit 1; }
if [[ $src != api ]]; then
    err=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('real_error') or '')" "$F" 2>/dev/null)
    PROJ=${QUOTA_PROJECTS:-$HOME/.claude/projects}; IDLE_MIN=${IDLE_MIN:-15}
    if [[ $err == *expired* ]] && [[ -z $(find $PROJ -name '*.jsonl' -mmin -"$IDLE_MIN" -print -quit 2>/dev/null) ]]; then
        echo "login expired while nobody was working (no transcript changed for ${IDLE_MIN} min) - no quota is spent; the first CLI start renews it"
        exit 0
    fi
fi
[[ $src == api ]] || { echo "the number is NOT real (transcript estimate, overstates up to 2x) - the usage endpoint does not answer or the login expired"; exit 1; }
(( ${real_age%.*} <= MAX_REAL_MIN )) || { echo "real reading older than ${MAX_REAL_MIN} min"; exit 1; }
