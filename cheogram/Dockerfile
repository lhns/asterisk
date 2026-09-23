# Asterisk with the Cheogram Jingle patches (DTLS-SRTP/XEP-0320, RTCP-MUX, ICE).
# Context is the repository root: the source built here is this checkout, not a release tarball.
FROM debian:trixie-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential wget ca-certificates patch pkg-config python3 file xmlstarlet \
      bison flex libedit-dev libjansson-dev libxml2-dev uuid-dev libsqlite3-dev \
      libssl-dev libsrtp2-dev libiksemel-dev libcurl4-openssl-dev libspeex-dev \
      libspeexdsp-dev libogg-dev libvorbis-dev libresample1-dev libncurses-dev \
      liblua5.1-0-dev libunbound-dev \
  && rm -rf /var/lib/apt/lists/*
WORKDIR /b/asterisk
COPY . /b/asterisk
# make_version would otherwise stamp a GIT-... version derived from the checkout depth.
RUN cp cheogram/VERSION .version && rm -rf .git
RUN ./configure --with-pjproject-bundled --with-jansson-bundled --with-lua \
      >/tmp/conf.log 2>&1 || (tail -60 /tmp/conf.log; false)
RUN make menuselect.makeopts >/dev/null \
 && menuselect/menuselect \
      --enable chan_motif --enable res_xmpp --enable res_rtp_asterisk --enable res_srtp \
      --enable pbx_lua --enable app_voicemail --enable app_mixmonitor --enable func_curl \
      --enable CORE-SOUNDS-EN-ULAW --enable CORE-SOUNDS-EN-GSM \
      --disable BUILD_NATIVE \
      menuselect.makeopts
# Serially, and before the parallel build: the bundled pjproject build races against
# itself under -j and fails with its own output sent to /dev/null.
RUN make third-party >/tmp/tp.log 2>&1 || (tail -60 /tmp/tp.log; false)
# CI sets -ftrivial-auto-var-init=pattern on a test-only build, so an uninitialized stack
# variable is a deterministic crash rather than whatever the stack happened to hold.
ARG ASTCFLAGS=
# First diagnostics, not make's trailing summary: that names victim modules and hides
# the cause -- a full disk reads as a pjsip compile failure.
RUN make -j"$(nproc)" ASTCFLAGS="$ASTCFLAGS" >/tmp/make.log 2>&1 \
 || (grep -nE 'fatal error|error:|No space left|cannot find' /tmp/make.log | head -30; \
     echo '--- tail ---'; tail -60 /tmp/make.log; false)
# Assert against the built objects, not the source: a hunk can apply and still be
# compiled out. This is the check a rebase onto a new tag has to keep passing.
RUN sh cheogram/tests/assert-modules.sh channels/chan_motif.so res/res_xmpp.so res/res_rtp_asterisk.so pbx/pbx_lua.so res/res_srtp.so
# /var/run is a symlink on Debian, so shipping a real one breaks the runtime COPY.
# /etc/asterisk goes because the deployment mounts a config over it.
RUN make install DESTDIR=/out >/dev/null && make samples DESTDIR=/out >/dev/null \
 && rm -rf /out/etc/asterisk /out/var/run

FROM debian:trixie-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      libedit2 libjansson4 libxml2 libuuid1 libsqlite3-0 libssl3 libsrtp2-1 libiksemel3 \
      libcurl4 libspeex1 libspeexdsp1 libogg0 libvorbis0a libvorbisenc2 libresample1 \
      libncursesw6 liblua5.1-0 libunbound8 ca-certificates \
  && rm -rf /var/lib/apt/lists/* \
  && groupadd -r asterisk && useradd -r -g asterisk -d /var/lib/asterisk asterisk
COPY --from=build /out/ /
COPY cheogram/tests/assert-modules.sh /usr/local/bin/assert-modules
RUN ldconfig \
 && mkdir -p /etc/asterisk /var/log/asterisk /var/spool/asterisk /var/run/asterisk \
 && chown -R asterisk:asterisk /var/log/asterisk /var/spool/asterisk /var/run/asterisk \
                               /var/lib/asterisk
USER asterisk
ENTRYPOINT ["/usr/sbin/asterisk"]
CMD ["-f"]
