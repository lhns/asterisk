#!/usr/bin/env python3
"""Tier 3: assert the session-initiate Asterisk actually emits.

Logs in as an ordinary XMPP client, waits for Asterisk to originate a Jingle call to
this full JID, and inspects the stanza. What is being tested is the patch's output --
a fingerprint with real CDATA -- not that the patch applied.
"""
import asyncio
import re
import sys
import xml.etree.ElementTree as ET

from slixmpp import ClientXMPP
from slixmpp.xmlstream.handler import Callback
from slixmpp.xmlstream.matcher import StanzaPath

JINGLE_NS = "urn:xmpp:jingle:1"
DTLS_NS = "urn:xmpp:jingle:apps:dtls:0"
FINGERPRINT_RE = re.compile(r"^(?:[0-9A-Fa-f]{2}:){31}[0-9A-Fa-f]{2}$")

JID = "user@example.invalid/testclient"
PASSWORD = "client-test-secret"
SERVER = ("xmpp", 5222)


def local(tag):
    return tag.rsplit("}", 1)[-1]


def check(stanza):
    problems = []
    jingle = stanza.find("{%s}jingle" % JINGLE_NS)
    if jingle is None:
        return ["no jingle element in the iq"]
    action = jingle.get("action")
    if action != "session-initiate":
        return ["jingle action is %r, expected session-initiate" % action]

    fps = [e for e in jingle.iter() if e.tag == "{%s}fingerprint" % DTLS_NS]
    if not fps:
        problems.append("no <fingerprint xmlns='%s'> in the session-initiate" % DTLS_NS)
    for fp in fps:
        if fp.get("hash") != "sha-256":
            problems.append("fingerprint hash is %r, expected sha-256" % fp.get("hash"))
        if fp.get("setup") != "actpass":
            problems.append("fingerprint setup is %r, expected actpass" % fp.get("setup"))
        text = (fp.text or "").strip()
        if not FINGERPRINT_RE.match(text):
            problems.append("fingerprint CDATA is not a SHA-256 fingerprint: %r" % text)
        else:
            print("ok    fingerprint %s setup=%s hash=%s"
                  % (text, fp.get("setup"), fp.get("hash")))

    muxes = [e for e in jingle.iter() if local(e.tag) == "rtcp-mux"]
    if muxes:
        print("ok    <rtcp-mux/> present in the description")
    else:
        problems.append("no <rtcp-mux/> in the description")

    return problems


class Probe(ClientXMPP):
    def __init__(self):
        ClientXMPP.__init__(self, JID, PASSWORD)
        # The test server has a self-signed cert and requires no encryption.
        self.enable_starttls = False
        self.enable_direct_tls = False
        self.enable_plaintext = True
        self.plugin["feature_mechanisms"].unencrypted_plain = True
        self.add_event_handler("session_start", self.started)
        self.register_handler(Callback("iq-set", StanzaPath("iq@type=set"), self.on_iq))
        self.status = 1

    def started(self, event):
        self.send_presence()
        print("CLIENT ONLINE", flush=True)

    def on_iq(self, iq):
        xml = ET.fromstring(str(iq))
        print("--- iq from %s ---\n%s" % (iq["from"], str(iq)), flush=True)
        problems = check(xml)
        for p in problems:
            print("FAIL  " + p, file=sys.stderr, flush=True)
        self.status = 1 if problems else 0
        self.disconnect()


if __name__ == "__main__":
    probe = Probe()
    probe.connect(*SERVER)
    try:
        probe.loop.run_until_complete(asyncio.wait_for(probe.disconnected, 90))
    except asyncio.TimeoutError:
        print("FAIL  no session-initiate within 90s", file=sys.stderr)
    sys.exit(probe.status)
