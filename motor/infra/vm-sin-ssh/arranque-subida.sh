#!/bin/bash
# Script de arranque v4 de insomnio-vm: sube /opt/salidas (productos chicos, sin .h5) a la URL de subida de un solo uso del metadato upload-url.
[ -f /opt/subida-hecha-v4 ] && { echo "INSOMNIO: v4 ya subió"; exit 0; }
log() { echo "INSOMNIO: $*"; }
U=$(curl -sf -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/upload-url)
[ -z "$U" ] && { log "v4 sin upload-url"; exit 0; }
cd /opt && tar czf /opt/salidas-v3.tgz salidas && log "v4 tar $(du -h /opt/salidas-v3.tgz | cut -f1); $(du -sh salidas/* | tr '\n' ' ')"
code=$(curl -sS -o /dev/null -w "%{http_code}" -X PUT -H "Content-Type: application/gzip" --upload-file /opt/salidas-v3.tgz "$U")
log "v4 subida http=$code"
[ "$code" = 200 ] || [ "$code" = 201 ] && touch /opt/subida-hecha-v4
log "v4 fin"
