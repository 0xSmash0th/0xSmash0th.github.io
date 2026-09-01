+++
title = 'Setting Up Shop'
date = 2026-08-31T00:00:00Z
draft = true
description = 'What this blog is, and the rules it publishes under.'
tags = ['meta']
+++

This is a placeholder so the templates have something to render. Delete it, or
rewrite it into a real first post.

## The rules

Everything here about someone else's software is published after coordinated
disclosure. Posts that carry a timeline print it under the title, from the
`disclosure` field in the front matter:

```toml
disclosure = 'reported 2026-01-05, patched in 4.2.1, published 2026-03-06'
```

Nothing from a paid engagement appears here. Where a technique came out of
client work, it gets rebuilt against a lab target I own and written up from
that.

## Code and addresses

Code blocks render without external highlighting JS:

```python
def check(host: str) -> bool:
    # documentation ranges only — 192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24
    return host.endswith("example.com")
```

The preflight scanner blocks a commit containing an RFC1918 address, because in
a writeup that is almost always a real host that should have been sanitized.
