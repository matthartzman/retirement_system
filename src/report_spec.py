from __future__ import annotations

"""Renderer-neutral report specification for v10.

Report pages are expressed as sections, typed tables, and chart specs before any
renderer decides whether the output is UI, Excel, PDF, or JSON.
"""

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass(frozen=True)
class ReportColumn:
    key: str
    label: str
    kind: str = "text"
    group: str = ""


@dataclass(frozen=True)
class ReportTable:
    title: str
    columns: tuple[ReportColumn, ...]
    rows: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class ReportChart:
    title: str
    chart_type: str
    unit: str
    x: tuple[Any, ...] = ()
    series: tuple[dict[str, Any], ...] = ()
    slices: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class ReportSection:
    title: str
    tables: tuple[ReportTable, ...] = ()
    charts: tuple[ReportChart, ...] = ()


@dataclass(frozen=True)
class ReportPage:
    name: str
    category: str
    sections: tuple[ReportSection, ...] = ()


@dataclass(frozen=True)
class ReportSpec:
    schema: str = "report_spec_v10"
    pages: tuple[ReportPage, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def report_spec_from_results_model(model: dict[str, Any]) -> ReportSpec:
    pages: list[ReportPage] = []
    for page in model.get("sheets") or []:
        sections: list[ReportSection] = []
        if page.get("kind") == "chart_dashboard":
            charts = []
            for ch in page.get("charts") or []:
                charts.append(ReportChart(
                    title=str(ch.get("title", "Chart")),
                    chart_type=str(ch.get("type", "line")),
                    unit=str(ch.get("unit", "number")),
                    x=tuple(ch.get("x") or ()),
                    series=tuple(ch.get("series") or ()),
                    slices=tuple(ch.get("slices") or ()),
                ))
            sections.append(ReportSection(title=str(page.get("display_name") or page.get("name")), charts=tuple(charts)))
        else:
            for sec in page.get("sections") or []:
                raw_rows = sec.get("rows") or []
                labels = []
                if raw_rows:
                    cells = raw_rows[min(1, len(raw_rows)-1)].get("cells") or raw_rows[0].get("cells") or []
                    labels = [str(c.get("display") or c.get("value") or f"Column {i+1}") for i, c in enumerate(cells)]
                columns = tuple(ReportColumn(key=f"c{i}", label=label) for i, label in enumerate(labels))
                body = []
                for rr in raw_rows[2:] if len(raw_rows) > 2 else raw_rows[1:]:
                    cells = rr.get("cells") or []
                    body.append({f"c{i}": c.get("value") for i, c in enumerate(cells)})
                sections.append(ReportSection(title=str(sec.get("title") or page.get("display_name") or page.get("name")), tables=(ReportTable(str(sec.get("title") or "Results"), columns, tuple(body)),)))
        pages.append(ReportPage(name=str(page.get("display_name") or page.get("name")), category=str(page.get("category") or "Results"), sections=tuple(sections)))
    return ReportSpec(pages=tuple(pages))


def report_spec_from_plan_result(plan_result: dict[str, Any]) -> ReportSpec:
    """Build renderer-neutral report spec from canonical PlanResult."""
    pages = plan_result.get("result_pages") or []
    return report_spec_from_results_model({"sheets": pages})


__all__ = [
    "ReportColumn", "ReportTable", "ReportChart", "ReportSection", "ReportPage", "ReportSpec",
    "report_spec_from_results_model", "report_spec_from_plan_result",
]
