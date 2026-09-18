FROM debian:trixie-slim
RUN apt-get update && apt-get install -y --no-install-recommends prosody \
 && rm -rf /var/lib/apt/lists/*
COPY prosody.cfg.lua /etc/prosody/prosody.cfg.lua
RUN rm -f /etc/prosody/conf.d/* 2>/dev/null || true
USER prosody
CMD ["sh", "-c", "prosodyctl register user example.invalid client-test-secret && exec prosody"]
