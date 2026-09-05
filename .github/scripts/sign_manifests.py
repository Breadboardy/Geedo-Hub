#!/usr/bin/env python3
"""Sign the Hub's animation manifests, so a robot knows the list is the Hub's.

    python3 tools/sign_manifests.py [hub-dir]              sign with the content key
    python3 tools/sign_manifests.py --check [hub-dir]      verify every .sig, change nothing
    python3 tools/sign_manifests.py --test-key [hub-dir]   tests only: the committed test key

Two things happen to each manifest - animations/manifest.json and every
animations/packs/<id>/manifest.json:

  1. Every entry gets a "sha256": the full hash of its .bin, computed here
     from the file beside it. The eight-character "hash" stays - it is the
     cache's idea of identity and what the website shows. Sixty-four
     characters are what a robot checks a download against.
  2. <manifest>.sig is written beside it: one line of base64, an ECDSA P-256
     signature over the SHA-256 of the manifest's exact bytes.

A robot fetches the .sig, then (only when it is new) the manifest, verifies
it against CONTENT_PUBLIC_KEY in the firmware, and only then reads the list -
and refuses any download whose bytes do not hash to what the signed list
promised. Nothing reaches his face that did not come from the Hub.

A manifest whose bytes have not changed and whose .sig still verifies is
left alone, so running this twice makes no second commit.

The key, in order: GEEDO_CONTENT_KEY (the PEM itself - how a GitHub Actions
secret arrives), GEEDO_CONTENT_KEY_FILE (a path), or
~/.geedo/content_signing_key.pem. --check needs only the public half:
GEEDO_CONTENT_PUB (a path), or it is derived from the private key.

This file is copied verbatim into the Hub as .github/scripts/sign_manifests.py,
where the publish action runs it with the repository secret.
"""
import base64
import glob
import hashlib
import json
import os
import subprocess
import sys
import tempfile


def die(msg):
    print(f"sign_manifests: {msg}", file=sys.stderr)
    sys.exit(1)


def openssl(*args, **kw):
    return subprocess.run(["openssl", *args], capture_output=True, **kw)


def detect_indent(text):
    """Keep whatever indent the file already uses, so the diff is the change."""
    for line in text.split("\n")[1:3]:
        stripped = line.lstrip(" ")
        if stripped and line != stripped:
            return len(line) - len(stripped)
    return 2


def fill_sha256(mpath):
    """Add/refresh "sha256" on every entry from the .bin beside the manifest.
    Returns True if the file changed."""
    with open(mpath) as f:
        text = f.read()
    m = json.loads(text)
    base = os.path.dirname(mpath)
    changed = False
    for a in m.get("animations", []):
        if not isinstance(a, dict) or not a.get("file"):
            continue
        bpath = os.path.join(base, a["file"])
        if not os.path.isfile(bpath):
            die(f"{mpath}: {a.get('id')} points at {a['file']}, which is not there")
        with open(bpath, "rb") as f:
            blob = f.read()
        digest = hashlib.sha256(blob).hexdigest()
        if a.get("sha256") != digest:
            a["sha256"] = digest
            changed = True
        if a.get("hash") and a["hash"] != digest[:8]:
            die(f"{mpath}: {a.get('id')} says hash {a['hash']} but the file is {digest[:8]} - "
                "the .bin changed without the manifest; re-run the tool that made it")
    if changed:
        with open(mpath, "w") as f:
            json.dump(m, f, indent=detect_indent(text))
            f.write("\n")
    return changed


def verify(pub_path, mpath):
    sig_path = mpath + ".sig"
    if not os.path.isfile(sig_path):
        return False, "no .sig"
    try:
        with open(sig_path) as f:
            der = base64.b64decode(f.read().strip())
    except Exception:
        return False, ".sig is not base64"
    with tempfile.NamedTemporaryFile(delete=False) as t:
        t.write(der)
        der_path = t.name
    try:
        r = openssl("dgst", "-sha256", "-verify", pub_path, "-signature", der_path, mpath)
    finally:
        os.unlink(der_path)
    return r.returncode == 0, (r.stdout or r.stderr).decode().strip()


def sign(key_path, mpath):
    r = openssl("dgst", "-sha256", "-sign", key_path, mpath)
    if r.returncode != 0:
        die(f"openssl could not sign {mpath}: {r.stderr.decode().strip()}")
    with open(mpath + ".sig", "w") as f:
        f.write(base64.b64encode(r.stdout).decode() + "\n")


def main(argv):
    check = "--check" in argv
    test_key = "--test-key" in argv
    rest = [a for a in argv if not a.startswith("--")]
    hub = os.path.abspath(rest[0]) if rest else os.getcwd()
    manifests = [p for p in [os.path.join(hub, "animations", "manifest.json")] if os.path.isfile(p)]
    manifests += sorted(glob.glob(os.path.join(hub, "animations", "packs", "*", "manifest.json")))
    if not manifests:
        die(f"no animations/manifest.json under {hub}")

    tmp_key = None
    key_path = None
    if test_key:
        here = os.path.dirname(os.path.abspath(__file__))
        key_path = os.path.join(here, "testdata", "test_content_key.pem")
        if not os.path.isfile(key_path):
            die("--test-key only works in the source repo, where tools/testdata/ is")
    elif os.environ.get("GEEDO_CONTENT_KEY", "").strip():
        fd, tmp_key = tempfile.mkstemp(suffix=".pem")
        os.write(fd, os.environ["GEEDO_CONTENT_KEY"].encode())
        os.close(fd)
        key_path = tmp_key
    elif os.environ.get("GEEDO_CONTENT_KEY_FILE"):
        key_path = os.environ["GEEDO_CONTENT_KEY_FILE"]
    else:
        key_path = os.path.expanduser("~/.geedo/content_signing_key.pem")

    pub_path = os.environ.get("GEEDO_CONTENT_PUB")
    tmp_pub = None
    try:
        if not pub_path:
            if not os.path.isfile(key_path):
                if check:
                    die("--check needs a public key: GEEDO_CONTENT_PUB=<pem>, or the private key to derive it from")
                die(f"no content key at {key_path}\n"
                    "  tools/make_signing_key.sh makes one; in GitHub Actions the secret "
                    "GEEDO_CONTENT_KEY carries it")
            r = openssl("ec", "-in", key_path, "-pubout")
            if r.returncode != 0:
                die(f"that is not an EC private key: {r.stderr.decode().strip()}")
            fd, tmp_pub = tempfile.mkstemp(suffix=".pem")
            os.write(fd, r.stdout)
            os.close(fd)
            pub_path = tmp_pub

        bad = 0
        for mpath in manifests:
            rel = os.path.relpath(mpath, hub)
            if check:
                ok, why = verify(pub_path, mpath)
                missing = [a.get("id") for a in json.load(open(mpath)).get("animations", [])
                           if isinstance(a, dict) and a.get("file") and not a.get("sha256")]
                if missing:
                    ok, why = False, f"{len(missing)} entries without sha256: {', '.join(map(str, missing[:4]))}"
                print(f"  {'ok  ' if ok else 'FAIL'}  {rel}  {why if not ok else ''}".rstrip())
                bad += 0 if ok else 1
                continue
            changed = fill_sha256(mpath)
            ok, _ = verify(pub_path, mpath)
            if changed or not ok:
                sign(key_path, mpath)
                ok2, why = verify(pub_path, mpath)
                if not ok2:
                    die(f"signed {rel} but it does not verify: {why}")
                print(f"  signed  {rel}{'  (sha256 filled in)' if changed else ''}")
            else:
                print(f"  kept    {rel}  (unchanged, signature still good)")
        if check and bad:
            die(f"{bad} manifest(s) would be refused by every robot")
        return 0
    finally:
        for p in (tmp_key, tmp_pub):
            if p and os.path.exists(p):
                os.unlink(p)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
