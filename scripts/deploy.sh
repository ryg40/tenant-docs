#!/bin/sh
# Deploy the site: build the image, start the container on the proxy network, check it.
# This script does not change the reverse proxy.
#
#   scripts/deploy.sh            Build the image, start the container, check it.
#   scripts/deploy.sh check      Check the container that runs.
#   scripts/deploy.sh rollback   Start the image of the deploy before, check it.
#   scripts/deploy.sh route      Print the route that the reverse proxy needs.
set -eu

cd "$(dirname "$0")/.."

SERVICE=tenant-docs
PORT=8080

die() {
  echo "error: $*" >&2
  exit 1
}

usage() {
  sed -n '2,8s/^# \{0,1\}//p' "$0"
}

# setting <name>: print the value from the environment, or else from .env. Docker Compose uses the same order.
# This script does not run .env as shell code.
setting() {
  eval "value=\${$1:-}"
  if [ -z "$value" ]; then
    value=$(sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" .env | tail -n 1 |
      sed -e 's/[[:space:]]*$//' -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'\$/\1/")
  fi
  [ -n "$value" ] || die "$1 has no value. Set it in .env."
  printf '%s\n' "$value"
}

image_id() {
  docker image inspect --format '{{.Id}}' "$1" 2>/dev/null || true
}

image_revision() {
  docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$1" 2>/dev/null || echo unknown
}

# The commit of the checkout. It goes into a label of the image.
checkout_revision() {
  if ! revision=$(git rev-parse --short HEAD 2>/dev/null); then
    echo unknown
    return
  fi
  [ -z "$(git status --porcelain 2>/dev/null)" ] || revision="$revision-dirty"
  echo "$revision"
}

# The container publishes no port. Ask it from inside.
wait_ready() {
  tries=0
  until docker compose exec -T "$SERVICE" wget -q -O /dev/null "http://127.0.0.1:$PORT/healthz" 2>/dev/null; do
    tries=$((tries + 1))
    if [ "$tries" -ge 20 ]; then
      docker compose logs --tail 20 "$SERVICE" >&2
      die "the container does not answer on port $PORT."
    fi
    sleep 1
  done
}

# A second container on the proxy network asks the site by its name. The reverse proxy uses the same path.
check() {
  docker run --rm -i --network "$NETWORK" --entrypoint sh "$IMAGE" -s "http://$SERVICE:$PORT" < deploy/check-site.sh
}

report() {
  echo "tenant-docs runs revision $(image_revision "$IMAGE") on port $PORT of the Docker network '$NETWORK'."
}

deploy() {
  before=$(image_id "$IMAGE")
  REVISION=$(checkout_revision)
  export REVISION
  docker compose build
  after=$(image_id "$IMAGE")
  # Keep the image of the deploy before. `rollback` starts it.
  if [ -n "$before" ] && [ "$before" != "$after" ]; then
    docker tag "$before" "$PREVIOUS"
  fi
  docker compose up -d --no-build
  wait_ready
  check || die "a check failed. To start the image of the deploy before, run: scripts/deploy.sh rollback"
  report
  echo "To print the route for the reverse proxy, run: scripts/deploy.sh route"
}

rollback() {
  target=$(image_id "$PREVIOUS")
  [ -n "$target" ] || die "the image '$PREVIOUS' is absent. There is no deploy before this one."
  current=$(image_id "$IMAGE")
  [ "$target" != "$current" ] || die "the image '$PREVIOUS' is the image that runs."
  # Exchange the two tags. A second rollback returns to the newer image.
  docker tag "$target" "$IMAGE"
  [ -z "$current" ] || docker tag "$current" "$PREVIOUS"
  docker compose up -d --no-build
  wait_ready
  check || die "a check failed after the rollback."
  report
}

route() {
  host=${SITE_URL#*://}
  host=${host%%/*}
  grep -v '^#' deploy/caddy-route.example | sed "s/docs\.example/$host/"
}

action=${1:-deploy}
case $action in
  deploy | check | rollback | route) ;;
  -h | --help | help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

[ -f .env ] || die ".env is absent. Copy .env.example to .env and set the values."
SITE_URL=$(setting SITE_URL)

if [ "$action" = route ]; then
  route
  exit 0
fi

command -v docker >/dev/null 2>&1 || die "docker is not installed."
NETWORK=$(setting DOCKER_PROXY_NETWORK)
docker network inspect "$NETWORK" >/dev/null 2>&1 ||
  die "the Docker network '$NETWORK' does not exist. Set DOCKER_PROXY_NETWORK in .env."
IMAGE=$(docker compose config --images | head -n 1)
PREVIOUS=${IMAGE%:*}:previous

case $action in
  deploy) deploy ;;
  rollback) rollback ;;
  check)
    check
    report
    ;;
esac
