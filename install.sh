#!/bin/zsh
# Install herdr-spaces hook into Claude Code settings.
# Usage: ./install.sh
#        ./install.sh --uninstall
set -euo pipefail
cd "$(dirname "$0")"

SCRIPT="$(pwd)/herdr-spaces-hook.sh"
SETTINGS="$HOME/.claude/settings.json"

chmod +x herdr-spaces-hook.sh
chmod +x herdr-spaces.py
mkdir -p "$HOME/.config/herdr-spaces"

if [[ "${1:-}" == "--uninstall" ]]; then
  if python3 -c "
import json, sys
s = json.load(open('$SETTINGS'))
hooks = s.get('hooks', {}).get('SessionStart', [{}])[0].get('hooks', [])
s['hooks']['SessionStart'][0]['hooks'] = [h for h in hooks if 'herdr-spaces' not in h.get('command', '')]
json.dump(s, open('$SETTINGS', 'w'), indent=2)
print('\n')
"; then
    echo "Removed herdr-spaces hook from $SETTINGS"
  fi
  rm -rf "$HOME/.config/herdr-spaces/locks"
  exit 0
fi

# Check if hook is already present
if grep -q "herdr-spaces" "$SETTINGS" 2>/dev/null; then
  echo "Hook already installed in $SETTINGS"
else
  echo "Add this hook to $SETTINGS under hooks.SessionStart:"
  echo ""
  echo '  {'
  echo '    "type": "command",'
  echo "    \"command\": \"bash '$SCRIPT'\","
  echo '    "timeout": 5'
  echo '  }'
  echo ""
  echo "(or run: python3 herdr-spaces.py  to rename workspaces now)"
fi

echo "Installed. New sessions will auto-name their workspace after 5 minutes."
echo "Run manually: python3 herdr-spaces.py"
