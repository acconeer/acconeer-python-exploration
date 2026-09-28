#!/bin/sh
# A stub rather than a copy, so the hook can't go stale.
HOOKS_DIR=$(git rev-parse --path-format=absolute --git-path hooks)

echo "Installing pre-push hook"
cat > "$HOOKS_DIR/pre-push" <<'EOF'
#!/bin/sh
hook="$(git rev-parse --show-toplevel)/internal_tools/hooks/pre-push"
# A checkout from before the hook was tracked has none.
[ -f "$hook" ] || { echo "No $hook, skipping pre-push checks" >&2; exit 0; }
exec sh "$hook" "$@"
EOF
chmod +x "$HOOKS_DIR/pre-push"
