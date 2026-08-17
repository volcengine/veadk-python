import assert from "node:assert/strict";
import { build } from "esbuild";
import { readFileSync } from "node:fs";
import test from "node:test";

const clientSource = readFileSync(
  new URL("../src/adk/knowledge.ts", import.meta.url),
  "utf8",
);
const pageSource = readFileSync(
  new URL("../src/ui/KnowledgeLibrary.tsx", import.meta.url),
  "utf8",
);
const stylesSource = readFileSync(
  new URL("../src/ui/KnowledgeLibrary.css", import.meta.url),
  "utf8",
);
const resourceCardSource = readFileSync(
  new URL("../src/ui/LibraryResourceCard.tsx", import.meta.url),
  "utf8",
);
const resourceCardStylesSource = readFileSync(
  new URL("../src/ui/LibraryResourceCard.css", import.meta.url),
  "utf8",
);
const actionMenuSource = readFileSync(
  new URL("../src/ui/StudioActionMenu.tsx", import.meta.url),
  "utf8",
);

let knowledgeClientPromise;
function loadKnowledgeClient() {
  knowledgeClientPromise ??= build({
    entryPoints: [new URL("../src/adk/knowledge.ts", import.meta.url).pathname],
    bundle: true,
    format: "esm",
    platform: "browser",
    target: "es2022",
    write: false,
  }).then(({ outputFiles }) => import(
    `data:text/javascript;base64,${Buffer.from(outputFiles[0].text).toString("base64")}`
  ));
  return knowledgeClientPromise;
}

test("uses the AgentKit knowledge routes for base and provider document CRUD", () => {
  assert.match(clientSource, /export async function listKnowledgeBases/);
  assert.match(clientSource, /export function createKnowledgeBase/);
  assert.match(clientSource, /export function updateKnowledgeBase/);
  assert.match(clientSource, /export function deleteKnowledgeBase/);
  assert.match(clientSource, /export async function listKnowledgeDocuments/);
  assert.match(clientSource, /export function createKnowledgeDocument/);
  assert.match(clientSource, /export function uploadKnowledgeDocument/);
  assert.match(clientSource, /export function updateKnowledgeDocument/);
  assert.match(clientSource, /export function deleteKnowledgeDocument/);
  assert.match(clientSource, /export async function previewKnowledgeDocument/);
  assert.match(clientSource, /documents\/\$\{encodeURIComponent\(documentId\)\}\/preview/);
  assert.match(clientSource, /\/web\/knowledge-bases/);
  assert.doesNotMatch(clientSource, /localStorage|indexedDB|JSON\.stringify\(\{[^}]*ownerId/s);
});

test("normalizes paginated knowledge preview chunks", async () => {
  const client = await loadKnowledgeClient();
  const originalFetch = globalThis.fetch;
  let requestedUrl = "";
  globalThis.fetch = async (input) => {
    requestedUrl = String(input);
    return Response.json({
      document: { id: "doc-1", name: "资料", type: "txt" },
      chunks: [{
        id: "chunk-1",
        title: "第一段",
        content: "正文",
        attachment: { previewUrl: "https://example.com/image.png", mimeType: "image/png" },
        tableFields: { name: ["Alice"], score: [98] },
      }],
      offset: 20,
      limit: 20,
      hasMore: true,
    });
  };
  try {
    const page = await client.previewKnowledgeDocument("kb-1", "doc-1", {
      region: "cn-beijing",
      offset: 20,
      limit: 20,
    });
    assert.match(requestedUrl, /\/web\/knowledge-bases\/kb-1\/documents\/doc-1\/preview\?/);
    assert.match(requestedUrl, /region=cn-beijing/);
    assert.match(requestedUrl, /offset=20/);
    assert.equal(page.document.id, "doc-1");
    assert.equal(page.chunks[0].attachmentUrl, "https://example.com/image.png");
    assert.equal(page.chunks[0].attachmentType, "image/png");
    assert.deepEqual(page.chunks[0].tableFields, { name: ["Alice"], score: [98] });
    assert.equal(page.hasMore, true);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("preserves stable knowledge error status and codes", async () => {
  const client = await loadKnowledgeClient();
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({
    detail: {
      message: "底层 Provider 知识库已不存在，此 AgentKit 关联已失效。",
      errorCode: "KNOWLEDGE_PROVIDER_ASSOCIATION_INVALID",
      requestId: "request-123",
      diagnostics: { provider: "viking", reason: "missing collection" },
    },
  }), {
    status: 409,
    headers: { "content-type": "application/json" },
  });
  try {
    await assert.rejects(
      client.listKnowledgeDocuments("kb-invalid", { region: "cn-beijing" }),
      (error) => {
        assert.ok(error instanceof client.KnowledgeRequestError);
        assert.equal(error.status, 409);
        assert.equal(error.errorCode, "KNOWLEDGE_PROVIDER_ASSOCIATION_INVALID");
        assert.equal(error.requestId, "request-123");
        assert.deepEqual(error.diagnostics, {
          provider: "viking",
          reason: "missing collection",
        });
        assert.deepEqual(error.detail, {
          message: "底层 Provider 知识库已不存在，此 AgentKit 关联已失效。",
          errorCode: "KNOWLEDGE_PROVIDER_ASSOCIATION_INVALID",
          requestId: "request-123",
          diagnostics: { provider: "viking", reason: "missing collection" },
        });
        assert.deepEqual(error.payload, {
          detail: error.detail,
        });
        assert.match(error.rawBody, /request-123/);
        assert.match(error.message, /关联已失效/);
        assert.doesNotMatch(error.message, /missing collection/);
        return true;
      },
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("preserves FastAPI validation details without stringifying unknown fields", async () => {
  const client = await loadKnowledgeClient();
  const originalFetch = globalThis.fetch;
  const detail = [{
    type: "missing",
    loc: ["body", "name"],
    msg: "Field required",
    input: { privateToken: "must-not-appear-in-message" },
  }];
  globalThis.fetch = async () => Response.json({ detail }, { status: 422 });
  try {
    await assert.rejects(
      client.createKnowledgeBase({
        name: "test",
      }),
      (error) => {
        assert.ok(error instanceof client.KnowledgeRequestError);
        assert.equal(error.status, 422);
        assert.match(error.message, /body\.name: Field required/);
        assert.doesNotMatch(error.message, /privateToken|must-not-appear/);
        assert.deepEqual(error.detail, detail);
        assert.deepEqual(error.payload, { detail });
        return true;
      },
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("preserves non-JSON knowledge error bodies", async () => {
  const client = await loadKnowledgeClient();
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response("upstream temporarily unavailable", {
    status: 502,
    headers: { "content-type": "text/plain; charset=utf-8" },
  });
  try {
    await assert.rejects(
      client.listKnowledgeDocuments("kb-1", { region: "cn-beijing" }),
      (error) => {
        assert.ok(error instanceof client.KnowledgeRequestError);
        assert.equal(error.message, "upstream temporarily unavailable");
        assert.equal(error.detail, "upstream temporarily unavailable");
        assert.equal(error.payload, "upstream temporarily unavailable");
        assert.equal(error.rawBody, "upstream temporarily unavailable");
        assert.equal(error.requestId, "");
        assert.equal(error.diagnostics, undefined);
        return true;
      },
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("formats complete knowledge diagnostics with recursive credential redaction", async () => {
  const client = await loadKnowledgeClient();
  const error = new client.KnowledgeRequestError("Provider rejected the document", 422, {
    errorCode: "DOCUMENT_FORMAT_UNSUPPORTED",
    requestId: "request-safe-123",
    diagnostics: {
      provider: "viking",
      model: "doubao-embedding-and-m3",
      accessKey: "AKLT-secret-value",
      apiKey: "api-secret-value",
      clientSecret: "client-secret-value",
      setCookie: "session=cookie-secret-value",
      securityToken: "security-token-value",
      nested: {
        authorization: "Bearer highly-sensitive-token",
        note: "token=another-secret; api_key=api-key-in-text; Set-Cookie: session=cookie-in-text",
      },
    },
    detail: {
      message: "WAV is unsupported",
      secretKey: "secret-value",
      upstreamBody: "<html><body>gateway secret</body></html>",
    },
    payload: { shouldNotRender: "payload-secret" },
    rawBody: "raw-body-secret",
  });

  const formatted = client.formatKnowledgeError(error, "上传失败");
  assert.match(formatted, /Provider rejected the document/);
  assert.match(formatted, /状态码：422/);
  assert.match(formatted, /错误码：DOCUMENT_FORMAT_UNSUPPORTED/);
  assert.match(formatted, /请求 ID：request-safe-123/);
  assert.match(formatted, /诊断：/);
  assert.match(formatted, /doubao-embedding-and-m3/);
  assert.match(formatted, /详情：/);
  assert.match(formatted, /WAV is unsupported/);
  assert.match(formatted, /\[已脱敏\]/);
  assert.match(formatted, /\[HTML 内容已隐藏\]/);
  assert.doesNotMatch(formatted, /AKLT-secret-value|api-secret-value|client-secret-value|cookie-secret-value|security-token-value|highly-sensitive-token|another-secret|api-key-in-text|cookie-in-text|secret-value|gateway secret|payload-secret|raw-body-secret/);
});

test("does not render non-JSON HTML error bodies", async () => {
  const client = await loadKnowledgeClient();
  const originalFetch = globalThis.fetch;
  const html = "<html><body>proxy secret response</body></html>";
  globalThis.fetch = async () => new Response(html, {
    status: 502,
    headers: { "content-type": "text/html; charset=utf-8" },
  });
  try {
    await assert.rejects(
      client.listKnowledgeDocuments("kb-1", { region: "cn-beijing" }),
      (error) => {
        assert.equal(error.message, "知识库请求失败 (502)");
        assert.equal(error.rawBody, html);
        assert.equal(error.detail, html);
        const formatted = client.formatKnowledgeError(error, "加载失败");
        assert.doesNotMatch(formatted, /proxy secret response/);
        assert.match(formatted, /HTML 内容已隐藏/);
        return true;
      },
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("aggregates every region error when all knowledge regions fail", async () => {
  const client = await loadKnowledgeClient();
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input) => {
    const region = new URL(String(input), "http://localhost").searchParams.get("region");
    return Response.json({
      detail: {
        message: `${region} unavailable`,
        errorCode: `FAILED_${region}`,
        requestId: `request-${region}`,
      },
    }, { status: 503 });
  };
  try {
    await assert.rejects(
      client.listKnowledgeBasesAcrossRegions({
        regions: ["cn-beijing", "cn-shanghai"],
      }),
      (error) => {
        assert.ok(error instanceof client.KnowledgeRegionAggregateError);
        assert.equal(error.failures.length, 2);
        assert.deepEqual(error.failures.map(({ region }) => region), [
          "cn-beijing",
          "cn-shanghai",
        ]);
        assert.match(error.message, /cn-beijing: cn-beijing unavailable/);
        assert.match(error.message, /cn-shanghai: cn-shanghai unavailable/);
        assert.equal(error.failures[0].error.requestId, "request-cn-beijing");
        assert.equal(error.failures[1].error.requestId, "request-cn-shanghai");
        const formatted = client.formatKnowledgeError(error, "加载知识库失败");
        assert.match(formatted, /cn-beijing[\s\S]*状态码：503[\s\S]*request-cn-beijing/);
        assert.match(formatted, /cn-shanghai[\s\S]*状态码：503[\s\S]*request-cn-shanghai/);
        return true;
      },
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("uses the shared safe knowledge error formatter in every UI error path", () => {
  assert.match(pageSource, /import[\s\S]*?formatKnowledgeError[\s\S]*?from "\.\.\/adk\/knowledge"/);
  assert.doesNotMatch(pageSource, /function normalizeError/);
  assert.doesNotMatch(pageSource, /set(?:Documents)?Error\(reason\.message\)/);
  assert.match(pageSource, /setDocumentsError\(formatKnowledgeError\(reason,/);
});

test("disables adding knowledge when the Provider association is invalid", () => {
  assert.match(pageSource, /reason instanceof KnowledgeRequestError/);
  assert.match(pageSource, /reason\.errorCode === KNOWLEDGE_PROVIDER_ASSOCIATION_INVALID/);
  assert.match(pageSource, /const providerAssociationInvalid = Boolean/);
  assert.match(pageSource, /disabled=\{providerAssociationInvalid\}/);
  assert.match(pageSource, />删除失效关联<\/button>/);
  assert.match(pageSource, /invalidProviderKey === baseKey\(item\)/);
  assert.match(pageSource, /onAssociationInvalid=\{\(reason\) =>/);
  assert.match(pageSource, /setInvalidProviderKey\(baseKey\(createDocumentBase\)\)/);
});

test("creates provider knowledge bases from name and description only", () => {
  const dialogSource = pageSource.slice(
    pageSource.indexOf("function CreateKnowledgeBaseDialog"),
    pageSource.indexOf("function EditKnowledgeBaseDialog"),
  );
  assert.doesNotMatch(dialogSource, /Provider Knowledge ID|providerKnowledgeId/);
  assert.doesNotMatch(dialogSource, /<span>项目<\/span>|projectName/);
  assert.doesNotMatch(dialogSource, /providerType/);
  assert.match(dialogSource, /const normalizedName = name\.trim\(\)/);
  assert.match(dialogSource, /name: normalizedName/);
  assert.match(dialogSource, /description: description\.trim\(\) \|\| undefined/);
  assert.match(dialogSource, /maxLength=\{48\}/);
  assert.match(dialogSource, /maxLength=\{80\}/);
  assert.match(dialogSource, /\^\[A-Za-z\]\[A-Za-z0-9_\]\{0,47\}\$/);
  assert.match(dialogSource, /role=\{nameTouched && nameInvalid \? "alert" : undefined\}/);
  assert.doesNotMatch(pageSource, /MOCK_|fakeKnowledge|本地知识库/);
});

test("sends only name and description when creating a knowledge base", async () => {
  const client = await loadKnowledgeClient();
  const originalFetch = globalThis.fetch;
  let requestBody;
  globalThis.fetch = async (_input, init) => {
    requestBody = JSON.parse(String(init?.body));
    return Response.json({
      id: "kb-1",
      name: "support",
      description: "Team docs",
      providerType: "VIKINGDB_KNOWLEDGE",
      providerKnowledgeId: "provider-1",
      projectName: "default",
      region: "cn-beijing",
      status: "Ready",
      createdAt: "",
      updatedAt: "",
      ownerId: "user-1",
      ownerLabel: "Alice",
      canManage: true,
    });
  };
  try {
    await client.createKnowledgeBase({
      name: "support",
      description: "Team docs",
    });
    assert.deepEqual(requestBody, {
      name: "support",
      description: "Team docs",
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("covers base and document create edit delete flows", () => {
  assert.match(pageSource, /function CreateKnowledgeBaseDialog/);
  assert.match(pageSource, /function EditKnowledgeBaseDialog/);
  assert.match(pageSource, /function CreateKnowledgeDocumentDialog/);
  assert.match(pageSource, /function EditKnowledgeDocumentDialog/);
  assert.match(pageSource, /<StudioConfirmDialog title="删除知识库？"/);
  assert.match(pageSource, /<StudioConfirmDialog title="删除知识？"/);
  assert.match(pageSource, /sourceType: "url"/);
  assert.doesNotMatch(pageSource, /TOS 路径|tos:\/\//);
});

test("offers verified image document and web knowledge sources", () => {
  assert.match(pageSource, /"image", "图片"/);
  assert.match(pageSource, /"document", "文档文件"/);
  assert.match(pageSource, /"web", "在线网页"/);
  assert.match(pageSource, /role="tablist"/);
  assert.match(pageSource, /role="tabpanel"/);
  assert.match(pageSource, /type="file"/);
  assert.match(pageSource, /IMAGE_ACCEPT/);
  assert.match(pageSource, /DOCUMENT_ACCEPT/);
  assert.match(pageSource, /支持 PNG、JPG 和 JPEG/);
  assert.match(pageSource, /支持 PDF、PPTX、DOCX、XLSX 和 TXT/);
  assert.doesNotMatch(pageSource, /多模态文件|视频和音频|\.mp4|\.wav|\.doc"|\.xls"|\.ppt"|\.gif|\.webp/);
  assert.match(pageSource, /onDragEnter/);
  assert.match(pageSource, /onDrop/);
  assert.match(pageSource, /formatFileSize\(file\.size\)/);
  assert.match(pageSource, /await uploadKnowledgeDocument/);
  assert.match(pageSource, /"上传中"/);
  assert.match(stylesSource, /\.knowledge-upload-dropzone/);
  assert.match(stylesSource, /\.knowledge-source-tabs/);
});

test("uploads files through the multipart AgentKit knowledge route", () => {
  assert.match(clientSource, /const form = new FormData\(\)/);
  assert.match(clientSource, /form\.set\("file", input\.file\)/);
  assert.match(clientSource, /form\.set\("metadata", JSON\.stringify\(input\.metadata\)\)/);
  assert.match(clientSource, /documents\/upload\$\{regionQuery\(region\)\}/);
  assert.match(clientSource, /body: form/);
});

test("forwards the local user on JSON and multipart knowledge requests", async () => {
  const client = await loadKnowledgeClient();
  const originalFetch = globalThis.fetch;
  const originalLocalStorage = globalThis.localStorage;
  const originalSessionStorage = globalThis.sessionStorage;
  const requests = [];
  globalThis.localStorage = { getItem: () => "alice" };
  globalThis.sessionStorage = { getItem: () => null };
  globalThis.fetch = async (_input, init = {}) => {
    requests.push({ headers: new Headers(init.headers), body: init.body });
    return Response.json({ id: "doc-1", name: "资料" });
  };
  try {
    await client.createKnowledgeDocument("kb-1", "cn-beijing", {
      sourceType: "url",
      url: "https://example.com/article",
    });
    await client.uploadKnowledgeDocument("kb-1", "cn-beijing", {
      file: new Blob(["hello"], { type: "text/plain" }),
    });

    assert.equal(requests.length, 2);
    assert.equal(requests[0].headers.get("X-VeADK-Local-User"), "alice");
    assert.equal(requests[0].headers.get("content-type"), "application/json");
    assert.ok(requests[0].body instanceof String || typeof requests[0].body === "string");
    assert.equal(requests[1].headers.get("X-VeADK-Local-User"), "alice");
    assert.equal(requests[1].headers.get("content-type"), null);
    assert.ok(requests[1].body instanceof FormData);
  } finally {
    globalThis.fetch = originalFetch;
    if (originalLocalStorage === undefined) delete globalThis.localStorage;
    else globalThis.localStorage = originalLocalStorage;
    if (originalSessionStorage === undefined) delete globalThis.sessionStorage;
    else globalThis.sessionStorage = originalSessionStorage;
  }
});

test("renders server-authorized ownership and management capabilities", () => {
  assert.match(clientSource, /ownerId: string/);
  assert.match(clientSource, /ownerLabel: string/);
  assert.match(clientSource, /canManage: boolean/);
  assert.match(pageSource, /item\.ownerLabel/);
  assert.match(pageSource, /selected\.canManage/);
  assert.doesNotMatch(pageSource, /access\.role === "admin"|userInfo\.email/);
});

test("provides a responsive card overview and a focused detail view", () => {
  assert.match(pageSource, /正在加载知识库/);
  assert.match(pageSource, /您还没有任何知识库/);
  assert.match(pageSource, /role="alert"/);
  assert.match(pageSource, />重试</);
  assert.match(pageSource, /className="knowledge-library__grid my-agent-grid"/);
  assert.match(pageSource, /knowledge-library__toolbar my-agent-type-bar library-resource-toolbar/);
  assert.doesNotMatch(pageSource, /<h1>知识库<\/h1>/);
  assert.match(pageSource, /import \{ LibraryResourceCard \} from "\.\/LibraryResourceCard"/);
  assert.match(pageSource, /<LibraryResourceCard[\s\S]*?className="knowledge-card"/);
  assert.match(resourceCardSource, /<article className=\{`my-agent-card library-resource-card/);
  assert.match(resourceCardSource, /function LibraryResourceCardActions/);
  assert.match(resourceCardSource, /className="library-resource-card__actions"/);
  assert.match(pageSource, /\? "关联已失效" : "添加数据"/);
  assert.match(pageSource, /setCreateDocumentBase\(item\)/);
  assert.match(pageSource, /label: "创建者"/);
  assert.match(pageSource, /label: "项目"/);
  assert.match(pageSource, /label: "编辑知识库"/);
  assert.match(pageSource, /label: "删除知识库"/);
  assert.match(pageSource, /menuLabel=\{`更多知识库操作：\$\{item\.name\}`\}/);
  assert.match(resourceCardStylesSource, /grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\) 28px/);
  assert.match(resourceCardStylesSource, /\.library-resource-card \.library-resource-card__action\s*\{[^}]*font-size:\s*12px;[^}]*font-weight:\s*500;[^}]*line-height:\s*18px;/);
  assert.doesNotMatch(pageSource, /RefreshIcon|刷新知识库/);
  assert.match(pageSource, /className="my-agent-loading-mark"/);
  assert.doesNotMatch(pageSource, /项目 \/ 地域/);
  assert.doesNotMatch(pageSource, /knowledge-detail-head__icon/);
  assert.match(pageSource, /aria-label="返回知识库列表"/);
  assert.doesNotMatch(pageSource, /\{documents\.length\} 项/);
  assert.match(pageSource, /<table className="knowledge-document-table">/);
  assert.match(pageSource, /<th scope="col">名称<\/th>/);
  assert.match(pageSource, /<th scope="col">格式<\/th>/);
  assert.match(pageSource, /<th scope="col">大小<\/th>/);
  assert.doesNotMatch(pageSource, /knowledge-document-row__source/);
  assert.doesNotMatch(pageSource, /item\.url \|\| item\.tosPath/);
  assert.match(clientSource, /sizeBytes: number/);
  assert.match(stylesSource, /\.knowledge-document-table-wrap\s*\{[^}]*overflow:\s*auto;/);
  assert.match(stylesSource, /\.knowledge-documents__body\.is-table\s*\{[^}]*flex:\s*1;[^}]*border:\s*0;/);
  assert.match(stylesSource, /\.knowledge-library \.knowledge-primary-button span\s*\{[^}]*color:\s*inherit;/);
  assert.match(stylesSource, /\.knowledge-back-button\s*\{[^}]*border:\s*1px solid transparent;[^}]*background:\s*transparent;/);
  assert.match(stylesSource, /\.knowledge-detail-meta\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1\.25fr\)[^}]*width:\s*calc\(100% - 64px\);[^}]*border-radius:\s*12px;[^}]*background:\s*hsl\(var\(--panel\)\);/);
  assert.match(stylesSource, /\.knowledge-detail-meta dt\s*\{[^}]*font-size:\s*12px;/);
  assert.match(stylesSource, /\.knowledge-detail-meta dd\s*\{[^}]*font-size:\s*13\.5px;[^}]*text-overflow:\s*ellipsis;[^}]*white-space:\s*nowrap;/);
  assert.match(pageSource, /setSelectedKey\(baseKey\(item\)\)/);
  assert.match(pageSource, /event\.key === "Escape"/);
  assert.match(pageSource, /event\.key !== "Tab"/);
  assert.match(pageSource, /documentsAbort\.current\?\.abort/);
  assert.match(clientSource, /signal: options\.signal/);
  assert.match(stylesSource, /:focus-visible/);
  assert.match(stylesSource, /knowledge-keyboard-reveal:focus/);
  assert.match(
    stylesSource,
    /\.knowledge-library \.my-agent-create-primary\s*\{[^}]*font-size:\s*12\.5px;[^}]*font-weight:\s*500;/,
  );
  assert.doesNotMatch(stylesSource, /\.knowledge-library__toolbar \.knowledge-primary-button/);
  assert.match(stylesSource, /\.knowledge-region-warning\s*\{/);
  assert.match(stylesSource, /@media \(max-width: 760px\)/);
  assert.match(stylesSource, /\.knowledge-detail-meta\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1\.25fr\)[^}]*minmax\(0, 1\.1fr\)/);
  assert.match(stylesSource, /@media \(max-width: 760px\)[\s\S]*?\.knowledge-detail-meta\s*\{[^}]*grid-template-columns:\s*repeat\(2,/);
  assert.match(stylesSource, /@media \(max-width: 560px\)[\s\S]*?\.knowledge-detail-meta\s*\{[^}]*grid-template-columns:\s*1fr/);
  assert.match(stylesSource, /@media \(prefers-reduced-motion: reduce\)/);
  assert.doesNotMatch(stylesSource, /#[0-9a-f]{3,8}/i);
});

test("previews knowledge data with safe media and paginated parsed chunks", () => {
  assert.match(pageSource, /import \{ Delete, Edit, Eye \} from "@openai\/apps-sdk-ui\/components\/Icon"/);
  assert.match(pageSource, /function KnowledgeDocumentPreviewDialog/);
  assert.match(pageSource, /aria-label=\{`预览 \$\{item\.name \|\| item\.id\}`\}/);
  assert.match(pageSource, /<Eye aria-hidden="true" \/>/);
  assert.match(pageSource, /await previewKnowledgeDocument/);
  assert.match(pageSource, /正在加载数据预览/);
  assert.doesNotMatch(pageSource, /<span>\{knowledgeDocumentFormat\(document\)\}<\/span>/);
  assert.match(pageSource, /暂无可预览的数据内容/);
  assert.match(pageSource, /knowledgePreviewTable\(chunk\.tableFields\)/);
  assert.match(pageSource, /<audio[\s\S]*controls[\s\S]*preload="metadata"/);
  assert.match(pageSource, /<video[\s\S]*controls[\s\S]*playsInline/);
  assert.match(pageSource, /<img className="knowledge-preview__image"/);
  assert.match(pageSource, /target="_blank" rel="noopener noreferrer">打开原网页/);
  assert.doesNotMatch(pageSource, /<iframe[^>]+\{sourceUrl\}/);
  assert.match(pageSource, /loadPreview\(chunks\.length\)/);
  assert.match(pageSource, /a\[href\], audio\[controls\], video\[controls\]/);
  assert.match(stylesSource, /\.knowledge-dialog--preview/);
  assert.match(stylesSource, /\.knowledge-preview__table-wrap/);
  assert.match(stylesSource, /\.knowledge-preview__audio/);
  assert.match(stylesSource, /\.knowledge-preview__video/);
});

test("renders provider doc-image and image attachments as image previews", () => {
  assert.match(
    pageSource,
    /type === "image" \|\| type === "doc-image" \|\| type\.startsWith\("image\/"\)/,
  );
  assert.match(pageSource, /if \(kind === "image"\) \{/);
  assert.match(pageSource, /<img className="knowledge-preview__image"/);
});

test("previews PDF attachments and explains Office or pending preview fallbacks", () => {
  assert.match(pageSource, /type KnowledgeAttachmentKind = "image" \| "audio" \| "video" \| "pdf" \| "file" \| "none"/);
  assert.match(pageSource, /type === "pdf" \|\| type === "application\/pdf"/);
  assert.match(pageSource, /if \(PDF_PREVIEW_EXTENSIONS\.has\(extension\)\) return "pdf"/);
  assert.match(pageSource, /<iframe[\s\S]*?sandbox=""[\s\S]*?referrerPolicy="no-referrer"/);
  assert.match(pageSource, /无法显示时，在新窗口打开 PDF/);
  assert.match(pageSource, /当前格式暂不支持直接在线预览，已优先显示解析后的内容/);
  assert.match(pageSource, /function knowledgePreviewEmptyCopy/);
  assert.match(pageSource, /数据正在处理中/);
  assert.match(pageSource, /数据解析失败/);
  assert.match(pageSource, /此类文件会在知识库完成解析后显示文本、表格或页面图片/);
  assert.match(pageSource, /onClick=\{\(\) => void loadPreview\(\)\}>重新加载/);
  assert.match(pageSource, /iframe, \[tabindex\]/);
  assert.match(stylesSource, /\.knowledge-preview__pdf iframe/);
  assert.match(stylesSource, /\.knowledge-preview__file-fallback/);
});

test("auto loads document pages inside an independent table scroller", () => {
  assert.match(pageSource, /const documentsScrollRef = useRef<HTMLDivElement>\(null\)/);
  assert.match(pageSource, /const documentsLoadingRef = useRef\(false\)/);
  assert.match(pageSource, /const documentsHasMoreRef = useRef\(false\)/);
  assert.match(pageSource, /new IntersectionObserver\(/);
  assert.match(pageSource, /root: documentsScrollRef\.current/);
  assert.match(pageSource, /onScroll=\{handleDocumentsScroll\}/);
  assert.match(pageSource, /scrollHeight - scrollTop - clientHeight <= 240/);
  assert.match(pageSource, /void loadDocuments\(selected, true\)/);
  assert.match(pageSource, /documentsMoreError/);
  assert.match(pageSource, /加载更多数据失败/);
  assert.match(pageSource, /重试加载/);
  assert.doesNotMatch(pageSource, /className="knowledge-load-more"/);
  assert.match(
    stylesSource,
    /\.knowledge-documents__body\.is-table\s*\{[^}]*flex:\s*1;[^}]*overflow:\s*hidden;/,
  );
  assert.match(
    stylesSource,
    /\.knowledge-document-table-wrap\s*\{[^}]*height:\s*100%;[^}]*overflow:\s*auto;/,
  );
});

test("uses one shared resource card for knowledge actions and overflow management", () => {
  assert.match(resourceCardSource, /secondaryAction: LibraryResourceCardAction/);
  assert.match(resourceCardSource, /primaryAction: LibraryResourceCardAction/);
  assert.match(resourceCardSource, /menuActions: readonly LibraryResourceCardMenuAction\[\]/);
  assert.match(resourceCardSource, /<LibraryResourceCardActions/);
  assert.match(resourceCardSource, /<StudioActionMenu/);
  assert.match(actionMenuSource, /role="menu"/);
  assert.match(actionMenuSource, /role="menuitem"/);
  assert.doesNotMatch(resourceCardSource, /<article[^>]*onClick=/);
});

test("loads every provider region without exposing a region selector", () => {
  assert.match(clientSource, /export async function listKnowledgeBasesAcrossRegions/);
  assert.match(clientSource, /Promise\.allSettled\(requestedRegions\.map/);
  assert.match(pageSource, /cloudRegionOptions\(cloudProvider\)\.map/);
  assert.match(pageSource, /nextTokens: append \? nextTokensRef\.current : undefined/);
  assert.match(pageSource, /page\.failures\.map/);
  assert.doesNotMatch(pageSource, /知识库地域|<CreateKnowledgeBaseDialog region=|<span>地域<\/span>/);
  assert.doesNotMatch(pageSource, /部分地域暂时不可用/);
  assert.match(pageSource, /maxLength=\{80\}/);
  assert.doesNotMatch(pageSource, /maxLength=\{1000\}/);
});

test("refreshes on activation and loads additional knowledge cards while scrolling", () => {
  assert.match(pageSource, /active = true/);
  assert.match(pageSource, /activationRevision = 0/);
  assert.match(pageSource, /\[active, activationRevision, loadBases\]/);
  assert.match(pageSource, /new IntersectionObserver\(/);
  assert.match(pageSource, /rootMargin: "240px 0px"/);
  assert.match(pageSource, /onScroll=\{handleResultsScroll\}/);
  assert.match(pageSource, /void loadBases\(true\)/);
  assert.doesNotMatch(pageSource, />\{loadingMore \? "加载中" : "加载更多"\}<\/button>/);
});

test("keeps successful region results when another region fails", async () => {
  const client = await loadKnowledgeClient();
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input) => {
    const region = new URL(String(input), "http://studio.test").searchParams.get("region");
    if (region === "cn-shanghai") {
      return new Response(JSON.stringify({ detail: "上海地域暂时不可用" }), {
        status: 503,
        headers: { "content-type": "application/json" },
      });
    }
    return Response.json({
      items: [{ id: "kb-1", name: "北京知识库", region: "" }],
      nextToken: "",
    });
  };
  try {
    const page = await client.listKnowledgeBasesAcrossRegions({
      regions: ["cn-beijing", "cn-shanghai"],
    });
    assert.equal(page.items.length, 1);
    assert.equal(page.items[0].region, "cn-beijing");
    assert.equal(page.failures.length, 1);
    assert.equal(page.failures[0].region, "cn-shanghai");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("merges same-id resources by region and pages only active cursors", async () => {
  const client = await loadKnowledgeClient();
  const originalFetch = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (input) => {
    const url = new URL(String(input), "http://studio.test");
    const region = url.searchParams.get("region");
    const token = url.searchParams.get("nextToken");
    requests.push({ region, token });
    if (token === "beijing-next") {
      return Response.json({
        items: [{ id: "kb-2", name: "第二页", region }],
        nextToken: "",
      });
    }
    return Response.json({
      items: [{ id: "same-id", name: region, region }],
      nextToken: region === "cn-beijing" ? "beijing-next" : "",
    });
  };
  try {
    const first = await client.listKnowledgeBasesAcrossRegions({
      regions: ["cn-beijing", "cn-shanghai"],
    });
    assert.equal(first.items.length, 2);
    assert.deepEqual(first.nextTokens, { "cn-beijing": "beijing-next" });

    const second = await client.listKnowledgeBasesAcrossRegions({
      regions: ["cn-beijing", "cn-shanghai"],
      nextTokens: first.nextTokens,
    });
    assert.deepEqual(second.items.map((item) => item.id), ["kb-2"]);
    assert.deepEqual(requests, [
      { region: "cn-beijing", token: null },
      { region: "cn-shanghai", token: null },
      { region: "cn-beijing", token: "beijing-next" },
    ]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("normalizes knowledge API payloads and refreshes documents after create", () => {
  assert.match(clientSource, /function normalizeKnowledgeBase/);
  assert.match(clientSource, /function normalizeKnowledgeDocument/);
  assert.match(clientSource, /Array\.isArray\(page\.items\)/);
  assert.match(clientSource, /metadata: asRecord\(item\.metadata\)/);
  assert.match(pageSource, /await createKnowledgeDocument/);
  assert.match(pageSource, /await uploadKnowledgeDocument/);
  assert.match(pageSource, /if \(selected && baseKey\(selected\) === baseKey\(createDocumentBase\)\) void loadDocuments\(selected\)/);
  assert.doesNotMatch(pageSource, /if \(item\.id\)/);
});
