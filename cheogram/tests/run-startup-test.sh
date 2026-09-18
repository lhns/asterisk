#!/bin/bash
# Tier 2: the image actually boots and the patched modules reach Running.
# Usage: run-startup-test.sh <image>
set -euo pipefail

IMAGE=${1:?usage: run-startup-test.sh <image>}
HERE=$(cd "$(dirname "$0")" && pwd)
CT=cheogram-startup-test

cleanup() { docker rm -f "$CT" >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup

docker run -d --name "$CT" -v "$HERE/startup:/etc/asterisk:ro" "$IMAGE" -f >/dev/null

# The console is detached, so stdout stays empty: the log is the file.
for _ in $(seq 1 60); do
	if docker exec "$CT" grep -q 'Asterisk Ready' /var/log/asterisk/messages 2>/dev/null; then
		ready=1
		break
	fi
	sleep 1
done
if [ "${ready:-0}" != 1 ]; then
	echo "FAIL  asterisk never reported ready" >&2
	docker exec "$CT" cat /var/log/asterisk/messages 2>/dev/null | tail -60 >&2 || true
	docker logs "$CT" >&2 || true
	exit 1
fi

fail=0
for m in chan_motif res_xmpp res_srtp res_rtp_asterisk pbx_lua; do
	out=$(docker exec "$CT" asterisk -rx "module show like $m")
	if printf '%s' "$out" | grep -qE "^$m\.so .*Running"; then
		echo "ok    $m Running"
	else
		echo "FAIL  $m is not Running:" >&2
		printf '%s\n' "$out" >&2
		fail=1
	fi
done

# A sorcery config error means a module loaded against a config it could not parse --
# it still says Running, so this has to be read out of the log.
if docker exec "$CT" grep -n 'res_sorcery_config' /var/log/asterisk/messages | grep -qiE 'error|warning'; then
	echo "FAIL  res_sorcery_config errors in the log:" >&2
	docker exec "$CT" grep -n 'res_sorcery_config' /var/log/asterisk/messages >&2
	fail=1
else
	echo "ok    no res_sorcery_config errors"
fi

# The in-image copy of the binary assertions, against the installed modules.
docker exec "$CT" assert-modules chan_motif.so res_xmpp.so res_srtp.so res_rtp_asterisk.so pbx_lua.so

[ "$fail" -eq 0 ] || exit 1
echo "startup test passed"
