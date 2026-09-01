# Deployment

Live target is **GitHub Pages**, built by `.github/workflows/pages.yml` on every
push to `main`.

`_headers.cloudflare` is inert here. GitHub Pages serves through a CDN with no
configurable header layer — no `_headers`, no `.htaccess`, no equivalent — so
the security headers are enforced by the `<meta http-equiv>` CSP in
`layouts/_partials/head.html` instead.

What the meta-tag CSP cannot express, and what you therefore do not have on
Pages:

| Header | Status on Pages |
| --- | --- |
| `Content-Security-Policy` | via meta tag, minus the directives below |
| `frame-ancestors` | **lost** — meta CSP ignores it, so no clickjacking defence |
| `Strict-Transport-Security` | **lost** — GitHub sets its own for *.github.io |
| `X-Content-Type-Options` | **lost** — no meta equivalent |
| `Referrer-Policy` | kept, via `<meta name="referrer">` |

To move to Cloudflare Pages later: move `_headers.cloudflare` back to
`static/_headers`, delete `.github/workflows/pages.yml`, and set the build to
`hugo --gc --minify` with output `public`. The meta CSP can stay — two
identical policies intersect to the same thing.
