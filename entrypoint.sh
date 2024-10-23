#!/bin/sh

cp -r /app/. /mount/
rm /mount/entrypoint.sh
rm -r /mount/.github

exec python /mount/main.py "$@"