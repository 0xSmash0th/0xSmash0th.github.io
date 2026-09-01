#!/usr/bin/env bash
# Strip all metadata from images, in place.
#
#   bin/scrub-image.sh static/img/*.png
#
# Removes every EXIF / XMP / IPTC / GPS / MakerNote tag and drops exiftool's
# backup copies. Structural data (dimensions, colour type) is untouched.
#
# This removes metadata. It does nothing about what the image actually shows —
# the hostname in your prompt, the tab bar, the notification that arrived while
# you were capturing. Look at every image at full zoom before it goes in.
set -euo pipefail

command -v exiftool >/dev/null || {
  echo "exiftool not found. Install it, or the pre-commit hook cannot check images." >&2
  exit 1
}
[ $# -gt 0 ] || { echo "usage: bin/scrub-image.sh FILE [FILE...]" >&2; exit 2; }

exiftool -all= -overwrite_original -P "$@"

echo
echo "remaining metadata:"
exiftool -G1 -All --System:All "$@" | sed 's/^/  /'
echo
echo "Redaction reminder: black boxes drawn over text are often recoverable and"
echo "blur is reversible for short strings. Crop it out or overwrite the pixels."
