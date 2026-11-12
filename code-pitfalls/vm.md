# vm

Setup these come from: a Linux VM on a Windows Hyper-V host, driven over SSH (plus QEMU rigs for OS development).

### A dynamic VHDX ceiling larger than the free space
- **Symptom:** a VM created with a 40 GB disk on a volume with 26 GB free.
- **Why:** a dynamic disk grows with data and can fill the whole host volume.
- **Right way:** `Get-PSDrive <volume>` before creating. Set the ceiling well below the free space, "as much as needed", not "with a margin". Remove intermediate images right away.

### Automatic Hyper-V checkpoints
- **Symptom:** writes go to an unnoticed `X_<GUID>.avhdx`; disk compaction fails.
- **Why:** Hyper-V on Windows 10 makes a checkpoint at every start by itself.
- **Right way:** `Set-VM -Name X -AutomaticCheckpointsEnabled $false` BEFORE the first start. For compaction: disable, merge the checkpoint, power Off, Compact.
- **Seen:** twice.

### `Stop-VM -Force` doesn't stop a hung guest
- **Symptom:** `Set-VMFirmware` fails "while running"; a disk is swapped hot.
- **Why:** `-Force` asks the guest to shut down; a hung guest doesn't answer.
- **Right way:** `Stop-VM -TurnOff` and wait for `State -eq 'Off'` before changing hardware or firmware.
- **Seen:** twice.

### Gen2 + Linux: Secure Boot
- **Symptom:** a Gen2 VM with Debian doesn't boot.
- **Why:** the default Secure Boot template is for Windows only.
- **Right way:** `Set-VMFirmware -SecureBootTemplate MicrosoftUEFICertificateAuthority`.

### Azure VHD on a local Hyper-V
- **Symptom:** an Ubuntu `*-azure.vhd` hangs at 1.5 s of boot and ignores the NoCloud seed.
- **Why:** the datasource is pinned to Azure and there is no Azure agent.
- **Right way:** use the generic cloud image (`*-server-cloudimg-amd64.img`; qcow2 is many times smaller than raw) → raw → `truncate` + `sgdisk -e` → `qemu-img convert -O vhdx -o subformat=dynamic`. Provide a NoCloud ISO labeled `cidata` (user-data / meta-data / network-config).

### Nocloud image: no SSH server; chroot and resolv.conf
- **Symptom:** the VM came up but SSH is unreachable; `apt` in a chroot has no DNS; services start inside the chroot.
- **Why:** `debian-*-nocloud` has no openssh-server; `/etc/resolv.conf` is a symlink to systemd-resolved, dead inside a chroot.
- **Right way:** chroot with bind mounts of `/proc /sys /dev /dev/pts`. Temporarily replace `resolv.conf` with a file using a public DNS, then restore the symlink. Add a `policy-rc.d` with `exit 101`; `systemctl enable ssh`. Take the root of a loop image explicitly as `${LOOP}p1` (lsblk may not show FSTYPE).

### `linux-modules-extra-generic` doesn't exist
- **Symptom:** cloud-init doesn't install the modules package.
- **Why:** the package is tied to the kernel version.
- **Right way:** `linux-modules-extra-$(uname -r)`.

### `/tmp` on the VM is a 1 GB tmpfs in RAM
- **Symptom:** ENOSPC breaks output capture of ALL commands in the session; OOM risk on already tight memory.
- **Why:** "75 GB free" referred to `/`, not `/tmp`.
- **Right way:** before writing more than 500 MB, run `df` on exactly that path. Put large files in `/var/tmp` (on disk).

### An overloaded machine fabricates "bugs"
- **Symptom:** a build fails with no error in the log (exit 101) and passes on a rerun; tests go red "every other time".
- **Why:** parallel QEMU/cargo/builds exhaust threads (`failed to spawn work thread: WouldBlock` → a compiler ICE) and CPU. The ICE leaves junk files that later block a release as a "dirty tree".
- **Right way:** limit build parallelism (`CARGO_BUILD_JOBS=2`). Under load, mark a test result "not measured" instead of red. Before concluding, run a controlled experiment: load → effect → removed → gone.
- **Seen:** 3 times over two months.

### QEMU drops serial bytes if nobody reads the socket
- **Symptom:** gaps in the serial log.
- **Why:** QEMU doesn't buffer chardev output without a reader.
- **Right way:** the rig keeps a background reader thread on the socket, and only ONE (see [concurrency](concurrency.md)).

### A rig without storage: persistence tests prove nothing
- **Symptom:** "files aren't saved after a reboot".
- **Why:** QEMU booted with `-cdrom` only, no `-drive`; the guest honestly logged that it ran in RAM mode.
- **Right way:** for persistence attach a raw image (`qemu-img create -f raw x.img 16M`, `-drive format=raw,if=ide,index=1`). Read what the guest says about its own storage.

### A Hyper-V console screenshot without RDP
- **Symptom:** you can't see where the guest's boot hung.
- **Why:** RDP/SSH aren't up yet.
- **Right way:** WMI `GetVirtualSystemThumbnailImage` → convert the RGB565 thumbnail to PNG. Limitation: in a bootloader framebuffer mode the thumbnail can't be captured (RET=32775).

### Reading a Hyper-V serial-port named pipe over SSH
- **Symptom:** the SSH session hangs.
- **Why:** asynchronous pipe readers hold the session.
- **Right way:** a detached process (`Start-Process … -WindowStyle Hidden`) that accumulates into a MemoryStream and writes the file ONCE when the pipe closes. `Stop-VM -TurnOff` closes the pipe.

### Compacting a Linux guest's VHDX returns little: 32 MB blocks
- **Symptom:** the guest uses 45 GB of 122; fstrim freed 62 GiB; the host file is 79.1 GB. Forecast "−30 GB" after `Optimize-VHD -Mode Full` (VM Off). Fact: 79.1 → 72.6 GB (−6.5).
- **Why:** a dynamic VHDX has `BlockSize = 32 MB` (`Get-VHD`). Compaction returns only COMPLETELY empty 32 MB blocks; ext4 spreads data over block groups across the whole disk, so almost every 32 MB block holds at least a little data. fstrim doesn't change that.
- **What works:** (1) don't let the disk grow: daily fstrim, fewer junk writes (worktrees, caches, scratch dirs). (2) Cut contents inside the guest. (3) Radically, shrink the disk itself: `resize2fs` to a smaller size (offline, from rescue) → move the partition → `Resize-VHD -ToMinimumSize` or a smaller `-SizeBytes`; then data compacts toward the start and the file ceiling drops. (3) is risky and needs a fresh verified backup.
- **Before promising "compaction will return N GB" for a Linux guest:** expect single GB, not tens.
- **Seen:** a person had remembered that earlier compaction "gave nothing", and an agent dismissed that with theory. The memory was right.

### Hyper-V internal network on a "popular" subnet collides with someone else's Wi-Fi
- **Symptom:** a VM NAT / vEthernet on a common home-router range plus a mobile laptop: the Wi-Fi of a public venue handed out an address in the same range. Two interfaces in one subnet, the VM lost internet and the laptop couldn't see the VM.
- **Why:** the ranges routers ship with by default (the common 192.x home ranges and 10.0.0.x) are everywhere.
- **Right way:** for the VM's internal network pick a rare /24 (for example from `172.16.0.0/12`), and check that the laptop's Wi-Fi isn't in it.

### RelativeWeight / Maximum / Reserve don't work on Windows 10/11 (root scheduler)
- **Symptom:** `Set-VMProcessor -RelativeWeight` is accepted but has no effect.
- **Why:** on client Windows Hyper-V uses the root scheduler by default (Hyper-V-Hypervisor event Id=2 → "type 0x4"). Under it the VM's CPU controls are ignored.
- **Right way:** check the scheduler type BEFORE the change. Working levers: fewer vCPUs (VM Off), or `bcdedit /set hypervisorschedulertype classic` + reboot (rollback: `... root`).

### Create a Linux guest's disk on Hyper-V with a 1 MB block, not 32 MB
- **Symptom:** 42 GB of data, and the vhdx file after fstrim + `Optimize-VHD` is 86 GB (101.19 → 86.04). It doesn't go lower.
- **Why:** the default `BlockSize` of a dynamic VHDX is 32 MB. `e2freefrag` shows 31% of free space in chunks under 32 MB, and only about 7% in chunks under 1 MB.
- **Right way (Microsoft, "Best Practices for running Linux on Hyper-V"):** `New-VHD ... -Dynamic -BlockSizeBytes 1MB` and `mkfs.ext4 -G 4096`. The block size of an existing disk can't be changed in place: either `Convert-VHD -BlockSizeBytes 1MB` into a new file, or a new disk + rsync. Both need room for a second file (up to the old one's size).
- **Also:** `Optimize-VHD -Mode Full` on a file that isn't attached silently runs as `Prezeroed` (cmdlet documentation); `Full` / `Quick` require `Mount-VHD -ReadOnly`. That doesn't remove the 32 MB ceiling either.
- **Before any new Linux VM:** a 1 MB block from the start. Later it costs a copy of the whole disk.

### Claude Code chats suddenly return "403 Access to this model requires an access grant" and bounce to login: an outdated extension, not a login problem
- **Symptom:** in open VS Code chats on a newer model: `Failed to authenticate. API Error: 403 Access to this model requires an access grant your request does not have`, then a login screen. A smaller model kept working. The model picker's "Default" flickered between two models.
- **Why:** the extension on the VM was on an old version (2.1.289) while the server had changed permissions / default models (2.1.290 was out). The account and token were intact: `claude -p "ok" --model <newer-model>` with the same credentials file answered without errors.
- **Right way:** update the Claude Code extension and reload the window. Confirmed: the 403 disappeared.
- **Don't:** press `/login` or sign out. A failed re-login kills even the sessions that still work.
- **Diagnose in a minute:** `ls -d ~/.vscode-server/extensions/anthropic.claude-code-*` against `curl -s https://registry.npmjs.org/@anthropic-ai/claude-code/latest`; a model probe through `claude -p` shows whether the grant is alive.

### A dynamic VHDX keeps growing with no new data: shrink the filesystem and cut the partition
- **Symptom:** the host file grows up to 2 GB/hour while the data stays constant.
- **Why:** Hyper-V allocates a 32 MB block on first write and doesn't give it back until it's entirely empty. Linux scatters temporary files across the whole disk. `Optimize-VHD` returns only entirely empty blocks (after `fstrim`).
- **Right way:** `resize2fs` to the wanted size from initramfs (local-premount, before the root is mounted), cut the partition with `sfdisk -N`, run `blkdiscard -f` on the freed gap (without `-f`: "device busy"), then `Optimize-VHD`.
- **Traps:** `parted -s` refuses to shrink (needs `---pretend-input-tty`); a `resize2fs` failure in a script without `pipefail` passes unnoticed; after cutting the partition the `/dev/sdaN` node disappears and reappears (use `udevadm settle` + a wait loop); a failure after `resize2fs` is a `panic`, not a normal boot (the filesystem may be half-moved); a `resize2fs -z` undo file needs space on another disk.
