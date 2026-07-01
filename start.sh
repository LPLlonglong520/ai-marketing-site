#!/bin/sh
pkill -f "python.*http.server" 2>/dev/null || true
pkill -f "node.*server" 2>/dev/null || true
cd /workspace && node server.js
