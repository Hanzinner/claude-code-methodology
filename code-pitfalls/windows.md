# windows

Setup these come from: a Linux VM on a Windows Hyper-V host, driven over SSH (PowerShell, WMI, drivers).

### `Set-Content` failed mid-write: the file is truncated
- **Symptom:** after a failed command (`Stream was not readable`) part of the entries in a critical file (`hosts`) were gone, so every old name returned NXDOMAIN. A completely different service looked broken.
- **Why:** `Set-Content` had already erased the contents before it failed; the next `Add-Content` appended the new lines to an empty file; only the fresh delta was checked.
- **Right way:** when a WRITE to a critical file fails, the first step is to read the whole file and compare it with what you expect, before any new writes or reports. Make a backup copy before the mutation.

### PowerShell formats numbers by locale
- **Symptom:** a bash wait loop spins until timeout although the condition has long been met (`integer expression expected`).
- **Why:** on a localized Windows PowerShell returns `256,156` (comma); `cut -d.` doesn't split it, bash arithmetic fails.
- **Right way:** pass a PS number through `tr ',' '.'` before bash arithmetic, or compute the integer on the PS side (`[math]::Floor(...)`), or compare state instead (`State -eq 'Running'`).

### Disabling a boot-start driver: BSOD
- **Symptom:** after "one safe command" `sc.exe config <drv> start= disabled` the machine doesn't boot (`INACCESSIBLE_BOOT_DEVICE`); hours of recovery.
- **Why:** a driver in the storage stack with `StartMode=Boot` loads before the kernel initializes. The web advice "safe to disable" applied to machines where it is app-level. The own measurement (`StartMode=Boot`) was in hand, and the search advice outweighed it.
- **Right way:** before any Stop/Disable/Uninstall of a driver, run `Get-CimInstance Win32_SystemDriver` and look at `StartMode`. `Boot` or `System` means STOP. If it must be done anyway, prepare a recovery / safe-mode rollback FIRST and warn explicitly about the BSOD.

### `Win32_Battery` lies with several batteries
- **Symptom:** the discharge detector stays silent, the host goes to sleep and takes the VM with it.
- **Why:** the capacity fields in `Win32_Battery` are empty and `BatteryStatus` per instance is unreliable. `min()` over percentages without a discharge flag means the alarm branch never runs. It was tested on one battery; the real setup is two in series.
- **Right way:** use `ROOT\WMI`: `BatteryStatus.RemainingCapacity` + `BatteryFullChargedCapacity.FullChargedCapacity`, summed over all batteries; derive `on_battery` from `Discharging` / `PowerOnline`.

### SSH to Windows runs in session 0
- **Symptom:** measuring button/cursor state over SSH always says "not pressed", whatever the reality.
- **Why:** `GetAsyncKeyState` / `MouseButtons` read only their own session. SSH is session 0; the user's desktop is session 1.
- **Right way:** hand input/UI measurements to the person to run in THEIR PowerShell; an SSH measurement of that state is invalid.

### Performance counters: localized names, broken sets, `catch {}`
- **Symptom:** the logger is "Running", the start marker is there, but zero data rows in two days.
- **Why:** the English counter name (`\PhysicalDisk(_Total)\…`) doesn't exist on a localized Windows; `Win32_PerfFormatted*` returned 0 instances (broken counters); a `try {} catch {}` around the whole line swallowed the error.
- **Right way:** don't depend on counter names (CPU: the difference of `Get-Process .CPU` between samples; WMI classes don't depend on the language). Put each metric in its own try with a visible error marker (`?`). An admin repairs broken counters with `lodctr /R` in `System32` (the first run gives error 2, normal; repeat it) and then `winmgmt /resyncperf`.

### The logger/monitor didn't survive a reboot
- **Symptom:** the long-awaited freeze happened, and the logger had died at the first restart.
- **Why:** it was started as a normal process, not as a persistent task.
- **Right way:** a scheduled task as SYSTEM with an AtStartup trigger. After a reboot, check for fresh data rows.
- **Seen:** twice (a recurrence of the same lesson a month later).

### A return code from a WinAPI call or utility lies
- **Symptom:** `SystemParametersInfo(SPI_SETCURSORS)` returns `False` and it worked; `taskkill` reports SUCCESS and the state remains.
- **Why:** the return code describes the call, not the result for the user.
- **Right way:** check the effect (what the person sees, the system state), not the code.

### Fixing before locating the layer where the state lives
- **Symptom:** four registry/driver changes in a row, all off target; the symptom goes away only with a reboot.
- **Why:** the state was a session-wide cursor override (`SetSystemCursor` from a process that had crashed), while the fixes hit hardware, driver and application.
- **Right way:** before any change, name the layer with three questions. Does it reproduce in unrelated programs? Does it survive restarting the affected program? Does it go away only on reboot? Yes/yes/yes means runtime session state. For the cursor: `SystemParametersInfo(0x0057,0,0,3)`.

### PowerShell 5.1 reads a file without a BOM as ANSI
- **Symptom:** a `.ps1` with non-ASCII text in strings gives a ParseError (`Unexpected token`, `The string is missing the terminator`).
- **Why:** Windows PowerShell 5.1 treats a BOM-less file as the system ANSI code page.
- **Right way:** scripts meant for a human to run are ASCII only, or UTF-8 with BOM (`printf '\xef\xbb\xbf' | cat - f.ps1`).
- **Seen:** 3 times.

### A native program's stderr under `$ErrorActionPreference='Stop'` kills the script
- **Symptom:** the script dies on a "Downloading…" line printed by an installer (`uv`).
- **Why:** under `Stop`, any line a native `.exe` writes to stderr becomes an exception.
- **Right way:** for native programs use `Continue` and check `$LASTEXITCODE`. Don't stuff complex commands into ssh quotes: put them in a file and run `-File`.

### Long PowerShell commands over SSH
- **Symptom:** quotes break; `|` and a comma inside quotes break cmd; output arrives only at the end; non-ASCII text in the console turns to garbage.
- **Why:** several layers of escaping (ssh → cmd → powershell); SSH output from Windows is buffered until the command ends; the console code page.
- **Right way:** `powershell -EncodedCommand <base64 utf-16-le>` (generate with `base64.b64encode(s.encode('utf-16-le'))`). Write the output to a UTF-8 file and fetch it with `scp` instead of reading the console.

### Registry / service / Hyper-V mutations from an agent session get blocked
- **Symptom:** `Set-VM`, `Stop-VM -TurnOff`, registry or pagefile edits are refused; reads work.
- **Why:** mutations on the human's machine are cut by the permission classifier (and they need the human's explicit yes anyway).
- **Right way:** prepare ONE idempotent ASCII `.ps1`, put it next to the target, and the human runs it once. Diagnostics and reads are free.

### "Not in the import table, so not used" is false for COM
- **Symptom:** the diagnosis "the program doesn't call API X" sends hours of iterations off target.
- **Why:** COM/vtable methods (D3D9, DirectDraw) and `LoadLibrary` + `GetProcAddress` don't appear in the PE import table. Only the factory is visible (`Direct3DCreate9`).
- **Right way:** check by disassembly or tracing (`WINEDEBUG=+<channel>` in a wine rig), not by the import table.

### PowerShell `Set-Content -Encoding UTF8` writes a BOM; Python `json.loads` treats it as an error
- **Symptom:** after editing a JSON state file through PowerShell, a Python service behaves as if the file were empty (and the next write wipes the data).
- **Why:** Windows PowerShell 5.1 with `-Encoding UTF8` adds a BOM (EF BB BF). `open(..., encoding="utf-8")` keeps `﻿` at the start, `json.loads` raises, and code with `except: return set()` silently sees "empty".
- **Right way:** edit machine state files with the same tool that reads them (Python), or `scp` a finished file. JSON readers on Windows use `encoding="utf-8-sig"` (reads with and without BOM). Log read errors, don't swallow them.
- **Cost:** a "was this already done" safeguard went blind and two actions were repeated by mistake.

### A directory and a flag file that differ only in case are one path on Windows
- **Symptom:** `unlink(state/FLAG)` gives "Access is denied"; the flag "exists" although nobody created it.
- **Why:** NTFS is case-insensitive by default: `state/flag/` (a directory) and `state/FLAG` (a flag file) are the same object.
- **Right way:** names of directories and flags in a shared directory must differ by more than case (`state/rec_data/` + `state/RECORD`).

### Walking the UI Automation tree hangs and kills VS Code / Electron
- **Symptom:** a tool that lists the buttons of all windows (a Windows automation MCP server's `Snapshot` / `WaitFor`) hangs. VS Code reports "Not responding", Windows terminates `Code.exe` (event 1002), taking every agent tab with it.
- **Why:** UIA requests into an Electron renderer deadlock its main process (an open upstream issue of that tool).
- **Right way:** on the human's machine, use only screenshots plus clicks by coordinates. Use the element tree only if VS Code runs with `--disable-renderer-accessibility` or the tool can exclude processes. Before running someone else's tool on a live machine, search its issues for the names of the programs you work in.

### Measuring Windows disk usage with `Get-ChildItem -Recurse`: minutes and heavy load
- **Symptom:** "what takes up C:" over SSH runs 5–10 minutes, slows the laptop, and dies with the SSH session. The profile is counted twice (junction loops `Application Data`, `Local Settings`).
- **Why:** PowerShell walks every file through the file system; WizTree reads the NTFS table directly.
- **Right way:** use a tool that reads the MFT (the WizTree CLI on the laptop: 8 s for a drive). Without one, at least `-Attributes !ReparsePoint`.
