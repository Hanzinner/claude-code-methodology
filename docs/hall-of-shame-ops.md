# Hall of shame: ops

Infrastructure failures of the swarm: network, services, the machines the human depends on. Read this
**before any change to network or services** on the human's laptop or a VM. Per-incident detail lives in
the mistakes journal ([`mistakes-journal.md`](mistakes-journal.md)).

## Case: "move the VM network to a new subnet" (2026-09)

**Cost of the day:** the swarm without internet for ~1h40 and again for ~1h; the human spent about 3
hours repairing by hand (from a phone browser, three laptop reboots). The laptop's Wi-Fi was also slowed
for a while by a bridged adapter.

Setup: a VM host (laptop) with a NAT network for VMs. The task was moving that NAT to a new subnet.

| # | Step the agent took | What broke | What it should have been |
|---|---|---|---|
| 1 | Deleted the NAT and created a new one on the new subnet without checking what was attached | A static port-forward rule to the old subnet stayed in the saved NAT config. After the host rebooted, the NAT service refused to start ("The parameter is incorrect") | Before replacing a NAT: list static mappings and remove them while the service is alive. Then restart the service — the same path as a boot |
| 2 | Left the old gateway address on the host adapter "temporarily" | The vendor documents that a stale gateway address on the adapter breaks NAT. The conflicting Wi-Fi range trap also remained | Compatibility for old code goes on the VM side (forwarding), not as an old address on the host |
| 3 | Wrote "DONE" because the internet worked *right now* | The whole outage that followed | For network changes, "done" only after a reboot (or a service restart that provably repeats boot) |
| 4 | "DONE" without checking the editor's remote-connection path | The human found the broken connection on their own | The change script checks **every path the human uses**: editor remote session, sites served from the VM, LAN, internet |
| 5 | — (outage began) | The human learned of it on their own: the watchdog alerts went to an agent inbox, the agent session wasn't running, and the chat bot is silent without internet too | A channel to the human that doesn't depend on the VM's internet (open hole) |
| 6 | After the human's repair, moved the VM to DHCP from the router and pointed ssh at the router-assigned address | Tied to an address the router controls; change the network and it fails again. Done without asking | Explain and ask first; don't depend on what someone else's router hands out |
| 7 | Proposed the host's "default switch" as a fallback | It didn't exist on that laptop | Check that a thing exists **before** putting it in the plan |
| 8 | Proposed "no NAT, internet through an external bridge" | A bridge on Wi-Fi slows the laptop's internet — a known thing, the human said so in advance | Know a variant's downsides before proposing it |
| 9 | First search: "no verified recipe"; offered a heavy workaround (disable the hypervisor, two reboots) | The right answer was a highly voted, accepted Q&A answer (a registry key for the NAT store) — found only after "search more" | Search the exact text of **your own** error, not the general topic |
| 10 | A watchdog on the VM waited for a ping reply from the laptop | The laptop doesn't answer ping — it was already recorded in the swarm's notes. The watchdog could never have fired | Read the machine's reference note before writing a script for it |
| 11 | Set DNS via `dns-nameservers` and verified with a dry run | Without the resolvconf package the line does nothing; when the DHCP client stopped it emptied `resolv.conf` → after the VM rebooted, 53 minutes without DNS | A real reboot, then read the self-check log after it. The agent installed the self-check and did not read it |
| 12 | A "watchdog is alive" check looked at change-files | A false alarm in the middle of the outage; noise up to 14 messages | The check must look at a sign the object writes **every time** (a heartbeat), not at a side effect |

## Common root

The agent checked what is easy to check ("works now", a dry run), not what can break (startup after a
reboot). And it did not read its own records — neither the swarm's notes (ping, bridge) nor its own self-check.

## Rule

For a network or service change on the human's laptop or a VM, "done" **only when**:

1. A rollback is written **before** the change, and tested.
2. A real reboot passed (or a service restart that repeats startup — with proof that it is the same path).
3. The agent **itself read** the self-check log after the reboot: address, route, DNS, curl outward, the editor connection, sites served to the laptop.

**Tool (since 2026-09):** VM network changes go only through a wrapper:
`net-change [--wait MIN] -- <command>`. It takes a snapshot, **schedules the rollback with a systemd timer
before the change** (it fires even if the change cuts the connection), restarts the network, and checks
internet, DNS and the laptop; if a check fails it rolls back by itself. Tested 23/23. Not suitable for the
laptop itself: there the rule is a rollback recorded before the change and a service restart as proof.

Related: [`rule-to-mechanism.md`](rule-to-mechanism.md) · [`measurement-and-proof.md`](measurement-and-proof.md)
