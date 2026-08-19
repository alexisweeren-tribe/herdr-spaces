# herdr-spaces

Automatically names Herdr workspaces based on agent context.

Instead of a sidebar full of `~`, each workspace gets a short label (max 4 words) derived from the Claude Code session's task title, with collision detection so no two workspaces share a name.

## How it works

A Claude Code `SessionStart` hook fires a 5-minute background timer. When it triggers, `herdr-spaces.py` reads `herdr api snapshot`, shortens each agent's terminal title to 4 words (stripping noise words like "with", "the", "for"), resolves any collisions by adding distinguishing words back, and renames workspaces via `herdr workspace rename`.

Manually-named workspaces are never touched — it only renames workspaces with the default `~` label or ones it previously set.

## Install

```sh
git clone <repo-url>
cd herdr-spaces
./install.sh
```

This adds a `SessionStart` hook to `~/.claude/settings.json`. New Claude Code sessions will auto-name their workspace 5 minutes after starting.

To rename workspaces right now:

```sh
python3 herdr-spaces.py
```

To uninstall:

```sh
./install.sh --uninstall
```

## Configuration

Constants at the top of `herdr-spaces.py`:

| Constant | Default | Description |
|---|---|---|
| `MAX_WORDS` | `4` | Max words in a workspace label |
| `MAX_LABEL_LEN` | `45` | Hard character limit for labels |
| `RUN_INTERVAL` | `300` | Delay (seconds) before renaming after session start |

State is stored in `~/.config/herdr-spaces/state.json`.

## License

MIT
