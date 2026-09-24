#!/usr/bin/env python3
"""Tier 3: assert the session-initiate Asterisk actually emits.

Logs in as an ordinary XMPP client, waits for Asterisk to originate a Jingle call to
this full JID, and inspects the stanza. What is being tested is the patch's output --
a fingerprint with real CDATA -- not that the patch applied.

With the argument `call` it instead places an inbound call: session-initiate with a
DTLS fingerprint, ICE candidate and <rtcp-mux/>, waits for Asterisk's session-accept,
then terminates. That drives the description/transport parsing and the hangup path.

DTLS=no (the runner's nodtls mode) expects Asterisk to send no fingerprint at all.
"""
import asyncio
import os
import re
import sys
import xml.etree.ElementTree as ET

from slixmpp import ClientXMPP
from slixmpp.xmlstream.handler import Callback
from slixmpp.xmlstream.matcher import StanzaPath

JINGLE_NS = "urn:xmpp:jingle:1"
DTLS_NS = "urn:xmpp:jingle:apps:dtls:0"
FINGERPRINT_RE = re.compile(r"^(?:[0-9A-Fa-f]{2}:){31}[0-9A-Fa-f]{2}$")
DTLS = os.environ.get("DTLS", "yes") == "yes"

JID = "user@example.invalid/testclient"
PASSWORD = "client-test-secret"
SERVER = ("xmpp", 5222)


def local(tag):
    return tag.rsplit("}", 1)[-1]


def check_fingerprints(jingle, action, setup):
    problems = []
    fps = [e for e in jingle.iter() if e.tag == "{%s}fingerprint" % DTLS_NS]
    if not DTLS:
        if fps:
            problems.append("fingerprint in the %s although dtlsenable=no" % action)
        else:
            print("ok    no fingerprint in the %s, as dtlsenable=no" % action)
        return problems
    if not fps:
        problems.append("no <fingerprint xmlns='%s'> in the %s" % (DTLS_NS, action))
    for fp in fps:
        if fp.get("hash") != "sha-256":
            problems.append("fingerprint hash is %r, expected sha-256" % fp.get("hash"))
        if fp.get("setup") != setup:
            problems.append("fingerprint setup is %r, expected %s" % (fp.get("setup"), setup))
        text = (fp.text or "").strip()
        if not FINGERPRINT_RE.match(text):
            problems.append("fingerprint CDATA is not a SHA-256 fingerprint: %r" % text)
        else:
            print("ok    fingerprint %s setup=%s hash=%s"
                  % (text, fp.get("setup"), fp.get("hash")))
    return problems


def check_rtcp_mux(jingle, action):
    if [e for e in jingle.iter() if local(e.tag) == "rtcp-mux"]:
        print("ok    <rtcp-mux/> present in the %s" % action)
        return []
    return ["no <rtcp-mux/> in the %s" % action]


def check(stanza):
    jingle = stanza.find("{%s}jingle" % JINGLE_NS)
    if jingle is None:
        return ["no jingle element in the iq"]
    action = jingle.get("action")
    if action != "session-initiate":
        return ["jingle action is %r, expected session-initiate" % action]

    return check_fingerprints(jingle, action, "actpass") + check_rtcp_mux(jingle, action)


def check_accept(jingle):
    """The call offered rtcp-mux, so the answer carries it and no RTCP candidates."""
    action = "session-accept"
    problems = check_fingerprints(jingle, action, "active") + check_rtcp_mux(jingle, action)
    rtcp = [c for c in jingle.iter() if local(c.tag) == "candidate" and c.get("component") != "1"]
    if rtcp:
        problems.append("%d RTCP candidate(s) in the %s despite rtcp-mux" % (len(rtcp), action))
    else:
        print("ok    only component 1 candidates in the %s" % action)
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


CALLEE = "echo@asterisk.example.invalid"
CALL_SID = "regression-call-1"
REMOTE_FINGERPRINT = ":".join(["5A"] * 32)
SESSION_INITIATE = """
<jingle xmlns='urn:xmpp:jingle:1' action='session-initiate' sid='{sid}' initiator='{me}'>
  <content creator='initiator' name='audio' senders='both'>
    <description xmlns='urn:xmpp:jingle:apps:rtp:1' media='audio'>
      <payload-type id='0' name='PCMU' clockrate='8000'/>
      <payload-type id='101' name='telephone-event' clockrate='8000'/>
      <rtcp-mux/>
    </description>
    <transport xmlns='urn:xmpp:jingle:transports:ice-udp:1' ufrag='rgUf' pwd='regressionIcePassword01'>
      <fingerprint xmlns='urn:xmpp:jingle:apps:dtls:0' hash='sha-256' setup='actpass'>{fp}</fingerprint>
      <candidate component='1' foundation='1' generation='0' id='c1' ip='192.0.2.10' port='9'
                 priority='2130706431' protocol='udp' type='host' network='0'/>
    </transport>
  </content>
</jingle>"""
SESSION_TERMINATE = """
<jingle xmlns='urn:xmpp:jingle:1' action='session-terminate' sid='{sid}'>
  <reason><success/></reason>
</jingle>"""


class Caller(ClientXMPP):
    def __init__(self):
        ClientXMPP.__init__(self, "user@example.invalid/caller", PASSWORD)
        self.enable_starttls = False
        self.enable_direct_tls = False
        self.enable_plaintext = True
        self.plugin["feature_mechanisms"].unencrypted_plain = True
        self.add_event_handler("session_start", self.started)
        self.register_handler(Callback("iq-set", StanzaPath("iq@type=set"), self.on_iq))
        self.status = 1
        self.problems = []

    async def jingle(self, template):
        iq = self.make_iq_set(ito=CALLEE)
        iq.xml.append(ET.fromstring(template.format(
            sid=CALL_SID, me=self.boundjid.full, fp=REMOTE_FINGERPRINT)))
        return await iq.send(timeout=20)

    async def started(self, event):
        self.send_presence()
        print("CLIENT ONLINE", flush=True)
        try:
            await self.jingle(SESSION_INITIATE)
            print("ok    session-initiate acknowledged", flush=True)
        except Exception as e:
            print("FAIL  session-initiate not acknowledged: %r" % e, file=sys.stderr, flush=True)
            self.disconnect()

    def on_iq(self, iq):
        print("--- iq from %s ---\n%s" % (iq["from"], str(iq)), flush=True)
        iq.reply().send()
        jingle = ET.fromstring(str(iq)).find("{%s}jingle" % JINGLE_NS)
        if jingle is not None and jingle.get("action") == "session-accept":
            print("ok    session-accept received", flush=True)
            self.problems = check_accept(jingle)
            for p in self.problems:
                print("FAIL  " + p, file=sys.stderr, flush=True)
            asyncio.ensure_future(self.hang_up())

    async def hang_up(self):
        try:
            await self.jingle(SESSION_TERMINATE)
            print("ok    session-terminate acknowledged", flush=True)
            self.status = 1 if self.problems else 0
        except Exception as e:
            print("FAIL  session-terminate not acknowledged: %r" % e, file=sys.stderr, flush=True)
        # Let Asterisk run the hangup and RTP instance teardown before the runner inspects it.
        await asyncio.sleep(3)
        self.disconnect()


if __name__ == "__main__":
    probe = Caller() if sys.argv[1:] == ["call"] else Probe()
    probe.connect(*SERVER)
    try:
        probe.loop.run_until_complete(asyncio.wait_for(probe.disconnected, 90))
    except asyncio.TimeoutError:
        print("FAIL  no Jingle exchange completed within 90s", file=sys.stderr)
    sys.exit(probe.status)
