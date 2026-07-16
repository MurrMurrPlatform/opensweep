#!/usr/bin/env bash
# One-command GitHub App provisioning — infra config, not platform code.
#
#   scripts/github-app-setup.sh dev     # → writes .env, restarts containers
#   scripts/github-app-setup.sh prod    # → writes deployment/terraform/terraform.tfvars
#
# GitHub Apps cannot be created by API alone: the manifest flow requires ONE
# click from a logged-in browser session. This script automates everything
# around that click:
#
#   1. builds the App manifest (permissions, events, webhook + setup URLs
#      pointing at the environment's public origin),
#   2. serves it from a one-shot localhost HTTP server and opens your browser
#      — you click "Create GitHub App" on github.com,
#   3. GitHub redirects back to the local server with a temporary code,
#   4. the script exchanges the code (POST /app-manifests/{code}/conversions —
#      needs no authentication) for the App credentials,
#   5. writes them where the environment owns them:
#        dev  → .env: GITHUB_APP_ID, GITHUB_APP_SLUG, GITHUB_APP_PRIVATE_KEY
#               (base64 PEM), GITHUB_WEBHOOK_SECRET — then recreates the app
#               containers so the backend picks them up.
#        prod → terraform.tfvars: github_app_id, github_app_slug,
#               github_app_private_key_b64, github_webhook_secret — then YOU
#               run `terraform apply` (env-hash change triggers the redeploy).
#
# Idempotent in spirit: re-running creates a NEW App (GitHub App names are
# global — a random suffix keeps them unique) and points the environment at
# it; the old App keeps existing on GitHub until you delete it there.
# Re-keying an EXISTING App needs no script: GitHub → Settings → Developer
# settings → your App → generate a new private key / set a new webhook
# secret, then update .env / terraform.tfvars by hand.
#
# Optional env:
#   APP_NAME    App name (default opensweep-dev-<rand> / opensweep-<rand>)
#   GITHUB_ORG  create the App under this GitHub organization instead of the
#               logged-in user account
#   BASE_URL    public OpenSweep origin for webhook/setup URLs (default:
#               dev = OPENSWEEP_WEBHOOK_PUBLIC_BASE_URL from .env or
#               http://127.0.0.1:8001; prod = https://<opensweep_domain> from
#               terraform.tfvars)
#   PORT        local callback port (default 8961)

set -euo pipefail
cd "$(dirname "$0")/.."
sedi() { if [ "$(uname)" = "Darwin" ]; then sed -i '' "$@"; else sed -i "$@"; fi; }

MODE="${1:-}"
if [ "$MODE" != "dev" ] && [ "$MODE" != "prod" ]; then
  echo "usage: $0 dev|prod" >&2
  exit 1
fi

TFVARS="deployment/terraform/terraform.tfvars"
PORT="${PORT:-8961}"

# ── resolve the public OpenSweep origin ──────────────────────────────────────
if [ -z "${BASE_URL:-}" ]; then
  if [ "$MODE" = "dev" ]; then
    BASE_URL=$(grep '^OPENSWEEP_WEBHOOK_PUBLIC_BASE_URL=' .env 2>/dev/null | cut -d= -f2- || true)
    BASE_URL="${BASE_URL:-http://127.0.0.1:8001}"
  else
    if [ -f "$TFVARS" ]; then
      DOMAIN=$(grep '^opensweep_domain' "$TFVARS" 2>/dev/null | sed 's/.*= *"\(.*\)".*/\1/' || true)
    fi
    BASE_URL="https://${DOMAIN:-app.opensweep.ai}"
  fi
fi
BASE_URL="${BASE_URL%/}"

if [ "$MODE" = "dev" ]; then
  APP_NAME="${APP_NAME:-opensweep-dev-$(openssl rand -hex 2)}"
else
  APP_NAME="${APP_NAME:-opensweep-$(openssl rand -hex 2)}"
fi

echo "environment : $MODE"
echo "app name    : $APP_NAME"
echo "origin      : $BASE_URL  (webhook + install-setup URLs)"
[ -n "${GITHUB_ORG:-}" ] && echo "github org  : $GITHUB_ORG"
if [[ "$BASE_URL" == *"127.0.0.1"* || "$BASE_URL" == *"localhost"* ]]; then
  echo "note        : local origin — the App is created WITHOUT a webhook"
  echo "              (GitHub refuses localhost webhook URLs, and deliveries"
  echo "              couldn't reach dev anyway; PR/push sync uses API reads)."
  echo "              For real webhooks: BASE_URL=<https tunnel URL> $0 $MODE"
fi
echo

# ── create the App: local form → one click on GitHub → code → conversion ─────
CREDS=$(mktemp)
trap 'rm -f "$CREDS"' EXIT
chmod 600 "$CREDS"

APP_NAME="$APP_NAME" BASE_URL="$BASE_URL" GITHUB_ORG="${GITHUB_ORG:-}" \
PORT="$PORT" CREDS_FILE="$CREDS" python3 <<'PYEOF'
import base64, json, os, secrets, sys, urllib.parse, urllib.request, webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

base = os.environ["BASE_URL"]
port = int(os.environ["PORT"])
org = os.environ["GITHUB_ORG"]
state = secrets.token_hex(16)

manifest = {
    "name": os.environ["APP_NAME"],
    "url": base,
    # GitHub sends the browser here with ?code= after the creation click.
    "redirect_url": f"http://localhost:{port}/callback",
    # After someone installs the App, GitHub sends their browser here with
    # ?installation_id=…&state=… — the platform links the installation to
    # the installing user's OpenSweep org. A local URL is fine: this is a
    # browser redirect, and the installing browser IS on this machine in dev.
    "setup_url": f"{base}/api/v1/github/app/setup",
    "setup_on_update": False,
    # public: org users must be able to install the App on THEIR GitHub
    # accounts/orgs — private Apps only install on the owning account.
    "public": True,
    "default_permissions": {
        "contents": "write",
        "pull_requests": "write",
        "checks": "read",
        "statuses": "write",
        "metadata": "read",
    },
}
if urllib.parse.urlparse(base).hostname not in ("localhost", "127.0.0.1"):
    # GitHub REFUSES localhost/127.0.0.1 webhook URLs in manifests — and a
    # local dev stack can't receive deliveries anyway. Local origin → create
    # the App webhook-less (add one later on the App's settings page, or
    # re-create with BASE_URL=<https tunnel URL> for real webhook parity).
    manifest["hook_attributes"] = {"url": f"{base}/api/v1/github/webhook"}
    # installation / installation_repositories are delivered automatically;
    # GitHub rejects manifests that subscribe to them explicitly.
    manifest["default_events"] = ["pull_request", "check_suite", "check_run", "push"]
else:
    print("local origin - creating the App WITHOUT a webhook (GitHub refuses")
    print("localhost webhook URLs; deliveries could not reach dev anyway)")

create_url = (
    f"https://github.com/organizations/{org}/settings/apps/new?state={state}"
    if org else f"https://github.com/settings/apps/new?state={state}"
)
form = f"""<!doctype html><html><body>
<form id="f" action="{create_url}" method="post">
<input type="hidden" name="manifest" value='{json.dumps(manifest).replace("'", "&#39;")}'>
<noscript><button type="submit">Create GitHub App</button></noscript>
</form>
<script>document.getElementById("f").submit()</script>
</body></html>"""

result = {}

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        if url.path == "/callback":
            q = urllib.parse.parse_qs(url.query)
            if q.get("state", [""])[0] != state:
                self.send_response(403); self.end_headers()
                self.wfile.write(b"state mismatch - re-run the script")
                return
            result["code"] = q.get("code", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h3>App created - you can close this tab.</h3>"
                             b"<p>Back to the terminal.</p>")
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(form.encode())

    def log_message(self, *a):  # keep the terminal clean
        pass

server = HTTPServer(("127.0.0.1", port), Handler)
print(f"Waiting for the browser flow on http://localhost:{port} ...")
print("(if no browser opens, open that URL yourself and click Create GitHub App)")
webbrowser.open(f"http://localhost:{port}")
while "code" not in result:
    server.handle_request()
server.server_close()
if not result["code"]:
    sys.exit("GitHub redirected without a code - App creation was cancelled?")

req = urllib.request.Request(
    f"https://api.github.com/app-manifests/{result['code']}/conversions",
    method="POST",
    headers={"Accept": "application/vnd.github+json",
             "X-GitHub-Api-Version": "2022-11-28"},
)
with urllib.request.urlopen(req, timeout=30) as r:
    data = json.load(r)

with open(os.environ["CREDS_FILE"], "w") as fh:
    json.dump({
        "app_id": str(data["id"]),
        "slug": data["slug"],
        "pem_b64": base64.b64encode(data["pem"].encode()).decode(),
        "webhook_secret": data["webhook_secret"],
        "html_url": data.get("html_url", ""),
    }, fh)
print(f"Created App '{data['slug']}' (id {data['id']}).")
PYEOF

field() { python3 -c "import json,sys; print(json.load(open('$CREDS'))['$1'])"; }
APP_ID=$(field app_id)
SLUG=$(field slug)
PEM_B64=$(field pem_b64)
WEBHOOK_SECRET=$(field webhook_secret)
HTML_URL=$(field html_url)

# ── write the credentials where the environment owns them ────────────────────
if [ "$MODE" = "dev" ]; then
  set_env() { # set_env KEY VALUE — replace or append
    if grep -q "^$1=" .env; then
      sedi "s|^$1=.*|$1=$2|" .env
    else
      printf '%s=%s\n' "$1" "$2" >> .env
    fi
  }
  set_env GITHUB_APP_ID "$APP_ID"
  set_env GITHUB_APP_SLUG "$SLUG"
  set_env GITHUB_APP_PRIVATE_KEY "$PEM_B64"
  set_env GITHUB_WEBHOOK_SECRET "$WEBHOOK_SECRET"
  echo "wrote GITHUB_APP_* to .env"
  docker compose up -d opensweep_backend opensweep_worker opensweep_beat >/dev/null 2>&1 \
    && echo "recreated backend/worker/beat with the new env" \
    || echo "WARNING: docker compose up failed — restart the app containers yourself"
else
  if [ -d "deployment/terraform" ]; then
    set_tfvar() { # set_tfvar KEY VALUE — replace or append
      if grep -q "^$1[[:space:]]*=" "$TFVARS"; then
        sedi "s|^$1[[:space:]]*=.*|$1 = \"$2\"|" "$TFVARS"
      else
        printf '%s = "%s"\n' "$1" "$2" >> "$TFVARS"
      fi
    }
    set_tfvar github_app_id "$APP_ID"
    set_tfvar github_app_slug "$SLUG"
    set_tfvar github_app_private_key_b64 "$PEM_B64"
    set_tfvar github_webhook_secret "$WEBHOOK_SECRET"
    echo "wrote github_app_* to $TFVARS"
  else
    echo "terraform overlay not present — add these to your deployment configuration (.env for docker-compose.prod.yml):"
    echo "  github_app_id              = \"$APP_ID\""
    echo "  github_app_slug            = \"$SLUG\""
    echo "  github_app_private_key_b64 = \"$PEM_B64\""
    echo "  github_webhook_secret      = \"$WEBHOOK_SECRET\""
  fi
fi

echo
echo "Done. App: ${HTML_URL:-https://github.com/apps/$SLUG}"
if [ "$MODE" = "prod" ]; then
  if [ -d "deployment/terraform" ]; then
    echo "Next: cd deployment/terraform && terraform apply"
    echo "(env-hash change triggers the redeploy that connects the App)"
  else
    echo "Next: add the values above to your deployment configuration, then redeploy (docker compose -f docker-compose.prod.yml up -d)."
  fi
else
  echo "Install it on your account from Settings → GitHub in the app,"
  echo "or directly: https://github.com/apps/$SLUG/installations/new"
fi
