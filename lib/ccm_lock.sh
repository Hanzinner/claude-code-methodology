# Shared lock for bash scripts (sourced, never run): flock where it exists, a mkdir lock where it does not
# (a stock macOS, Git Bash on Windows).
#
#   ccm_lock <fd> <lock file> <wait seconds, 0 = one try> <stale minutes>   -> 0 = got it, 1 = did not
#
# With flock: <lock file> is opened on <fd> and held until the script exits - the same as `exec 9>>f; flock -w N 9`.
# Without flock: the folder "<lock file>.d" is the lock. It is removed when the script exits: ccm_unlock is added to
# the EXIT trap (an EXIT trap set before stays; one set AFTER replaces it, so such a trap calls ccm_unlock itself).
# A lock folder older than <stale minutes> belongs to a process that died and is taken over: give the longest time
# a holder can really need.
CCM_LOCK_DIRS=()
ccm_unlock() {
    local d
    for d in ${CCM_LOCK_DIRS[@]+"${CCM_LOCK_DIRS[@]}"}; do rmdir "$d" 2>/dev/null; done
    CCM_LOCK_DIRS=()
}
ccm_lock() {
    local fd="$1" file="$2" wait="$3" stale="$4" d="$2.d" n=0
    if command -v flock >/dev/null 2>&1; then
        eval "exec $fd>>\"\$file\"" || return 1
        if [[ "$wait" == 0 ]]; then flock -n "$fd"; else flock -w "$wait" "$fd"; fi
        return
    fi
    until mkdir "$d" 2>/dev/null; do
        if [[ -n "$(find "$d" -maxdepth 0 -mmin "+$stale" 2>/dev/null)" ]] && rmdir "$d" 2>/dev/null; then continue; fi
        (( n++ >= wait * 10 )) && return 1
        sleep 0.1
    done
    CCM_LOCK_DIRS+=("$d")
    local t; t=$(trap -p EXIT)
    case "$t" in
        *ccm_unlock*) ;;
        '') trap ccm_unlock EXIT ;;
        *) eval "set -- $t"; trap "$3; ccm_unlock" EXIT ;;   # t = trap -- '<the commands>' EXIT
    esac
}
