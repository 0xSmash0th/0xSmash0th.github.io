#!/usr/bin/env bash
# Fill in the pseudonym across the repo and scope the git identity to it.
# Safe to re-run; it rewrites the same placeholders each time.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

die() { printf '%s\n' "$*" >&2; exit 1; }

usage() {
  cat <<USAGE
usage: bin/set-identity.sh <handle> <domain> <contact-email> [git-email]

  handle         the name you publish under, e.g. lowbitrot
  domain         where the site lives, no scheme. For GitHub Pages:
                   handle.github.io          user site, repo <handle>.github.io
                   handle.github.io/blog     project site, repo named "blog"
                   example.net               custom domain (writes static/CNAME)
  contact-email  the address printed on the site and in security.txt
  git-email      the address on your commits. Defaults to contact-email.
                 If the repo lives on GitHub, prefer the noreply form:
                 12345678+handle@users.noreply.github.com

Everything this writes is intended to be public. Do not pass an address
here that resolves to your legal identity.
USAGE
}

[ $# -ge 3 ] || { usage; exit 2; }
HANDLE=$1 DOMAIN=$2 CONTACT=$3 GITMAIL=${4:-$3}

case "$DOMAIN" in
  *://*) die "domain should have no scheme: use example.net, not https://example.net" ;;
  *@*)   die "that looks like an email address, not a domain" ;;
esac
case "$CONTACT" in *@*) ;; *) die "contact-email does not look like an address" ;; esac

# security.txt must carry an expiry; RFC 9116 says under a year. Use 6 months.
EXPIRES=$(date -u -d '+6 months' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
       || date -u -v+6m +%Y-%m-%dT%H:%M:%SZ)

subst() {
  [ -f "$1" ] || return 0
  sed -i.bak \
    -e "s|__HANDLE__|$HANDLE|g" \
    -e "s|__DOMAIN__|$DOMAIN|g" \
    -e "s|__CONTACT_EMAIL__|$CONTACT|g" \
    -e "s|__SECURITY_TXT_EXPIRES__|$EXPIRES|g" \
    "$1" && rm -f "$1.bak"
}

for f in hugo.toml static/robots.txt deploy/_headers.cloudflare \
         static/.well-known/security.txt README.md CHECKLIST.md deploy/README.md; do
  subst "$f"
done

# GitHub Pages serves a custom domain only if a CNAME file is in the published
# output. A *.github.io address must NOT have one, and a project site (a path
# after the host) cannot use one at all.
HOST=${DOMAIN%%/*}
PATHPART=${DOMAIN#"$HOST"}
if [ "$HOST" != "$DOMAIN" ] || case "$HOST" in *.github.io) true ;; *) false ;; esac; then
  rm -f static/CNAME
  [ -n "$PATHPART" ] && printf 'note: project site at a subpath — no CNAME, baseURL carries the path\n'
else
  printf '%s\n' "$HOST" > static/CNAME
  printf 'wrote static/CNAME for %s\n' "$HOST"
fi

# IDENTITY: --local, never --global. This is the single setting that keeps the
# machine's default identity off these commits, and it applies to this clone
# only — so it has to be re-run on every machine you write from.
git config --local user.name  "$HANDLE"
git config --local user.email "$GITMAIL"

# Refuse to fall back to the global identity if the local one is ever cleared.
git config --local user.useConfigOnly true

# Activate the committed hooks. Hooks are not cloned, so this must run per machine.
git config --local core.hooksPath .githooks

mkdir -p .identity
cat > .identity/expected.env <<EXP
# The identity this repo is allowed to commit as. bin/preflight.py enforces it.
# These values are public by design — the handle and its address.
HANDLE='$HANDLE'
GIT_EMAIL='$GITMAIL'
DOMAIN='$DOMAIN'
EXP

printf '\nidentity set:\n'
printf '  publishes as   %s\n' "$HANDLE"
printf '  commits as     %s <%s>\n' "$(git config --local user.name)" "$(git config --local user.email)"
printf '  domain         %s\n' "$DOMAIN"
printf '  security.txt   expires %s\n' "$EXPIRES"

printf '\nGitHub Pages next steps:\n'
printf '  1. create the repo, then:  git remote add origin git@github.com:%s/<repo>.git\n' "$HANDLE"
printf '  2. Settings > Pages > Source: GitHub Actions\n'
printf '  3. push to main; .github/workflows/pages.yml builds and deploys\n'
printf '  4. generate a FRESH ssh key for this handle — github.com/<user>.keys is\n'
printf '     public, and a reused key correlates your accounts\n'

if git log -1 >/dev/null 2>&1; then
  printf '\nNOTE: this repo already has commits. Check them:\n'
  printf '  git log --format="%%an <%%ae>" | sort -u\n'
  printf 'Rewriting author history is possible but the old objects survive in\n'
  printf 'any clone and any fork. If a real name is already in there, the clean\n'
  printf 'fix is a fresh repo with a fresh initial commit.\n'
fi
