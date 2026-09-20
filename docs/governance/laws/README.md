# Laws source record

Authoritative upstream: https://github.com/promptctl/laws

Pinned revision: `4fb6c66df5d084a215c798c84e3cbc6090f695f9`.
Retrieved 2026-09-20 after the user identified this repository as the Laws source.

The following files preserve upstream content verbatim under its MIT license:

| Local file | Upstream path |
| --- | --- |
| `code/SKILL.md` | `plugins/laws/skills/code/SKILL.md` |
| `prompt/SKILL.md` | `plugins/laws/skills/prompt/SKILL.md` |
| `prompt/references/craft.md` | `plugins/laws/skills/prompt/references/craft.md` |
| `application-spec/SKILL.md`, `application-spec/references/craft.md` | Same paths under `plugins/laws/skills/` |
| `backlog/SKILL.md`, `backlog/references/craft.md` | Same paths under `plugins/laws/skills/` |
| `chat/SKILL.md` | `plugins/laws/skills/chat/SKILL.md` |
| `prose/SKILL.md`, `prose/references/craft.md` | Same paths under `plugins/laws/skills/` |
| `ticket/DISABLED_SKILL.md`, `ticket/references/craft.md` | Same paths under `plugins/laws/skills/`; disabled entrypoint preserved |
| `LICENSE` | `LICENSE` |

This is repository-local guidance loaded through `AGENTS.md`. It does not install
the upstream Claude launcher, hooks, or a machine-wide Codex plugin. Existing
worktrees on older commits need explicit pointers to these files until the
governance change is integrated into their branch.

All six active skill directories are included. The ticket guidance is also
preserved with its upstream disabled filename; the user's full-Laws instruction
requests its principles for ticket work without claiming upstream enabled it.

Update by reviewing a new upstream revision, replacing the corresponding full
files, checking their exact content against upstream, and updating this revision.
Do not independently edit or summarize the vendored guidance. Keep project-specific
instructions in `AGENTS.md` and team handoffs. These sources remain subordinate to
system/developer instructions and explicit user direction.
