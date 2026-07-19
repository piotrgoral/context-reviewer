# context-reviewer

CLI tool to review **context used by AI coding agents** — files and line ranges gathered through Read, search, and edit tool calls during an agent session.

Currently supports **Cursor IDE** via `--cursor`. Additional agents will be added as separate flags.

## Install

```bash
pip install -e .
```

## Quick start

List projects and dialogs:

```bash
context-reviewer --cursor --list-projects
context-reviewer --cursor --list-dialogs myproject
context-reviewer --cursor --list-all
```

Show the **context tree** for a dialog (default output when `-p`/`-d` are given):

```bash
context-reviewer --cursor -p myproject -d "my chat"
```

## Context tree modifiers

| Flag | Description |
|------|-------------|
| `--files-only` | List file names only (no line ranges) |
| `--context-tree-depth N` | Limit directory depth below root |
| `--last-turn` | Only files touched after the last user message |
| `--color` / `--no-color` | Force or disable ANSI colors |

Examples:

```bash
context-reviewer --cursor -p myproject -d "my chat" --files-only
context-reviewer --cursor -p myproject -d "my chat" --last-turn --context-tree-depth 2
```

## List filters

When using `--list-all`:

- `--from` / `--before` — date filters
- `-p` — filter by project name (partial match)
- `--limit`, `--sort`, `--desc`, `--updated`

## Environment

Override the Cursor user data directory:

```bash
export CONTEXT_REVIEWER_CURSOR_USER_DIR=~/path/to/Cursor/User
```

The legacy variable `CURSOR_CHRONICLE_CURSOR_USER_DIR` is also accepted.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Attribution

This project is a **combined work** under AGPL-3.0:

- **From [cursor-chronicle](https://github.com/cursor-chronicle/cursor-chronicle) (main):** Cursor DB access in `context_reviewer/agents/cursor/` (messages, utils, viewer) — see [NOTICE](NOTICE).
- **Original to context-reviewer:** domain models in `context/`, terminal rendering in `render/`, Cursor context extraction in `agents/cursor/` (tool_results, extractor, context), and CLI in `cli.py`.

## License

GNU Affero General Public License v3 — see [LICENSE](LICENSE).
