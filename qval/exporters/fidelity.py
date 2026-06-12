"""Export fidelity report (F-17).

A qval native suite is richer than any single external tool's config. When we
export, some fields translate cleanly, some are approximated, some degrade to
metadata/comments, and some have no home at all. This module records that
per-field translation *honestly* so the exporter can both print it and write it
to ``PATH.fidelity.md`` — the user sees exactly what survived the round trip
instead of assuming a lossless export.
"""
from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field


# Translation quality, worst kept explicit so a reviewer can scan for trouble.
CLEAN = "clean"                # carried with full meaning
APPROXIMATED = "approximated"  # a best-effort equivalent, not identical
DEGRADED = "degraded"          # preserved as metadata/comment, not enforced
DROPPED = "dropped"            # no equivalent; not represented at all

ALL_STATUSES = (CLEAN, APPROXIMATED, DEGRADED, DROPPED)

_SYMBOL = {CLEAN: "[ok]", APPROXIMATED: "[~]", DEGRADED: "[v]", DROPPED: "[x]"}


@dataclass
class FieldFidelity:
    """How one qval field fared in a single export."""

    field: str
    status: str
    note: str = ""
    case_ids: list[str] = dc_field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status not in ALL_STATUSES:
            raise ValueError(
                f"invalid fidelity status {self.status!r}; "
                f"must be one of {ALL_STATUSES}"
            )


@dataclass
class FidelityReport:
    """Per-field translation record for one suite export.

    ``tool``/``suite``/``summary`` describe the export; ``fields`` is the ordered
    list of per-field outcomes rendered as a table by the CLI and the sidecar
    markdown file.
    """

    tool: str
    suite: str
    summary: str = ""
    fields: list[FieldFidelity] = dc_field(default_factory=list)

    def add(self, field: str, status: str, note: str = "",
            case_ids: list[str] | None = None) -> "FidelityReport":
        """Append a field outcome. Returns self for chaining."""
        self.fields.append(FieldFidelity(field, status, note, list(case_ids or [])))
        return self

    # --- rendering ----------------------------------------------------------

    def render_markdown(self) -> str:
        """A standalone ``PATH.fidelity.md`` document."""
        lines = [
            f"# Fidelity report — {self.tool} export of suite `{self.suite}`",
            "",
        ]
        if self.summary:
            lines += [self.summary, ""]
        lines += [
            "| Field | Status | Notes |",
            "|-------|--------|-------|",
        ]
        for f in self.fields:
            note = f.note
            if f.case_ids:
                note = f"{note} (cases: {', '.join(f.case_ids)})".strip()
            lines.append(f"| {f.field} | {f.status} | {note} |")
        lines += [
            "",
            "Legend: clean = carried fully · approximated = best-effort equivalent · "
            "degraded = preserved as metadata/comment, not enforced · "
            "dropped = no equivalent.",
            "",
        ]
        return "\n".join(lines)

    def render_table(self) -> str:
        """A compact aligned table for the terminal."""
        header = f"Fidelity — {self.tool} ← suite '{self.suite}'"
        rows = [(_SYMBOL.get(f.status, "?"), f.field, f.status, f.note)
                for f in self.fields]
        fw = max([len(r[1]) for r in rows] + [5])
        sw = max([len(r[2]) for r in rows] + [6])
        out = [header]
        if self.summary:
            out.append(self.summary)
        out.append("")
        for sym, field, status, note in rows:
            out.append(f"  {sym} {field:<{fw}}  {status:<{sw}}  {note}")
        return "\n".join(out)
