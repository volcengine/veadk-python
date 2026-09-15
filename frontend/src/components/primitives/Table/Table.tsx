import { useLayoutEffect, useRef, type CSSProperties, type Key, type ReactNode } from "react";
import { Button } from "../Button";
import { ScrollArea } from "../ScrollArea";
import { Select, type SelectOption } from "../Select";
import "./Table.css";

export type TableSortDirection = "asc" | "desc" | null;

export interface TableColumnSort {
  /** 当前排序方向；null 为原顺序 */
  direction: TableSortDirection;
  /** 点击依次返回 asc、desc、null；由调用方更新数据 */
  onChange: (direction: TableSortDirection) => void;
  disabled?: boolean;
  /** 列标题不是纯文本时，可指定排序操作名称 */
  "aria-label"?: string;
}

export interface TableColumnFilter {
  value: string;
  /** 包含需要的全部选项，例如 All、Pass、Fail */
  options: readonly SelectOption[];
  /** 由调用方更新筛选状态和行数据 */
  onChange: (value: string) => void;
  disabled?: boolean;
  "aria-label"?: string;
}

export interface TableColumn<T> {
  key: string;
  title: ReactNode;
  width?: CSSProperties["width"];
  align?: "left" | "center" | "right";
  /** wrap 自动换行；ellipsis 单行省略，纯文本悬停可查看全文 */
  overflow?: "wrap" | "ellipsis";
  /** 冻结到左侧或右侧，横向滚动时保持可见 */
  fixed?: "left" | "right";
  /** 表头排序按钮；只发送排序方向，数据处理由调用方负责 */
  sort?: TableColumnSort;
  /** 表头筛选，复用 Select 选项与交互 */
  filter?: TableColumnFilter;
  render: (row: T, index: number) => ReactNode;
}
export interface TableProps<T> {
  /** 列定义：key、title、render 必填；可配置宽度、冻结、排序与筛选 */
  columns: readonly TableColumn<T>[];
  /** 行数据 */
  data: readonly T[];
  /** 返回稳定且唯一的行标识 */
  rowKey: (row: T) => Key;
  /** 表格标题 */
  caption?: ReactNode;
  /** 无数据时的内容 */
  emptyContent?: ReactNode;
  /** 最小表格宽度，容器较窄时支持横向滚动；设为 0 则适应容器 */
  minWidth?: CSSProperties["minWidth"];
  /** fixed 按列宽分配；auto 根据内容自动分配列宽 */
  layout?: "fixed" | "auto";
  /** 限制表格滚动区域高度；不包含顶部工具栏 */
  maxHeight?: CSSProperties["maxHeight"];
  /** 设置 maxHeight 后，滚动时固定列标题 */
  stickyHeader?: boolean;
  /** 隐藏滚动条，保留原生滚动 */
  hideScrollbar?: boolean;
  /** 顶部工具栏左侧插槽，例如搜索框 */
  toolbarStart?: ReactNode;
  /** 顶部工具栏右侧插槽，例如主按钮 */
  toolbarEnd?: ReactNode;
  "aria-label"?: string;
  className?: string;
}

function textTitle(content: ReactNode) {
  return typeof content === "string" || typeof content === "number" ? String(content) : undefined;
}

function TableSortIcon({ direction }: { direction: TableSortDirection }) {
  return <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="m4.5 6 3.5-3.5L11.5 6" opacity={direction === "desc" ? .3 : 1} />
    <path d="m4.5 10 3.5 3.5 3.5-3.5" opacity={direction === "asc" ? .3 : 1} />
  </svg>;
}

export function Table<T>({ columns, data, rowKey, caption, emptyContent = "暂无数据", minWidth = 640, layout = "fixed", maxHeight, stickyHeader = true, hideScrollbar = true, toolbarStart, toolbarEnd, "aria-label": label, className = "" }: TableProps<T>) {
  const tableRef = useRef<HTMLTableElement>(null);
  useLayoutEffect(() => {
    const table = tableRef.current;
    if (!table || !columns.some(column => column.fixed)) return;
    const cells = Array.from(table.tHead?.rows[0]?.cells ?? []);
    function measure() {
      const widths = cells.map(cell => cell.getBoundingClientRect().width);
      let left = 0;
      let right = 0;
      columns.forEach((column, index) => {
        if (column.fixed !== "left") return;
        table!.style.setProperty(`--table-fixed-${index}`, `${left}px`);
        left += widths[index] ?? 0;
      });
      for (let index = columns.length - 1; index >= 0; index--) {
        if (columns[index].fixed !== "right") continue;
        table!.style.setProperty(`--table-fixed-${index}`, `${right}px`);
        right += widths[index] ?? 0;
      }
    }
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(table);
    cells.forEach(cell => observer.observe(cell));
    return () => observer.disconnect();
  }, [columns]);

  function cellStyle(column: TableColumn<T>, index: number): CSSProperties {
    return {
      textAlign: column.align ?? "left",
      left: column.fixed === "left" ? `var(--table-fixed-${index}, 0px)` : undefined,
      right: column.fixed === "right" ? `var(--table-fixed-${index}, 0px)` : undefined,
    };
  }
  function boundary(column: TableColumn<T>, index: number) {
    if (column.fixed === "left" && columns[index + 1]?.fixed !== "left") return "left";
    if (column.fixed === "right" && columns[index - 1]?.fixed !== "right") return "right";
    return undefined;
  }

  return <div className={`studio-table-container ${className}`.trim()}>
    {(toolbarStart != null || toolbarEnd != null) && <div className="studio-table-toolbar">
      <div className="studio-table-toolbar__start">{toolbarStart}</div>
      <div className="studio-table-toolbar__end">{toolbarEnd}</div>
    </div>}
    <ScrollArea tabIndex={0} role="region" aria-label={label ?? "表格滚动区域"} orientation={maxHeight != null ? "both" : "horizontal"} maxHeight={maxHeight} hideScrollbar={hideScrollbar} className="studio-table-scroll">
      <table ref={tableRef} className="studio-table" aria-label={label} data-sticky-header={stickyHeader && maxHeight != null || undefined} style={{ minWidth, tableLayout: layout }}>
        {caption != null && <caption>{caption}</caption>}
        <colgroup>{columns.map(column => <col key={column.key} style={{ width: column.width }} />)}</colgroup>
        <thead><tr>{columns.map((column, index) => {
          const sort = column.sort;
          const filter = column.filter;
          const nextDirection: TableSortDirection = sort?.direction === "asc" ? "desc" : sort?.direction === "desc" ? null : "asc";
          const columnLabel = textTitle(column.title) ?? column.key;
          const sortLabel = sort?.["aria-label"] ?? `${columnLabel}：${nextDirection === "asc" ? "升序排列" : nextDirection === "desc" ? "降序排列" : "恢复原顺序"}`;
          return <th key={column.key} scope="col" aria-sort={sort ? sort.direction === "asc" ? "ascending" : sort.direction === "desc" ? "descending" : "none" : undefined} data-fixed={column.fixed} data-fixed-boundary={boundary(column, index)} style={cellStyle(column, index)}>
            {sort || filter ? <div className="studio-table__header-content" data-align={column.align ?? "left"}>
              <span className="studio-table__header-title">{column.title}</span>
              {sort && <Button variant="ghost" iconOnly className="studio-table__sort-button" data-active={sort.direction != null || undefined} aria-label={sortLabel} title={sortLabel} disabled={sort.disabled} startIcon={<TableSortIcon direction={sort.direction} />} onClick={() => sort.onChange(nextDirection)} />}
              {filter && <Select className="studio-table__filter" aria-label={filter["aria-label"] ?? `筛选 ${columnLabel}`} value={filter.value} options={filter.options} disabled={filter.disabled} onChange={event => filter.onChange(event.target.value)} />}
            </div> : column.title}
          </th>;
        })}</tr></thead>
        <tbody>{data.length ? data.map((row, index) => <tr key={rowKey(row)}>{columns.map((column, columnIndex) => {
          const content = column.render(row, index);
          return <td key={column.key} data-fixed={column.fixed} data-fixed-boundary={boundary(column, columnIndex)} style={cellStyle(column, columnIndex)}>
            <div className="studio-table__cell-value" data-overflow={column.overflow ?? "wrap"} title={column.overflow === "ellipsis" ? textTitle(content) : undefined}>{content}</div>
          </td>;
        })}</tr>) : <tr><td colSpan={Math.max(1, columns.length)} className="studio-table__empty">{emptyContent}</td></tr>}</tbody>
      </table>
    </ScrollArea>
  </div>;
}

export interface TableCellTextProps {
  /** 主标题 */
  title: ReactNode;
  /** 标题下方的次要说明 */
  description?: ReactNode;
  /** 标题单行省略，纯文本悬停可查看全文 */
  truncate?: boolean;
  /** 说明最大行数，省略时保留全文提示；不设置则自动换行 */
  descriptionLines?: number;
  className?: string;
}

export function TableCellText({ title, description, truncate = false, descriptionLines, className = "" }: TableCellTextProps) {
  const lines = descriptionLines != null && Number.isFinite(descriptionLines) && descriptionLines > 0 ? Math.max(1, Math.floor(descriptionLines)) : undefined;
  return <div className={`studio-table-cell-text ${className}`.trim()}>
    <div className="studio-table-cell-text__title" data-truncate={truncate || undefined} title={truncate ? textTitle(title) : undefined}>{title}</div>
    {description != null && <div className="studio-table-cell-text__description" data-clamped={lines != null || undefined} style={lines != null ? { WebkitLineClamp: lines } : undefined} title={lines != null ? textTitle(description) : undefined}>{description}</div>}
  </div>;
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
