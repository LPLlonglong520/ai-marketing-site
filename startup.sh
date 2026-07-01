#!/bin/sh
# Kill any existing server on port 3000
fuser -k 3000/tcp 2>/dev/null || true
sleep 1
# Install express if not already
cd /workspace || cd /app || cd $(dirname $0)
if [ -f package.json ]; then
  npm install --production 2>/dev/null || true
  nohup node server.js > /tmp/server.log 2>&1 &
fi
