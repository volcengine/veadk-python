import { useId, useRef, useState, type DragEvent, type HTMLAttributes } from "react";
import { DashedZone } from "../DashedZone";
import { Button } from "../../primitives/Button";
import "./FileUpload.css";

export interface FileUploadRejection {
  file: File;
  reason: "type" | "size" | "count";
  message: string;
}

export interface FileUploadProps extends Omit<HTMLAttributes<HTMLDivElement>, "onChange" | "children" | "defaultValue"> {
  /** 虚线区域中的按钮文字 */
  label?: string;
  /** 受控文件列表；组件仅选择文件，不发起网络上传 */
  files?: readonly File[];
  /** 非受控模式的初始文件列表 */
  defaultFiles?: readonly File[];
  /** 添加或移除文件后返回完整文件列表 */
  onFilesChange?: (files: File[]) => void;
  /** 原生 accept 格式，支持扩展名、MIME 类型和 image/* 等通配类型 */
  accept?: string;
  /** 单个文件的大小上限，单位为字节；不传则不限制 */
  maxSize?: number;
  /** 文件总数上限；不传则不限制，multiple=false 时最多一个 */
  maxFiles?: number;
  /** 是否允许多选；关闭时，新文件替换原文件 */
  multiple?: boolean;
  disabled?: boolean;
  /** 返回本次未通过校验的文件与原因，重复文件会直接忽略 */
  onReject?: (rejections: FileUploadRejection[]) => void;
}

function fileKey(file: File) {
  return JSON.stringify([file.name, file.size, file.lastModified]);
}

function uniqueFiles(files: readonly File[]) {
  return Array.from(new Map(files.map(file => [fileKey(file), file])).values());
}

function fileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length);
  return `${Number((bytes / 1024 ** exponent).toFixed(1))} ${units[exponent - 1]}`;
}

function matchesAccept(file: File, accept: string | undefined) {
  const types = accept?.split(",").map(type => type.trim().toLowerCase()).filter(Boolean) ?? [];
  return types.length === 0 || types.some(type => {
    if (type === "*/*") return true;
    if (type.startsWith(".")) return file.name.toLowerCase().endsWith(type);
    if (type.endsWith("/*")) return file.type.toLowerCase().startsWith(type.slice(0, -1));
    return file.type.toLowerCase() === type;
  });
}

function isFileDrag(event: DragEvent) {
  return Array.from(event.dataTransfer.types).includes("Files");
}

export function FileUpload({
  label = "添加文件",
  files,
  defaultFiles = [],
  onFilesChange,
  accept,
  maxSize,
  maxFiles,
  multiple = true,
  disabled = false,
  onReject,
  className = "",
  ...props
}: FileUploadProps) {
  const input = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);
  const [internalFiles, setInternalFiles] = useState(() => uniqueFiles(defaultFiles));
  const [dragging, setDragging] = useState(false);
  const [rejections, setRejections] = useState<FileUploadRejection[]>([]);
  const id = useId();
  const currentFiles = uniqueFiles(files ?? internalFiles);
  const countLimit = Math.max(0, Math.min(multiple ? Infinity : 1, Math.floor(maxFiles ?? Infinity)));
  const hints = [
    "支持拖拽添加文件",
    accept && `类型 ${accept.split(",").map(type => type.trim()).filter(Boolean).join("、")}`,
    maxSize !== undefined && `单个文件不超过 ${fileSize(maxSize)}`,
    Number.isFinite(countLimit) && `最多 ${countLimit} 个文件`,
  ].filter(Boolean).join(" · ");

  function update(nextFiles: File[]) {
    if (files === undefined) setInternalFiles(nextFiles);
    onFilesChange?.(nextFiles);
  }

  function addFiles(incoming: readonly File[]) {
    if (disabled || incoming.length === 0) return;
    const known = new Set(currentFiles.map(fileKey));
    const accepted: File[] = [];
    const rejected: FileUploadRejection[] = [];
    const existingCount = multiple ? currentFiles.length : 0;

    for (const file of incoming) {
      const key = fileKey(file);
      if (known.has(key)) continue;
      known.add(key);
      if (!matchesAccept(file, accept)) {
        rejected.push({ file, reason: "type", message: "不支持此文件类型" });
      } else if (maxSize !== undefined && file.size > maxSize) {
        rejected.push({ file, reason: "size", message: `文件大小不能超过 ${fileSize(maxSize)}` });
      } else if (existingCount + accepted.length >= countLimit) {
        rejected.push({ file, reason: "count", message: `最多可选择 ${countLimit} 个文件` });
      } else {
        accepted.push(file);
      }
    }

    setRejections(rejected);
    if (accepted.length > 0) update(multiple ? [...currentFiles, ...accepted] : accepted);
    if (rejected.length > 0) onReject?.(rejected);
  }

  return <div {...props} className={`studio-file-upload ${className}`.trim()} data-disabled={disabled || undefined}>
    <input
      ref={input}
      type="file"
      hidden
      aria-label={label}
      accept={accept}
      multiple={multiple}
      disabled={disabled}
      onChange={event => {
        addFiles(Array.from(event.currentTarget.files ?? []));
        event.currentTarget.value = "";
      }}
    />
    <fieldset className="studio-file-upload__field" disabled={disabled} aria-label={label} aria-describedby={`${id}-hint${rejections.length ? ` ${id}-errors` : ""}`}>
      <DashedZone
        label={dragging && !disabled ? "松开以添加文件" : label}
        className="studio-file-upload__zone"
        data-drag-active={dragging && !disabled || undefined}
        onClick={() => { if (!disabled) input.current?.click(); }}
        onDragEnter={event => {
          if (!isFileDrag(event)) return;
          event.preventDefault();
          if (!disabled) { dragDepth.current += 1; setDragging(true); }
        }}
        onDragOver={event => {
          if (!isFileDrag(event)) return;
          event.preventDefault();
          event.dataTransfer.dropEffect = disabled ? "none" : "copy";
        }}
        onDragLeave={event => {
          if (!isFileDrag(event)) return;
          dragDepth.current = Math.max(0, dragDepth.current - 1);
          if (dragDepth.current === 0) setDragging(false);
        }}
        onDrop={event => {
          if (!isFileDrag(event)) return;
          event.preventDefault();
          event.stopPropagation();
          dragDepth.current = 0;
          setDragging(false);
          addFiles(Array.from(event.dataTransfer.files));
        }}
      />
    </fieldset>
    <p id={`${id}-hint`} className="studio-file-upload__hint">{hints}</p>
    {rejections.length > 0 && <ul id={`${id}-errors`} className="studio-file-upload__errors" role="alert">
      {rejections.map(({ file, message }) => <li key={fileKey(file)}>{file.name}：{message}</li>)}
    </ul>}
    {currentFiles.length > 0 && <ul className="studio-file-upload__files" aria-label="已选择的文件">
      {currentFiles.map(file => <li className="studio-file-upload__file" key={fileKey(file)}>
        <span className="studio-file-upload__name" title={file.name}>{file.name}</span>
        <span className="studio-file-upload__size">{fileSize(file.size)}</span>
        <Button
          variant="ghost"
          size="compact"
          iconOnly
          disabled={disabled}
          aria-label={`移除 ${file.name}`}
          title={`移除 ${file.name}`}
          onClick={() => {
            if (disabled) return;
            setRejections([]);
            update(currentFiles.filter(item => fileKey(item) !== fileKey(file)));
          }}
          startIcon={<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="m4 4 8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>}
        />
      </li>)}
    </ul>}
  </div>;
}
