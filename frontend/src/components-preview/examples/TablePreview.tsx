import { Table, TableStatus, type TableColumn } from "../../components/primitives/Table";
import { ComponentApi } from "../api/ComponentApi";

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
export function TablePreview() {
  return <section aria-labelledby="table-preview-title">
    <h2 id="table-preview-title" className="component-preview-title">Table</h2>
    <Table caption="Cases" columns={columns} data={data} rowKey={row => row.id} />
    <ComponentApi names={["Table", "TableStatus"]} />
  </section>;
}
