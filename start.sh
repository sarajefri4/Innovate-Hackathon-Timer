#!/usr/bin/env bash
# Convenience launcher — double-clickable from Finder.
cd "$(dirname "$0")" || exit 1
exec node server.js "$@"
