#!/bin/sh
# Assert the Jingle patches are present in the compiled modules. Takes module paths;
# accepts either build-tree paths or installed ones. No strings(1) in the runtime image,
# hence tr.
set -e

find_mod() {
	for c in "$1" "/usr/lib/asterisk/modules/$(basename "$1")"; do
		[ -f "$c" ] && { echo "$c"; return 0; }
	done
	echo "missing module: $1" >&2
	return 1
}

has() {
	tr -c '[:print:]' '\n' < "$1" | grep -qF "$2"
}

fail=0
for m in "$@"; do
	p=$(find_mod "$m") || { fail=1; continue; }
	echo "ok    present $p"
	case $(basename "$p") in
	chan_motif.so)
		has "$p" 'urn:xmpp:jingle:apps:dtls:0' \
			|| { echo "FAIL  chan_motif.so lacks the DTLS namespace" >&2; fail=1; }
		has "$p" 'Enabling RTCP MUX for session' \
			|| { echo "FAIL  chan_motif.so lacks the RTCP-MUX path" >&2; fail=1; }
		;;
	res_xmpp.so)
		has "$p" 'urn:xmpp:jingle:apps:dtls:0' \
			|| { echo "FAIL  res_xmpp.so does not advertise DTLS-SRTP" >&2; fail=1; }
		;;
	esac
done

# chan_sip was removed upstream in 22; its return would mean the build is not what we think.
if [ -f /usr/lib/asterisk/modules/chan_sip.so ] || [ -f channels/chan_sip.so ]; then
	echo "FAIL  chan_sip.so is present" >&2
	fail=1
fi

[ "$fail" -eq 0 ] || { echo "module assertions failed" >&2; exit 1; }
echo "module assertions passed"
