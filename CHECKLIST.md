# Pre-publish checklist

Run before every post. `bin/preflight.py` automates the mechanical half; the
rest is judgement and cannot be scripted.

## Automated (the pre-commit hook does this)

- [ ] `bin/preflight.py` clean — no BLOCK findings, WARNs read and dismissed
- [ ] `git log --format='%an <%ae>' | sort -u` shows only the handle
- [ ] images passed through `bin/scrub-image.sh`

## Images — look at them, at full zoom

- [ ] no shell prompt showing `user@host`
- [ ] no home-directory path in any terminal, title bar, or file dialog
- [ ] no browser tabs, bookmark bar, history dropdown, or autofill
- [ ] no notification toast, calendar popup, or unread badge
- [ ] no internal hostname, IP, ticket ID, or org name in scrollback
- [ ] scrollback above and below the interesting region is clean
- [ ] redactions are crops or overwritten pixels — **not** black boxes drawn
      over text (frequently recoverable) and **not** blur (reversible for
      short strings)
- [ ] capture was taken in a dedicated VM or clean profile, not your desktop

## Content

- [ ] no client, customer, or engagement data of any kind
- [ ] addresses sanitized to documentation ranges (192.0.2.0/24, 198.51.100.0/24,
      203.0.113.0/24), hostnames to example.com
- [ ] technique from paid work was rebuilt against a lab target you own
- [ ] nothing in the post describes access you did not have authorization for

## Disclosure and employment

- [ ] vendor notified, patch shipped, agreed window elapsed
- [ ] `disclosure` front-matter field filled in with the timeline
- [ ] no working exploit for anything still unpatched
- [ ] employer's publication-approval requirement satisfied, in writing

## Pseudonym hygiene

- [ ] post does not narrow your location, employer, or timezone
- [ ] no cross-post that links this handle to a real-name account
- [ ] any new subdomain you issued a cert for is fine to be public forever
      (Certificate Transparency logs it permanently)
- [ ] writing does not reference the handle's other accounts unless intended

## After deploy

- [ ] Actions run went green; the deploy job published
- [ ] view-source: meta CSP present, no unexpected external request
- [ ] `curl -s https://0xsmash0th.github.io/ | grep -i "content-security-policy"` — the
      meta tag is the CSP on Pages; response headers are GitHub's, not yours
- [ ] repo is public: skim `git log --format='%an <%ae>'` one more time, since
      anything pushed is now permanent and forkable
- [ ] fresh ssh key for this handle — `github.com/<user>.keys` is public and a
      reused key correlates accounts
- [ ] WHOIS still redacted (custom domain only); registrar privacy still on
