# _arch — soft-delete bin

The recycle bin for the w0m estate workspace. When something looks safe to delete but
you'd rather not lose it outright, `mv` it here instead of `rm`. Gitignored (this
README is the one tracked exception, same pattern as `_in/` and `_msg/`), so nothing
landing here touches any of the seven repos or estate history.

Not a permanent archive — periodically empty it once its contents are confirmed dead.
Give each moved item its own subfolder named for what it was, so provenance survives
the move without needing this file to enumerate contents.

## Current contents

- `ds_arc/` — extracted copies of five divergent "Webomage Design System" Claude
  Design canvas exports (2026-07-11 to 2026-07-14). Superseded: diffed file-by-file
  against `wom7web/design-system/` (2026-09-08) and confirmed fully absorbed except
  two tech icons and a `templates/cv/` template, which were pulled into the repo.
- `ds_arc_pack/` — the zip form of the same five exports.
