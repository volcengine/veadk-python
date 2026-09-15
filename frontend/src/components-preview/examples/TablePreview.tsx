import { useRef, useState } from "react";
import { PlusIcon } from "../../components/icons/PlusIcon";
import { Button } from "../../components/primitives/Button";
import { InputWithTailIcon } from "../../components/primitives/InputWithTailIcon";
import { Table, TableCellText, TableStatus, type TableColumn } from "../../components/primitives/Table";
import { ComponentApi } from "../api/ComponentApi";
import { TableHeaderControlsPreview } from "./TableHeaderControlsPreview";
import "./TablePreview.css";

type CaseRow = { id: number; question: string; score: number; status: "pass" | "fail" };
const data: CaseRow[] = [
  { id: 1, question: "Without calendar access, is there a meeting this afternoon?", score: 43, status: "fail" },
  { id: 2, question: "Summarize this week’s 1:1 and list action items", score: 56, status: "fail" },
  { id: 3, question: "What should I prepare for tomorrow’s sync with Zhou Ran?", score: 95, status: "pass" },
  { id: 4, question: "Aggregate project risks from the Lark docs", score: 93, status: "pass" },
  { id: 5, question: "Draft a pre-meeting brief for the Q3 planning review", score: 88, status: "pass" },
  { id: 6, question: "List blocked tasks and their owners across the workspace", score: 90, status: "pass" },
];
const columns: TableColumn<CaseRow>[] = [
  { key: "question", title: "Eval question", width: "73%", render: row => row.question },
  { key: "score", title: "v12 score", width: "14%", render: row => row.score },
  { key: "status", title: "Result", width: "13%", render: row => <TableStatus status={row.status} /> },
];

type DetailedCase = CaseRow & { title: string; reference: string };

const detailedData: DetailedCase[] = [
  { ...data[0], title: "Calendar availability", reference: "Workspace calendar access and meeting availability policy" },
  { ...data[1], title: "Weekly action items", reference: "Weekly team one-on-one notes and follow-up actions" },
  { ...data[2], title: "Meeting preparation", reference: "Product team sync / agenda and preparation checklist" },
  { ...data[3], title: "Project risk review", reference: "Quarterly project risk register and team delivery updates" },
  { ...data[4], title: "Planning brief", reference: "Q3 planning review / pre-meeting brief" },
  { ...data[5], title: "Blocked tasks", reference: "Workspace task dependencies and ownership" },
  { id: 7, title: "Release readiness", question: "Review the release checklist, open quality issues, and cross-team dependencies before deciding whether the workspace is ready for the next production release", reference: "Production release readiness checklist / September workspace update", score: 92, status: "pass" },
  { id: 8, title: "Customer feedback", question: "Summarize recurring customer feedback from this month and separate immediate usability issues from longer-term feature requests", reference: "Customer research synthesis and product feedback archive", score: 91, status: "pass" },
  { id: 9, title: "Document permissions", question: "Can everyone in the project read the launch plan and its linked documents?", reference: "Launch plan document access and sharing policy", score: 52, status: "fail" },
  { id: 10, title: "Decision summary", question: "Find the latest architecture review decisions, explain the trade-offs, and identify decisions that still need an owner", reference: "Architecture review meeting notes and decision records", score: 96, status: "pass" },
  { id: 11, title: "Milestone changes", question: "Compare this week’s milestones with last week’s plan and highlight changes that affect the launch date", reference: "Weekly roadmap and delivery milestones / launch preparation", score: 87, status: "pass" },
  { id: 12, title: "Workspace handover", question: "Prepare a handover summary covering the project goals, active work, outstanding risks, and the people responsible for each next step", reference: "Workspace handover guide / team responsibilities and next steps", score: 94, status: "pass" },
];

function SearchIcon() {
  return <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <circle cx="7" cy="7" r="4.5" stroke="currentColor" strokeWidth="1.5" />
    <path d="m10.5 10.5 3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>;
}

function DuplicateIcon() {
  return <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <rect x="2.5" y="5.5" width="8" height="8" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
    <path d="M5.5 3.5v-1h8v8h-1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>;
}

function ResultIcon({ status }: { status: DetailedCase["status"] }) {
  return <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path d={status === "pass" ? "m4.5 4.5 7 7m0-7-7 7" : "m3 8 3 3 7-7"} stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>;
}

export function TablePreview() {
  const [rows, setRows] = useState(detailedData);
  const [query, setQuery] = useState("");
  const [announcement, setAnnouncement] = useState("");
  const nextId = useRef(13);
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const visibleRows = rows.filter(row => `${row.title} ${row.question} ${row.reference}`.toLocaleLowerCase().includes(normalizedQuery));

  function addCase() {
    const id = nextId.current++;
    setRows(current => [{ id, title: `New case ${id}`, question: "Summarize the next steps from the latest project update", reference: "Project update and follow-up actions", score: 90, status: "pass" }, ...current]);
    setQuery("");
    setAnnouncement(`Added New case ${id}`);
  }

  function duplicateCase(row: DetailedCase) {
    const id = nextId.current++;
    setRows(current => current.flatMap(item => item.id === row.id ? [item, { ...row, id, title: `${row.title} copy` }] : [item]));
    setAnnouncement(`Duplicated ${row.title}`);
  }

  function toggleResult(row: DetailedCase) {
    const status = row.status === "pass" ? "fail" : "pass";
    setRows(current => current.map(item => item.id === row.id ? { ...item, status } : item));
    setAnnouncement(`${row.title}: ${status === "pass" ? "Pass" : "Fail"}`);
  }

  const detailColumns: TableColumn<DetailedCase>[] = [
    { key: "case", title: "Case", width: 300, fixed: "left", overflow: "wrap", render: row => <TableCellText title={row.title} description={row.question} descriptionLines={2} /> },
    { key: "reference", title: "Reference", overflow: "ellipsis", render: row => <span title={row.reference}>{row.reference}</span> },
    { key: "score", title: "v12 score", width: 80, render: row => row.score },
    { key: "status", title: "Result", width: 84, render: row => <TableStatus status={row.status} /> },
    { key: "actions", title: "Actions", width: 92, fixed: "right", align: "right", render: row => <div className="table-preview__actions" role="group" aria-label={`Actions for ${row.title}`}>
      <Button variant="ghost" iconOnly aria-label={`Duplicate ${row.title}`} title="Duplicate case" startIcon={<DuplicateIcon />} onClick={() => duplicateCase(row)} />
      <Button variant="ghost" iconOnly aria-label={`Mark ${row.title} as ${row.status === "pass" ? "fail" : "pass"}`} title={`Mark as ${row.status === "pass" ? "fail" : "pass"}`} startIcon={<ResultIcon status={row.status} />} onClick={() => toggleResult(row)} />
    </div> },
  ];

  return <section aria-labelledby="table-preview-title">
    <h2 id="table-preview-title" className="component-preview-title">Table</h2>
    <Table caption="Cases" columns={columns} data={data} rowKey={row => row.id} />

    <section className="table-preview__example" aria-labelledby="table-content-preview-title">
      <h3 id="table-content-preview-title" className="table-preview__heading">搜索、长内容与操作</h3>
      <p className="table-preview__description">标题与描述分层展示，长文本可换行或省略；滚动时固定表头、首列和操作列</p>
      <Table
        aria-label="Searchable cases"
        columns={detailColumns}
        data={visibleRows}
        rowKey={row => row.id}
        minWidth={860}
        maxHeight={280}
        hideScrollbar={false}
        emptyContent="No matching cases"
        toolbarStart={<InputWithTailIcon className="table-preview__search" type="search" aria-label="Search cases" placeholder="Search cases" value={query} onChange={event => { setQuery(event.target.value); setAnnouncement(""); }} tailIcon={<SearchIcon />} />}
        toolbarEnd={<Button startIcon={<PlusIcon />} onClick={addCase}>Add case</Button>}
      />
      <p className="table-preview__feedback" role="status">{announcement || `${visibleRows.length} cases`}</p>
    </section>

    <TableHeaderControlsPreview />
    <ComponentApi names={["Table", "TableCellText", "TableStatus"]} />
  </section>;
}
