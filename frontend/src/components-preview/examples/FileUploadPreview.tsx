import { useState } from "react";
import { FileUpload } from "../../components/composites/FileUpload";
import { ComponentApi } from "../api/ComponentApi";
import "./FileUploadPreview.css";

export function FileUploadPreview() {
  const [files, setFiles] = useState<File[]>([]);
  return <section aria-labelledby="file-upload-preview-title">
    <h2 id="file-upload-preview-title" className="component-preview-title">File upload</h2>
    <div className="file-upload-preview__examples">
      <section aria-labelledby="file-upload-multiple-title">
        <h3 id="file-upload-multiple-title" className="file-upload-preview__subtitle">多文件选择</h3>
        <FileUpload files={files} onFilesChange={setFiles} accept=".pdf,.txt,.png,.jpg" maxSize={10 * 1024 * 1024} maxFiles={5} />
      </section>
      <section aria-labelledby="file-upload-single-title">
        <h3 id="file-upload-single-title" className="file-upload-preview__subtitle">单文件选择</h3>
        <FileUpload label="选择 PDF 文件" multiple={false} accept=".pdf" maxSize={10 * 1024 * 1024} />
      </section>
      <section aria-labelledby="file-upload-disabled-title">
        <h3 id="file-upload-disabled-title" className="file-upload-preview__subtitle">禁用状态</h3>
        <FileUpload disabled />
      </section>
    </div>
    <ComponentApi names={["FileUpload"]} />
  </section>;
}
