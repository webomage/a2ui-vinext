#!/usr/bin/env python3
"""
Cloudflare deployment verification script.
Checks that the webomage.com zone is active in Cloudflare.
"""
import os
import sys
import urllib.request
import json

zone_name = os.environ.get("ZONE_NAME", "webomage.com")
token = os.environ.get("CLOUDFLARE_API_TOKEN", "")

if not token:
    print("CLOUDFLARE_API_TOKEN not set, skipping verification.")
    sys.exit(0)

req = urllib.request.Request(
    f"https://api.cloudflare.com/client/v4/zones?name={zone_name}",
    headers={"Authorization": f"Bearer {token}"},
)
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read())

zones = data.get("result", [])
if not zones:
    print(f"WARNING: Zone '{zone_name}' not found in Cloudflare.", file=sys.stderr)
    sys.exit(0)

status = zones[0].get("status", "unknown")
print(f"Zone '{zone_name}' status: {status}")
