#!/bin/bash
cp -r /app/* /data
exec "$@"
