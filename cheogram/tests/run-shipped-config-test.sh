#!/bin/bash
# Boots the image on its OWN /etc/asterisk plus the files a deployment supplies (startup/'s
# pjsip, rtp, xmpp and motif), so a shipped file that stops parsing fails here, not in a
# cluster.
# Usage: run-shipped-config-test.sh <image>
set -euo pipefail

IMAGE=${1:?usage: run-shipped-config-test.sh <image>}
HERE=$(cd "$(dirname "$0")" && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

docker run --rm --entrypoint tar "$IMAGE" -C /etc/asterisk -cf - . | tar -C "$TMP" -xf -
for f in asterisk logger modules pjproject; do
	[ -s "$TMP/$f.conf" ] || { echo "FAIL  the image ships no $f.conf" >&2; exit 1; }
done
# The deployment-supplied files only: never overwrite what the image ships.
for f in pjsip rtp xmpp motif; do
	cp "$HERE/startup/$f.conf" "$TMP/$f.conf"
done
chmod -R a+rX "$TMP"
exec "$HERE/run-startup-test.sh" "$IMAGE" "$TMP"
