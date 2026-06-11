"""F-13 · AI Release Passport tests.

Covers Ed25519 signing, the content-addressed manifest, passport assembly +
signing, trustless verification, tamper/forgery detection, key pinning, and the
`qval passport` / `qval verify` CLI — including the acceptance-criteria demo
(good → VERIFIED; one byte edited → TAMPERED, exit non-zero).
"""
from __future__ import annotations

import json

import pytest

from qval.canonical import (
    CanonicalRun, Case, Finding, Decision,
    STATUS_PASSED, STATUS_FAILED,
    SEVERITY_CRITICAL, SEVERITY_LOW,
    DECISION_NO_GO,
)
from qval.canonical.io import save_canonical
from qval.controls import load_catalog, map_controls
from qval.passport import (
    generate_keypair, fingerprint, build_passport, assemble_core,
    verify_passport, load_passport, PassportError,
    canonical_bytes, build_manifest, sha256_hex,
)
from qval.passport import signing


# --- helpers ----------------------------------------------------------------

def sample_run(*, approved=False):
    cases = [Case(case_id="c1", name="PII leak", category="privacy", prompt="p1"),
             Case(case_id="c2", name="ok", category="privacy", prompt="p2")]
    findings = [
        Finding(finding_id="c1", case_id="c1", status=STATUS_FAILED,
                severity=SEVERITY_CRITICAL, reason="leaked PII"),
        Finding(finding_id="c2", case_id="c2", status=STATUS_PASSED,
                severity=SEVERITY_LOW),
    ]
    run = CanonicalRun(run_id="run_x", source_tool="qval", model="gpt-4o",
                       provider="openai", suite="support-bot", prompt_version="2.1.0",
                       cases=cases, findings=findings,
                       decision=Decision(verdict=DECISION_NO_GO,
                                         rationale=["1 new critical"],
                                         policy_version="builtin-v1"))
    map_controls(run, load_catalog())
    return run


KP = generate_keypair()


def make_passport(tmp_path, *, approver="Jane Doe", run=None):
    run = run or sample_run()
    return build_passport(run, private_pem=KP.private_pem, approver=approver,
                          system_name="support-bot", version="2.1.0",
                          out_dir=tmp_path / "passport")


# --- signing ----------------------------------------------------------------

def test_sign_verify_roundtrip():
    sig = signing.sign_data(KP.private_pem, b"hello")
    assert signing.verify_data(KP.public_pem, sig, b"hello") is True


def test_verify_fails_on_altered_data():
    sig = signing.sign_data(KP.private_pem, b"hello")
    assert signing.verify_data(KP.public_pem, sig, b"hello!") is False


def test_verify_fails_with_other_key():
    other = generate_keypair()
    sig = signing.sign_data(KP.private_pem, b"hello")
    assert signing.verify_data(other.public_pem, sig, b"hello") is False


def test_fingerprint_stable_and_keyed():
    assert fingerprint(KP.public_pem) == fingerprint(KP.public_pem)
    assert fingerprint(KP.public_pem) != fingerprint(generate_keypair().public_pem)
    assert fingerprint(KP.public_pem).startswith("ed25519:")


# --- manifest / canonical ---------------------------------------------------

def test_canonical_bytes_order_independent():
    assert canonical_bytes({"a": 1, "b": 2}) == canonical_bytes({"b": 2, "a": 1})


def test_build_manifest_hashes_and_sorts():
    m = build_manifest([("z.txt", b"Z"), ("a.txt", b"A")])
    assert [e["path"] for e in m["artifacts"]] == ["a.txt", "z.txt"]
    assert m["artifacts"][0]["sha256"] == sha256_hex(b"A")


# --- assembly ---------------------------------------------------------------

def test_assemble_requires_approver():
    with pytest.raises(PassportError):
        assemble_core(sample_run(), approver="", system_name="", version="",
                      public_pem=KP.public_pem)


def test_assemble_derives_approver_from_review():
    run = sample_run()
    from qval.review import apply_decision
    apply_decision(run, "c1", reviewer_id="alice", decision="approve")
    core, _ = assemble_core(run, approver="", system_name="s", version="1",
                            public_pem=KP.public_pem)
    assert core["decision"]["approver"] == "alice"


def test_core_summary_and_governance():
    core, _ = assemble_core(sample_run(), approver="Jane", system_name="s",
                            version="1", public_pem=KP.public_pem)
    assert core["summary"]["tests"] == 2
    assert core["summary"]["critical_failures"] == 1
    # privacy -> OWASP-LLM-02 in the default catalog
    assert any(g["control_id"] == "OWASP-LLM-02" for g in core["governance"])


# --- build + verify (happy path) --------------------------------------------

def test_build_writes_bundle(tmp_path):
    passport, out = make_passport(tmp_path)
    for name in ("passport.json", "run.json", "report.md", "report.html", "issuer.pub"):
        assert (out / name).is_file()
    assert passport["format"] == "qval-release-passport/v1"


def test_verify_good_passport_pinned(tmp_path):
    _, out = make_passport(tmp_path)
    res = verify_passport(out, pubkey_pem=KP.public_pem)
    assert res.ok is True
    assert res.problems == []
    assert res.key_source == "pinned"
    assert res.core["decision"]["approver"] == "Jane Doe"
    assert res.core["summary"]["critical_failures"] == 1


def test_verify_without_pubkey_warns_but_ok(tmp_path):
    _, out = make_passport(tmp_path)
    res = verify_passport(out)
    assert res.ok is True
    assert res.key_source == "embedded"
    assert any("EMBEDDED" in w for w in res.warnings)


# --- tamper / forgery -------------------------------------------------------

def test_tamper_artifact_byte_detected(tmp_path):
    _, out = make_passport(tmp_path)
    # edit one byte of the evidence
    p = out / "run.json"
    data = p.read_bytes()
    p.write_bytes(data[:-2] + b"X" + data[-1:])
    res = verify_passport(out, pubkey_pem=KP.public_pem)
    assert res.ok is False
    assert any("run.json" in prob for prob in res.problems)


def test_tamper_core_claim_detected(tmp_path):
    _, out = make_passport(tmp_path)
    passport = load_passport(out)
    passport["core"]["decision"]["approver"] = "Mallory"   # forge the approver
    (out / "passport.json").write_text(json.dumps(passport), encoding="utf-8")
    res = verify_passport(out, pubkey_pem=KP.public_pem)
    assert res.ok is False
    assert any("signature" in prob.lower() for prob in res.problems)


def test_verify_wrong_pubkey_fails(tmp_path):
    _, out = make_passport(tmp_path)
    other = generate_keypair()
    res = verify_passport(out, pubkey_pem=other.public_pem)
    assert res.ok is False


def test_fingerprint_pin_match_and_mismatch(tmp_path):
    _, out = make_passport(tmp_path)
    good = fingerprint(KP.public_pem)
    assert verify_passport(out, pubkey_pem=KP.public_pem,
                           expected_fingerprint=good).ok is True
    bad = verify_passport(out, pubkey_pem=KP.public_pem,
                          expected_fingerprint="ed25519:deadbeef")
    assert bad.ok is False


def test_missing_passport_dir(tmp_path):
    res = verify_passport(tmp_path / "nope")
    assert res.ok is False


# --- CLI: the acceptance demo -----------------------------------------------

def _keyfiles(tmp_path):
    priv = tmp_path / "issuer_key"
    pub = tmp_path / "issuer_key.pub"
    priv.write_bytes(KP.private_pem)
    pub.write_bytes(KP.public_pem)
    return priv, pub


def test_cli_keygen(tmp_path, capsys):
    from qval.cli import main
    rc = main(["passport", "keygen", "--out", str(tmp_path / "k")])
    assert rc == 0
    assert (tmp_path / "k").is_file() and (tmp_path / "k.pub").is_file()
    assert "PUBLISH" in capsys.readouterr().out


def test_cli_create_then_verify_good(tmp_path, capsys):
    from qval.cli import main
    priv, pub = _keyfiles(tmp_path)
    run_path = tmp_path / "run.json"
    save_canonical(sample_run(), run_path)
    bundle = tmp_path / "passport"
    rc = main(["passport", "create", "--from", str(run_path), "--approver",
               "Jane Doe", "--key", str(priv), "--out", str(bundle)])
    assert rc == 0
    capsys.readouterr()
    rc = main(["verify", str(bundle), "--pubkey", str(pub)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "VERIFIED" in out and "evidence unaltered" in out
    assert "support-bot" in out and "NO-GO" in out and "Jane Doe" in out
    assert "not that the AI system is safe" in out   # guardrail present


def test_cli_verify_tampered_exits_nonzero(tmp_path, capsys):
    from qval.cli import main
    priv, pub = _keyfiles(tmp_path)
    run_path = tmp_path / "run.json"
    save_canonical(sample_run(), run_path)
    bundle = tmp_path / "passport"
    main(["passport", "create", "--from", str(run_path), "--approver", "Jane",
          "--key", str(priv), "--out", str(bundle)])
    capsys.readouterr()
    # flip one byte of an artifact
    art = bundle / "report.md"
    data = art.read_bytes()
    art.write_bytes(b"X" + data[1:])
    rc = main(["verify", str(bundle), "--pubkey", str(pub)])
    out = capsys.readouterr().out
    assert rc == 2
    assert "TAMPERED" in out and "report.md" in out


def test_cli_create_requires_approver(tmp_path):
    from qval.cli import main
    priv, _ = _keyfiles(tmp_path)
    run_path = tmp_path / "run.json"
    save_canonical(sample_run(), run_path)
    rc = main(["passport", "create", "--from", str(run_path),
               "--key", str(priv), "--out", str(tmp_path / "p")])
    assert rc == 2


def test_cli_create_without_key_exit_2(tmp_path, monkeypatch):
    from qval.cli import main
    monkeypatch.delenv("QVAL_PASSPORT_KEY", raising=False)
    run_path = tmp_path / "run.json"
    save_canonical(sample_run(), run_path)
    rc = main(["passport", "create", "--from", str(run_path), "--approver", "J",
               "--out", str(tmp_path / "p")])
    assert rc == 2
