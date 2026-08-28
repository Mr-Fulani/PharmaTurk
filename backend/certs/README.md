# Trusted scraper proxy certificates

`brightdata_root_ca_44445.crt` is the Bright Data Root CA for native proxy port
`44445`, downloaded from the official archive:

- source: `https://brightdata.com/static/brightdata_proxy_ca.zip`
- archive SHA-256 on 2026-08-28:
  `af8092570205eec5986f374f2e9b1ea9697f597e19ef6d1be11034f94cb903bc`
- certificate SHA-256 fingerprint:
  `DB:85:48:F8:A5:B1:16:65:36:92:0C:CD:04:73:84:0F:7F:DB:AF:16:5D:ED:F9:07:B7:B5:23:61:AB:C8:7B:60`
- validity: 2026-07-23 through 2046-07-18 UTC

The file is copied into the immutable backend image at
`/app/certs/brightdata_root_ca_44445.crt`. Configure
`SCRAPER_PROXY_CA_BUNDLE` with that path. Do not replace it with an intercepted
leaf certificate and do not disable TLS verification.
