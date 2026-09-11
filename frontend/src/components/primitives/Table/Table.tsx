import type { CSSProperties, Key, ReactNode } from "react";
import { ScrollArea } from "../ScrollArea";
import "./Table.css";

export interface TableColumn<T> {
  key: string;
  title: ReactNode;
  width?: CSSProperties["width"];
  align?: "left" | "center" | "right";
  render: (row: T, index: number) => ReactNode;
}
export interface TableProps<T> {
  /** 列定义：key、title、render 必填，width 和 align 可选 */
  columns: readonly TableColumn<T>[];
  /** 行数据 */
  data: readonly T[];
  /** 返回稳定且唯一的行标识 */
  rowKey: (row: T) => Key;
  /** 表格标题 */
  caption?: ReactNode;
  /** 无数据时的内容 */
  emptyContent?: ReactNode;
  /** 最小表格宽度，容器较窄时支持横向滚动 */
  minWidth?: CSSProperties["minWidth"];
  "aria-label"?: string;
  className?: string;
}

export function Table<T>({ columns, data, rowKey, caption, emptyContent = "暂无数据", minWidth = 640, "aria-label": label, className = "" }: TableProps<T>) {
  return <ScrollArea orientation="horizontal" hideScrollbar className={`studio-table-scroll ${className}`.trim()}>
    <table className="studio-table" aria-label={label} style={{ minWidth }}>
      {caption && <caption>{caption}</caption>}
      <colgroup>{columns.map(column => <col key={column.key} style={{ width: column.width }} />)}</colgroup>
      <thead><tr>{columns.map(column => <th key={column.key} scope="col" style={{ textAlign: column.align ?? "left" }}>{column.title}</th>)}</tr></thead>
      <tbody>{data.length ? data.map((row, index) => <tr key={rowKey(row)}>{columns.map(column => <td key={column.key} style={{ textAlign: column.align ?? "left" }}>{column.render(row, index)}</td>)}</tr>) : <tr><td colSpan={Math.max(1, columns.length)} className="studio-table__empty">{emptyContent}</td></tr>}</tbody>
    </table>
  </ScrollArea>;
}

export interface TableStatusProps {
  status: "pass" | "fail";
  children?: ReactNode;
}
export function TableStatus({ status, children }: TableStatusProps) {
  return <span className="studio-table-status" data-status={status}>
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
      <path d={status === "pass" ? "M2 6.2 4.5 8.7 10 3.2" : "m3 3 6 6M9 3 3 9"} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
    {children ?? (status === "pass" ? "Pass" : "Fail")}
  </span>;
}
