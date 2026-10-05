#!/usr/bin/env python3
"""Pre-publication leak scan.

Checks, in order:
  1. the repo's git identity is the pseudonym, not the machine default
  2. staged text does not contain known-real strings or generic leak shapes
  3. staged images carry no EXIF / XMP / IPTC / GPS metadata

Usage:
    bin/preflight.py                # staged changes (what the hook runs)
    bin/preflight.py --all          # everything tracked in the working tree
    bin/preflight.py FILE [FILE..]  # specific files

Exit status is 1 if anything BLOCKing was found, else 0.
This catches strings. It cannot see what is in a screenshot; you still have to
look at those yourself.
"""

import json
import os
import re
import subprocess
import sys

ROOT = subprocess.run(
    ["git", "rev-parse", "--show-toplevel"],
    capture_output=True, text=True,
).stdout.strip() or "."

RED, YEL, GRN, DIM, OFF = "\033[31m", "\033[33m", "\033[32m", "\033[2m", "\033[0m"
if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
    RED = YEL = GRN = DIM = OFF = ""

# Files that legitimately contain leak-shaped strings: this scanner's own
# pattern lists, and the scanner itself.
SELF_EXEMPT = {
    "bin/preflight.py",
    ".identity/patterns.local",
    ".identity/patterns.example",
}

# ---------------------------------------------------------------------------
# Generic patterns. These describe leak *shapes* and are safe to commit; the
# strings specific to you live in .identity/patterns.local.
# ---------------------------------------------------------------------------
# The site's own published addresses are not leaks. Without this the scanner
# warns about the contact address on every single commit, and a scanner that
# cries wolf every commit gets bypassed within a week.
EMAIL_MSG = "email address"
DOC_DOMAINS = ("example.com", "example.net", "example.org", "users.noreply.github.com")

BUILTIN = [
    # secrets
    ("BLOCK", r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY", "private key block"),
    ("BLOCK", r"\bAKIA[0-9A-Z]{16}\b", "AWS access key id"),
    ("BLOCK", r"\bgh[pousr]_[A-Za-z0-9]{36}\b", "GitHub token"),
    ("BLOCK", r"\bxox[baprs]-[A-Za-z0-9-]{10,}", "Slack token"),
    ("BLOCK", r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}", "JWT"),
    ("BLOCK", r"\bsk-[A-Za-z0-9]{20,}\b", "API secret key"),
    # local paths that name a user
    ("BLOCK", r"/home/(?!<)[a-z_][a-z0-9_-]{1,30}\b", "unix home directory path"),
    ("BLOCK", r"/Users/(?!<)[A-Za-z][A-Za-z0-9._-]{1,30}\b", "macOS home directory path"),
    ("BLOCK", r"C:\\+Users\\+(?!<)[^\\\s\"']{1,30}", "Windows profile path"),
    ("BLOCK", r"~/\.ssh/id_(?:rsa|ed25519|ecdsa|dsa)\b", "ssh private key path"),
    # infrastructure that should have been sanitised
    ("BLOCK", r"\b10\.(?:\d{1,3}\.){2}\d{1,3}\b", "RFC1918 address (use 192.0.2.0/24)"),
    ("BLOCK", r"\b192\.168\.(?:\d{1,3})\.\d{1,3}\b", "RFC1918 address (use 192.0.2.0/24)"),
    ("BLOCK", r"\b172\.(?:1[6-9]|2\d|3[01])\.(?:\d{1,3})\.\d{1,3}\b", "RFC1918 address (use 192.0.2.0/24)"),
    ("BLOCK", r"\b[\w-]+\.(?:internal|corp|intranet|lan)\b", "internal hostname"),
    ("WARN",  r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b", "MAC address"),
    # documents that were not yours to publish
    ("WARN",  r"\b(?:CONFIDENTIAL|INTERNAL USE ONLY|DO NOT DISTRIBUTE|PROPRIETARY)\b", "confidentiality marking"),
    ("WARN",  r"\b[A-Z]{2,10}-\d{2,6}\b", "possible ticket reference"),
    ("WARN",  r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b", EMAIL_MSG),
]

# exiftool tags that are disqualifying on their own
IMG_BLOCK = re.compile(
    r"(GPS|Artist|Creator|Author|Owner|By-?line|Copyright|SerialNumber|Software|"
    r"HostComputer|Make$|Model$|LensMake|UserComment|DocumentID|InstanceID|"
    r"OriginalDocumentID|MakerNote|CameraID|DeviceSetting|ImageDescription|"
    r"XPAuthor|XPComment|XPSubject|XPTitle|Rights|Marked|WebStatement)",
    re.I,
)
# tags that are structural and carry no identity
IMG_SAFE = re.compile(
    r"^(?:File|PNG|JPEG|GIF|WEBP|Composite|ICC_Profile):"
    r"(?:FileType\w*|MIMEType|ExifByteOrder|Image(?:Width|Height|Size)|BitDepth|"
    r"ColorType|Compression|Filter|Interlace|SRGBRendering|Gamma|Background\w*|"
    r"Palette|Transparency|SignificantBits|Pixels\w*|Resolution\w*|[XY]Resolution|"
    r"EncodingProcess|ColorComponents|YCbCrSubSampling|Megapixels|ProfileName|"
    r"ColorSpaceData|ProfileClass|ProfileVersion|ProfileCMMType|RenderingIntent|"
    r"ProfileConnectionSpace|MediaWhitePoint|DeviceModel|ProfileDescription|"
    r"ProfileID|PrimaryPlatform|CMMFlags|ProfileFileSignature|ProfileCreator|"
    r"ProfileDateTime|BlueMatrixColumn|GreenMatrixColumn|RedMatrixColumn|"
    r"BlueTRC|GreenTRC|RedTRC|ChromaticAdaptation|Luminance|Measurement\w*|"
    r"Technology|ViewingCond\w*|CurrentIPTCDigest)$",
    re.I,
)

OWN_ADDRESSES = set()

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".tif", ".tiff", ".heic", ".avif", ".pdf", ".svg"}
VIDEO_EXT = {".mp4", ".m4v", ".mov", ".webm", ".mkv"}
# Free-text tags muxers and editors write into a video container. Manim and
# FFmpeg put versioned toolchain strings in Encoder/Comment; editors put names,
# paths and places in the rest. animations/render.py strips all of them.
VIDEO_BLOCK = re.compile(
    r"^(Encoder|Comment|Title|Description|Artist|Author|Copyright|Software|"
    r"Make|Model|Location\w*|GPS\w*|Keywords|Album|Genre)$",
    re.I,
)
SKIP_EXT = {".woff", ".woff2", ".zip", ".gz", ".tar", ".bin", ".ico"}


def own_addresses():
    """Addresses this site publishes on purpose, read from its own config."""
    own = set()
    exp = os.path.join(ROOT, ".identity", "expected.env")
    if os.path.exists(exp):
        for line in open(exp, encoding="utf-8", errors="replace"):
            if line.startswith("GIT_EMAIL"):
                own.add(line.partition("=")[2].strip().strip("'\"").lower())
    cfg = os.path.join(ROOT, "hugo.toml")
    if os.path.exists(cfg):
        m = re.search(r"contactEmail\s*=\s*['\"]([^'\"]+)['\"]",
                      open(cfg, encoding="utf-8", errors="replace").read())
        if m:
            own.add(m.group(1).lower())
    return {a for a in own if "@" in a}


def is_own_address(addr):
    a = addr.lower()
    # "git@github.com" in a clone URL is an SSH remote, not an email address.
    if a.startswith("git@"):
        return True
    return a in OWN_ADDRESSES or a.endswith(DOC_DOMAINS)


def load_local_patterns():
    """Read .identity/patterns.local, falling back to the committed example."""
    out, path = [], os.path.join(ROOT, ".identity", "patterns.local")
    if not os.path.exists(path):
        print(f"{YEL}warn{OFF}  no .identity/patterns.local — copy .identity/patterns.example "
              f"and fill in your real strings, or this scan only catches generic shapes.")
        return out
    with open(path, encoding="utf-8", errors="replace") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            if len(parts) != 2 or parts[0] not in ("BLOCK", "WARN"):
                print(f"{YEL}warn{OFF}  patterns.local:{n}: skipped, must start with BLOCK or WARN")
                continue
            sev, rest = parts
            rx, _, msg = rest.partition("##")
            try:
                re.compile(rx.strip())
            except re.error as e:
                print(f"{YEL}warn{OFF}  patterns.local:{n}: bad regex ({e}), skipped")
                continue
            out.append((sev, rx.strip(), (msg.strip() or "local deny-list match")))
    return out


def compiled_rules():
    rules = []
    for sev, rx, msg in BUILTIN + load_local_patterns():
        rules.append((sev, re.compile(rx, re.I), msg))
    return rules


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, cwd=ROOT).stdout


def target_files(argv):
    args = [a for a in argv if not a.startswith("-")]
    if args:
        return args
    if "--all" in argv:
        return [f for f in git("ls-files").splitlines() if f]
    names = git("diff", "--cached", "--name-only", "--diff-filter=ACMR").splitlines()
    return [f for f in names if f]


def is_binary(path):
    try:
        with open(path, "rb") as fh:
            return b"\0" in fh.read(8000)
    except OSError:
        return True


def check_identity(findings):
    """The repo must commit as the pseudonym, never as the machine default."""
    name = git("config", "--local", "--get", "user.name").strip()
    mail = git("config", "--local", "--get", "user.email").strip()
    if not name or not mail:
        findings.append(("BLOCK", ".git/config", 0,
                         "repo has no local git identity — it will commit as your global "
                         "one. Run ./bin/set-identity.sh"))
        return
    if "__" in name or "__" in mail:
        findings.append(("BLOCK", ".git/config", 0,
                         f"git identity still a placeholder ({name} <{mail}>). "
                         "Run ./bin/set-identity.sh"))
        return
    expected = os.path.join(ROOT, ".identity", "expected.env")
    if os.path.exists(expected):
        want = {}
        for line in open(expected, encoding="utf-8"):
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.strip().partition("=")
                want[k] = v.strip().strip("'\"")
        if want.get("HANDLE") and want["HANDLE"] != name:
            findings.append(("BLOCK", ".git/config", 0,
                             f"committing as '{name}' but this blog publishes as "
                             f"'{want['HANDLE']}'"))
        if want.get("GIT_EMAIL") and want["GIT_EMAIL"] != mail:
            findings.append(("BLOCK", ".git/config", 0,
                             f"commit email is '{mail}', expected '{want['GIT_EMAIL']}'"))


def scan_text(path, rules, findings):
    rel = os.path.relpath(path, ROOT) if os.path.isabs(path) else path
    for sev, rx, msg in rules:
        m = rx.search(rel)
        if m:
            findings.append((sev, rel, 0, f"{msg} in the file path: {m.group(0)!r}"))
    if rel in SELF_EXEMPT:
        return
    try:
        with open(os.path.join(ROOT, rel), encoding="utf-8", errors="replace") as fh:
            for n, line in enumerate(fh, 1):
                if len(line) > 4000:
                    line = line[:4000]
                for sev, rx, msg in rules:
                    m = rx.search(line)
                    if not m:
                        continue
                    if msg == EMAIL_MSG and is_own_address(m.group(0)):
                        continue
                    findings.append((sev, rel, n, f"{msg}: {m.group(0)!r}"))
    except OSError as e:
        findings.append(("WARN", rel, 0, f"unreadable: {e}"))


def scan_image(path, findings):
    rel = os.path.relpath(path, ROOT) if os.path.isabs(path) else path
    exif = subprocess.run(
        ["exiftool", "-j", "-G1", "-All", "--System:All", os.path.join(ROOT, rel)],
        capture_output=True, text=True,
    )
    if exif.returncode != 0 or not exif.stdout.strip():
        findings.append(("WARN", rel, 0,
                         "exiftool unavailable or failed — image metadata NOT checked"))
        return
    try:
        tags = json.loads(exif.stdout)[0]
    except (ValueError, IndexError):
        findings.append(("WARN", rel, 0, "could not parse exiftool output"))
        return
    for tag, val in tags.items():
        if tag in ("SourceFile", "ExifTool:ExifToolVersion"):
            continue
        # Composite tags are computed by exiftool from other tags, which are
        # reported on their own lines. Reporting both triples the output on a
        # real photo without adding information.
        if tag.startswith("Composite:") and IMG_BLOCK.search(tag.split(":", 1)[-1]):
            continue
        bare = tag.split(":", 1)[-1]
        if IMG_BLOCK.search(bare):
            findings.append(("BLOCK", rel, 0,
                             f"image metadata {tag} = {str(val)[:60]!r} — run ./bin/scrub-image.sh"))
        elif not IMG_SAFE.match(tag):
            findings.append(("WARN", rel, 0, f"unexpected image metadata {tag} = {str(val)[:60]!r}"))


def scan_video(path, findings):
    """Container metadata, not frames: a screen recording still needs looking at."""
    rel = os.path.relpath(path, ROOT) if os.path.isabs(path) else path
    exif = subprocess.run(
        ["exiftool", "-j", "-G1", "-All", "--System:All", os.path.join(ROOT, rel)],
        capture_output=True, text=True,
    )
    if exif.returncode != 0 or not exif.stdout.strip():
        findings.append(("WARN", rel, 0,
                         "exiftool unavailable or failed — video metadata NOT checked"))
        return
    try:
        tags = json.loads(exif.stdout)[0]
    except (ValueError, IndexError):
        findings.append(("WARN", rel, 0, "could not parse exiftool output"))
        return
    for tag, val in tags.items():
        if tag == "SourceFile" or tag.startswith(("ExifTool:", "Composite:")):
            continue
        group, _, bare = tag.partition(":")
        sval = str(val)
        if IMG_BLOCK.search(bare) or VIDEO_BLOCK.match(bare):
            findings.append(("BLOCK", rel, 0,
                             f"video metadata {tag} = {sval[:60]!r} — re-render through animations/render.py"))
        elif bare in ("MuxingApp", "WritingApp") and sval != "Lavf":
            # FFmpeg writes a bare "Lavf" when told to be bitexact, and its
            # version otherwise; anything else names a different toolchain.
            findings.append(("WARN", rel, 0, f"versioned muxer string {tag} = {sval[:60]!r}"))
        elif bare.endswith("Date") and sval.strip("0: ") != "":
            # Muxers write zeroes; a real timestamp narrows down when, and in
            # which timezone, the file was made.
            findings.append(("WARN", rel, 0, f"timestamp in video metadata {tag} = {sval[:60]!r}"))
        elif group in ("ItemList", "UserData", "Keys") or group.startswith("XMP"):
            findings.append(("WARN", rel, 0, f"unexpected video metadata {tag} = {sval[:60]!r}"))


def main():
    global OWN_ADDRESSES
    OWN_ADDRESSES = own_addresses()
    argv = sys.argv[1:]
    rules = compiled_rules()
    findings = []
    check_identity(findings)

    files = target_files(argv)
    if not files:
        print(f"{DIM}nothing staged to scan{OFF}")
    for f in files:
        full = os.path.join(ROOT, f)
        if not os.path.isfile(full):
            continue
        ext = os.path.splitext(f)[1].lower()
        if f.startswith("public/"):
            findings.append(("BLOCK", f, 0, "build output staged — public/ belongs in .gitignore"))
            continue
        if ext in VIDEO_EXT:
            scan_video(f, findings)
            continue
        if ext in IMAGE_EXT:
            scan_image(f, findings)
            if ext == ".svg":
                scan_text(f, rules, findings)
            continue
        if ext in SKIP_EXT or is_binary(full):
            continue
        scan_text(f, rules, findings)

    blocks = [x for x in findings if x[0] == "BLOCK"]
    warns = [x for x in findings if x[0] == "WARN"]
    for sev, path, line, msg in blocks + warns:
        tag = f"{RED}BLOCK{OFF}" if sev == "BLOCK" else f"{YEL} WARN{OFF}"
        where = f"{path}:{line}" if line else path
        print(f"{tag}  {where}  {msg}")

    print()
    if blocks:
        print(f"{RED}{len(blocks)} blocking, {len(warns)} warnings.{OFF}")
        print(f"{DIM}Fix them, or bypass deliberately with:  git commit --no-verify{OFF}")
        return 1
    print(f"{GRN}no blocking findings{OFF}"
          f"{f' ({len(warns)} warnings above)' if warns else ''} — "
          f"{len(files)} file(s) scanned.")
    print(f"{DIM}Strings are clean. Now go look at the screenshots yourself.{OFF}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
