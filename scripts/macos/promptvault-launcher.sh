#!/bin/zsh

set -u
set -o pipefail

SCRIPT_DIR="${0:A:h}"
PROJECT_ROOT="${SCRIPT_DIR:h:h}"
LOG_DIR="${HOME}/Library/Logs/PromptVault"
LOG_FILE="${LOG_DIR}/launcher.log"
COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.local.yml)

umask 077
mkdir -p "${LOG_DIR}"
: > "${LOG_FILE}"

log() {
  print -r -- "[$(/bin/date '+%Y-%m-%d %H:%M:%S')] $1" >> "${LOG_FILE}"
}

fail() {
  local message="$1"
  log "ERROR: ${message}"
  print -u2 -r -- "${message}"
  print -u2 -r -- "See ${LOG_FILE} for details."
  /usr/bin/tail -n 12 "${LOG_FILE}" >&2
  exit 1
}

find_docker() {
  local candidate
  for candidate in \
    /usr/local/bin/docker \
    /opt/homebrew/bin/docker \
    "${HOME}/.docker/bin/docker" \
    /Applications/Docker.app/Contents/Resources/bin/docker
  do
    if [[ -x "${candidate}" ]]; then
      print -r -- "${candidate}"
      return 0
    fi
  done
  return 1
}

wait_for_url() {
  local label="$1"
  local url="$2"
  local attempts="$3"
  local count=1
  while (( count <= attempts )); do
    if /usr/bin/curl --silent --show-error --fail --max-time 3 "${url}" >/dev/null 2>&1; then
      log "${label} is ready at ${url}"
      return 0
    fi
    /bin/sleep 2
    (( count += 1 ))
  done
  return 1
}

log "PromptVault launcher started."

[[ -f "${PROJECT_ROOT}/docker-compose.yml" ]] || fail "PromptVault project files were not found at ${PROJECT_ROOT}. Rebuild the app after moving the repository."
[[ -f "${PROJECT_ROOT}/docker-compose.local.yml" ]] || fail "docker-compose.local.yml is missing from ${PROJECT_ROOT}."
[[ -f "${PROJECT_ROOT}/.env" ]] || fail "The root .env file is missing. Create it from .env.example before starting PromptVault."

if ! /usr/bin/open -Ra Docker; then
  fail "Docker Desktop is not installed. Install Docker Desktop, then try again."
fi

log "Opening Docker Desktop."
/usr/bin/open -gja Docker >> "${LOG_FILE}" 2>&1 || fail "Docker Desktop could not be opened."

DOCKER_BIN="$(find_docker)" || fail "The Docker command-line tool was not found. Reinstall or repair Docker Desktop."
log "Using Docker CLI at ${DOCKER_BIN}."

docker_ready=false
for _ in {1..60}; do
  if "${DOCKER_BIN}" info >/dev/null 2>&1; then
    docker_ready=true
    break
  fi
  /bin/sleep 2
done
[[ "${docker_ready}" == true ]] || fail "Docker Desktop did not become ready within two minutes. Open Docker Desktop and check its status."
log "Docker Desktop is ready."

postgres_ready=false
for _ in {1..10}; do
  if /usr/bin/nc -z 127.0.0.1 5432 >/dev/null 2>&1; then
    postgres_ready=true
    break
  fi
  /bin/sleep 1
done
[[ "${postgres_ready}" == true ]] || fail "PostgreSQL is not listening on localhost:5432. Start the local PostgreSQL server used by pgAdmin, then try again."
log "PostgreSQL is accepting TCP connections on localhost:5432."

cd "${PROJECT_ROOT}" || fail "Could not open the PromptVault project directory."
log "Building and starting the PromptVault Compose services."
if ! "${DOCKER_BIN}" compose "${COMPOSE_FILES[@]}" up -d --build --wait >> "${LOG_FILE}" 2>&1; then
  "${DOCKER_BIN}" compose "${COMPOSE_FILES[@]}" ps >> "${LOG_FILE}" 2>&1 || true
  "${DOCKER_BIN}" compose "${COMPOSE_FILES[@]}" logs --tail=80 api migrate web >> "${LOG_FILE}" 2>&1 || true
  fail "PromptVault could not start. Check that the .env database settings match PostgreSQL on localhost:5432."
fi

wait_for_url "PromptVault API" "http://localhost:8000/ready" 45 || fail "The API did not become ready at http://localhost:8000/ready."
wait_for_url "PromptVault frontend" "http://localhost:5173" 30 || fail "The frontend did not become ready at http://localhost:5173."

log "PromptVault startup completed successfully."
print -r -- "PromptVault is ready."
