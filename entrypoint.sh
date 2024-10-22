#!/bin/sh

cp -r /app/. /mount/
rm /mount/entrypoint.sh

exec python /mount/main.py "$@"