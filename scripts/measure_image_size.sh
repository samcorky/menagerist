#!/usr/bin/env bash
# Print the size of a local Docker image as JSON: {"compressed", "uncompressed", "commit"}.
#
# Compressed is the saved image gzipped, an estimate of the pull size that is measured
# the same way for the pull request's image and the published `edge` one, so the two
# compare. Commit is the image's revision label, or empty when it has none.
set -euo pipefail

image="${1:?usage: measure_image_size.sh IMAGE}"

uncompressed="$(docker image inspect "${image}" --format '{{.Size}}')"
compressed="$(docker save "${image}" | gzip -n | wc -c)"
commit="$(docker image inspect "${image}" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"

jq -n --argjson compressed "${compressed}" --argjson uncompressed "${uncompressed}" \
  --arg commit "${commit}" \
  '{compressed: $compressed, uncompressed: $uncompressed, commit: $commit}'
