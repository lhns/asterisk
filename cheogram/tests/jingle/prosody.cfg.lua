-- Throwaway server for the Jingle test. Encryption is off and the credentials are in the
-- clear on purpose: this exercises Asterisk's signalling, nothing here is reachable.
daemonize = false
pidfile = "/var/lib/prosody/prosody.pid"
admins = { }
modules_enabled = {
	"roster", "saslauth", "tls", "dialback", "disco",
	"ping", "time", "uptime", "version", "posix",
}
allow_registration = false
c2s_require_encryption = false
s2s_require_encryption = false
allow_unencrypted_plain_auth = true
authentication = "internal_plain"
storage = "internal"
component_interface = "0.0.0.0"
log = { info = "*console" }

VirtualHost "example.invalid"

Component "asterisk.example.invalid"
	component_secret = "component-test-secret"
