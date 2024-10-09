#!/bin/sh
GIT_TOP_DIR=$(git rev-parse --show-toplevel)

echo "Installing pre-push hook"
cp $GIT_TOP_DIR/utils/hooks/pre-push $GIT_TOP_DIR/.git/hooks/
chmod +x $GIT_TOP_DIR/.git/hooks/pre-push
