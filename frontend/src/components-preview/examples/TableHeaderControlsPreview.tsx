import { useState } from "react";
import { Table, TableCellText, TableStatus, type TableColumn, type TableSortDirection } from "../../components/primitives/Table";
import "./TablePreview.css";

interface HeaderControlCase {
  id: number;
  title: string;
  description: string;
  score: number;
  status: "pass" | "fail";
}

const cases: readonly HeaderControlCase[] = [
  { id: 1, title: "Calendar access", description: "Check availability for the next team meeting", score: 94, status: "pass" },
  { id: 2, title: "Weekly action items", description: "Extract owners and due dates from meeting notes", score: 86, status: "pass" },
  { id: 3, title: "Document permissions", description: "Review access to the linked launch documents", score: 52, status: "fail" },
  { id: 4, title: "Meeting preparation", description: "Create an agenda from recent project updates", score: 91, status: "pass" },
  { id: 5, title: "Project risk review", description: "Find unresolved dependencies and delivery risks", score: 68, status: "fail" },
  { id: 6, title: "Release readiness", description: "Review the checklist before the next release", score: 97, status: "pass" },
  { id: 7, title: "Customer feedback", description: "Group recurring feedback into product themes", score: 88, status: "pass" },
  { id: 8, title: "Workspace handover", description: "Identify missing owners in the handover summary", score: 63, status: "fail" },
];

const resultOptions = [
  { value: "all", label: "All" },
  { value: "pass", label: "Pass" },
  { value: "fail", label: "Fail" },
];

export function TableHeaderControlsPreview() {
  const [direction, setDirection] = useState<TableSortDirection>(null);
  const [result, setResult] = useState("all");
  const visibleRows = cases.filter(row => result === "all" || row.status === result);
  if (direction) visibleRows.sort((left, right) => direction === "asc" ? left.score - right.score : right.score - left.score);

  const columns: TableColumn<HeaderControlCase>[] = [
    { key: "case", title: "Case", render: row => <TableCellText title={row.title} description={row.description} descriptionLines={2} /> },
    { key: "score", title: "Score", width: 132, sort: { direction, onChange: setDirection }, render: row => row.score },
    { key: "result", title: "Result", width: 180, filter: { value: result, options: resultOptions, onChange: setResult }, render: row => <TableStatus status={row.status} /> },
  ];

  return <section className="table-preview__example" aria-labelledby="table-header-controls-title">
    <h3 id="table-header-controls-title" className="table-preview__heading">表头排序与筛选</h3>
    <p className="table-preview__description">点击 Score 箭头切换升序、降序和原顺序；Result 可筛选 Pass 或 Fail</p>
    <Table aria-label="Cases with header controls" columns={columns} data={visibleRows} rowKey={row => row.id} minWidth={640} maxHeight={320} hideScrollbar={false} emptyContent="No matching cases" />
    <p className="table-preview__feedback" role="status">{visibleRows.length} / {cases.length} cases · {direction === "asc" ? "Score ascending" : direction === "desc" ? "Score descending" : "Original order"}</p>
  </section>;
}
