"""F-08 · Evidence pack tests.

Covers the builder (artifacts + manifest + signing), the verifier (intact,
tampered, wrong key), hash-only mode, mode validation, and the `qval pack` CLI
(build + verify exit codes). All packs are written under tmp_path.
"""
from __future__ import annotations

import json

import pytest

from qval.canonical import (
    CanonicalRun, Case, Finding, Decision,
    STATUS_PASSED, STATUS_FAILED,
    SEVERITY_LOW, SEVERITY_CRITICAL,
    DECISION_NO_GO,
)
from qval.canonical.io import save_canonical
from qval.evidence import (
    build_pack, verify_pack, EvidencePackError,
    MODE_HASH_ONLY, MODE_REGULATED, MANIFEST_NAME,
)

KEY = "s3cret-signing-key"


# --- helpers ----------------------------------------------------------------

def sample_run():
    cases = [Case(case_id="c1", name="leak", category="privacy", prompt="p")]
    findings = [Finding(finding_id="c1", case_id="c1", status=STATUS_FAILED,
                        severity=SEVERITY_CRITICAL, reason="leaked PII")]
    return CanonicalRun(run_id="run_x", source_tool="qval", model="m", provider="p",
                        cases=cases, findings=findings,
                        decision=Decision(verdict=DECISION_NO_GO,
                                          rationale=["1 new critical"],
                                          policy_version="builtin-v1"))


# --- build ------------------------------------------------------------------

def test_build_writes_all_artifacts(tmp_path):
    run = sample_run()
    pack, out = build_pack(run, tmp_path / "pack", mode="internal")
    for name in ("run.json", "report.md", "report.html", MANIFEST_NAME):
        assert (out / name).is_file()
    assert run.evidence_pack is pack
    assert {a.path for a in pack.artifacts} == {"run.json", "report.md", "report.html"}
    assert all(len(a.sha256) == 64 for a in pack.artifacts)


def test_run_json_artifact_excludes_evidence_pack(tmp_path):
    # the sealed run.json must not contain the pack pointer (circular hash)
    run = sample_run()
    _, out = build_pack(run, tmp_path / "pack")
    sealed = json.loads((out / "run.json").read_text(encoding="utf-8"))
    assert sealed["evidence_pack"] is None


def test_unsigned_when_no_key(tmp_path):
    pack, _ = build_pack(sample_run(), tmp_path / "pack")
    assert pack.signature == ""


def test_signed_when_key_given(tmp_path):
    pack, _ = build_pack(sample_run(), tmp_path / "pack", sign_key=KEY)
    assert pack.signature and len(pack.signature) == 64


def test_ttl_recorded_in_manifest(tmp_path):
    _, out = build_pack(sample_run(), tmp_path / "pack", ttl_days=90)
    manifest = json.loads((out / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["retention_ttl_days"] == 90


# --- verify -----------------------------------------------------------------

def test_verify_clean_pack(tmp_path):
    _, out = build_pack(sample_run(), tmp_path / "pack", sign_key=KEY)
    assert verify_pack(out, sign_key=KEY) == []


def test_verify_detects_artifact_tampering(tmp_path):
    _, out = build_pack(sample_run(), tmp_path / "pack", sign_key=KEY)
    (out / "report.html").write_text("tampered", encoding="utf-8")
    problems = verify_pack(out, sign_key=KEY)
    assert any("report.html" in p for p in problems)


def test_verify_detects_wrong_key(tmp_path):
    _, out = build_pack(sample_run(), tmp_path / "pack", sign_key=KEY)
    problems = verify_pack(out, sign_key="wrong-key")
    assert any("signature" in p for p in problems)


def test_verify_signature_without_key_is_flagged(tmp_path):
    _, out = build_pack(sample_run(), tmp_path / "pack", sign_key=KEY)
    problems = verify_pack(out)  # no key supplied
    assert any("no key" in p for p in problems)


def test_verify_detects_manifest_tampering(tmp_path):
    _, out = build_pack(sample_run(), tmp_path / "pack")
    manifest = json.loads((out / MANIFEST_NAME).read_text(encoding="utf-8"))
    manifest["artifacts"][0]["sha256"] = "0" * 64
    (out / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
    problems = verify_pack(out)
    assert any("manifest_sha256 mismatch" in p for p in problems)


def test_verify_missing_manifest(tmp_path):
    problems = verify_pack(tmp_path / "empty")
    assert problems and "manifest not found" in problems[0]


# --- modes ------------------------------------------------------------------

def test_hash_only_writes_only_manifest(tmp_path):
    pack, out = build_pack(sample_run(), tmp_path / "pack", mode=MODE_HASH_ONLY)
    assert (out / MANIFEST_NAME).is_file()
    assert not (out / "run.json").exists()
    assert not (out / "report.html").exists()
    # hashes still recorded; verify skips the absent files and passes
    assert all(a.sha256 for a in pack.artifacts)
    assert verify_pack(out) == []


def test_regulated_without_key_raises(tmp_path):
    with pytest.raises(EvidencePackError):
        build_pack(sample_run(), tmp_path / "pack", mode=MODE_REGULATED)


def test_regulated_with_key_ok(tmp_path):
    pack, _ = build_pack(sample_run(), tmp_path / "pack",
                         mode=MODE_REGULATED, sign_key=KEY)
    assert pack.signature


def test_unknown_mode_raises(tmp_path):
    with pytest.raises(EvidencePackError):
        build_pack(sample_run(), tmp_path / "pack", mode="bogus")


# --- CLI --------------------------------------------------------------------

def test_cli_pack_build(tmp_path, capsys):
    from qval.cli import main
    src = tmp_path / "run.json"
    save_canonical(sample_run(), src)
    out = tmp_path / "pack"
    rc = main(["pack", str(src), "--out", str(out)])
    assert rc == 0
    assert (out / MANIFEST_NAME).is_file()
    assert "Evidence pack written" in capsys.readouterr().out


def test_cli_pack_verify_roundtrip(tmp_path, capsys):
    from qval.cli import main
    src = tmp_path / "run.json"
    save_canonical(sample_run(), src)
    out = tmp_path / "pack"
    main(["pack", str(src), "--out", str(out), "--key", KEY])
    rc = main(["pack", "--verify", str(out), "--key", KEY])
    assert rc == 0
    assert "OK" in capsys.readouterr().out


def test_cli_pack_verify_tampered_exit_1(tmp_path):
    from qval.cli import main
    src = tmp_path / "run.json"
    save_canonical(sample_run(), src)
    out = tmp_path / "pack"
    main(["pack", str(src), "--out", str(out)])
    (out / "report.md").write_text("tampered", encoding="utf-8")
    rc = main(["pack", "--verify", str(out)])
    assert rc == 1


def test_cli_pack_regulated_no_key_exit_2(tmp_path):
    from qval.cli import main
    src = tmp_path / "run.json"
    save_canonical(sample_run(), src)
    rc = main(["pack", str(src), "--out", str(tmp_path / "pack"), "--mode", "regulated"])
    assert rc == 2


def test_cli_pack_no_args_exit_2(tmp_path):
    from qval.cli import main
    rc = main(["pack"])
    assert rc == 2
