# T618 — Linux Host Session Audit, Moksha/Bodhi 8-Zone Window Snapping & Desktop Icon Backports, and 9 Prepared Upstream PRs

- **Ticket:** `T618`
- **Date:** `2026-11-03`
- **Agent:** `agy:t618-linux-distro-oss-prs`
- **Host:** Bodhi Linux 7.0 (`Ubuntu 22.04 Jammy`, `Moksha 0.4.2-4`, `X11 :0.0`, `1680x1050`)

## 1. Cross-Session Host Audit Summary

Across Antigravity, Claude Code, Codex, and Orca session histories on this Linux host, nine distinct host/desktop/tooling fixes and enhancements were identified, separated from host-specific operations (such as CPU pinning on `AMD A10-5745M` or personal credentials), and prepared as clean, GPG-signed (`952D3D46E7ACF73E27ED11573B58673D024322CF`), single-concern upstream PR branches across **Track A** (Window Manager & Bodhi Linux Distro) and **Track B** (Developer Desktop & Security Tooling).

## 2. Track A — Moksha WM & Bodhi Linux Distro (`6` PR Branches + Local `.deb`)

### Prepared Upstream PR Branches

| Upstream Repo | Fork Branch (`webomage/*`) | Base | Signed SHA | Compare URL |
| :--- | :--- | :--- | :--- | :--- |
| `JeffHoogland/moksha` | `feat/eight-zone-window-snapping` | `master` | `ab2ccde251` | <https://github.com/JeffHoogland/moksha/compare/master...webomage:feat/eight-zone-window-snapping?expand=1> |
| `JeffHoogland/moksha` | `fix/desktop-editor-icon-path-and-size` | `master` | `8fa2b5ff76` | <https://github.com/JeffHoogland/moksha/compare/master...webomage:fix/desktop-editor-icon-path-and-size?expand=1> |
| `JeffHoogland/moksha` | `feat/appimage-diricon-and-rdns-wmclass` | `master` | `ab44d40c0b` | <https://github.com/JeffHoogland/moksha/compare/master...webomage:feat/appimage-diricon-and-rdns-wmclass?expand=1> |
| `BodhiDev/bodhi-profile-iso` | `feat/eight-zone-window-snap-bindings` | `main` | `c67f582c31` | <https://github.com/BodhiDev/bodhi-profile-iso/compare/main...webomage:feat/eight-zone-window-snap-bindings?expand=1> |
| `BodhiDev/bodhi7packages` | `feat/moksha-snap-and-icon-backports` | `main` | `04cf2574ae` | <https://github.com/BodhiDev/bodhi7packages/compare/main...webomage:feat/moksha-snap-and-icon-backports?expand=1> |
| `BodhiDev/bodhi8packages` | `feat/moksha-snap-and-icon-backports` | `main` | `78adb66686` | <https://github.com/BodhiDev/bodhi8packages/compare/main...webomage:feat/moksha-snap-and-icon-backports?expand=1> |

*(Combined Moksha integration branch also pushed to `webomage/moksha:beta` at `75839c83c`.)*

### Design Rationale: Proposing Top Half (`E_MAXIMIZE_TOP`) as the Default Top-Edge Drag Action

1. **4-Edge + 4-Corner Geometric Symmetry**: Dragging to Left, Right, Top, or Bottom edges snaps to the corresponding `50%` half (`E_MAXIMIZE_LEFT`, `E_MAXIMIZE_RIGHT`, `E_MAXIMIZE_TOP`, `E_MAXIMIZE_BOTTOM`), while dragging within `64px` of any of the 4 screen corners snaps to the `25%` corner quarter (`E_MAXIMIZE_TOP_LEFT`, `E_MAXIMIZE_TOP_RIGHT`, `E_MAXIMIZE_BOTTOM_LEFT`, `E_MAXIMIZE_BOTTOM_RIGHT`).
2. **Missing Mouse Gesture vs. Existing Redundant Triggers**: Full Maximize already has three fast triggers in Moksha (titlebar double-click, titlebar Maximize button, and double `Super+Up` via `Top Half -> Full Maximize` promotion), whereas Top Half previously had zero mouse gesture—leaving vertical top/bottom split tiling impossible by mouse.
3. **Opt-In Full Maximize Toggle**: Added `"Maximize fully when dragging to top edge"` (`e_config->snap_top_edge_maximize`, default `0`) in **Settings -> Windows -> Window Geometry -> Maximization** for users who prefer GNOME/Windows top-edge full maximize.

### Desktop & AppImage Icon Root Causes Fixed

- **`src/bin/e_eap_editor.c`**: `e_desktop_border_edit()` wrote `~/.e/e/icons/<bname>-<pid>.png` (`path`) and copied `editor->tmp_image_path = strdup(editor->desktop->icon)` for cancel-unlink, yet assigned `desktop->icon = strdup(file)` (bare filename), causing `efreet_icon_path_find` to fail (`?` icon) and leaking temp PNGs on cancel; it also selected `icons[0]` (`16x16`) instead of the largest `_NET_WM_ICON` entry. Fixed to sanitize `bname` with `ecore_file_file_get`, pick the highest-resolution `_NET_WM_ICON`, and store `strdup(path)`.
- **`src/bin/e_border.c`**: Added `MAX(0, ...)` clamping in `_e_border_client_inset_calc` for GTK3/4 CSD `_GTK_FRAME_EXTENTS`, reverse-DNS `WM_CLASS` trailing-segment matching (`md.obsidian.Obsidian -> Obsidian`), `>=64x64` `_NET_WM_ICON` selection, and `/proc/<pid>/exe -> /tmp/.mount_*/.DirIcon` fallback for portable AppImages.

### Local `.deb` Package & Turnkey Cutover Helper

- Built and verified `/home/aleksei/.local/share/moksha-backport/moksha_0.4.2-4+w0m1_amd64.deb` (`45.7 MB`, `ldd OK`, `04755` SUID bits verified on `enlightenment_sys`, `enlightenment_backlight`, and `freqset`, quilt patches archived under `~/.local/share/moksha-backport/patches/`).
- Installed `/home/aleksei/.local/bin/moksha-apply-native-snap` to retire the user-space XInput2 `moksha-snap --daemon` workaround, clean `~/.e/e/applications/startup/.order`, update `e.cfg` via `eet`, and restart Moksha once `sudo dpkg -i` is run.

## 3. Track B — Developer Desktop & Security Tooling (`3` PR Branches)

| Upstream Repo | Fork Branch (`webomage/*`) | Base | Signed SHA | Verification | Compare URL |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `stablyai/orca` | `fix/linux-cli-stale-appimage-and-dispatcher` | `main` | `42f3b336fd` | `40/40` Vitest tests passing | <https://github.com/stablyai/orca/compare/main...webomage:fix/linux-cli-stale-appimage-and-dispatcher?expand=1> |
| `stablyai/orca` | `fix/webgl-atlas-version-desync-recovery` | `main` | `8eb9e8651f` | `11/11` Vitest tests passing | <https://github.com/stablyai/orca/compare/main...webomage:fix/webgl-atlas-version-desync-recovery?expand=1> |
| `bulwarkid/virtual-fido` | `feat/linux-desktop-hotkey-helper` | `master` | `20e460bf57` | `3/3` `unittest` + `bash -n` passing | <https://github.com/bulwarkid/virtual-fido/compare/master...webomage:feat/linux-desktop-hotkey-helper?expand=1> |

## 4. Estate Registration & Verification (`scripts/w0m_prs.py`)

- Registered `JeffHoogland/moksha`, `BodhiDev/bodhi-profile-iso`, `BodhiDev/bodhi7packages`, and `BodhiDev/bodhi8packages` in `PRESET_REPOS` and `FORK_UPSTREAM_MAP`, updated `build_pr_proposals` `master` base-branch resolution for `/moksha`, and added all 9 structured **Why / What For / How** proposals to `CONTRIBUTION_PROPOSALS`.
- `python3 scripts/tests/test_w0m_prs.py`: `88/88` checks passing.
- Per `T435`, zero upstream PRs were opened automatically via `gh pr create`; all 9 branches are pushed to `webomage/*` and ready for owner-confirmed submission via compare URLs or `just prs-submit`.
