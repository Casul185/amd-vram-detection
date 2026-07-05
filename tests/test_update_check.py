"""Regression for the passive startup update check in vram.py — semver,
fail-silent, opt-out.

Never touches the real network: the fetch function is replaced with a stub, and
the cache is redirected to a temp dir. Run: python tests/test_update_check.py
"""
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import vram as u  # noqa: E402

CURRENT = "0.1.1"


def _isolate_cache():
    tmp = tempfile.mkdtemp()
    os.environ["XDG_CACHE_HOME"] = tmp
    os.environ.pop("LOCALAPPDATA", None)
    try:
        os.remove(u._cache_file())
    except OSError:
        pass


def _run():
    buf = io.StringIO()
    old = sys.stderr
    sys.stderr = buf
    try:
        u.notify_if_update_available(CURRENT)
    finally:
        sys.stderr = old
    return buf.getvalue()


def check_semver(fail):
    cases = [
        (("0.1.7", "0.1.6"), True),
        (("0.1.6", "0.1.6"), False),
        (("0.1.9", "0.2.0"), False),
        (("abc", "0.1.6"), False),
        (("", "0.1.6"), False),
        (("v0.1.7", "0.1.6"), True),
        (("0.1.10", "0.1.9"), True),
    ]
    for (remote, local), want in cases:
        got = u._is_newer(remote, local)
        if got != want:
            fail(f"semver {remote!r} vs {local!r}: got {got}, want {want}")


def check_fail_silent(fail):
    _isolate_cache()
    orig = u._fetch_latest_tag

    def boom(url, timeout):
        raise OSError("network down")

    u._fetch_latest_tag = boom
    try:
        out = _run()
    except Exception as exc:
        fail(f"fail-silent (raising fetch) propagated: {exc!r}")
        out = ""
    finally:
        u._fetch_latest_tag = orig
    if out:
        fail(f"fail-silent (raising fetch) printed: {out!r}")

    _isolate_cache()

    def junk(url, timeout):
        return "not-a-version"

    u._fetch_latest_tag = junk
    try:
        out = _run()
    finally:
        u._fetch_latest_tag = orig
    if out:
        fail(f"fail-silent (malformed tag) printed: {out!r}")


def check_optout(fail):
    _isolate_cache()
    orig = u._fetch_latest_tag
    called = {"net": False}

    def flag(url, timeout):
        called["net"] = True
        return "v9.9.9"

    u._fetch_latest_tag = flag
    os.environ["AMD_VRAM_NO_UPDATE_CHECK"] = "1"
    try:
        out = _run()
    finally:
        os.environ.pop("AMD_VRAM_NO_UPDATE_CHECK", None)
        u._fetch_latest_tag = orig
    if called["net"]:
        fail("opt-out set but network fetch was still attempted")
    if out:
        fail(f"opt-out set but a notice was printed: {out!r}")


def check_notice_and_cache(fail):
    _isolate_cache()
    orig = u._fetch_latest_tag

    def newer(url, timeout):
        return "v9.9.9"

    u._fetch_latest_tag = newer
    try:
        out = _run()
    finally:
        u._fetch_latest_tag = orig
    expected = (f">> A new version of amd-vram-detection is available: v9.9.9 "
                f"(you have {CURRENT}) — "
                f"https://github.com/casul185/amd-vram-detection/releases/latest\n")
    if out != expected:
        fail(f"notice mismatch:\n got: {out!r}\n exp: {expected!r}")

    called = {"net": False}

    def flag(url, timeout):
        called["net"] = True
        return "v9.9.9"

    u._fetch_latest_tag = flag
    try:
        out2 = _run()
    finally:
        u._fetch_latest_tag = orig
    if called["net"]:
        fail("fresh cache (<24h) still hit the network")
    if out2 != expected:
        fail(f"fresh-cache notice mismatch:\n got: {out2!r}\n exp: {expected!r}")


def main() -> int:
    failures = []
    fail = failures.append
    check_semver(fail)
    check_fail_silent(fail)
    check_optout(fail)
    check_notice_and_cache(fail)
    if failures:
        print("UPDATE-CHECK FAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("OK — passive update check: semver, fail-silent, opt-out, cache all pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
