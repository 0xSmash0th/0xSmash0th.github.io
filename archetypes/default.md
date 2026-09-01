+++
title = '{{ replace .File.ContentBaseName "-" " " | title }}'
date = {{ .Date }}
draft = true
description = ''
tags = []
toc = false   # set true for long posts to render a table of contents

# Fill this in for any post about someone else's bug, and leave it out
# otherwise. It renders under the title, and writing it forces you to confirm
# the window actually closed before you publish.
# disclosure = 'reported 2026-01-05, patched in 4.2.1, published 2026-03-06'
+++

<!--
Before publishing, run:  ./bin/preflight.sh
It will not catch a screenshot that shows your desktop. You have to look.
-->
