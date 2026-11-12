# android

Automating Android apps over adb (physical phones and redroid containers; uiautomator, uiautomator2).

### resource-ids in third-party apps are obfuscated
- **Symptom:** the automation works on one device/version and breaks on another.
- **Why:** ids in app builds are obfuscated and change between versions.
- **Right way:** find elements by `text` / `content-desc`; an id is only a hint. Elements with bounds `[0,0][0,0]` are hidden junk; filter them out.

### `uiautomator dump` is slow
- **Symptom:** a scroll loop is "unhumanly" slow (2–5 s per dump on an old device).
- **Why:** each dump launches the tool on the device separately.
- **Right way:** the uiautomator2 agent (`Phone(fast=True)`-style wrapper, ~0.5 s).

### MIUI blocks `input tap`
- **Symptom:** `SecurityException: INJECT_EVENTS`; screenshots and dumps work.
- **Why:** Xiaomi requires a separate permission for event injection.
- **Right way:** enable "USB debugging (Security settings)" (needs a Mi account). Samsung doesn't require this.
- **Seen:** twice.

### The adb server lives inside the SSH session
- **Symptom:** between SSH calls the device "disappears" or asks for authorization again.
- **Why:** the adb server on a Windows host starts inside the session and dies with it; an authorization without the checkbox is one-time.
- **Right way:** every call brings up adb itself; on the phone, authorize with "Always allow".

### `monkey` doesn't start an app in redroid
- **Symptom:** launching via `monkey -p` does nothing.
- **Why:** root cause not established; only a working workaround is recorded.
- **Right way:** `am start -n <pkg>/<activity>`.

### Getting an APK without a browser
- **Symptom:** apkmirror/apkpure return HTML instead of a file.
- **Why:** the sites expect a browser.
- **Right way:** `apkeep -d apk-pure` → XAPK → unpack with `python3 -m zipfile` → `adb install-multiple base + config.<abi> + languages`. Check the device's ABI (old ones are armeabi-v7a only).

### redroid: host OS and binder
- **Symptom:** redroid doesn't boot on Debian; on a working machine the binder module is "busy".
- **Why:** redroid expects `/dev/binder`, while Ubuntu's `linux-modules-extra` provides binderfs; binder parameters can only be set before the module's first load. One binder context per host.
- **Right way:** Ubuntu 22.04/24.04. Symlink `/dev/binder → /dev/binderfs/binder` (tmpfiles.d), mount binderfs via fstab, mode 0666. Put module parameters in `/etc/modprobe.d` before the first load (otherwise reboot). One redroid container per host.

### redroid ignores `docker --dns`; netd breaks a shared netns
- **Symptom:** DNS in redroid is wrong; a VPN container (gluetun) loses its route seconds after redroid starts; the timezone from boot args is ignored.
- **Why:** Android's `netd` rewrites routes/iptables in the shared netns; redroid reads DNS from boot props.
- **Right way:** run the VPN on the host (policy routing for the subnet + a kill-switch in DOCKER-USER), not `--network=container:`. DNS: `androidboot.redroid_net_dns1=…`. Timezone: `setprop persist.sys.timezone` after boot.

### A bot on a break leaves the app on screen
- **Symptom:** the app's feed "learns" from a random video although the bot did nothing.
- **Why:** during the pause between sessions the app stayed in the foreground with the screen on; a video looped for minutes, which for a recommender is the strongest "likes it" signal.
- **Right way:** before EVERY break press HOME and turn the screen off (`input keyevent 3`, then `223`), check `dumpsys power` (`mWakefulness` is not `Awake`), and write it to the log. After the break wake the device (`224`) and reconnect uiautomator2.

### uiautomator2: "No display found" in a screenshot
- **Symptom:** `AdbError: No display found` and the process dies, most often right after the screen went off or just woke.
- **Right way:** wrap the screenshot in 3 attempts: wake the screen, reconnect the u2 agent, and on the last attempt use a bare `adb screencap`. Same for the UI dump.

### Invisible direction marks in app texts
- **Symptom:** comparing a username with a search result fails although the text on screen is the same.
- **Why:** the app wraps usernames in U+200E, U+2068, U+2069 (bidi isolates).
- **Right way:** before comparing, strip U+200E / U+200F / U+202A–202E / U+2066–2069 and decode XML entities (`&#10;` → newline).

### redroid: the system Home button matches an app's tab
- **Symptom:** the bot taps "Home" to return to the feed and ends up on the Android home screen.
- **Why:** redroid's navigation bar has an element with `content-desc="Home"` (resource-id `home`), just like the app's bottom tab.
- **Right way:** when searching for elements skip the ids `home`, `back`, `recent_apps`.

### Checking a toggle's state via `selected` on an old Samsung
- **Symptom:** a script that undoes toggles doesn't "see" that one was undone and loops, tapping on.
- **Why:** the toggle button's `selected` updates in the UI tree late or not at all.
- **Right way:** verify the result by a change in a count visible elsewhere (tap once → back → recount), and stop if the count didn't drop.

### `svc power stayon usb` makes the screen permanently "Awake"
- **Symptom:** the "phone is in a human's hands" detector (screen on, not by the bot) always fires, and the schedule skips every session.
- **Why:** `svc power stayon usb` sets `settings global stay_on_while_plugged_in=2`: while the phone is on USB power the screen never turns off and `mWakefulness` is always `Awake`. The bot itself turned this on at every connect.
- **Right way:** never enable stayon. At start check `settings get global stay_on_while_plugged_in` and set `0`, with a log line. Human detector = `mWakefulness=Awake` AND `isStatusBarKeyguard=false` (a lock screen woken by a notification isn't a human). An explicit human command (START_NOW, /resume) bypasses the detector.

### A hidden loop and a console window in Windows Task Scheduler
- **Symptom:** a task with a logon trigger starts, and a minute later its process is dead, `Last Result = -1073741510` (0xC000013A).
- **Why:** a task with `/IT` opens a visible console window; closing the window is Ctrl+C for the whole process tree. Separately: creating a task with an ONLOGON trigger needs administrator rights; a double-click without elevation doesn't create it.
- **Right way:** the `.cmd` immediately relaunches itself through `wscript.exe` + a `.vbs` with `Run ..., 0` (no window) and exits. The installer asks for elevation itself (`Start-Process -Verb RunAs`).

### uiautomator2 `touch.down/move/up` over Wi-Fi ADB: the app doesn't see a tap
- **Symptom:** a "human-like" tap (down → 55–130 ms pause → move ±2 px → up) over Wi-Fi ADB on an old Samsung: the app doesn't open a profile on an avatar tap (4× `handle=None` in 2 minutes after deploy).
- **Why:** each u2 call is a separate HTTP request to the agent on the phone; over Wi-Fi hundreds of ms accumulate between down and up, plus the move, and the gesture stops being a tap.
- **Right way:** a single `u.click(x, y)` with a ±4 px offset (confirmed: the next profile opened). A real hold duration is possible only in one stream (minitouch / writing to `/dev/input/eventN`). After changing gestures, run a live test on EVERY changed gesture (tap, swipe, double tap), not only the one you changed it for: the test covered swipes only and missed the tap.

### `cmd vibrator vibrate` on Samsung (Android 8.1): at most 200 ms, error as text
- **Symptom:** `adb shell cmd vibrator vibrate 500 <tag>` gives no vibration and exit code 0; `vibrate 150` works.
- **Why:** VibratorShellCommand limits the duration. The output contains `java.lang.IllegalArgumentException: maximum duration is 200`, but the shell returns 0, so an exit-code check doesn't see the error.
- **Right way:** pulses ≤200 ms; "long" means several 200 ms pulses back to back. Check the command's OUTPUT for "Exception". The fact of vibration is in `dumpsys vibrator` (lines `opPkg: <tag>`, `mTiming=`).

### Giving feedback to a human from adb on Android 8.1: no toast, no vibration out of the box
- **Symptom:** `cmd vibrator vibrate N` leaves an entry in `dumpsys vibrator` ("uid: 2000") but the motor is silent (the motor works; a normal notification vibrates). `cmd notification post` doesn't exist (appeared in Android 9); uiautomator2 3.x has no toast (`-32601 method not found`).
- **Why:** Samsung ignores vibration from the shell; there are no other stock shell means of showing a message on 8.1.
- **Right way:** your own tiny receiver APK (BroadcastReceiver → Toast + a notification with an IMPORTANCE_HIGH channel and a vibration pattern + `Vibrator` with the VIBRATE permission), triggered by `am broadcast -f 0x20 -n <pkg>/.Say --es text …`. Build without Gradle: aapt2 + javac + d8 + zipalign + apksigner. Verify vibration with `dumpsys vibrator` showing `opPkg: <pkg>`.

### d8 fails on an anonymous class with JDK 21 (`-source 8`)
- **Symptom:** `Error in …/Say$1.class: java.lang.NullPointerException: Cannot invoke "String.length()" because "<parameter1>" is null`, in both build-tools 30.0.3 and 34.
- **Right way:** replace the anonymous class (`new Runnable() {…}`) with a regular named class; d8 then builds. Avoid lambdas too unless you want to deal with desugaring.

### Your own accessibility service doesn't come up while uiautomator2 is running
- **Symptom:** an AccessibilityService (here a volume-button filter) is enabled via `settings put secure enabled_accessibility_services`, the value is set, but `dumpsys activity services <pkg>` says "(nothing)" and `onKeyEvent` is never called. `dumpsys accessibility` crashes with an NPE on the UiAutomation entry.
- **Why:** an active UiAutomation (uiautomator2 holds one the whole time) SUSPENDS all other accessibility services unless connected with `FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES`; u2 doesn't set that flag.
- **Right way:** don't build anything on an accessibility service that must work during u2 automation. Read buttons with `getevent` on the button device; "block" a volume change only by rolling it back (`media volume --set`) after each press. Between u2 sessions the service comes alive; disable it so it doesn't intercept at the wrong time.

### uiautomator2: retrying a gesture after a dropped connection taps the new screen
- **Symptom:** the uiautomator2 service on the phone dies mid-session (`http.client.RemoteDisconnected` on `press("back")`). A naive "reconnect and retry" doubles the action: a tap that already opened a video repeats at the same point of the new screen (Follow/Report), "back" runs twice.
- **Why:** `RemoteDisconnected` or a timeout doesn't say whether the command executed; the request may have arrived while the reply was lost.
- **Right way:** retry only when the connection was refused BEFORE sending (`ConnectionRefused` / `NewConnectionError`). Otherwise reconnect and raise the exception upward, where state is restored from the screen (back to the feed, next block). If gestures come from several threads (human buttons + the main loop), use one `RLock` for all u2 calls of one phone.
- **Found by:** an independent review of the first version of the retry.

### A "system window" detector that matches screen text fires on other people's content
- **Symptom:** the bot stops with an alarm "TOO MANY ATTEMPTS" while the screen shows an ordinary video captioned "…WAY TOO MANY ATTEMPTS BUT YAY SO CUTE".
- **Why:** the captcha/block regex searched the whole dump, and the dump contains captions, usernames, comments, bios: text written by people. Broad phrases ("too many attempts", "suspicious", "select all") occur there.
- **Right way:** search only in "system" nodes (no caption/username ids, no long texts, none containing `@` or `#`). Use full system wordings ("Too many attempts. Try again later"). Add a negative test on a dump with such a caption, plus a run over all saved dumps.
- **Cost:** the bot sat idle for 11 minutes.

### A toggle's state can't be read from the UI tree on an old phone: only by color on a screenshot
- **Symptom:** the bot "toggled" (log says so) but the icon is white; a second pass taps the already-set toggle and undoes it; a count in another tab doesn't change (it counts only on-screen cells, ≤6).
- **Why:** the toggled and untoggled items have the same desc ("Like video. N likes"), N isn't updated locally, and `selected` isn't updated (see above).
- **Right way:** take a screenshot → crop the button with the matching desc → the share of red pixels (r>200, g<90, b<120) above 0.15 means "on". Before a tap: red means don't tap. After a tap: check it turned red, otherwise log a warning. Verified white → tap → red on 3 items.

### A swipe via uiautomator2 / `input swipe` is taken for a TAP by an app on an old Samsung
- **Symptom:** ~15–27% of swipes "don't finish scrolling"; the video pauses (▶ icon) or the long-press menu opens. Tuning the chord/speed changes nothing (failures at 270 px / 6000 px/s too).
- **Why:** both paths go through Android's InputManager (event injection); on a slow Android 8.1 device the app sees some of these gestures as a tap. Separately: a gesture with s=t⁵ motion "stands" for the first ~50% of the time → hold → menu.
- **Right way:** minitouch (npm `@devicefarmer/minitouch-prebuilt`, armeabi-v7a, Apache-2.0) writes events straight to the sensor's `/dev/input/eventN`; the shell is in the `input` group, no root needed: `printf '%s\n' 'd 0 x y 50' c 'w 12' 'm 0 x y 50' c 'u 0' c | minitouch -i`. Control: 40/40 scrolled (was ~80%). Make the motion with no "standing" at the start (k≤2.2). A listener for human touches can tell them apart: a finger produces `BTN_TOOL_FINGER` and `ABS_MT_TOUCH_MAJOR`, minitouch doesn't.
- **Test-rig note:** after a failed swipe close the menu over the video, otherwise all later "failures" are artifacts (the first run gave 0/45).

### `getevent -t` is not the same clock as `/proc/uptime`
- **Symptom:** merging sensor events with the computer's time gives −20000 s.
- **Why:** kernel time in getevent stops while the phone sleeps (monotonic), while `/proc/uptime` counts sleep too; on one phone they diverged by ~5.6 h in a day.
- **Right way:** while reading the stream, write the computer's receive time next to each event; the offset is the minimum of (receive time − kernel time) over all events (the fastest-delivered one has ≈0 latency).

### The UI dump on old Android writes non-BMP emoji as dots
- **Symptom:** in bios/names/captions flags and some emoji become "...." ("18🇺🇦" → "18....").
- **Why:** the dump serializer on Android 8.1 writes each half of a UTF-16 surrogate pair as ".", so the dots are already in the raw XML.
- **Right way:** re-read exactly that element with a targeted uiautomator2 query (`d(resourceId=…, instance=k).get_text()`; without a resource-id, `textStartsWith=<text before the first dots>`): JSON-RPC returns the real text. Verify "same element" by matching letters/digits.
- **Found by:** a judge pass: 0 flags out of 69 bios.

### Volume button: a real press can be shorter than the "chatter" threshold
- **Symptom:** a person presses "up ×2", ×1 is counted, and the command doesn't fire.
- **Why:** the chatter filter dropped presses under 30 ms, while a quick finger press on that phone is 20 ms.
- **Right way:** don't discard a short press; defer it. If no chatter continuation arrives within ~0.3 s (or before the next press starts), count it. The check-then-act runs under the same lock as the counting (timer and reader thread).

### A horizontal swipe on a photo carousel "doesn't carry through"
- **Symptom:** the bot swipes sideways on a photo, the photo shifts and snaps back; the "N / M" counter doesn't change.
- **Why:** a uiautomator2 swipe (`d.swipe`) runs at constant speed: 60% of the width in 200–350 ms the app treats as a drag without a fling. A human swipes short and fast: 18% of the width in ~80 ms, peak speed at the end, release at ~3300 px/s.
- **Right way:** a gesture with speed rising toward release (minitouch, points s = t^k, k≈2), with parameters taken from a recording of a human, not from your head. Verify by the counter after each swipe, not by "swipe executed".

### Tapping an author's avatar opens stories, and "back" from the profile returns to stories
- **Symptom:** the bot "opens a profile", then scrolls and taps on the wrong screen: a "Message <name>..." field opens with a keyboard, swipes type junk into the reply field.
- **Why:** an avatar with a story ring leads to stories, not the profile. If you go from stories to the profile, the back stack returns to stories. A bot that thinks it's in the feed taps someone else's screen.
- **Right way:** open the profile by tapping the username text. Before each action on a "video" check the screen: an input field in focus / a keyboard (except the search screen), or a screen with no feed/video/profile/search markers means press "back" until it's gone. Long-press only on a real video.

### "Charging from USB" does not mean "won't run down"
- **Symptom:** a robot phone is cabled to a PC; `dumpsys battery` says `USB powered: true`, `status: 2` (charging); mid-session the phone shuts down, and the collector sees "device offline" and counts it as crashes.
- **Why:** a PC USB port gives ~0.5 A. Under load (screen, video, Wi-Fi adb) the phone draws more, so the battery drains even "on charge".
- **Right way:** base the safeguard on the level alone (don't start below 20%, wind down gently below 20%, resume from 30%), not on the "charging" flag. A phone vanishing at a low level is its own cause, not a "crash".
