#!/bin/bash
# Tier 3: prosody + this Asterisk + a scripted XMPP client. Asserts the session-initiate
# Asterisk emits actually carries a DTLS fingerprint and rtcp-mux -- i.e. that the patched
# code runs, not that its strings are in the binary.
# Usage: run-jingle-test.sh <image>
set -euo pipefail

IMAGE=${1:?usage: run-jingle-test.sh <image>}
HERE=$(cd "$(dirname "$0")" && pwd)/jingle
NET=cheogram-jingle-net

cleanup() {
	docker rm -f jingle-client jingle-ast xmpp >/dev/null 2>&1 || true
	docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup

docker build -q -t cheogram-test-prosody -f "$HERE/prosody.Dockerfile" "$HERE" >/dev/null
docker build -q -t cheogram-test-client -f "$HERE/client.Dockerfile" "$HERE" >/dev/null
docker network create "$NET" >/dev/null

docker run -d --name xmpp --network "$NET" cheogram-test-prosody >/dev/null
for _ in $(seq 1 40); do
	docker logs xmpp 2>&1 | grep -q 'Activated service' && break
	sleep 1
done

docker run -d --name jingle-ast --network "$NET" \
	-v "$HERE/asterisk:/etc/asterisk:ro" "$IMAGE" -f >/dev/null

ready=0
for _ in $(seq 1 60); do
	if docker exec jingle-ast grep -q 'Asterisk Ready' /var/log/asterisk/messages 2>/dev/null; then
		ready=1
		break
	fi
	sleep 1
done
[ "$ready" = 1 ] || { echo "FAIL  asterisk never became ready" >&2; docker exec jingle-ast tail -40 /var/log/asterisk/messages >&2 || true; exit 1; }

# The component link is what carries the session-initiate; without it the test would time
# out with no useful diagnosis.
linked=0
for _ in $(seq 1 30); do
	if docker exec jingle-ast asterisk -rx 'xmpp show connections' | grep -qi 'asterisk'; then
		linked=1
		break
	fi
	sleep 1
done
[ "$linked" = 1 ] || echo "warn  xmpp show connections did not list the component" >&2

docker run -d --name jingle-client --network "$NET" cheogram-test-client >/dev/null
online=0
for _ in $(seq 1 60); do
	docker logs jingle-client 2>&1 | grep -q 'CLIENT ONLINE' && { online=1; break; }
	sleep 1
done
if [ "$online" != 1 ]; then
	echo "FAIL  the test client never came online" >&2
	docker logs jingle-client >&2 || true
	docker logs xmpp >&2 || true
	exit 1
fi

docker exec jingle-ast asterisk -rx \
	'channel originate Motif/jingle-endpoint/user@example.invalid/testclient application Echo' || true

rc=0
timeout 180 docker wait jingle-client >/dev/null 2>&1 || true
rc=$(docker inspect -f '{{.State.ExitCode}}' jingle-client)
docker logs jingle-client 2>&1

if [ "$rc" != 0 ]; then
	echo "FAIL  jingle stanza assertions failed (client exit $rc)" >&2
	echo "--- asterisk log ---" >&2
	docker exec jingle-ast tail -60 /var/log/asterisk/messages >&2 || true
	echo "--- prosody log ---" >&2
	docker logs xmpp 2>&1 | tail -40 >&2 || true
	exit 1
fi
echo "jingle stanza test passed"
