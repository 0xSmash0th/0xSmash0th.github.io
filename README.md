# 0xSmash0th — blog

Hugo site, static build, deployed to GitHub Pages. Written under a
persistent pseudonym: the handle carries the reputation, and it is not publicly
joined to a legal name.

## First run

```sh
bin/set-identity.sh <handle> <domain> <contact-email> [git-email]
```

This substitutes the `__PLACEHOLDER__` values across the config, scopes
`user.name` / `user.email` to this repo (`--local`, never `--global`), sets
`user.useConfigOnly` so git refuses to silently fall back to your machine
identity, and activates the pre-commit hook.

Then seed the local deny-list, which is what makes the hook useful:

```sh
cp .identity/patterns.example .identity/patterns.local   # already done here
$EDITOR .identity/patterns.local                          # add real name, employer, hosts
```

`.identity/patterns.local` is gitignored on purpose — it contains exactly the
strings you are trying to keep out of the repo, so it can never be committed.

## Daily use

```sh
hugo new content posts/some-slug.md   # drafts start with draft = true
hugo server -D                        # preview, drafts included
bin/preflight.py                      # scan staged changes
bin/preflight.py --all                # scan everything tracked
bin/scrub-image.sh static/img/*.png   # strip metadata before committing images
```

Publishing is `draft = false` plus a commit; Pages builds on push.

## Deploy

GitHub Pages, built by `.github/workflows/pages.yml` on every push to `main`.
Set **Settings > Pages > Source** to *GitHub Actions* once; nothing else to
configure. Hugo is pinned to 0.165.0 in the workflow and checksum-verified
before install.

On the free plan the repo must be **public**, which means your git history is
public too. Two consequences worth internalising:

- The first commit must already be authored as the handle. `bin/preflight.py`
  refuses to commit until `set-identity.sh` has run, which is what enforces
  this — but it only protects commits made after the hook is active.
- History is forever, and forks keep copies. A real name committed once and
  "removed" later is still there. If that happens, the clean fix is a new repo
  with a fresh initial commit, not a rewrite.

See `deploy/README.md` for what Pages costs you in response headers, and how to
move to Cloudflare later if you want them back.

## What is wired for identity safety

- `enableGitInfo = false` — Hugo otherwise exposes the commit author's name and
  email to templates, and themes render it as a "last edited by" line.
- `timeZone = 'UTC'` — local-zone timestamps on every post narrow down where
  you live.
- No generator meta tag, no webfonts, no CDN, no analytics, no comment widget.
  Every external request hands a third party your readers' IP addresses, and
  this audience checks.
- `markup.goldmark.renderer.unsafe = false` — raw HTML in Markdown is how a
  tracking pixel gets onto the site without passing review.
- `<meta http-equiv="Content-Security-Policy">` in `head.html` with
  `script-src 'none'` — on Pages this is the only CSP available, since GitHub
  serves through a CDN with no configurable headers. `frame-ancestors`, HSTS
  and `X-Content-Type-Options` are unavailable here; `deploy/_headers.cloudflare`
  holds the full header set for a future move.
- Pre-commit hook runs `bin/preflight.py` over staged files: git identity,
  deny-list strings, generic leak shapes (keys, tokens, RFC1918 addresses,
  home-directory paths), and image metadata.

## What none of this protects you from

The hook reads strings. It cannot see a screenshot showing your shell prompt,
your bookmark bar, or a notification that arrived mid-capture. It does not know
whether your employment contract requires publication approval, and it does not
know whether the vendor's disclosure window has actually closed.

See CHECKLIST.md, and run it.
