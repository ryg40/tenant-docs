#!/bin/sh
# Check a tenant-docs site that runs.
#
#   sh deploy/check-site.sh <base URL>
#
# `scripts/deploy.sh` runs this file in a container on the proxy network, with the site container as the base URL.
# With the public origin as the base URL, the same checks go through the reverse proxy.
# The only tool that this file needs is curl.
set -eu

if [ $# -ne 1 ]; then
  echo "usage: check-site.sh <base URL>" >&2
  exit 2
fi

base=${1%/}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
failed=0

# request <path> [curl option ...]: the status goes into $status, the headers and the body go into files.
request() {
  path=$1
  shift
  status=$(curl -sS -o "$work/body" -D "$work/headers" -w '%{http_code}' --max-time 10 "$@" "$base$path") || status=000
}

# header <name>: print the value of one response header.
header() {
  tr -d '\r' < "$work/headers" | grep -i "^$1:" | head -n 1 | sed 's/^[^:]*:[[:space:]]*//'
}

# check <text> <value> <pattern>: the value must match the shell pattern.
check() {
  case $2 in
    $3) echo "ok    $1" ;;
    *)
      echo "FAIL  $1: the value is '$2'"
      failed=1
      ;;
  esac
}

request /
check "home page: status 200" "$status" 200
check "home page: HTML" "$(header content-type)" 'text/html*'
check "home page: the browser asks again before it uses its copy" "$(header cache-control)" no-cache
check "home page: X-Content-Type-Options" "$(header x-content-type-options)" nosniff
check "home page: X-Frame-Options" "$(header x-frame-options)" DENY
check "home page: Referrer-Policy" "$(header referrer-policy)" strict-origin-when-cross-origin
check "home page: Content-Security-Policy" "$(header content-security-policy)" "default-src 'self'*"
asset=$(grep -o '/_astro/[^"]*\.css' "$work/body" | head -n 1)

request / -H 'Accept-Encoding: gzip'
check "home page: gzip compression" "$(header content-encoding)" gzip

request /tenant-pi/install/
check "nested page: status 200" "$status" 200
check "nested page: HTML" "$(header content-type)" 'text/html*'

request /404.html
cp "$work/body" "$work/not-found"
request /no-such-page-for-the-check/
check "missing page: status 404" "$status" 404
check "missing page: X-Content-Type-Options" "$(header x-content-type-options)" nosniff
if cmp -s "$work/body" "$work/not-found"; then
  echo "ok    missing page: the body is the 404 page"
else
  echo "FAIL  missing page: the body is not the 404 page"
  failed=1
fi

if [ -n "$asset" ]; then
  request "$asset"
  check "file under /_astro/: status 200" "$status" 200
  check "file under /_astro/: one-year cache header" "$(header cache-control)" '*max-age=31536000*immutable*'
else
  echo "FAIL  file under /_astro/: the home page names no such file"
  failed=1
fi

request /_astro/no-such-file-for-the-check.js
check "missing file under /_astro/: status 404" "$status" 404
check "missing file under /_astro/: no one-year cache header" "$(header cache-control)" no-cache

exit "$failed"
