# Operator Copy-Paste Command Snippets

- **Max 58 characters per physical line:** Every physical line inside a `bash` / `sh` snippet handed to the operator MUST be `<= 58` characters; split longer commands across lines with trailing ` \` (or separate lines) so narrow split terminal panes (`~65–80` cols) never hard-wrap mid-flag or mid-branch-name on mouse selection.
- **Single-quote every `!` path segment (`histexpand` safety):** Interactive Bash expands `!` inside double quotes (`".../!self/..."` -> `bash: !self: event not found`) and keeps literal backslashes inside `"\!self"`. Always write `cd ~/Projects/'!self'/w0m` or `'/home/aleksei/Projects/!self/w0m'`.
- **Pure runnable commands inside fences:** Never include `$` prompts, `#` comments, or prose inside copy-pasteable `bash` blocks.
- **Short `just` aliases first:** Prefer 2–3 word `just` recipes (`just pr-open triple-tap`, `just pr-dry triple-tap`, `just orca-apply`, `just moksha-apply`) over verbose `ENV=1` + multi-flag CLI incantations.
