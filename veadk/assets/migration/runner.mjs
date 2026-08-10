#!/usr/bin/env node
import { createRequire as __agentkitCreateRequire } from "node:module"; const require = __agentkitCreateRequire(import.meta.url);
var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __getProtoOf = Object.getPrototypeOf;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __require = /* @__PURE__ */ ((x) => typeof require !== "undefined" ? require : typeof Proxy !== "undefined" ? new Proxy(x, {
  get: (a, b2) => (typeof require !== "undefined" ? require : a)[b2]
}) : x)(function(x) {
  if (typeof require !== "undefined") return require.apply(this, arguments);
  throw Error('Dynamic require of "' + x + '" is not supported');
});
var __commonJS = (cb, mod) => function __require2() {
  return mod || (0, cb[__getOwnPropNames(cb)[0]])((mod = { exports: {} }).exports, mod), mod.exports;
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
  // If the importer is in node compatibility mode or this is not an ESM
  // file that has been converted to a CommonJS file using a Babel-
  // compatible transform (i.e. "__esModule" has not been set), then set
  // "default" to the CommonJS "module.exports" for node compatibility.
  isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
  mod
));

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/nodes/identity.js
var require_identity = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/nodes/identity.js"(exports) {
    "use strict";
    var ALIAS = /* @__PURE__ */ Symbol.for("yaml.alias");
    var DOC = /* @__PURE__ */ Symbol.for("yaml.document");
    var MAP = /* @__PURE__ */ Symbol.for("yaml.map");
    var PAIR = /* @__PURE__ */ Symbol.for("yaml.pair");
    var SCALAR = /* @__PURE__ */ Symbol.for("yaml.scalar");
    var SEQ = /* @__PURE__ */ Symbol.for("yaml.seq");
    var NODE_TYPE = /* @__PURE__ */ Symbol.for("yaml.node.type");
    var isAlias = (node) => !!node && typeof node === "object" && node[NODE_TYPE] === ALIAS;
    var isDocument = (node) => !!node && typeof node === "object" && node[NODE_TYPE] === DOC;
    var isMap = (node) => !!node && typeof node === "object" && node[NODE_TYPE] === MAP;
    var isPair = (node) => !!node && typeof node === "object" && node[NODE_TYPE] === PAIR;
    var isScalar = (node) => !!node && typeof node === "object" && node[NODE_TYPE] === SCALAR;
    var isSeq = (node) => !!node && typeof node === "object" && node[NODE_TYPE] === SEQ;
    function isCollection(node) {
      if (node && typeof node === "object")
        switch (node[NODE_TYPE]) {
          case MAP:
          case SEQ:
            return true;
        }
      return false;
    }
    function isNode(node) {
      if (node && typeof node === "object")
        switch (node[NODE_TYPE]) {
          case ALIAS:
          case MAP:
          case SCALAR:
          case SEQ:
            return true;
        }
      return false;
    }
    var hasAnchor = (node) => (isScalar(node) || isCollection(node)) && !!node.anchor;
    exports.ALIAS = ALIAS;
    exports.DOC = DOC;
    exports.MAP = MAP;
    exports.NODE_TYPE = NODE_TYPE;
    exports.PAIR = PAIR;
    exports.SCALAR = SCALAR;
    exports.SEQ = SEQ;
    exports.hasAnchor = hasAnchor;
    exports.isAlias = isAlias;
    exports.isCollection = isCollection;
    exports.isDocument = isDocument;
    exports.isMap = isMap;
    exports.isNode = isNode;
    exports.isPair = isPair;
    exports.isScalar = isScalar;
    exports.isSeq = isSeq;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/visit.js
var require_visit = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/visit.js"(exports) {
    "use strict";
    var identity = require_identity();
    var BREAK = /* @__PURE__ */ Symbol("break visit");
    var SKIP = /* @__PURE__ */ Symbol("skip children");
    var REMOVE = /* @__PURE__ */ Symbol("remove node");
    function visit(node, visitor) {
      const visitor_ = initVisitor(visitor);
      if (identity.isDocument(node)) {
        const cd = visit_(null, node.contents, visitor_, Object.freeze([node]));
        if (cd === REMOVE)
          node.contents = null;
      } else
        visit_(null, node, visitor_, Object.freeze([]));
    }
    visit.BREAK = BREAK;
    visit.SKIP = SKIP;
    visit.REMOVE = REMOVE;
    function visit_(key, node, visitor, path) {
      const ctrl = callVisitor(key, node, visitor, path);
      if (identity.isNode(ctrl) || identity.isPair(ctrl)) {
        replaceNode(key, path, ctrl);
        return visit_(key, ctrl, visitor, path);
      }
      if (typeof ctrl !== "symbol") {
        if (identity.isCollection(node)) {
          path = Object.freeze(path.concat(node));
          for (let i = 0; i < node.items.length; ++i) {
            const ci = visit_(i, node.items[i], visitor, path);
            if (typeof ci === "number")
              i = ci - 1;
            else if (ci === BREAK)
              return BREAK;
            else if (ci === REMOVE) {
              node.items.splice(i, 1);
              i -= 1;
            }
          }
        } else if (identity.isPair(node)) {
          path = Object.freeze(path.concat(node));
          const ck = visit_("key", node.key, visitor, path);
          if (ck === BREAK)
            return BREAK;
          else if (ck === REMOVE)
            node.key = null;
          const cv = visit_("value", node.value, visitor, path);
          if (cv === BREAK)
            return BREAK;
          else if (cv === REMOVE)
            node.value = null;
        }
      }
      return ctrl;
    }
    async function visitAsync(node, visitor) {
      const visitor_ = initVisitor(visitor);
      if (identity.isDocument(node)) {
        const cd = await visitAsync_(null, node.contents, visitor_, Object.freeze([node]));
        if (cd === REMOVE)
          node.contents = null;
      } else
        await visitAsync_(null, node, visitor_, Object.freeze([]));
    }
    visitAsync.BREAK = BREAK;
    visitAsync.SKIP = SKIP;
    visitAsync.REMOVE = REMOVE;
    async function visitAsync_(key, node, visitor, path) {
      const ctrl = await callVisitor(key, node, visitor, path);
      if (identity.isNode(ctrl) || identity.isPair(ctrl)) {
        replaceNode(key, path, ctrl);
        return visitAsync_(key, ctrl, visitor, path);
      }
      if (typeof ctrl !== "symbol") {
        if (identity.isCollection(node)) {
          path = Object.freeze(path.concat(node));
          for (let i = 0; i < node.items.length; ++i) {
            const ci = await visitAsync_(i, node.items[i], visitor, path);
            if (typeof ci === "number")
              i = ci - 1;
            else if (ci === BREAK)
              return BREAK;
            else if (ci === REMOVE) {
              node.items.splice(i, 1);
              i -= 1;
            }
          }
        } else if (identity.isPair(node)) {
          path = Object.freeze(path.concat(node));
          const ck = await visitAsync_("key", node.key, visitor, path);
          if (ck === BREAK)
            return BREAK;
          else if (ck === REMOVE)
            node.key = null;
          const cv = await visitAsync_("value", node.value, visitor, path);
          if (cv === BREAK)
            return BREAK;
          else if (cv === REMOVE)
            node.value = null;
        }
      }
      return ctrl;
    }
    function initVisitor(visitor) {
      if (typeof visitor === "object" && (visitor.Collection || visitor.Node || visitor.Value)) {
        return Object.assign({
          Alias: visitor.Node,
          Map: visitor.Node,
          Scalar: visitor.Node,
          Seq: visitor.Node
        }, visitor.Value && {
          Map: visitor.Value,
          Scalar: visitor.Value,
          Seq: visitor.Value
        }, visitor.Collection && {
          Map: visitor.Collection,
          Seq: visitor.Collection
        }, visitor);
      }
      return visitor;
    }
    function callVisitor(key, node, visitor, path) {
      if (typeof visitor === "function")
        return visitor(key, node, path);
      if (identity.isMap(node))
        return visitor.Map?.(key, node, path);
      if (identity.isSeq(node))
        return visitor.Seq?.(key, node, path);
      if (identity.isPair(node))
        return visitor.Pair?.(key, node, path);
      if (identity.isScalar(node))
        return visitor.Scalar?.(key, node, path);
      if (identity.isAlias(node))
        return visitor.Alias?.(key, node, path);
      return void 0;
    }
    function replaceNode(key, path, node) {
      const parent = path[path.length - 1];
      if (identity.isCollection(parent)) {
        parent.items[key] = node;
      } else if (identity.isPair(parent)) {
        if (key === "key")
          parent.key = node;
        else
          parent.value = node;
      } else if (identity.isDocument(parent)) {
        parent.contents = node;
      } else {
        const pt = identity.isAlias(parent) ? "alias" : "scalar";
        throw new Error(`Cannot replace node with ${pt} parent`);
      }
    }
    exports.visit = visit;
    exports.visitAsync = visitAsync;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/doc/directives.js
var require_directives = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/doc/directives.js"(exports) {
    "use strict";
    var identity = require_identity();
    var visit = require_visit();
    var escapeChars = {
      "!": "%21",
      ",": "%2C",
      "[": "%5B",
      "]": "%5D",
      "{": "%7B",
      "}": "%7D"
    };
    var escapeTagName = (tn) => tn.replace(/[!,[\]{}]/g, (ch) => escapeChars[ch]);
    var Directives = class _Directives {
      constructor(yaml, tags) {
        this.docStart = null;
        this.docEnd = false;
        this.yaml = Object.assign({}, _Directives.defaultYaml, yaml);
        this.tags = Object.assign({}, _Directives.defaultTags, tags);
      }
      clone() {
        const copy = new _Directives(this.yaml, this.tags);
        copy.docStart = this.docStart;
        return copy;
      }
      /**
       * During parsing, get a Directives instance for the current document and
       * update the stream state according to the current version's spec.
       */
      atDocument() {
        const res = new _Directives(this.yaml, this.tags);
        switch (this.yaml.version) {
          case "1.1":
            this.atNextDocument = true;
            break;
          case "1.2":
            this.atNextDocument = false;
            this.yaml = {
              explicit: _Directives.defaultYaml.explicit,
              version: "1.2"
            };
            this.tags = Object.assign({}, _Directives.defaultTags);
            break;
        }
        return res;
      }
      /**
       * @param onError - May be called even if the action was successful
       * @returns `true` on success
       */
      add(line, onError) {
        if (this.atNextDocument) {
          this.yaml = { explicit: _Directives.defaultYaml.explicit, version: "1.1" };
          this.tags = Object.assign({}, _Directives.defaultTags);
          this.atNextDocument = false;
        }
        const parts = line.trim().split(/[ \t]+/);
        const name = parts.shift();
        switch (name) {
          case "%TAG": {
            if (parts.length !== 2) {
              onError(0, "%TAG directive should contain exactly two parts");
              if (parts.length < 2)
                return false;
            }
            const [handle, prefix] = parts;
            this.tags[handle] = prefix;
            return true;
          }
          case "%YAML": {
            this.yaml.explicit = true;
            if (parts.length !== 1) {
              onError(0, "%YAML directive should contain exactly one part");
              return false;
            }
            const [version] = parts;
            if (version === "1.1" || version === "1.2") {
              this.yaml.version = version;
              return true;
            } else {
              const isValid = /^\d+\.\d+$/.test(version);
              onError(6, `Unsupported YAML version ${version}`, isValid);
              return false;
            }
          }
          default:
            onError(0, `Unknown directive ${name}`, true);
            return false;
        }
      }
      /**
       * Resolves a tag, matching handles to those defined in %TAG directives.
       *
       * @returns Resolved tag, which may also be the non-specific tag `'!'` or a
       *   `'!local'` tag, or `null` if unresolvable.
       */
      tagName(source, onError) {
        if (source === "!")
          return "!";
        if (source[0] !== "!") {
          onError(`Not a valid tag: ${source}`);
          return null;
        }
        if (source[1] === "<") {
          const verbatim = source.slice(2, -1);
          if (verbatim === "!" || verbatim === "!!") {
            onError(`Verbatim tags aren't resolved, so ${source} is invalid.`);
            return null;
          }
          if (source[source.length - 1] !== ">")
            onError("Verbatim tags must end with a >");
          return verbatim;
        }
        const [, handle, suffix] = source.match(/^(.*!)([^!]*)$/s);
        if (!suffix)
          onError(`The ${source} tag has no suffix`);
        const prefix = this.tags[handle];
        if (prefix) {
          try {
            return prefix + decodeURIComponent(suffix);
          } catch (error) {
            onError(String(error));
            return null;
          }
        }
        if (handle === "!")
          return source;
        onError(`Could not resolve tag: ${source}`);
        return null;
      }
      /**
       * Given a fully resolved tag, returns its printable string form,
       * taking into account current tag prefixes and defaults.
       */
      tagString(tag) {
        for (const [handle, prefix] of Object.entries(this.tags)) {
          if (tag.startsWith(prefix))
            return handle + escapeTagName(tag.substring(prefix.length));
        }
        return tag[0] === "!" ? tag : `!<${tag}>`;
      }
      toString(doc) {
        const lines = this.yaml.explicit ? [`%YAML ${this.yaml.version || "1.2"}`] : [];
        const tagEntries = Object.entries(this.tags);
        let tagNames;
        if (doc && tagEntries.length > 0 && identity.isNode(doc.contents)) {
          const tags = {};
          visit.visit(doc.contents, (_key, node) => {
            if (identity.isNode(node) && node.tag)
              tags[node.tag] = true;
          });
          tagNames = Object.keys(tags);
        } else
          tagNames = [];
        for (const [handle, prefix] of tagEntries) {
          if (handle === "!!" && prefix === "tag:yaml.org,2002:")
            continue;
          if (!doc || tagNames.some((tn) => tn.startsWith(prefix)))
            lines.push(`%TAG ${handle} ${prefix}`);
        }
        return lines.join("\n");
      }
    };
    Directives.defaultYaml = { explicit: false, version: "1.2" };
    Directives.defaultTags = { "!!": "tag:yaml.org,2002:" };
    exports.Directives = Directives;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/doc/anchors.js
var require_anchors = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/doc/anchors.js"(exports) {
    "use strict";
    var identity = require_identity();
    var visit = require_visit();
    function anchorIsValid(anchor) {
      if (/[\x00-\x19\s,[\]{}]/.test(anchor)) {
        const sa = JSON.stringify(anchor);
        const msg = `Anchor must not contain whitespace or control characters: ${sa}`;
        throw new Error(msg);
      }
      return true;
    }
    function anchorNames(root) {
      const anchors = /* @__PURE__ */ new Set();
      visit.visit(root, {
        Value(_key, node) {
          if (node.anchor)
            anchors.add(node.anchor);
        }
      });
      return anchors;
    }
    function findNewAnchor(prefix, exclude) {
      for (let i = 1; true; ++i) {
        const name = `${prefix}${i}`;
        if (!exclude.has(name))
          return name;
      }
    }
    function createNodeAnchors(doc, prefix) {
      const aliasObjects = [];
      const sourceObjects = /* @__PURE__ */ new Map();
      let prevAnchors = null;
      return {
        onAnchor: (source) => {
          aliasObjects.push(source);
          prevAnchors ?? (prevAnchors = anchorNames(doc));
          const anchor = findNewAnchor(prefix, prevAnchors);
          prevAnchors.add(anchor);
          return anchor;
        },
        /**
         * With circular references, the source node is only resolved after all
         * of its child nodes are. This is why anchors are set only after all of
         * the nodes have been created.
         */
        setAnchors: () => {
          for (const source of aliasObjects) {
            const ref = sourceObjects.get(source);
            if (typeof ref === "object" && ref.anchor && (identity.isScalar(ref.node) || identity.isCollection(ref.node))) {
              ref.node.anchor = ref.anchor;
            } else {
              const error = new Error("Failed to resolve repeated object (this should not happen)");
              error.source = source;
              throw error;
            }
          }
        },
        sourceObjects
      };
    }
    exports.anchorIsValid = anchorIsValid;
    exports.anchorNames = anchorNames;
    exports.createNodeAnchors = createNodeAnchors;
    exports.findNewAnchor = findNewAnchor;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/doc/applyReviver.js
var require_applyReviver = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/doc/applyReviver.js"(exports) {
    "use strict";
    function applyReviver(reviver, obj, key, val) {
      if (val && typeof val === "object") {
        if (Array.isArray(val)) {
          for (let i = 0, len = val.length; i < len; ++i) {
            const v0 = val[i];
            const v1 = applyReviver(reviver, val, String(i), v0);
            if (v1 === void 0)
              delete val[i];
            else if (v1 !== v0)
              val[i] = v1;
          }
        } else if (val instanceof Map) {
          for (const k2 of Array.from(val.keys())) {
            const v0 = val.get(k2);
            const v1 = applyReviver(reviver, val, k2, v0);
            if (v1 === void 0)
              val.delete(k2);
            else if (v1 !== v0)
              val.set(k2, v1);
          }
        } else if (val instanceof Set) {
          for (const v0 of Array.from(val)) {
            const v1 = applyReviver(reviver, val, v0, v0);
            if (v1 === void 0)
              val.delete(v0);
            else if (v1 !== v0) {
              val.delete(v0);
              val.add(v1);
            }
          }
        } else {
          for (const [k2, v0] of Object.entries(val)) {
            const v1 = applyReviver(reviver, val, k2, v0);
            if (v1 === void 0)
              delete val[k2];
            else if (v1 !== v0)
              val[k2] = v1;
          }
        }
      }
      return reviver.call(obj, key, val);
    }
    exports.applyReviver = applyReviver;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/nodes/toJS.js
var require_toJS = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/nodes/toJS.js"(exports) {
    "use strict";
    var identity = require_identity();
    function toJS(value, arg, ctx) {
      if (Array.isArray(value))
        return value.map((v, i) => toJS(v, String(i), ctx));
      if (value && typeof value.toJSON === "function") {
        if (!ctx || !identity.hasAnchor(value))
          return value.toJSON(arg, ctx);
        const data = { aliasCount: 0, count: 1, res: void 0 };
        ctx.anchors.set(value, data);
        ctx.onCreate = (res2) => {
          data.res = res2;
          delete ctx.onCreate;
        };
        const res = value.toJSON(arg, ctx);
        if (ctx.onCreate)
          ctx.onCreate(res);
        return res;
      }
      if (typeof value === "bigint" && !ctx?.keep)
        return Number(value);
      return value;
    }
    exports.toJS = toJS;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/nodes/Node.js
var require_Node = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/nodes/Node.js"(exports) {
    "use strict";
    var applyReviver = require_applyReviver();
    var identity = require_identity();
    var toJS = require_toJS();
    var NodeBase = class {
      constructor(type) {
        Object.defineProperty(this, identity.NODE_TYPE, { value: type });
      }
      /** Create a copy of this node.  */
      clone() {
        const copy = Object.create(Object.getPrototypeOf(this), Object.getOwnPropertyDescriptors(this));
        if (this.range)
          copy.range = this.range.slice();
        return copy;
      }
      /** A plain JavaScript representation of this node. */
      toJS(doc, { mapAsMap, maxAliasCount, onAnchor, reviver } = {}) {
        if (!identity.isDocument(doc))
          throw new TypeError("A document argument is required");
        const ctx = {
          anchors: /* @__PURE__ */ new Map(),
          doc,
          keep: true,
          mapAsMap: mapAsMap === true,
          mapKeyWarned: false,
          maxAliasCount: typeof maxAliasCount === "number" ? maxAliasCount : 100
        };
        const res = toJS.toJS(this, "", ctx);
        if (typeof onAnchor === "function")
          for (const { count, res: res2 } of ctx.anchors.values())
            onAnchor(res2, count);
        return typeof reviver === "function" ? applyReviver.applyReviver(reviver, { "": res }, "", res) : res;
      }
    };
    exports.NodeBase = NodeBase;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/nodes/Alias.js
var require_Alias = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/nodes/Alias.js"(exports) {
    "use strict";
    var anchors = require_anchors();
    var visit = require_visit();
    var identity = require_identity();
    var Node = require_Node();
    var toJS = require_toJS();
    var Alias = class extends Node.NodeBase {
      constructor(source) {
        super(identity.ALIAS);
        this.source = source;
        Object.defineProperty(this, "tag", {
          set() {
            throw new Error("Alias nodes cannot have tags");
          }
        });
      }
      /**
       * Resolve the value of this alias within `doc`, finding the last
       * instance of the `source` anchor before this node.
       */
      resolve(doc, ctx) {
        if (ctx?.maxAliasCount === 0)
          throw new ReferenceError("Alias resolution is disabled");
        let nodes;
        if (ctx?.aliasResolveCache) {
          nodes = ctx.aliasResolveCache;
        } else {
          nodes = [];
          visit.visit(doc, {
            Node: (_key, node) => {
              if (identity.isAlias(node) || identity.hasAnchor(node))
                nodes.push(node);
            }
          });
          if (ctx)
            ctx.aliasResolveCache = nodes;
        }
        let found = void 0;
        for (const node of nodes) {
          if (node === this)
            break;
          if (node.anchor === this.source)
            found = node;
        }
        return found;
      }
      toJSON(_arg, ctx) {
        if (!ctx)
          return { source: this.source };
        const { anchors: anchors2, doc, maxAliasCount } = ctx;
        const source = this.resolve(doc, ctx);
        if (!source) {
          const msg = `Unresolved alias (the anchor must be set before the alias): ${this.source}`;
          throw new ReferenceError(msg);
        }
        let data = anchors2.get(source);
        if (!data) {
          toJS.toJS(source, null, ctx);
          data = anchors2.get(source);
        }
        if (data?.res === void 0) {
          const msg = "This should not happen: Alias anchor was not resolved?";
          throw new ReferenceError(msg);
        }
        if (maxAliasCount >= 0) {
          data.count += 1;
          if (data.aliasCount === 0)
            data.aliasCount = getAliasCount(doc, source, anchors2);
          if (data.count * data.aliasCount > maxAliasCount) {
            const msg = "Excessive alias count indicates a resource exhaustion attack";
            throw new ReferenceError(msg);
          }
        }
        return data.res;
      }
      toString(ctx, _onComment, _onChompKeep) {
        const src = `*${this.source}`;
        if (ctx) {
          anchors.anchorIsValid(this.source);
          if (ctx.options.verifyAliasOrder && !ctx.anchors.has(this.source)) {
            const msg = `Unresolved alias (the anchor must be set before the alias): ${this.source}`;
            throw new Error(msg);
          }
          if (ctx.implicitKey)
            return `${src} `;
        }
        return src;
      }
    };
    function getAliasCount(doc, node, anchors2) {
      if (identity.isAlias(node)) {
        const source = node.resolve(doc);
        const anchor = anchors2 && source && anchors2.get(source);
        return anchor ? anchor.count * anchor.aliasCount : 0;
      } else if (identity.isCollection(node)) {
        let count = 0;
        for (const item of node.items) {
          const c = getAliasCount(doc, item, anchors2);
          if (c > count)
            count = c;
        }
        return count;
      } else if (identity.isPair(node)) {
        const kc = getAliasCount(doc, node.key, anchors2);
        const vc = getAliasCount(doc, node.value, anchors2);
        return Math.max(kc, vc);
      }
      return 1;
    }
    exports.Alias = Alias;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/nodes/Scalar.js
var require_Scalar = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/nodes/Scalar.js"(exports) {
    "use strict";
    var identity = require_identity();
    var Node = require_Node();
    var toJS = require_toJS();
    var isScalarValue = (value) => !value || typeof value !== "function" && typeof value !== "object";
    var Scalar = class extends Node.NodeBase {
      constructor(value) {
        super(identity.SCALAR);
        this.value = value;
      }
      toJSON(arg, ctx) {
        return ctx?.keep ? this.value : toJS.toJS(this.value, arg, ctx);
      }
      toString() {
        return String(this.value);
      }
    };
    Scalar.BLOCK_FOLDED = "BLOCK_FOLDED";
    Scalar.BLOCK_LITERAL = "BLOCK_LITERAL";
    Scalar.PLAIN = "PLAIN";
    Scalar.QUOTE_DOUBLE = "QUOTE_DOUBLE";
    Scalar.QUOTE_SINGLE = "QUOTE_SINGLE";
    exports.Scalar = Scalar;
    exports.isScalarValue = isScalarValue;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/doc/createNode.js
var require_createNode = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/doc/createNode.js"(exports) {
    "use strict";
    var Alias = require_Alias();
    var identity = require_identity();
    var Scalar = require_Scalar();
    var defaultTagPrefix = "tag:yaml.org,2002:";
    function findTagObject(value, tagName, tags) {
      if (tagName) {
        const match = tags.filter((t) => t.tag === tagName);
        const tagObj = match.find((t) => !t.format) ?? match[0];
        if (!tagObj)
          throw new Error(`Tag ${tagName} not found`);
        return tagObj;
      }
      return tags.find((t) => t.identify?.(value) && !t.format);
    }
    function createNode(value, tagName, ctx) {
      if (identity.isDocument(value))
        value = value.contents;
      if (identity.isNode(value))
        return value;
      if (identity.isPair(value)) {
        const map = ctx.schema[identity.MAP].createNode?.(ctx.schema, null, ctx);
        map.items.push(value);
        return map;
      }
      if (value instanceof String || value instanceof Number || value instanceof Boolean || typeof BigInt !== "undefined" && value instanceof BigInt) {
        value = value.valueOf();
      }
      const { aliasDuplicateObjects, onAnchor, onTagObj, schema, sourceObjects } = ctx;
      let ref = void 0;
      if (aliasDuplicateObjects && value && typeof value === "object") {
        ref = sourceObjects.get(value);
        if (ref) {
          ref.anchor ?? (ref.anchor = onAnchor(value));
          return new Alias.Alias(ref.anchor);
        } else {
          ref = { anchor: null, node: null };
          sourceObjects.set(value, ref);
        }
      }
      if (tagName?.startsWith("!!"))
        tagName = defaultTagPrefix + tagName.slice(2);
      let tagObj = findTagObject(value, tagName, schema.tags);
      if (!tagObj) {
        if (value && typeof value.toJSON === "function") {
          value = value.toJSON();
        }
        if (!value || typeof value !== "object") {
          const node2 = new Scalar.Scalar(value);
          if (ref)
            ref.node = node2;
          return node2;
        }
        tagObj = value instanceof Map ? schema[identity.MAP] : Symbol.iterator in Object(value) ? schema[identity.SEQ] : schema[identity.MAP];
      }
      if (onTagObj) {
        onTagObj(tagObj);
        delete ctx.onTagObj;
      }
      const node = tagObj?.createNode ? tagObj.createNode(ctx.schema, value, ctx) : typeof tagObj?.nodeClass?.from === "function" ? tagObj.nodeClass.from(ctx.schema, value, ctx) : new Scalar.Scalar(value);
      if (tagName)
        node.tag = tagName;
      else if (!tagObj.default)
        node.tag = tagObj.tag;
      if (ref)
        ref.node = node;
      return node;
    }
    exports.createNode = createNode;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/nodes/Collection.js
var require_Collection = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/nodes/Collection.js"(exports) {
    "use strict";
    var createNode = require_createNode();
    var identity = require_identity();
    var Node = require_Node();
    function collectionFromPath(schema, path, value) {
      let v = value;
      for (let i = path.length - 1; i >= 0; --i) {
        const k2 = path[i];
        if (typeof k2 === "number" && Number.isInteger(k2) && k2 >= 0) {
          const a = [];
          a[k2] = v;
          v = a;
        } else {
          v = /* @__PURE__ */ new Map([[k2, v]]);
        }
      }
      return createNode.createNode(v, void 0, {
        aliasDuplicateObjects: false,
        keepUndefined: false,
        onAnchor: () => {
          throw new Error("This should not happen, please report a bug.");
        },
        schema,
        sourceObjects: /* @__PURE__ */ new Map()
      });
    }
    var isEmptyPath = (path) => path == null || typeof path === "object" && !!path[Symbol.iterator]().next().done;
    var Collection = class extends Node.NodeBase {
      constructor(type, schema) {
        super(type);
        Object.defineProperty(this, "schema", {
          value: schema,
          configurable: true,
          enumerable: false,
          writable: true
        });
      }
      /**
       * Create a copy of this collection.
       *
       * @param schema - If defined, overwrites the original's schema
       */
      clone(schema) {
        const copy = Object.create(Object.getPrototypeOf(this), Object.getOwnPropertyDescriptors(this));
        if (schema)
          copy.schema = schema;
        copy.items = copy.items.map((it) => identity.isNode(it) || identity.isPair(it) ? it.clone(schema) : it);
        if (this.range)
          copy.range = this.range.slice();
        return copy;
      }
      /**
       * Adds a value to the collection. For `!!map` and `!!omap` the value must
       * be a Pair instance or a `{ key, value }` object, which may not have a key
       * that already exists in the map.
       */
      addIn(path, value) {
        if (isEmptyPath(path))
          this.add(value);
        else {
          const [key, ...rest] = path;
          const node = this.get(key, true);
          if (identity.isCollection(node))
            node.addIn(rest, value);
          else if (node === void 0 && this.schema)
            this.set(key, collectionFromPath(this.schema, rest, value));
          else
            throw new Error(`Expected YAML collection at ${key}. Remaining path: ${rest}`);
        }
      }
      /**
       * Removes a value from the collection.
       * @returns `true` if the item was found and removed.
       */
      deleteIn(path) {
        const [key, ...rest] = path;
        if (rest.length === 0)
          return this.delete(key);
        const node = this.get(key, true);
        if (identity.isCollection(node))
          return node.deleteIn(rest);
        else
          throw new Error(`Expected YAML collection at ${key}. Remaining path: ${rest}`);
      }
      /**
       * Returns item at `key`, or `undefined` if not found. By default unwraps
       * scalar values from their surrounding node; to disable set `keepScalar` to
       * `true` (collections are always returned intact).
       */
      getIn(path, keepScalar) {
        const [key, ...rest] = path;
        const node = this.get(key, true);
        if (rest.length === 0)
          return !keepScalar && identity.isScalar(node) ? node.value : node;
        else
          return identity.isCollection(node) ? node.getIn(rest, keepScalar) : void 0;
      }
      hasAllNullValues(allowScalar) {
        return this.items.every((node) => {
          if (!identity.isPair(node))
            return false;
          const n = node.value;
          return n == null || allowScalar && identity.isScalar(n) && n.value == null && !n.commentBefore && !n.comment && !n.tag;
        });
      }
      /**
       * Checks if the collection includes a value with the key `key`.
       */
      hasIn(path) {
        const [key, ...rest] = path;
        if (rest.length === 0)
          return this.has(key);
        const node = this.get(key, true);
        return identity.isCollection(node) ? node.hasIn(rest) : false;
      }
      /**
       * Sets a value in this collection. For `!!set`, `value` needs to be a
       * boolean to add/remove the item from the set.
       */
      setIn(path, value) {
        const [key, ...rest] = path;
        if (rest.length === 0) {
          this.set(key, value);
        } else {
          const node = this.get(key, true);
          if (identity.isCollection(node))
            node.setIn(rest, value);
          else if (node === void 0 && this.schema)
            this.set(key, collectionFromPath(this.schema, rest, value));
          else
            throw new Error(`Expected YAML collection at ${key}. Remaining path: ${rest}`);
        }
      }
    };
    exports.Collection = Collection;
    exports.collectionFromPath = collectionFromPath;
    exports.isEmptyPath = isEmptyPath;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/stringify/stringifyComment.js
var require_stringifyComment = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/stringify/stringifyComment.js"(exports) {
    "use strict";
    var stringifyComment = (str) => str.replace(/^(?!$)(?: $)?/gm, "#");
    function indentComment(comment, indent) {
      if (/^\n+$/.test(comment))
        return comment.substring(1);
      return indent ? comment.replace(/^(?! *$)/gm, indent) : comment;
    }
    var lineComment = (str, indent, comment) => str.endsWith("\n") ? indentComment(comment, indent) : comment.includes("\n") ? "\n" + indentComment(comment, indent) : (str.endsWith(" ") ? "" : " ") + comment;
    exports.indentComment = indentComment;
    exports.lineComment = lineComment;
    exports.stringifyComment = stringifyComment;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/stringify/foldFlowLines.js
var require_foldFlowLines = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/stringify/foldFlowLines.js"(exports) {
    "use strict";
    var FOLD_FLOW = "flow";
    var FOLD_BLOCK = "block";
    var FOLD_QUOTED = "quoted";
    function foldFlowLines(text, indent, mode = "flow", { indentAtStart, lineWidth = 80, minContentWidth = 20, onFold, onOverflow } = {}) {
      if (!lineWidth || lineWidth < 0)
        return text;
      if (lineWidth < minContentWidth)
        minContentWidth = 0;
      const endStep = Math.max(1 + minContentWidth, 1 + lineWidth - indent.length);
      if (text.length <= endStep)
        return text;
      const folds = [];
      const escapedFolds = {};
      let end = lineWidth - indent.length;
      if (typeof indentAtStart === "number") {
        if (indentAtStart > lineWidth - Math.max(2, minContentWidth))
          folds.push(0);
        else
          end = lineWidth - indentAtStart;
      }
      let split = void 0;
      let prev = void 0;
      let overflow = false;
      let i = -1;
      let escStart = -1;
      let escEnd = -1;
      if (mode === FOLD_BLOCK) {
        i = consumeMoreIndentedLines(text, i, indent.length);
        if (i !== -1)
          end = i + endStep;
      }
      for (let ch; ch = text[i += 1]; ) {
        if (mode === FOLD_QUOTED && ch === "\\") {
          escStart = i;
          switch (text[i + 1]) {
            case "x":
              i += 3;
              break;
            case "u":
              i += 5;
              break;
            case "U":
              i += 9;
              break;
            default:
              i += 1;
          }
          escEnd = i;
        }
        if (ch === "\n") {
          if (mode === FOLD_BLOCK)
            i = consumeMoreIndentedLines(text, i, indent.length);
          end = i + indent.length + endStep;
          split = void 0;
        } else {
          if (ch === " " && prev && prev !== " " && prev !== "\n" && prev !== "	") {
            const next = text[i + 1];
            if (next && next !== " " && next !== "\n" && next !== "	")
              split = i;
          }
          if (i >= end) {
            if (split) {
              folds.push(split);
              end = split + endStep;
              split = void 0;
            } else if (mode === FOLD_QUOTED) {
              while (prev === " " || prev === "	") {
                prev = ch;
                ch = text[i += 1];
                overflow = true;
              }
              const j2 = i > escEnd + 1 ? i - 2 : escStart - 1;
              if (escapedFolds[j2])
                return text;
              folds.push(j2);
              escapedFolds[j2] = true;
              end = j2 + endStep;
              split = void 0;
            } else {
              overflow = true;
            }
          }
        }
        prev = ch;
      }
      if (overflow && onOverflow)
        onOverflow();
      if (folds.length === 0)
        return text;
      if (onFold)
        onFold();
      let res = text.slice(0, folds[0]);
      for (let i2 = 0; i2 < folds.length; ++i2) {
        const fold = folds[i2];
        const end2 = folds[i2 + 1] || text.length;
        if (fold === 0)
          res = `
${indent}${text.slice(0, end2)}`;
        else {
          if (mode === FOLD_QUOTED && escapedFolds[fold])
            res += `${text[fold]}\\`;
          res += `
${indent}${text.slice(fold + 1, end2)}`;
        }
      }
      return res;
    }
    function consumeMoreIndentedLines(text, i, indent) {
      let end = i;
      let start = i + 1;
      let ch = text[start];
      while (ch === " " || ch === "	") {
        if (i < start + indent) {
          ch = text[++i];
        } else {
          do {
            ch = text[++i];
          } while (ch && ch !== "\n");
          end = i;
          start = i + 1;
          ch = text[start];
        }
      }
      return end;
    }
    exports.FOLD_BLOCK = FOLD_BLOCK;
    exports.FOLD_FLOW = FOLD_FLOW;
    exports.FOLD_QUOTED = FOLD_QUOTED;
    exports.foldFlowLines = foldFlowLines;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/stringify/stringifyString.js
var require_stringifyString = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/stringify/stringifyString.js"(exports) {
    "use strict";
    var Scalar = require_Scalar();
    var foldFlowLines = require_foldFlowLines();
    var getFoldOptions = (ctx, isBlock) => ({
      indentAtStart: isBlock ? ctx.indent.length : ctx.indentAtStart,
      lineWidth: ctx.options.lineWidth,
      minContentWidth: ctx.options.minContentWidth
    });
    var containsDocumentMarker = (str) => /^(%|---|\.\.\.)/m.test(str);
    function lineLengthOverLimit(str, lineWidth, indentLength) {
      if (!lineWidth || lineWidth < 0)
        return false;
      const limit = lineWidth - indentLength;
      const strLen = str.length;
      if (strLen <= limit)
        return false;
      for (let i = 0, start = 0; i < strLen; ++i) {
        if (str[i] === "\n") {
          if (i - start > limit)
            return true;
          start = i + 1;
          if (strLen - start <= limit)
            return false;
        }
      }
      return true;
    }
    function doubleQuotedString(value, ctx) {
      const json = JSON.stringify(value);
      if (ctx.options.doubleQuotedAsJSON)
        return json;
      const { implicitKey } = ctx;
      const minMultiLineLength = ctx.options.doubleQuotedMinMultiLineLength;
      const indent = ctx.indent || (containsDocumentMarker(value) ? "  " : "");
      let str = "";
      let start = 0;
      for (let i = 0, ch = json[i]; ch; ch = json[++i]) {
        if (ch === " " && json[i + 1] === "\\" && json[i + 2] === "n") {
          str += json.slice(start, i) + "\\ ";
          i += 1;
          start = i;
          ch = "\\";
        }
        if (ch === "\\")
          switch (json[i + 1]) {
            case "u":
              {
                str += json.slice(start, i);
                const code = json.substr(i + 2, 4);
                switch (code) {
                  case "0000":
                    str += "\\0";
                    break;
                  case "0007":
                    str += "\\a";
                    break;
                  case "000b":
                    str += "\\v";
                    break;
                  case "001b":
                    str += "\\e";
                    break;
                  case "0085":
                    str += "\\N";
                    break;
                  case "00a0":
                    str += "\\_";
                    break;
                  case "2028":
                    str += "\\L";
                    break;
                  case "2029":
                    str += "\\P";
                    break;
                  default:
                    if (code.substr(0, 2) === "00")
                      str += "\\x" + code.substr(2);
                    else
                      str += json.substr(i, 6);
                }
                i += 5;
                start = i + 1;
              }
              break;
            case "n":
              if (implicitKey || json[i + 2] === '"' || json.length < minMultiLineLength) {
                i += 1;
              } else {
                str += json.slice(start, i) + "\n\n";
                while (json[i + 2] === "\\" && json[i + 3] === "n" && json[i + 4] !== '"') {
                  str += "\n";
                  i += 2;
                }
                str += indent;
                if (json[i + 2] === " ")
                  str += "\\";
                i += 1;
                start = i + 1;
              }
              break;
            default:
              i += 1;
          }
      }
      str = start ? str + json.slice(start) : json;
      return implicitKey ? str : foldFlowLines.foldFlowLines(str, indent, foldFlowLines.FOLD_QUOTED, getFoldOptions(ctx, false));
    }
    function singleQuotedString(value, ctx) {
      if (ctx.options.singleQuote === false || ctx.implicitKey && value.includes("\n") || /[ \t]\n|\n[ \t]/.test(value))
        return doubleQuotedString(value, ctx);
      const indent = ctx.indent || (containsDocumentMarker(value) ? "  " : "");
      const res = "'" + value.replace(/'/g, "''").replace(/\n+/g, `$&
${indent}`) + "'";
      return ctx.implicitKey ? res : foldFlowLines.foldFlowLines(res, indent, foldFlowLines.FOLD_FLOW, getFoldOptions(ctx, false));
    }
    function quotedString(value, ctx) {
      const { singleQuote } = ctx.options;
      let qs;
      if (singleQuote === false)
        qs = doubleQuotedString;
      else {
        const hasDouble = value.includes('"');
        const hasSingle = value.includes("'");
        if (hasDouble && !hasSingle)
          qs = singleQuotedString;
        else if (hasSingle && !hasDouble)
          qs = doubleQuotedString;
        else
          qs = singleQuote ? singleQuotedString : doubleQuotedString;
      }
      return qs(value, ctx);
    }
    var blockEndNewlines;
    try {
      blockEndNewlines = new RegExp("(^|(?<!\n))\n+(?!\n|$)", "g");
    } catch {
      blockEndNewlines = /\n+(?!\n|$)/g;
    }
    function blockString({ comment, type, value }, ctx, onComment, onChompKeep) {
      const { blockQuote, commentString, lineWidth } = ctx.options;
      if (!blockQuote || /\n[\t ]+$/.test(value)) {
        return quotedString(value, ctx);
      }
      const indent = ctx.indent || (ctx.forceBlockIndent || containsDocumentMarker(value) ? "  " : "");
      const literal = blockQuote === "literal" ? true : blockQuote === "folded" || type === Scalar.Scalar.BLOCK_FOLDED ? false : type === Scalar.Scalar.BLOCK_LITERAL ? true : !lineLengthOverLimit(value, lineWidth, indent.length);
      if (!value)
        return literal ? "|\n" : ">\n";
      let chomp;
      let endStart;
      for (endStart = value.length; endStart > 0; --endStart) {
        const ch = value[endStart - 1];
        if (ch !== "\n" && ch !== "	" && ch !== " ")
          break;
      }
      let end = value.substring(endStart);
      const endNlPos = end.indexOf("\n");
      if (endNlPos === -1) {
        chomp = "-";
      } else if (value === end || endNlPos !== end.length - 1) {
        chomp = "+";
        if (onChompKeep)
          onChompKeep();
      } else {
        chomp = "";
      }
      if (end) {
        value = value.slice(0, -end.length);
        if (end[end.length - 1] === "\n")
          end = end.slice(0, -1);
        end = end.replace(blockEndNewlines, `$&${indent}`);
      }
      let startWithSpace = false;
      let startEnd;
      let startNlPos = -1;
      for (startEnd = 0; startEnd < value.length; ++startEnd) {
        const ch = value[startEnd];
        if (ch === " ")
          startWithSpace = true;
        else if (ch === "\n")
          startNlPos = startEnd;
        else
          break;
      }
      let start = value.substring(0, startNlPos < startEnd ? startNlPos + 1 : startEnd);
      if (start) {
        value = value.substring(start.length);
        start = start.replace(/\n+/g, `$&${indent}`);
      }
      const indentSize = indent ? "2" : "1";
      let header = (startWithSpace ? indentSize : "") + chomp;
      if (comment) {
        header += " " + commentString(comment.replace(/ ?[\r\n]+/g, " "));
        if (onComment)
          onComment();
      }
      if (!literal) {
        const foldedValue = value.replace(/\n+/g, "\n$&").replace(/(?:^|\n)([\t ].*)(?:([\n\t ]*)\n(?![\n\t ]))?/g, "$1$2").replace(/\n+/g, `$&${indent}`);
        let literalFallback = false;
        const foldOptions = getFoldOptions(ctx, true);
        if (blockQuote !== "folded" && type !== Scalar.Scalar.BLOCK_FOLDED) {
          foldOptions.onOverflow = () => {
            literalFallback = true;
          };
        }
        const body = foldFlowLines.foldFlowLines(`${start}${foldedValue}${end}`, indent, foldFlowLines.FOLD_BLOCK, foldOptions);
        if (!literalFallback)
          return `>${header}
${indent}${body}`;
      }
      value = value.replace(/\n+/g, `$&${indent}`);
      return `|${header}
${indent}${start}${value}${end}`;
    }
    function plainString(item, ctx, onComment, onChompKeep) {
      const { type, value } = item;
      const { actualString, implicitKey, indent, indentStep, inFlow } = ctx;
      if (implicitKey && value.includes("\n") || inFlow && /[[\]{},]/.test(value)) {
        return quotedString(value, ctx);
      }
      if (/^[\n\t ,[\]{}#&*!|>'"%@`]|^[?-]$|^[?-][ \t]|[\n:][ \t]|[ \t]\n|[\n\t ]#|[\n\t :]$/.test(value)) {
        return implicitKey || inFlow || !value.includes("\n") ? quotedString(value, ctx) : blockString(item, ctx, onComment, onChompKeep);
      }
      if (!implicitKey && !inFlow && type !== Scalar.Scalar.PLAIN && value.includes("\n")) {
        return blockString(item, ctx, onComment, onChompKeep);
      }
      if (containsDocumentMarker(value)) {
        if (indent === "") {
          ctx.forceBlockIndent = true;
          return blockString(item, ctx, onComment, onChompKeep);
        } else if (implicitKey && indent === indentStep) {
          return quotedString(value, ctx);
        }
      }
      const str = value.replace(/\n+/g, `$&
${indent}`);
      if (actualString) {
        const test = (tag) => tag.default && tag.tag !== "tag:yaml.org,2002:str" && tag.test?.test(str);
        const { compat, tags } = ctx.doc.schema;
        if (tags.some(test) || compat?.some(test))
          return quotedString(value, ctx);
      }
      return implicitKey ? str : foldFlowLines.foldFlowLines(str, indent, foldFlowLines.FOLD_FLOW, getFoldOptions(ctx, false));
    }
    function stringifyString(item, ctx, onComment, onChompKeep) {
      const { implicitKey, inFlow } = ctx;
      const ss = typeof item.value === "string" ? item : Object.assign({}, item, { value: String(item.value) });
      let { type } = item;
      if (type !== Scalar.Scalar.QUOTE_DOUBLE) {
        if (/[\x00-\x08\x0b-\x1f\x7f-\x9f\u{D800}-\u{DFFF}]/u.test(ss.value))
          type = Scalar.Scalar.QUOTE_DOUBLE;
      }
      const _stringify = (_type) => {
        switch (_type) {
          case Scalar.Scalar.BLOCK_FOLDED:
          case Scalar.Scalar.BLOCK_LITERAL:
            return implicitKey || inFlow ? quotedString(ss.value, ctx) : blockString(ss, ctx, onComment, onChompKeep);
          case Scalar.Scalar.QUOTE_DOUBLE:
            return doubleQuotedString(ss.value, ctx);
          case Scalar.Scalar.QUOTE_SINGLE:
            return singleQuotedString(ss.value, ctx);
          case Scalar.Scalar.PLAIN:
            return plainString(ss, ctx, onComment, onChompKeep);
          default:
            return null;
        }
      };
      let res = _stringify(type);
      if (res === null) {
        const { defaultKeyType, defaultStringType } = ctx.options;
        const t = implicitKey && defaultKeyType || defaultStringType;
        res = _stringify(t);
        if (res === null)
          throw new Error(`Unsupported default string type ${t}`);
      }
      return res;
    }
    exports.stringifyString = stringifyString;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/stringify/stringify.js
var require_stringify = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/stringify/stringify.js"(exports) {
    "use strict";
    var anchors = require_anchors();
    var identity = require_identity();
    var stringifyComment = require_stringifyComment();
    var stringifyString = require_stringifyString();
    function createStringifyContext(doc, options) {
      const opt = Object.assign({
        blockQuote: true,
        commentString: stringifyComment.stringifyComment,
        defaultKeyType: null,
        defaultStringType: "PLAIN",
        directives: null,
        doubleQuotedAsJSON: false,
        doubleQuotedMinMultiLineLength: 40,
        falseStr: "false",
        flowCollectionPadding: true,
        indentSeq: true,
        lineWidth: 80,
        minContentWidth: 20,
        nullStr: "null",
        simpleKeys: false,
        singleQuote: null,
        trailingComma: false,
        trueStr: "true",
        verifyAliasOrder: true
      }, doc.schema.toStringOptions, options);
      let inFlow;
      switch (opt.collectionStyle) {
        case "block":
          inFlow = false;
          break;
        case "flow":
          inFlow = true;
          break;
        default:
          inFlow = null;
      }
      return {
        anchors: /* @__PURE__ */ new Set(),
        doc,
        flowCollectionPadding: opt.flowCollectionPadding ? " " : "",
        indent: "",
        indentStep: typeof opt.indent === "number" ? " ".repeat(opt.indent) : "  ",
        inFlow,
        options: opt
      };
    }
    function getTagObject(tags, item) {
      if (item.tag) {
        const match = tags.filter((t) => t.tag === item.tag);
        if (match.length > 0)
          return match.find((t) => t.format === item.format) ?? match[0];
      }
      let tagObj = void 0;
      let obj;
      if (identity.isScalar(item)) {
        obj = item.value;
        let match = tags.filter((t) => t.identify?.(obj));
        if (match.length > 1) {
          const testMatch = match.filter((t) => t.test);
          if (testMatch.length > 0)
            match = testMatch;
        }
        tagObj = match.find((t) => t.format === item.format) ?? match.find((t) => !t.format);
      } else {
        obj = item;
        tagObj = tags.find((t) => t.nodeClass && obj instanceof t.nodeClass);
      }
      if (!tagObj) {
        const name = obj?.constructor?.name ?? (obj === null ? "null" : typeof obj);
        throw new Error(`Tag not resolved for ${name} value`);
      }
      return tagObj;
    }
    function stringifyProps(node, tagObj, { anchors: anchors$1, doc }) {
      if (!doc.directives)
        return "";
      const props = [];
      const anchor = (identity.isScalar(node) || identity.isCollection(node)) && node.anchor;
      if (anchor && anchors.anchorIsValid(anchor)) {
        anchors$1.add(anchor);
        props.push(`&${anchor}`);
      }
      const tag = node.tag ?? (tagObj.default ? null : tagObj.tag);
      if (tag)
        props.push(doc.directives.tagString(tag));
      return props.join(" ");
    }
    function stringify(item, ctx, onComment, onChompKeep) {
      if (identity.isPair(item))
        return item.toString(ctx, onComment, onChompKeep);
      if (identity.isAlias(item)) {
        if (ctx.doc.directives)
          return item.toString(ctx);
        if (ctx.resolvedAliases?.has(item)) {
          throw new TypeError(`Cannot stringify circular structure without alias nodes`);
        } else {
          if (ctx.resolvedAliases)
            ctx.resolvedAliases.add(item);
          else
            ctx.resolvedAliases = /* @__PURE__ */ new Set([item]);
          item = item.resolve(ctx.doc);
        }
      }
      let tagObj = void 0;
      const node = identity.isNode(item) ? item : ctx.doc.createNode(item, { onTagObj: (o2) => tagObj = o2 });
      tagObj ?? (tagObj = getTagObject(ctx.doc.schema.tags, node));
      const props = stringifyProps(node, tagObj, ctx);
      if (props.length > 0)
        ctx.indentAtStart = (ctx.indentAtStart ?? 0) + props.length + 1;
      const str = typeof tagObj.stringify === "function" ? tagObj.stringify(node, ctx, onComment, onChompKeep) : identity.isScalar(node) ? stringifyString.stringifyString(node, ctx, onComment, onChompKeep) : node.toString(ctx, onComment, onChompKeep);
      if (!props)
        return str;
      return identity.isScalar(node) || str[0] === "{" || str[0] === "[" ? `${props} ${str}` : `${props}
${ctx.indent}${str}`;
    }
    exports.createStringifyContext = createStringifyContext;
    exports.stringify = stringify;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/stringify/stringifyPair.js
var require_stringifyPair = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/stringify/stringifyPair.js"(exports) {
    "use strict";
    var identity = require_identity();
    var Scalar = require_Scalar();
    var stringify = require_stringify();
    var stringifyComment = require_stringifyComment();
    function stringifyPair({ key, value }, ctx, onComment, onChompKeep) {
      const { allNullValues, doc, indent, indentStep, options: { commentString, indentSeq, simpleKeys } } = ctx;
      let keyComment = identity.isNode(key) && key.comment || null;
      if (simpleKeys) {
        if (keyComment) {
          throw new Error("With simple keys, key nodes cannot have comments");
        }
        if (identity.isCollection(key) || !identity.isNode(key) && typeof key === "object") {
          const msg = "With simple keys, collection cannot be used as a key value";
          throw new Error(msg);
        }
      }
      let explicitKey = !simpleKeys && (!key || keyComment && value == null && !ctx.inFlow || identity.isCollection(key) || (identity.isScalar(key) ? key.type === Scalar.Scalar.BLOCK_FOLDED || key.type === Scalar.Scalar.BLOCK_LITERAL : typeof key === "object"));
      ctx = Object.assign({}, ctx, {
        allNullValues: false,
        implicitKey: !explicitKey && (simpleKeys || !allNullValues),
        indent: indent + indentStep
      });
      let keyCommentDone = false;
      let chompKeep = false;
      let str = stringify.stringify(key, ctx, () => keyCommentDone = true, () => chompKeep = true);
      if (!explicitKey && !ctx.inFlow && str.length > 1024) {
        if (simpleKeys)
          throw new Error("With simple keys, single line scalar must not span more than 1024 characters");
        explicitKey = true;
      }
      if (ctx.inFlow) {
        if (allNullValues || value == null) {
          if (keyCommentDone && onComment)
            onComment();
          return str === "" ? "?" : explicitKey ? `? ${str}` : str;
        }
      } else if (allNullValues && !simpleKeys || value == null && explicitKey) {
        str = `? ${str}`;
        if (keyComment && !keyCommentDone) {
          str += stringifyComment.lineComment(str, ctx.indent, commentString(keyComment));
        } else if (chompKeep && onChompKeep)
          onChompKeep();
        return str;
      }
      if (keyCommentDone)
        keyComment = null;
      if (explicitKey) {
        if (keyComment)
          str += stringifyComment.lineComment(str, ctx.indent, commentString(keyComment));
        str = `? ${str}
${indent}:`;
      } else {
        str = `${str}:`;
        if (keyComment)
          str += stringifyComment.lineComment(str, ctx.indent, commentString(keyComment));
      }
      let vsb, vcb, valueComment;
      if (identity.isNode(value)) {
        vsb = !!value.spaceBefore;
        vcb = value.commentBefore;
        valueComment = value.comment;
      } else {
        vsb = false;
        vcb = null;
        valueComment = null;
        if (value && typeof value === "object")
          value = doc.createNode(value);
      }
      ctx.implicitKey = false;
      if (!explicitKey && !keyComment && identity.isScalar(value))
        ctx.indentAtStart = str.length + 1;
      chompKeep = false;
      if (!indentSeq && indentStep.length >= 2 && !ctx.inFlow && !explicitKey && identity.isSeq(value) && !value.flow && !value.tag && !value.anchor) {
        ctx.indent = ctx.indent.substring(2);
      }
      let valueCommentDone = false;
      const valueStr = stringify.stringify(value, ctx, () => valueCommentDone = true, () => chompKeep = true);
      let ws = " ";
      if (keyComment || vsb || vcb) {
        ws = vsb ? "\n" : "";
        if (vcb) {
          const cs = commentString(vcb);
          ws += `
${stringifyComment.indentComment(cs, ctx.indent)}`;
        }
        if (valueStr === "" && !ctx.inFlow) {
          if (ws === "\n" && valueComment)
            ws = "\n\n";
        } else {
          ws += `
${ctx.indent}`;
        }
      } else if (!explicitKey && identity.isCollection(value)) {
        const vs0 = valueStr[0];
        const nl0 = valueStr.indexOf("\n");
        const hasNewline = nl0 !== -1;
        const flow = ctx.inFlow ?? value.flow ?? value.items.length === 0;
        if (hasNewline || !flow) {
          let hasPropsLine = false;
          if (hasNewline && (vs0 === "&" || vs0 === "!")) {
            let sp0 = valueStr.indexOf(" ");
            if (vs0 === "&" && sp0 !== -1 && sp0 < nl0 && valueStr[sp0 + 1] === "!") {
              sp0 = valueStr.indexOf(" ", sp0 + 1);
            }
            if (sp0 === -1 || nl0 < sp0)
              hasPropsLine = true;
          }
          if (!hasPropsLine)
            ws = `
${ctx.indent}`;
        }
      } else if (valueStr === "" || valueStr[0] === "\n") {
        ws = "";
      }
      str += ws + valueStr;
      if (ctx.inFlow) {
        if (valueCommentDone && onComment)
          onComment();
      } else if (valueComment && !valueCommentDone) {
        str += stringifyComment.lineComment(str, ctx.indent, commentString(valueComment));
      } else if (chompKeep && onChompKeep) {
        onChompKeep();
      }
      return str;
    }
    exports.stringifyPair = stringifyPair;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/log.js
var require_log = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/log.js"(exports) {
    "use strict";
    var node_process = __require("process");
    function debug(logLevel, ...messages) {
      if (logLevel === "debug")
        console.log(...messages);
    }
    function warn(logLevel, warning) {
      if (logLevel === "debug" || logLevel === "warn") {
        if (typeof node_process.emitWarning === "function")
          node_process.emitWarning(warning);
        else
          console.warn(warning);
      }
    }
    exports.debug = debug;
    exports.warn = warn;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/yaml-1.1/merge.js
var require_merge = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/yaml-1.1/merge.js"(exports) {
    "use strict";
    var identity = require_identity();
    var Scalar = require_Scalar();
    var MERGE_KEY = "<<";
    var merge = {
      identify: (value) => value === MERGE_KEY || typeof value === "symbol" && value.description === MERGE_KEY,
      default: "key",
      tag: "tag:yaml.org,2002:merge",
      test: /^<<$/,
      resolve: () => Object.assign(new Scalar.Scalar(Symbol(MERGE_KEY)), {
        addToJSMap: addMergeToJSMap
      }),
      stringify: () => MERGE_KEY
    };
    var isMergeKey = (ctx, key) => (merge.identify(key) || identity.isScalar(key) && (!key.type || key.type === Scalar.Scalar.PLAIN) && merge.identify(key.value)) && ctx?.doc.schema.tags.some((tag) => tag.tag === merge.tag && tag.default);
    function addMergeToJSMap(ctx, map, value) {
      const source = resolveAliasValue(ctx, value);
      if (identity.isSeq(source))
        for (const it of source.items)
          mergeValue(ctx, map, it);
      else if (Array.isArray(source))
        for (const it of source)
          mergeValue(ctx, map, it);
      else
        mergeValue(ctx, map, source);
    }
    function mergeValue(ctx, map, value) {
      const source = resolveAliasValue(ctx, value);
      if (!identity.isMap(source))
        throw new Error("Merge sources must be maps or map aliases");
      const srcMap = source.toJSON(null, ctx, Map);
      for (const [key, value2] of srcMap) {
        if (map instanceof Map) {
          if (!map.has(key))
            map.set(key, value2);
        } else if (map instanceof Set) {
          map.add(key);
        } else if (!Object.prototype.hasOwnProperty.call(map, key)) {
          Object.defineProperty(map, key, {
            value: value2,
            writable: true,
            enumerable: true,
            configurable: true
          });
        }
      }
      return map;
    }
    function resolveAliasValue(ctx, value) {
      return ctx && identity.isAlias(value) ? value.resolve(ctx.doc, ctx) : value;
    }
    exports.addMergeToJSMap = addMergeToJSMap;
    exports.isMergeKey = isMergeKey;
    exports.merge = merge;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/nodes/addPairToJSMap.js
var require_addPairToJSMap = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/nodes/addPairToJSMap.js"(exports) {
    "use strict";
    var log = require_log();
    var merge = require_merge();
    var stringify = require_stringify();
    var identity = require_identity();
    var toJS = require_toJS();
    function addPairToJSMap(ctx, map, { key, value }) {
      if (identity.isNode(key) && key.addToJSMap)
        key.addToJSMap(ctx, map, value);
      else if (merge.isMergeKey(ctx, key))
        merge.addMergeToJSMap(ctx, map, value);
      else {
        const jsKey = toJS.toJS(key, "", ctx);
        if (map instanceof Map) {
          map.set(jsKey, toJS.toJS(value, jsKey, ctx));
        } else if (map instanceof Set) {
          map.add(jsKey);
        } else {
          const stringKey = stringifyKey(key, jsKey, ctx);
          const jsValue = toJS.toJS(value, stringKey, ctx);
          if (stringKey in map)
            Object.defineProperty(map, stringKey, {
              value: jsValue,
              writable: true,
              enumerable: true,
              configurable: true
            });
          else
            map[stringKey] = jsValue;
        }
      }
      return map;
    }
    function stringifyKey(key, jsKey, ctx) {
      if (jsKey === null)
        return "";
      if (typeof jsKey !== "object")
        return String(jsKey);
      if (identity.isNode(key) && ctx?.doc) {
        const strCtx = stringify.createStringifyContext(ctx.doc, {});
        strCtx.anchors = /* @__PURE__ */ new Set();
        for (const node of ctx.anchors.keys())
          strCtx.anchors.add(node.anchor);
        strCtx.inFlow = true;
        strCtx.inStringifyKey = true;
        const strKey = key.toString(strCtx);
        if (!ctx.mapKeyWarned) {
          let jsonStr = JSON.stringify(strKey);
          if (jsonStr.length > 40)
            jsonStr = jsonStr.substring(0, 36) + '..."';
          log.warn(ctx.doc.options.logLevel, `Keys with collection values will be stringified due to JS Object restrictions: ${jsonStr}. Set mapAsMap: true to use object keys.`);
          ctx.mapKeyWarned = true;
        }
        return strKey;
      }
      return JSON.stringify(jsKey);
    }
    exports.addPairToJSMap = addPairToJSMap;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/nodes/Pair.js
var require_Pair = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/nodes/Pair.js"(exports) {
    "use strict";
    var createNode = require_createNode();
    var stringifyPair = require_stringifyPair();
    var addPairToJSMap = require_addPairToJSMap();
    var identity = require_identity();
    function createPair(key, value, ctx) {
      const k2 = createNode.createNode(key, void 0, ctx);
      const v = createNode.createNode(value, void 0, ctx);
      return new Pair(k2, v);
    }
    var Pair = class _Pair {
      constructor(key, value = null) {
        Object.defineProperty(this, identity.NODE_TYPE, { value: identity.PAIR });
        this.key = key;
        this.value = value;
      }
      clone(schema) {
        let { key, value } = this;
        if (identity.isNode(key))
          key = key.clone(schema);
        if (identity.isNode(value))
          value = value.clone(schema);
        return new _Pair(key, value);
      }
      toJSON(_3, ctx) {
        const pair = ctx?.mapAsMap ? /* @__PURE__ */ new Map() : {};
        return addPairToJSMap.addPairToJSMap(ctx, pair, this);
      }
      toString(ctx, onComment, onChompKeep) {
        return ctx?.doc ? stringifyPair.stringifyPair(this, ctx, onComment, onChompKeep) : JSON.stringify(this);
      }
    };
    exports.Pair = Pair;
    exports.createPair = createPair;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/stringify/stringifyCollection.js
var require_stringifyCollection = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/stringify/stringifyCollection.js"(exports) {
    "use strict";
    var identity = require_identity();
    var stringify = require_stringify();
    var stringifyComment = require_stringifyComment();
    function stringifyCollection(collection, ctx, options) {
      const flow = ctx.inFlow ?? collection.flow;
      const stringify2 = flow ? stringifyFlowCollection : stringifyBlockCollection;
      return stringify2(collection, ctx, options);
    }
    function stringifyBlockCollection({ comment, items }, ctx, { blockItemPrefix, flowChars, itemIndent, onChompKeep, onComment }) {
      const { indent, options: { commentString } } = ctx;
      const itemCtx = Object.assign({}, ctx, { indent: itemIndent, type: null });
      let chompKeep = false;
      const lines = [];
      for (let i = 0; i < items.length; ++i) {
        const item = items[i];
        let comment2 = null;
        if (identity.isNode(item)) {
          if (!chompKeep && item.spaceBefore)
            lines.push("");
          addCommentBefore(ctx, lines, item.commentBefore, chompKeep);
          if (item.comment)
            comment2 = item.comment;
        } else if (identity.isPair(item)) {
          const ik = identity.isNode(item.key) ? item.key : null;
          if (ik) {
            if (!chompKeep && ik.spaceBefore)
              lines.push("");
            addCommentBefore(ctx, lines, ik.commentBefore, chompKeep);
          }
        }
        chompKeep = false;
        let str2 = stringify.stringify(item, itemCtx, () => comment2 = null, () => chompKeep = true);
        if (comment2)
          str2 += stringifyComment.lineComment(str2, itemIndent, commentString(comment2));
        if (chompKeep && comment2)
          chompKeep = false;
        lines.push(blockItemPrefix + str2);
      }
      let str;
      if (lines.length === 0) {
        str = flowChars.start + flowChars.end;
      } else {
        str = lines[0];
        for (let i = 1; i < lines.length; ++i) {
          const line = lines[i];
          str += line ? `
${indent}${line}` : "\n";
        }
      }
      if (comment) {
        str += "\n" + stringifyComment.indentComment(commentString(comment), indent);
        if (onComment)
          onComment();
      } else if (chompKeep && onChompKeep)
        onChompKeep();
      return str;
    }
    function stringifyFlowCollection({ items }, ctx, { flowChars, itemIndent }) {
      const { indent, indentStep, flowCollectionPadding: fcPadding, options: { commentString } } = ctx;
      itemIndent += indentStep;
      const itemCtx = Object.assign({}, ctx, {
        indent: itemIndent,
        inFlow: true,
        type: null
      });
      let reqNewline = false;
      let linesAtValue = 0;
      const lines = [];
      for (let i = 0; i < items.length; ++i) {
        const item = items[i];
        let comment = null;
        if (identity.isNode(item)) {
          if (item.spaceBefore)
            lines.push("");
          addCommentBefore(ctx, lines, item.commentBefore, false);
          if (item.comment)
            comment = item.comment;
        } else if (identity.isPair(item)) {
          const ik = identity.isNode(item.key) ? item.key : null;
          if (ik) {
            if (ik.spaceBefore)
              lines.push("");
            addCommentBefore(ctx, lines, ik.commentBefore, false);
            if (ik.comment)
              reqNewline = true;
          }
          const iv = identity.isNode(item.value) ? item.value : null;
          if (iv) {
            if (iv.comment)
              comment = iv.comment;
            if (iv.commentBefore)
              reqNewline = true;
          } else if (item.value == null && ik?.comment) {
            comment = ik.comment;
          }
        }
        if (comment)
          reqNewline = true;
        let str = stringify.stringify(item, itemCtx, () => comment = null);
        reqNewline || (reqNewline = lines.length > linesAtValue || str.includes("\n"));
        if (i < items.length - 1) {
          str += ",";
        } else if (ctx.options.trailingComma) {
          if (ctx.options.lineWidth > 0) {
            reqNewline || (reqNewline = lines.reduce((sum, line) => sum + line.length + 2, 2) + (str.length + 2) > ctx.options.lineWidth);
          }
          if (reqNewline) {
            str += ",";
          }
        }
        if (comment)
          str += stringifyComment.lineComment(str, itemIndent, commentString(comment));
        lines.push(str);
        linesAtValue = lines.length;
      }
      const { start, end } = flowChars;
      if (lines.length === 0) {
        return start + end;
      } else {
        if (!reqNewline) {
          const len = lines.reduce((sum, line) => sum + line.length + 2, 2);
          reqNewline = ctx.options.lineWidth > 0 && len > ctx.options.lineWidth;
        }
        if (reqNewline) {
          let str = start;
          for (const line of lines)
            str += line ? `
${indentStep}${indent}${line}` : "\n";
          return `${str}
${indent}${end}`;
        } else {
          return `${start}${fcPadding}${lines.join(" ")}${fcPadding}${end}`;
        }
      }
    }
    function addCommentBefore({ indent, options: { commentString } }, lines, comment, chompKeep) {
      if (comment && chompKeep)
        comment = comment.replace(/^\n+/, "");
      if (comment) {
        const ic = stringifyComment.indentComment(commentString(comment), indent);
        lines.push(ic.trimStart());
      }
    }
    exports.stringifyCollection = stringifyCollection;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/nodes/YAMLMap.js
var require_YAMLMap = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/nodes/YAMLMap.js"(exports) {
    "use strict";
    var stringifyCollection = require_stringifyCollection();
    var addPairToJSMap = require_addPairToJSMap();
    var Collection = require_Collection();
    var identity = require_identity();
    var Pair = require_Pair();
    var Scalar = require_Scalar();
    function findPair(items, key) {
      const k2 = identity.isScalar(key) ? key.value : key;
      for (const it of items) {
        if (identity.isPair(it)) {
          if (it.key === key || it.key === k2)
            return it;
          if (identity.isScalar(it.key) && it.key.value === k2)
            return it;
        }
      }
      return void 0;
    }
    var YAMLMap = class extends Collection.Collection {
      static get tagName() {
        return "tag:yaml.org,2002:map";
      }
      constructor(schema) {
        super(identity.MAP, schema);
        this.items = [];
      }
      /**
       * A generic collection parsing method that can be extended
       * to other node classes that inherit from YAMLMap
       */
      static from(schema, obj, ctx) {
        const { keepUndefined, replacer } = ctx;
        const map = new this(schema);
        const add = (key, value) => {
          if (typeof replacer === "function")
            value = replacer.call(obj, key, value);
          else if (Array.isArray(replacer) && !replacer.includes(key))
            return;
          if (value !== void 0 || keepUndefined)
            map.items.push(Pair.createPair(key, value, ctx));
        };
        if (obj instanceof Map) {
          for (const [key, value] of obj)
            add(key, value);
        } else if (obj && typeof obj === "object") {
          for (const key of Object.keys(obj))
            add(key, obj[key]);
        }
        if (typeof schema.sortMapEntries === "function") {
          map.items.sort(schema.sortMapEntries);
        }
        return map;
      }
      /**
       * Adds a value to the collection.
       *
       * @param overwrite - If not set `true`, using a key that is already in the
       *   collection will throw. Otherwise, overwrites the previous value.
       */
      add(pair, overwrite) {
        let _pair;
        if (identity.isPair(pair))
          _pair = pair;
        else if (!pair || typeof pair !== "object" || !("key" in pair)) {
          _pair = new Pair.Pair(pair, pair?.value);
        } else
          _pair = new Pair.Pair(pair.key, pair.value);
        const prev = findPair(this.items, _pair.key);
        const sortEntries = this.schema?.sortMapEntries;
        if (prev) {
          if (!overwrite)
            throw new Error(`Key ${_pair.key} already set`);
          if (identity.isScalar(prev.value) && Scalar.isScalarValue(_pair.value))
            prev.value.value = _pair.value;
          else
            prev.value = _pair.value;
        } else if (sortEntries) {
          const i = this.items.findIndex((item) => sortEntries(_pair, item) < 0);
          if (i === -1)
            this.items.push(_pair);
          else
            this.items.splice(i, 0, _pair);
        } else {
          this.items.push(_pair);
        }
      }
      delete(key) {
        const it = findPair(this.items, key);
        if (!it)
          return false;
        const del = this.items.splice(this.items.indexOf(it), 1);
        return del.length > 0;
      }
      get(key, keepScalar) {
        const it = findPair(this.items, key);
        const node = it?.value;
        return (!keepScalar && identity.isScalar(node) ? node.value : node) ?? void 0;
      }
      has(key) {
        return !!findPair(this.items, key);
      }
      set(key, value) {
        this.add(new Pair.Pair(key, value), true);
      }
      /**
       * @param ctx - Conversion context, originally set in Document#toJS()
       * @param {Class} Type - If set, forces the returned collection type
       * @returns Instance of Type, Map, or Object
       */
      toJSON(_3, ctx, Type) {
        const map = Type ? new Type() : ctx?.mapAsMap ? /* @__PURE__ */ new Map() : {};
        if (ctx?.onCreate)
          ctx.onCreate(map);
        for (const item of this.items)
          addPairToJSMap.addPairToJSMap(ctx, map, item);
        return map;
      }
      toString(ctx, onComment, onChompKeep) {
        if (!ctx)
          return JSON.stringify(this);
        for (const item of this.items) {
          if (!identity.isPair(item))
            throw new Error(`Map items must all be pairs; found ${JSON.stringify(item)} instead`);
        }
        if (!ctx.allNullValues && this.hasAllNullValues(false))
          ctx = Object.assign({}, ctx, { allNullValues: true });
        return stringifyCollection.stringifyCollection(this, ctx, {
          blockItemPrefix: "",
          flowChars: { start: "{", end: "}" },
          itemIndent: ctx.indent || "",
          onChompKeep,
          onComment
        });
      }
    };
    exports.YAMLMap = YAMLMap;
    exports.findPair = findPair;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/common/map.js
var require_map = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/common/map.js"(exports) {
    "use strict";
    var identity = require_identity();
    var YAMLMap = require_YAMLMap();
    var map = {
      collection: "map",
      default: true,
      nodeClass: YAMLMap.YAMLMap,
      tag: "tag:yaml.org,2002:map",
      resolve(map2, onError) {
        if (!identity.isMap(map2))
          onError("Expected a mapping for this tag");
        return map2;
      },
      createNode: (schema, obj, ctx) => YAMLMap.YAMLMap.from(schema, obj, ctx)
    };
    exports.map = map;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/nodes/YAMLSeq.js
var require_YAMLSeq = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/nodes/YAMLSeq.js"(exports) {
    "use strict";
    var createNode = require_createNode();
    var stringifyCollection = require_stringifyCollection();
    var Collection = require_Collection();
    var identity = require_identity();
    var Scalar = require_Scalar();
    var toJS = require_toJS();
    var YAMLSeq = class extends Collection.Collection {
      static get tagName() {
        return "tag:yaml.org,2002:seq";
      }
      constructor(schema) {
        super(identity.SEQ, schema);
        this.items = [];
      }
      add(value) {
        this.items.push(value);
      }
      /**
       * Removes a value from the collection.
       *
       * `key` must contain a representation of an integer for this to succeed.
       * It may be wrapped in a `Scalar`.
       *
       * @returns `true` if the item was found and removed.
       */
      delete(key) {
        const idx = asItemIndex(key);
        if (typeof idx !== "number")
          return false;
        const del = this.items.splice(idx, 1);
        return del.length > 0;
      }
      get(key, keepScalar) {
        const idx = asItemIndex(key);
        if (typeof idx !== "number")
          return void 0;
        const it = this.items[idx];
        return !keepScalar && identity.isScalar(it) ? it.value : it;
      }
      /**
       * Checks if the collection includes a value with the key `key`.
       *
       * `key` must contain a representation of an integer for this to succeed.
       * It may be wrapped in a `Scalar`.
       */
      has(key) {
        const idx = asItemIndex(key);
        return typeof idx === "number" && idx < this.items.length;
      }
      /**
       * Sets a value in this collection. For `!!set`, `value` needs to be a
       * boolean to add/remove the item from the set.
       *
       * If `key` does not contain a representation of an integer, this will throw.
       * It may be wrapped in a `Scalar`.
       */
      set(key, value) {
        const idx = asItemIndex(key);
        if (typeof idx !== "number")
          throw new Error(`Expected a valid index, not ${key}.`);
        const prev = this.items[idx];
        if (identity.isScalar(prev) && Scalar.isScalarValue(value))
          prev.value = value;
        else
          this.items[idx] = value;
      }
      toJSON(_3, ctx) {
        const seq = [];
        if (ctx?.onCreate)
          ctx.onCreate(seq);
        let i = 0;
        for (const item of this.items)
          seq.push(toJS.toJS(item, String(i++), ctx));
        return seq;
      }
      toString(ctx, onComment, onChompKeep) {
        if (!ctx)
          return JSON.stringify(this);
        return stringifyCollection.stringifyCollection(this, ctx, {
          blockItemPrefix: "- ",
          flowChars: { start: "[", end: "]" },
          itemIndent: (ctx.indent || "") + "  ",
          onChompKeep,
          onComment
        });
      }
      static from(schema, obj, ctx) {
        const { replacer } = ctx;
        const seq = new this(schema);
        if (obj && Symbol.iterator in Object(obj)) {
          let i = 0;
          for (let it of obj) {
            if (typeof replacer === "function") {
              const key = obj instanceof Set ? it : String(i++);
              it = replacer.call(obj, key, it);
            }
            seq.items.push(createNode.createNode(it, void 0, ctx));
          }
        }
        return seq;
      }
    };
    function asItemIndex(key) {
      let idx = identity.isScalar(key) ? key.value : key;
      if (idx && typeof idx === "string")
        idx = Number(idx);
      return typeof idx === "number" && Number.isInteger(idx) && idx >= 0 ? idx : null;
    }
    exports.YAMLSeq = YAMLSeq;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/common/seq.js
var require_seq = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/common/seq.js"(exports) {
    "use strict";
    var identity = require_identity();
    var YAMLSeq = require_YAMLSeq();
    var seq = {
      collection: "seq",
      default: true,
      nodeClass: YAMLSeq.YAMLSeq,
      tag: "tag:yaml.org,2002:seq",
      resolve(seq2, onError) {
        if (!identity.isSeq(seq2))
          onError("Expected a sequence for this tag");
        return seq2;
      },
      createNode: (schema, obj, ctx) => YAMLSeq.YAMLSeq.from(schema, obj, ctx)
    };
    exports.seq = seq;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/common/string.js
var require_string = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/common/string.js"(exports) {
    "use strict";
    var stringifyString = require_stringifyString();
    var string = {
      identify: (value) => typeof value === "string",
      default: true,
      tag: "tag:yaml.org,2002:str",
      resolve: (str) => str,
      stringify(item, ctx, onComment, onChompKeep) {
        ctx = Object.assign({ actualString: true }, ctx);
        return stringifyString.stringifyString(item, ctx, onComment, onChompKeep);
      }
    };
    exports.string = string;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/common/null.js
var require_null = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/common/null.js"(exports) {
    "use strict";
    var Scalar = require_Scalar();
    var nullTag = {
      identify: (value) => value == null,
      createNode: () => new Scalar.Scalar(null),
      default: true,
      tag: "tag:yaml.org,2002:null",
      test: /^(?:~|[Nn]ull|NULL)?$/,
      resolve: () => new Scalar.Scalar(null),
      stringify: ({ source }, ctx) => typeof source === "string" && nullTag.test.test(source) ? source : ctx.options.nullStr
    };
    exports.nullTag = nullTag;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/core/bool.js
var require_bool = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/core/bool.js"(exports) {
    "use strict";
    var Scalar = require_Scalar();
    var boolTag = {
      identify: (value) => typeof value === "boolean",
      default: true,
      tag: "tag:yaml.org,2002:bool",
      test: /^(?:[Tt]rue|TRUE|[Ff]alse|FALSE)$/,
      resolve: (str) => new Scalar.Scalar(str[0] === "t" || str[0] === "T"),
      stringify({ source, value }, ctx) {
        if (source && boolTag.test.test(source)) {
          const sv = source[0] === "t" || source[0] === "T";
          if (value === sv)
            return source;
        }
        return value ? ctx.options.trueStr : ctx.options.falseStr;
      }
    };
    exports.boolTag = boolTag;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/stringify/stringifyNumber.js
var require_stringifyNumber = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/stringify/stringifyNumber.js"(exports) {
    "use strict";
    function stringifyNumber({ format, minFractionDigits, tag, value }) {
      if (typeof value === "bigint")
        return String(value);
      const num = typeof value === "number" ? value : Number(value);
      if (!isFinite(num))
        return isNaN(num) ? ".nan" : num < 0 ? "-.inf" : ".inf";
      let n = Object.is(value, -0) ? "-0" : JSON.stringify(value);
      if (!format && minFractionDigits && (!tag || tag === "tag:yaml.org,2002:float") && /^-?\d/.test(n) && !n.includes("e")) {
        let i = n.indexOf(".");
        if (i < 0) {
          i = n.length;
          n += ".";
        }
        let d2 = minFractionDigits - (n.length - i - 1);
        while (d2-- > 0)
          n += "0";
      }
      return n;
    }
    exports.stringifyNumber = stringifyNumber;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/core/float.js
var require_float = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/core/float.js"(exports) {
    "use strict";
    var Scalar = require_Scalar();
    var stringifyNumber = require_stringifyNumber();
    var floatNaN = {
      identify: (value) => typeof value === "number",
      default: true,
      tag: "tag:yaml.org,2002:float",
      test: /^(?:[-+]?\.(?:inf|Inf|INF)|\.nan|\.NaN|\.NAN)$/,
      resolve: (str) => str.slice(-3).toLowerCase() === "nan" ? NaN : str[0] === "-" ? Number.NEGATIVE_INFINITY : Number.POSITIVE_INFINITY,
      stringify: stringifyNumber.stringifyNumber
    };
    var floatExp = {
      identify: (value) => typeof value === "number",
      default: true,
      tag: "tag:yaml.org,2002:float",
      format: "EXP",
      test: /^[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)[eE][-+]?[0-9]+$/,
      resolve: (str) => parseFloat(str),
      stringify(node) {
        const num = Number(node.value);
        return isFinite(num) ? num.toExponential() : stringifyNumber.stringifyNumber(node);
      }
    };
    var float = {
      identify: (value) => typeof value === "number",
      default: true,
      tag: "tag:yaml.org,2002:float",
      test: /^[-+]?(?:\.[0-9]+|[0-9]+\.[0-9]*)$/,
      resolve(str) {
        const node = new Scalar.Scalar(parseFloat(str));
        const dot = str.indexOf(".");
        if (dot !== -1 && str[str.length - 1] === "0")
          node.minFractionDigits = str.length - dot - 1;
        return node;
      },
      stringify: stringifyNumber.stringifyNumber
    };
    exports.float = float;
    exports.floatExp = floatExp;
    exports.floatNaN = floatNaN;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/core/int.js
var require_int = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/core/int.js"(exports) {
    "use strict";
    var stringifyNumber = require_stringifyNumber();
    var intIdentify = (value) => typeof value === "bigint" || Number.isInteger(value);
    var intResolve = (str, offset, radix, { intAsBigInt }) => intAsBigInt ? BigInt(str) : parseInt(str.substring(offset), radix);
    function intStringify(node, radix, prefix) {
      const { value } = node;
      if (intIdentify(value) && value >= 0)
        return prefix + value.toString(radix);
      return stringifyNumber.stringifyNumber(node);
    }
    var intOct = {
      identify: (value) => intIdentify(value) && value >= 0,
      default: true,
      tag: "tag:yaml.org,2002:int",
      format: "OCT",
      test: /^0o[0-7]+$/,
      resolve: (str, _onError, opt) => intResolve(str, 2, 8, opt),
      stringify: (node) => intStringify(node, 8, "0o")
    };
    var int = {
      identify: intIdentify,
      default: true,
      tag: "tag:yaml.org,2002:int",
      test: /^[-+]?[0-9]+$/,
      resolve: (str, _onError, opt) => intResolve(str, 0, 10, opt),
      stringify: stringifyNumber.stringifyNumber
    };
    var intHex = {
      identify: (value) => intIdentify(value) && value >= 0,
      default: true,
      tag: "tag:yaml.org,2002:int",
      format: "HEX",
      test: /^0x[0-9a-fA-F]+$/,
      resolve: (str, _onError, opt) => intResolve(str, 2, 16, opt),
      stringify: (node) => intStringify(node, 16, "0x")
    };
    exports.int = int;
    exports.intHex = intHex;
    exports.intOct = intOct;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/core/schema.js
var require_schema = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/core/schema.js"(exports) {
    "use strict";
    var map = require_map();
    var _null = require_null();
    var seq = require_seq();
    var string = require_string();
    var bool = require_bool();
    var float = require_float();
    var int = require_int();
    var schema = [
      map.map,
      seq.seq,
      string.string,
      _null.nullTag,
      bool.boolTag,
      int.intOct,
      int.int,
      int.intHex,
      float.floatNaN,
      float.floatExp,
      float.float
    ];
    exports.schema = schema;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/json/schema.js
var require_schema2 = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/json/schema.js"(exports) {
    "use strict";
    var Scalar = require_Scalar();
    var map = require_map();
    var seq = require_seq();
    function intIdentify(value) {
      return typeof value === "bigint" || Number.isInteger(value);
    }
    var stringifyJSON = ({ value }) => JSON.stringify(value);
    var jsonScalars = [
      {
        identify: (value) => typeof value === "string",
        default: true,
        tag: "tag:yaml.org,2002:str",
        resolve: (str) => str,
        stringify: stringifyJSON
      },
      {
        identify: (value) => value == null,
        createNode: () => new Scalar.Scalar(null),
        default: true,
        tag: "tag:yaml.org,2002:null",
        test: /^null$/,
        resolve: () => null,
        stringify: stringifyJSON
      },
      {
        identify: (value) => typeof value === "boolean",
        default: true,
        tag: "tag:yaml.org,2002:bool",
        test: /^true$|^false$/,
        resolve: (str) => str === "true",
        stringify: stringifyJSON
      },
      {
        identify: intIdentify,
        default: true,
        tag: "tag:yaml.org,2002:int",
        test: /^-?(?:0|[1-9][0-9]*)$/,
        resolve: (str, _onError, { intAsBigInt }) => intAsBigInt ? BigInt(str) : parseInt(str, 10),
        stringify: ({ value }) => intIdentify(value) ? value.toString() : JSON.stringify(value)
      },
      {
        identify: (value) => typeof value === "number",
        default: true,
        tag: "tag:yaml.org,2002:float",
        test: /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*)?(?:[eE][-+]?[0-9]+)?$/,
        resolve: (str) => parseFloat(str),
        stringify: stringifyJSON
      }
    ];
    var jsonError = {
      default: true,
      tag: "",
      test: /^/,
      resolve(str, onError) {
        onError(`Unresolved plain scalar ${JSON.stringify(str)}`);
        return str;
      }
    };
    var schema = [map.map, seq.seq].concat(jsonScalars, jsonError);
    exports.schema = schema;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/yaml-1.1/binary.js
var require_binary = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/yaml-1.1/binary.js"(exports) {
    "use strict";
    var node_buffer = __require("buffer");
    var Scalar = require_Scalar();
    var stringifyString = require_stringifyString();
    var binary = {
      identify: (value) => value instanceof Uint8Array,
      // Buffer inherits from Uint8Array
      default: false,
      tag: "tag:yaml.org,2002:binary",
      /**
       * Returns a Buffer in node and an Uint8Array in browsers
       *
       * To use the resulting buffer as an image, you'll want to do something like:
       *
       *   const blob = new Blob([buffer], { type: 'image/jpeg' })
       *   document.querySelector('#photo').src = URL.createObjectURL(blob)
       */
      resolve(src, onError) {
        if (typeof node_buffer.Buffer === "function") {
          return node_buffer.Buffer.from(src, "base64");
        } else if (typeof atob === "function") {
          const str = atob(src.replace(/[\n\r]/g, ""));
          const buffer = new Uint8Array(str.length);
          for (let i = 0; i < str.length; ++i)
            buffer[i] = str.charCodeAt(i);
          return buffer;
        } else {
          onError("This environment does not support reading binary tags; either Buffer or atob is required");
          return src;
        }
      },
      stringify({ comment, type, value }, ctx, onComment, onChompKeep) {
        if (!value)
          return "";
        const buf = value;
        let str;
        if (typeof node_buffer.Buffer === "function") {
          str = buf instanceof node_buffer.Buffer ? buf.toString("base64") : node_buffer.Buffer.from(buf.buffer).toString("base64");
        } else if (typeof btoa === "function") {
          let s = "";
          for (let i = 0; i < buf.length; ++i)
            s += String.fromCharCode(buf[i]);
          str = btoa(s);
        } else {
          throw new Error("This environment does not support writing binary tags; either Buffer or btoa is required");
        }
        type ?? (type = Scalar.Scalar.BLOCK_LITERAL);
        if (type !== Scalar.Scalar.QUOTE_DOUBLE) {
          const lineWidth = Math.max(ctx.options.lineWidth - ctx.indent.length, ctx.options.minContentWidth);
          const n = Math.ceil(str.length / lineWidth);
          const lines = new Array(n);
          for (let i = 0, o2 = 0; i < n; ++i, o2 += lineWidth) {
            lines[i] = str.substr(o2, lineWidth);
          }
          str = lines.join(type === Scalar.Scalar.BLOCK_LITERAL ? "\n" : " ");
        }
        return stringifyString.stringifyString({ comment, type, value: str }, ctx, onComment, onChompKeep);
      }
    };
    exports.binary = binary;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/yaml-1.1/pairs.js
var require_pairs = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/yaml-1.1/pairs.js"(exports) {
    "use strict";
    var identity = require_identity();
    var Pair = require_Pair();
    var Scalar = require_Scalar();
    var YAMLSeq = require_YAMLSeq();
    function resolvePairs(seq, onError) {
      if (identity.isSeq(seq)) {
        for (let i = 0; i < seq.items.length; ++i) {
          let item = seq.items[i];
          if (identity.isPair(item))
            continue;
          else if (identity.isMap(item)) {
            if (item.items.length > 1)
              onError("Each pair must have its own sequence indicator");
            const pair = item.items[0] || new Pair.Pair(new Scalar.Scalar(null));
            if (item.commentBefore)
              pair.key.commentBefore = pair.key.commentBefore ? `${item.commentBefore}
${pair.key.commentBefore}` : item.commentBefore;
            if (item.comment) {
              const cn = pair.value ?? pair.key;
              cn.comment = cn.comment ? `${item.comment}
${cn.comment}` : item.comment;
            }
            item = pair;
          }
          seq.items[i] = identity.isPair(item) ? item : new Pair.Pair(item);
        }
      } else
        onError("Expected a sequence for this tag");
      return seq;
    }
    function createPairs(schema, iterable, ctx) {
      const { replacer } = ctx;
      const pairs2 = new YAMLSeq.YAMLSeq(schema);
      pairs2.tag = "tag:yaml.org,2002:pairs";
      let i = 0;
      if (iterable && Symbol.iterator in Object(iterable))
        for (let it of iterable) {
          if (typeof replacer === "function")
            it = replacer.call(iterable, String(i++), it);
          let key, value;
          if (Array.isArray(it)) {
            if (it.length === 2) {
              key = it[0];
              value = it[1];
            } else
              throw new TypeError(`Expected [key, value] tuple: ${it}`);
          } else if (it && it instanceof Object) {
            const keys = Object.keys(it);
            if (keys.length === 1) {
              key = keys[0];
              value = it[key];
            } else {
              throw new TypeError(`Expected tuple with one key, not ${keys.length} keys`);
            }
          } else {
            key = it;
          }
          pairs2.items.push(Pair.createPair(key, value, ctx));
        }
      return pairs2;
    }
    var pairs = {
      collection: "seq",
      default: false,
      tag: "tag:yaml.org,2002:pairs",
      resolve: resolvePairs,
      createNode: createPairs
    };
    exports.createPairs = createPairs;
    exports.pairs = pairs;
    exports.resolvePairs = resolvePairs;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/yaml-1.1/omap.js
var require_omap = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/yaml-1.1/omap.js"(exports) {
    "use strict";
    var identity = require_identity();
    var toJS = require_toJS();
    var YAMLMap = require_YAMLMap();
    var YAMLSeq = require_YAMLSeq();
    var pairs = require_pairs();
    var YAMLOMap = class _YAMLOMap extends YAMLSeq.YAMLSeq {
      constructor() {
        super();
        this.add = YAMLMap.YAMLMap.prototype.add.bind(this);
        this.delete = YAMLMap.YAMLMap.prototype.delete.bind(this);
        this.get = YAMLMap.YAMLMap.prototype.get.bind(this);
        this.has = YAMLMap.YAMLMap.prototype.has.bind(this);
        this.set = YAMLMap.YAMLMap.prototype.set.bind(this);
        this.tag = _YAMLOMap.tag;
      }
      /**
       * If `ctx` is given, the return type is actually `Map<unknown, unknown>`,
       * but TypeScript won't allow widening the signature of a child method.
       */
      toJSON(_3, ctx) {
        if (!ctx)
          return super.toJSON(_3);
        const map = /* @__PURE__ */ new Map();
        if (ctx?.onCreate)
          ctx.onCreate(map);
        for (const pair of this.items) {
          let key, value;
          if (identity.isPair(pair)) {
            key = toJS.toJS(pair.key, "", ctx);
            value = toJS.toJS(pair.value, key, ctx);
          } else {
            key = toJS.toJS(pair, "", ctx);
          }
          if (map.has(key))
            throw new Error("Ordered maps must not include duplicate keys");
          map.set(key, value);
        }
        return map;
      }
      static from(schema, iterable, ctx) {
        const pairs$1 = pairs.createPairs(schema, iterable, ctx);
        const omap2 = new this();
        omap2.items = pairs$1.items;
        return omap2;
      }
    };
    YAMLOMap.tag = "tag:yaml.org,2002:omap";
    var omap = {
      collection: "seq",
      identify: (value) => value instanceof Map,
      nodeClass: YAMLOMap,
      default: false,
      tag: "tag:yaml.org,2002:omap",
      resolve(seq, onError) {
        const pairs$1 = pairs.resolvePairs(seq, onError);
        const seenKeys = [];
        for (const { key } of pairs$1.items) {
          if (identity.isScalar(key)) {
            if (seenKeys.includes(key.value)) {
              onError(`Ordered maps must not include duplicate keys: ${key.value}`);
            } else {
              seenKeys.push(key.value);
            }
          }
        }
        return Object.assign(new YAMLOMap(), pairs$1);
      },
      createNode: (schema, iterable, ctx) => YAMLOMap.from(schema, iterable, ctx)
    };
    exports.YAMLOMap = YAMLOMap;
    exports.omap = omap;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/yaml-1.1/bool.js
var require_bool2 = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/yaml-1.1/bool.js"(exports) {
    "use strict";
    var Scalar = require_Scalar();
    function boolStringify({ value, source }, ctx) {
      const boolObj = value ? trueTag : falseTag;
      if (source && boolObj.test.test(source))
        return source;
      return value ? ctx.options.trueStr : ctx.options.falseStr;
    }
    var trueTag = {
      identify: (value) => value === true,
      default: true,
      tag: "tag:yaml.org,2002:bool",
      test: /^(?:Y|y|[Yy]es|YES|[Tt]rue|TRUE|[Oo]n|ON)$/,
      resolve: () => new Scalar.Scalar(true),
      stringify: boolStringify
    };
    var falseTag = {
      identify: (value) => value === false,
      default: true,
      tag: "tag:yaml.org,2002:bool",
      test: /^(?:N|n|[Nn]o|NO|[Ff]alse|FALSE|[Oo]ff|OFF)$/,
      resolve: () => new Scalar.Scalar(false),
      stringify: boolStringify
    };
    exports.falseTag = falseTag;
    exports.trueTag = trueTag;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/yaml-1.1/float.js
var require_float2 = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/yaml-1.1/float.js"(exports) {
    "use strict";
    var Scalar = require_Scalar();
    var stringifyNumber = require_stringifyNumber();
    var floatNaN = {
      identify: (value) => typeof value === "number",
      default: true,
      tag: "tag:yaml.org,2002:float",
      test: /^(?:[-+]?\.(?:inf|Inf|INF)|\.nan|\.NaN|\.NAN)$/,
      resolve: (str) => str.slice(-3).toLowerCase() === "nan" ? NaN : str[0] === "-" ? Number.NEGATIVE_INFINITY : Number.POSITIVE_INFINITY,
      stringify: stringifyNumber.stringifyNumber
    };
    var floatExp = {
      identify: (value) => typeof value === "number",
      default: true,
      tag: "tag:yaml.org,2002:float",
      format: "EXP",
      test: /^[-+]?(?:[0-9][0-9_]*)?(?:\.[0-9_]*)?[eE][-+]?[0-9]+$/,
      resolve: (str) => parseFloat(str.replace(/_/g, "")),
      stringify(node) {
        const num = Number(node.value);
        return isFinite(num) ? num.toExponential() : stringifyNumber.stringifyNumber(node);
      }
    };
    var float = {
      identify: (value) => typeof value === "number",
      default: true,
      tag: "tag:yaml.org,2002:float",
      test: /^[-+]?(?:[0-9][0-9_]*)?\.[0-9_]*$/,
      resolve(str) {
        const node = new Scalar.Scalar(parseFloat(str.replace(/_/g, "")));
        const dot = str.indexOf(".");
        if (dot !== -1) {
          const f = str.substring(dot + 1).replace(/_/g, "");
          if (f[f.length - 1] === "0")
            node.minFractionDigits = f.length;
        }
        return node;
      },
      stringify: stringifyNumber.stringifyNumber
    };
    exports.float = float;
    exports.floatExp = floatExp;
    exports.floatNaN = floatNaN;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/yaml-1.1/int.js
var require_int2 = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/yaml-1.1/int.js"(exports) {
    "use strict";
    var stringifyNumber = require_stringifyNumber();
    var intIdentify = (value) => typeof value === "bigint" || Number.isInteger(value);
    function intResolve(str, offset, radix, { intAsBigInt }) {
      const sign = str[0];
      if (sign === "-" || sign === "+")
        offset += 1;
      str = str.substring(offset).replace(/_/g, "");
      if (intAsBigInt) {
        switch (radix) {
          case 2:
            str = `0b${str}`;
            break;
          case 8:
            str = `0o${str}`;
            break;
          case 16:
            str = `0x${str}`;
            break;
        }
        const n2 = BigInt(str);
        return sign === "-" ? BigInt(-1) * n2 : n2;
      }
      const n = parseInt(str, radix);
      return sign === "-" ? -1 * n : n;
    }
    function intStringify(node, radix, prefix) {
      const { value } = node;
      if (intIdentify(value)) {
        const str = value.toString(radix);
        return value < 0 ? "-" + prefix + str.substr(1) : prefix + str;
      }
      return stringifyNumber.stringifyNumber(node);
    }
    var intBin = {
      identify: intIdentify,
      default: true,
      tag: "tag:yaml.org,2002:int",
      format: "BIN",
      test: /^[-+]?0b[0-1_]+$/,
      resolve: (str, _onError, opt) => intResolve(str, 2, 2, opt),
      stringify: (node) => intStringify(node, 2, "0b")
    };
    var intOct = {
      identify: intIdentify,
      default: true,
      tag: "tag:yaml.org,2002:int",
      format: "OCT",
      test: /^[-+]?0[0-7_]+$/,
      resolve: (str, _onError, opt) => intResolve(str, 1, 8, opt),
      stringify: (node) => intStringify(node, 8, "0")
    };
    var int = {
      identify: intIdentify,
      default: true,
      tag: "tag:yaml.org,2002:int",
      test: /^[-+]?[0-9][0-9_]*$/,
      resolve: (str, _onError, opt) => intResolve(str, 0, 10, opt),
      stringify: stringifyNumber.stringifyNumber
    };
    var intHex = {
      identify: intIdentify,
      default: true,
      tag: "tag:yaml.org,2002:int",
      format: "HEX",
      test: /^[-+]?0x[0-9a-fA-F_]+$/,
      resolve: (str, _onError, opt) => intResolve(str, 2, 16, opt),
      stringify: (node) => intStringify(node, 16, "0x")
    };
    exports.int = int;
    exports.intBin = intBin;
    exports.intHex = intHex;
    exports.intOct = intOct;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/yaml-1.1/set.js
var require_set = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/yaml-1.1/set.js"(exports) {
    "use strict";
    var identity = require_identity();
    var Pair = require_Pair();
    var YAMLMap = require_YAMLMap();
    var YAMLSet = class _YAMLSet extends YAMLMap.YAMLMap {
      constructor(schema) {
        super(schema);
        this.tag = _YAMLSet.tag;
      }
      add(key) {
        let pair;
        if (identity.isPair(key))
          pair = key;
        else if (key && typeof key === "object" && "key" in key && "value" in key && key.value === null)
          pair = new Pair.Pair(key.key, null);
        else
          pair = new Pair.Pair(key, null);
        const prev = YAMLMap.findPair(this.items, pair.key);
        if (!prev)
          this.items.push(pair);
      }
      /**
       * If `keepPair` is `true`, returns the Pair matching `key`.
       * Otherwise, returns the value of that Pair's key.
       */
      get(key, keepPair) {
        const pair = YAMLMap.findPair(this.items, key);
        return !keepPair && identity.isPair(pair) ? identity.isScalar(pair.key) ? pair.key.value : pair.key : pair;
      }
      set(key, value) {
        if (typeof value !== "boolean")
          throw new Error(`Expected boolean value for set(key, value) in a YAML set, not ${typeof value}`);
        const prev = YAMLMap.findPair(this.items, key);
        if (prev && !value) {
          this.items.splice(this.items.indexOf(prev), 1);
        } else if (!prev && value) {
          this.items.push(new Pair.Pair(key));
        }
      }
      toJSON(_3, ctx) {
        return super.toJSON(_3, ctx, Set);
      }
      toString(ctx, onComment, onChompKeep) {
        if (!ctx)
          return JSON.stringify(this);
        if (this.hasAllNullValues(true))
          return super.toString(Object.assign({}, ctx, { allNullValues: true }), onComment, onChompKeep);
        else
          throw new Error("Set items must all have null values");
      }
      static from(schema, iterable, ctx) {
        const { replacer } = ctx;
        const set2 = new this(schema);
        if (iterable && Symbol.iterator in Object(iterable))
          for (let value of iterable) {
            if (typeof replacer === "function")
              value = replacer.call(iterable, value, value);
            set2.items.push(Pair.createPair(value, null, ctx));
          }
        return set2;
      }
    };
    YAMLSet.tag = "tag:yaml.org,2002:set";
    var set = {
      collection: "map",
      identify: (value) => value instanceof Set,
      nodeClass: YAMLSet,
      default: false,
      tag: "tag:yaml.org,2002:set",
      createNode: (schema, iterable, ctx) => YAMLSet.from(schema, iterable, ctx),
      resolve(map, onError) {
        if (identity.isMap(map)) {
          if (map.hasAllNullValues(true))
            return Object.assign(new YAMLSet(), map);
          else
            onError("Set items must all have null values");
        } else
          onError("Expected a mapping for this tag");
        return map;
      }
    };
    exports.YAMLSet = YAMLSet;
    exports.set = set;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/yaml-1.1/timestamp.js
var require_timestamp = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/yaml-1.1/timestamp.js"(exports) {
    "use strict";
    var stringifyNumber = require_stringifyNumber();
    function parseSexagesimal(str, asBigInt) {
      const sign = str[0];
      const parts = sign === "-" || sign === "+" ? str.substring(1) : str;
      const num = (n) => asBigInt ? BigInt(n) : Number(n);
      const res = parts.replace(/_/g, "").split(":").reduce((res2, p) => res2 * num(60) + num(p), num(0));
      return sign === "-" ? num(-1) * res : res;
    }
    function stringifySexagesimal(node) {
      let { value } = node;
      let num = (n) => n;
      if (typeof value === "bigint")
        num = (n) => BigInt(n);
      else if (isNaN(value) || !isFinite(value))
        return stringifyNumber.stringifyNumber(node);
      let sign = "";
      if (value < 0) {
        sign = "-";
        value *= num(-1);
      }
      const _60 = num(60);
      const parts = [value % _60];
      if (value < 60) {
        parts.unshift(0);
      } else {
        value = (value - parts[0]) / _60;
        parts.unshift(value % _60);
        if (value >= 60) {
          value = (value - parts[0]) / _60;
          parts.unshift(value);
        }
      }
      return sign + parts.map((n) => String(n).padStart(2, "0")).join(":").replace(/000000\d*$/, "");
    }
    var intTime = {
      identify: (value) => typeof value === "bigint" || Number.isInteger(value),
      default: true,
      tag: "tag:yaml.org,2002:int",
      format: "TIME",
      test: /^[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+$/,
      resolve: (str, _onError, { intAsBigInt }) => parseSexagesimal(str, intAsBigInt),
      stringify: stringifySexagesimal
    };
    var floatTime = {
      identify: (value) => typeof value === "number",
      default: true,
      tag: "tag:yaml.org,2002:float",
      format: "TIME",
      test: /^[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.[0-9_]*$/,
      resolve: (str) => parseSexagesimal(str, false),
      stringify: stringifySexagesimal
    };
    var timestamp = {
      identify: (value) => value instanceof Date,
      default: true,
      tag: "tag:yaml.org,2002:timestamp",
      // If the time zone is omitted, the timestamp is assumed to be specified in UTC. The time part
      // may be omitted altogether, resulting in a date format. In such a case, the time part is
      // assumed to be 00:00:00Z (start of day, UTC).
      test: RegExp("^([0-9]{4})-([0-9]{1,2})-([0-9]{1,2})(?:(?:t|T|[ \\t]+)([0-9]{1,2}):([0-9]{1,2}):([0-9]{1,2}(\\.[0-9]+)?)(?:[ \\t]*(Z|[-+][012]?[0-9](?::[0-9]{2})?))?)?$"),
      resolve(str) {
        const match = str.match(timestamp.test);
        if (!match)
          throw new Error("!!timestamp expects a date, starting with yyyy-mm-dd");
        const [, year, month, day, hour, minute, second] = match.map(Number);
        const millisec = match[7] ? Number((match[7] + "00").substr(1, 3)) : 0;
        let date = Date.UTC(year, month - 1, day, hour || 0, minute || 0, second || 0, millisec);
        const tz = match[8];
        if (tz && tz !== "Z") {
          let d2 = parseSexagesimal(tz, false);
          if (Math.abs(d2) < 30)
            d2 *= 60;
          date -= 6e4 * d2;
        }
        return new Date(date);
      },
      stringify: ({ value }) => value?.toISOString().replace(/(T00:00:00)?\.000Z$/, "") ?? ""
    };
    exports.floatTime = floatTime;
    exports.intTime = intTime;
    exports.timestamp = timestamp;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/yaml-1.1/schema.js
var require_schema3 = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/yaml-1.1/schema.js"(exports) {
    "use strict";
    var map = require_map();
    var _null = require_null();
    var seq = require_seq();
    var string = require_string();
    var binary = require_binary();
    var bool = require_bool2();
    var float = require_float2();
    var int = require_int2();
    var merge = require_merge();
    var omap = require_omap();
    var pairs = require_pairs();
    var set = require_set();
    var timestamp = require_timestamp();
    var schema = [
      map.map,
      seq.seq,
      string.string,
      _null.nullTag,
      bool.trueTag,
      bool.falseTag,
      int.intBin,
      int.intOct,
      int.int,
      int.intHex,
      float.floatNaN,
      float.floatExp,
      float.float,
      binary.binary,
      merge.merge,
      omap.omap,
      pairs.pairs,
      set.set,
      timestamp.intTime,
      timestamp.floatTime,
      timestamp.timestamp
    ];
    exports.schema = schema;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/tags.js
var require_tags = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/tags.js"(exports) {
    "use strict";
    var map = require_map();
    var _null = require_null();
    var seq = require_seq();
    var string = require_string();
    var bool = require_bool();
    var float = require_float();
    var int = require_int();
    var schema = require_schema();
    var schema$1 = require_schema2();
    var binary = require_binary();
    var merge = require_merge();
    var omap = require_omap();
    var pairs = require_pairs();
    var schema$2 = require_schema3();
    var set = require_set();
    var timestamp = require_timestamp();
    var schemas = /* @__PURE__ */ new Map([
      ["core", schema.schema],
      ["failsafe", [map.map, seq.seq, string.string]],
      ["json", schema$1.schema],
      ["yaml11", schema$2.schema],
      ["yaml-1.1", schema$2.schema]
    ]);
    var tagsByName = {
      binary: binary.binary,
      bool: bool.boolTag,
      float: float.float,
      floatExp: float.floatExp,
      floatNaN: float.floatNaN,
      floatTime: timestamp.floatTime,
      int: int.int,
      intHex: int.intHex,
      intOct: int.intOct,
      intTime: timestamp.intTime,
      map: map.map,
      merge: merge.merge,
      null: _null.nullTag,
      omap: omap.omap,
      pairs: pairs.pairs,
      seq: seq.seq,
      set: set.set,
      timestamp: timestamp.timestamp
    };
    var coreKnownTags = {
      "tag:yaml.org,2002:binary": binary.binary,
      "tag:yaml.org,2002:merge": merge.merge,
      "tag:yaml.org,2002:omap": omap.omap,
      "tag:yaml.org,2002:pairs": pairs.pairs,
      "tag:yaml.org,2002:set": set.set,
      "tag:yaml.org,2002:timestamp": timestamp.timestamp
    };
    function getTags(customTags, schemaName, addMergeTag) {
      const schemaTags = schemas.get(schemaName);
      if (schemaTags && !customTags) {
        return addMergeTag && !schemaTags.includes(merge.merge) ? schemaTags.concat(merge.merge) : schemaTags.slice();
      }
      let tags = schemaTags;
      if (!tags) {
        if (Array.isArray(customTags))
          tags = [];
        else {
          const keys = Array.from(schemas.keys()).filter((key) => key !== "yaml11").map((key) => JSON.stringify(key)).join(", ");
          throw new Error(`Unknown schema "${schemaName}"; use one of ${keys} or define customTags array`);
        }
      }
      if (Array.isArray(customTags)) {
        for (const tag of customTags)
          tags = tags.concat(tag);
      } else if (typeof customTags === "function") {
        tags = customTags(tags.slice());
      }
      if (addMergeTag)
        tags = tags.concat(merge.merge);
      return tags.reduce((tags2, tag) => {
        const tagObj = typeof tag === "string" ? tagsByName[tag] : tag;
        if (!tagObj) {
          const tagName = JSON.stringify(tag);
          const keys = Object.keys(tagsByName).map((key) => JSON.stringify(key)).join(", ");
          throw new Error(`Unknown custom tag ${tagName}; use one of ${keys}`);
        }
        if (!tags2.includes(tagObj))
          tags2.push(tagObj);
        return tags2;
      }, []);
    }
    exports.coreKnownTags = coreKnownTags;
    exports.getTags = getTags;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/Schema.js
var require_Schema = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/schema/Schema.js"(exports) {
    "use strict";
    var identity = require_identity();
    var map = require_map();
    var seq = require_seq();
    var string = require_string();
    var tags = require_tags();
    var sortMapEntriesByKey = (a, b2) => a.key < b2.key ? -1 : a.key > b2.key ? 1 : 0;
    var Schema = class _Schema {
      constructor({ compat, customTags, merge, resolveKnownTags, schema, sortMapEntries, toStringDefaults }) {
        this.compat = Array.isArray(compat) ? tags.getTags(compat, "compat") : compat ? tags.getTags(null, compat) : null;
        this.name = typeof schema === "string" && schema || "core";
        this.knownTags = resolveKnownTags ? tags.coreKnownTags : {};
        this.tags = tags.getTags(customTags, this.name, merge);
        this.toStringOptions = toStringDefaults ?? null;
        Object.defineProperty(this, identity.MAP, { value: map.map });
        Object.defineProperty(this, identity.SCALAR, { value: string.string });
        Object.defineProperty(this, identity.SEQ, { value: seq.seq });
        this.sortMapEntries = typeof sortMapEntries === "function" ? sortMapEntries : sortMapEntries === true ? sortMapEntriesByKey : null;
      }
      clone() {
        const copy = Object.create(_Schema.prototype, Object.getOwnPropertyDescriptors(this));
        copy.tags = this.tags.slice();
        return copy;
      }
    };
    exports.Schema = Schema;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/stringify/stringifyDocument.js
var require_stringifyDocument = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/stringify/stringifyDocument.js"(exports) {
    "use strict";
    var identity = require_identity();
    var stringify = require_stringify();
    var stringifyComment = require_stringifyComment();
    function stringifyDocument(doc, options) {
      const lines = [];
      let hasDirectives = options.directives === true;
      if (options.directives !== false && doc.directives) {
        const dir = doc.directives.toString(doc);
        if (dir) {
          lines.push(dir);
          hasDirectives = true;
        } else if (doc.directives.docStart)
          hasDirectives = true;
      }
      if (hasDirectives)
        lines.push("---");
      const ctx = stringify.createStringifyContext(doc, options);
      const { commentString } = ctx.options;
      if (doc.commentBefore) {
        if (lines.length !== 1)
          lines.unshift("");
        const cs = commentString(doc.commentBefore);
        lines.unshift(stringifyComment.indentComment(cs, ""));
      }
      let chompKeep = false;
      let contentComment = null;
      if (doc.contents) {
        if (identity.isNode(doc.contents)) {
          if (doc.contents.spaceBefore && hasDirectives)
            lines.push("");
          if (doc.contents.commentBefore) {
            const cs = commentString(doc.contents.commentBefore);
            lines.push(stringifyComment.indentComment(cs, ""));
          }
          ctx.forceBlockIndent = !!doc.comment;
          contentComment = doc.contents.comment;
        }
        const onChompKeep = contentComment ? void 0 : () => chompKeep = true;
        let body = stringify.stringify(doc.contents, ctx, () => contentComment = null, onChompKeep);
        if (contentComment)
          body += stringifyComment.lineComment(body, "", commentString(contentComment));
        if ((body[0] === "|" || body[0] === ">") && lines[lines.length - 1] === "---") {
          lines[lines.length - 1] = `--- ${body}`;
        } else
          lines.push(body);
      } else {
        lines.push(stringify.stringify(doc.contents, ctx));
      }
      if (doc.directives?.docEnd) {
        if (doc.comment) {
          const cs = commentString(doc.comment);
          if (cs.includes("\n")) {
            lines.push("...");
            lines.push(stringifyComment.indentComment(cs, ""));
          } else {
            lines.push(`... ${cs}`);
          }
        } else {
          lines.push("...");
        }
      } else {
        let dc = doc.comment;
        if (dc && chompKeep)
          dc = dc.replace(/^\n+/, "");
        if (dc) {
          if ((!chompKeep || contentComment) && lines[lines.length - 1] !== "")
            lines.push("");
          lines.push(stringifyComment.indentComment(commentString(dc), ""));
        }
      }
      return lines.join("\n") + "\n";
    }
    exports.stringifyDocument = stringifyDocument;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/doc/Document.js
var require_Document = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/doc/Document.js"(exports) {
    "use strict";
    var Alias = require_Alias();
    var Collection = require_Collection();
    var identity = require_identity();
    var Pair = require_Pair();
    var toJS = require_toJS();
    var Schema = require_Schema();
    var stringifyDocument = require_stringifyDocument();
    var anchors = require_anchors();
    var applyReviver = require_applyReviver();
    var createNode = require_createNode();
    var directives = require_directives();
    var Document = class _Document {
      constructor(value, replacer, options) {
        this.commentBefore = null;
        this.comment = null;
        this.errors = [];
        this.warnings = [];
        Object.defineProperty(this, identity.NODE_TYPE, { value: identity.DOC });
        let _replacer = null;
        if (typeof replacer === "function" || Array.isArray(replacer)) {
          _replacer = replacer;
        } else if (options === void 0 && replacer) {
          options = replacer;
          replacer = void 0;
        }
        const opt = Object.assign({
          intAsBigInt: false,
          keepSourceTokens: false,
          logLevel: "warn",
          prettyErrors: true,
          strict: true,
          stringKeys: false,
          uniqueKeys: true,
          version: "1.2"
        }, options);
        this.options = opt;
        let { version } = opt;
        if (options?._directives) {
          this.directives = options._directives.atDocument();
          if (this.directives.yaml.explicit)
            version = this.directives.yaml.version;
        } else
          this.directives = new directives.Directives({ version });
        this.setSchema(version, options);
        this.contents = value === void 0 ? null : this.createNode(value, _replacer, options);
      }
      /**
       * Create a deep copy of this Document and its contents.
       *
       * Custom Node values that inherit from `Object` still refer to their original instances.
       */
      clone() {
        const copy = Object.create(_Document.prototype, {
          [identity.NODE_TYPE]: { value: identity.DOC }
        });
        copy.commentBefore = this.commentBefore;
        copy.comment = this.comment;
        copy.errors = this.errors.slice();
        copy.warnings = this.warnings.slice();
        copy.options = Object.assign({}, this.options);
        if (this.directives)
          copy.directives = this.directives.clone();
        copy.schema = this.schema.clone();
        copy.contents = identity.isNode(this.contents) ? this.contents.clone(copy.schema) : this.contents;
        if (this.range)
          copy.range = this.range.slice();
        return copy;
      }
      /** Adds a value to the document. */
      add(value) {
        if (assertCollection(this.contents))
          this.contents.add(value);
      }
      /** Adds a value to the document. */
      addIn(path, value) {
        if (assertCollection(this.contents))
          this.contents.addIn(path, value);
      }
      /**
       * Create a new `Alias` node, ensuring that the target `node` has the required anchor.
       *
       * If `node` already has an anchor, `name` is ignored.
       * Otherwise, the `node.anchor` value will be set to `name`,
       * or if an anchor with that name is already present in the document,
       * `name` will be used as a prefix for a new unique anchor.
       * If `name` is undefined, the generated anchor will use 'a' as a prefix.
       */
      createAlias(node, name) {
        if (!node.anchor) {
          const prev = anchors.anchorNames(this);
          node.anchor = // eslint-disable-next-line @typescript-eslint/prefer-nullish-coalescing
          !name || prev.has(name) ? anchors.findNewAnchor(name || "a", prev) : name;
        }
        return new Alias.Alias(node.anchor);
      }
      createNode(value, replacer, options) {
        let _replacer = void 0;
        if (typeof replacer === "function") {
          value = replacer.call({ "": value }, "", value);
          _replacer = replacer;
        } else if (Array.isArray(replacer)) {
          const keyToStr = (v) => typeof v === "number" || v instanceof String || v instanceof Number;
          const asStr = replacer.filter(keyToStr).map(String);
          if (asStr.length > 0)
            replacer = replacer.concat(asStr);
          _replacer = replacer;
        } else if (options === void 0 && replacer) {
          options = replacer;
          replacer = void 0;
        }
        const { aliasDuplicateObjects, anchorPrefix, flow, keepUndefined, onTagObj, tag } = options ?? {};
        const { onAnchor, setAnchors, sourceObjects } = anchors.createNodeAnchors(
          this,
          // eslint-disable-next-line @typescript-eslint/prefer-nullish-coalescing
          anchorPrefix || "a"
        );
        const ctx = {
          aliasDuplicateObjects: aliasDuplicateObjects ?? true,
          keepUndefined: keepUndefined ?? false,
          onAnchor,
          onTagObj,
          replacer: _replacer,
          schema: this.schema,
          sourceObjects
        };
        const node = createNode.createNode(value, tag, ctx);
        if (flow && identity.isCollection(node))
          node.flow = true;
        setAnchors();
        return node;
      }
      /**
       * Convert a key and a value into a `Pair` using the current schema,
       * recursively wrapping all values as `Scalar` or `Collection` nodes.
       */
      createPair(key, value, options = {}) {
        const k2 = this.createNode(key, null, options);
        const v = this.createNode(value, null, options);
        return new Pair.Pair(k2, v);
      }
      /**
       * Removes a value from the document.
       * @returns `true` if the item was found and removed.
       */
      delete(key) {
        return assertCollection(this.contents) ? this.contents.delete(key) : false;
      }
      /**
       * Removes a value from the document.
       * @returns `true` if the item was found and removed.
       */
      deleteIn(path) {
        if (Collection.isEmptyPath(path)) {
          if (this.contents == null)
            return false;
          this.contents = null;
          return true;
        }
        return assertCollection(this.contents) ? this.contents.deleteIn(path) : false;
      }
      /**
       * Returns item at `key`, or `undefined` if not found. By default unwraps
       * scalar values from their surrounding node; to disable set `keepScalar` to
       * `true` (collections are always returned intact).
       */
      get(key, keepScalar) {
        return identity.isCollection(this.contents) ? this.contents.get(key, keepScalar) : void 0;
      }
      /**
       * Returns item at `path`, or `undefined` if not found. By default unwraps
       * scalar values from their surrounding node; to disable set `keepScalar` to
       * `true` (collections are always returned intact).
       */
      getIn(path, keepScalar) {
        if (Collection.isEmptyPath(path))
          return !keepScalar && identity.isScalar(this.contents) ? this.contents.value : this.contents;
        return identity.isCollection(this.contents) ? this.contents.getIn(path, keepScalar) : void 0;
      }
      /**
       * Checks if the document includes a value with the key `key`.
       */
      has(key) {
        return identity.isCollection(this.contents) ? this.contents.has(key) : false;
      }
      /**
       * Checks if the document includes a value at `path`.
       */
      hasIn(path) {
        if (Collection.isEmptyPath(path))
          return this.contents !== void 0;
        return identity.isCollection(this.contents) ? this.contents.hasIn(path) : false;
      }
      /**
       * Sets a value in this document. For `!!set`, `value` needs to be a
       * boolean to add/remove the item from the set.
       */
      set(key, value) {
        if (this.contents == null) {
          this.contents = Collection.collectionFromPath(this.schema, [key], value);
        } else if (assertCollection(this.contents)) {
          this.contents.set(key, value);
        }
      }
      /**
       * Sets a value in this document. For `!!set`, `value` needs to be a
       * boolean to add/remove the item from the set.
       */
      setIn(path, value) {
        if (Collection.isEmptyPath(path)) {
          this.contents = value;
        } else if (this.contents == null) {
          this.contents = Collection.collectionFromPath(this.schema, Array.from(path), value);
        } else if (assertCollection(this.contents)) {
          this.contents.setIn(path, value);
        }
      }
      /**
       * Change the YAML version and schema used by the document.
       * A `null` version disables support for directives, explicit tags, anchors, and aliases.
       * It also requires the `schema` option to be given as a `Schema` instance value.
       *
       * Overrides all previously set schema options.
       */
      setSchema(version, options = {}) {
        if (typeof version === "number")
          version = String(version);
        let opt;
        switch (version) {
          case "1.1":
            if (this.directives)
              this.directives.yaml.version = "1.1";
            else
              this.directives = new directives.Directives({ version: "1.1" });
            opt = { resolveKnownTags: false, schema: "yaml-1.1" };
            break;
          case "1.2":
          case "next":
            if (this.directives)
              this.directives.yaml.version = version;
            else
              this.directives = new directives.Directives({ version });
            opt = { resolveKnownTags: true, schema: "core" };
            break;
          case null:
            if (this.directives)
              delete this.directives;
            opt = null;
            break;
          default: {
            const sv = JSON.stringify(version);
            throw new Error(`Expected '1.1', '1.2' or null as first argument, but found: ${sv}`);
          }
        }
        if (options.schema instanceof Object)
          this.schema = options.schema;
        else if (opt)
          this.schema = new Schema.Schema(Object.assign(opt, options));
        else
          throw new Error(`With a null YAML version, the { schema: Schema } option is required`);
      }
      // json & jsonArg are only used from toJSON()
      toJS({ json, jsonArg, mapAsMap, maxAliasCount, onAnchor, reviver } = {}) {
        const ctx = {
          anchors: /* @__PURE__ */ new Map(),
          doc: this,
          keep: !json,
          mapAsMap: mapAsMap === true,
          mapKeyWarned: false,
          maxAliasCount: typeof maxAliasCount === "number" ? maxAliasCount : 100
        };
        const res = toJS.toJS(this.contents, jsonArg ?? "", ctx);
        if (typeof onAnchor === "function")
          for (const { count, res: res2 } of ctx.anchors.values())
            onAnchor(res2, count);
        return typeof reviver === "function" ? applyReviver.applyReviver(reviver, { "": res }, "", res) : res;
      }
      /**
       * A JSON representation of the document `contents`.
       *
       * @param jsonArg Used by `JSON.stringify` to indicate the array index or
       *   property name.
       */
      toJSON(jsonArg, onAnchor) {
        return this.toJS({ json: true, jsonArg, mapAsMap: false, onAnchor });
      }
      /** A YAML representation of the document. */
      toString(options = {}) {
        if (this.errors.length > 0)
          throw new Error("Document with errors cannot be stringified");
        if ("indent" in options && (!Number.isInteger(options.indent) || Number(options.indent) <= 0)) {
          const s = JSON.stringify(options.indent);
          throw new Error(`"indent" option must be a positive integer, not ${s}`);
        }
        return stringifyDocument.stringifyDocument(this, options);
      }
    };
    function assertCollection(contents) {
      if (identity.isCollection(contents))
        return true;
      throw new Error("Expected a YAML collection as document contents");
    }
    exports.Document = Document;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/errors.js
var require_errors = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/errors.js"(exports) {
    "use strict";
    var YAMLError = class extends Error {
      constructor(name, pos, code, message) {
        super();
        this.name = name;
        this.code = code;
        this.message = message;
        this.pos = pos;
      }
    };
    var YAMLParseError = class extends YAMLError {
      constructor(pos, code, message) {
        super("YAMLParseError", pos, code, message);
      }
    };
    var YAMLWarning = class extends YAMLError {
      constructor(pos, code, message) {
        super("YAMLWarning", pos, code, message);
      }
    };
    var prettifyError = (src, lc) => (error) => {
      if (error.pos[0] === -1)
        return;
      error.linePos = error.pos.map((pos) => lc.linePos(pos));
      const { line, col } = error.linePos[0];
      error.message += ` at line ${line}, column ${col}`;
      let ci = col - 1;
      let lineStr = src.substring(lc.lineStarts[line - 1], lc.lineStarts[line]).replace(/[\n\r]+$/, "");
      if (ci >= 60 && lineStr.length > 80) {
        const trimStart = Math.min(ci - 39, lineStr.length - 79);
        lineStr = "\u2026" + lineStr.substring(trimStart);
        ci -= trimStart - 1;
      }
      if (lineStr.length > 80)
        lineStr = lineStr.substring(0, 79) + "\u2026";
      if (line > 1 && /^ *$/.test(lineStr.substring(0, ci))) {
        let prev = src.substring(lc.lineStarts[line - 2], lc.lineStarts[line - 1]);
        if (prev.length > 80)
          prev = prev.substring(0, 79) + "\u2026\n";
        lineStr = prev + lineStr;
      }
      if (/[^ ]/.test(lineStr)) {
        let count = 1;
        const end = error.linePos[1];
        if (end?.line === line && end.col > col) {
          count = Math.max(1, Math.min(end.col - col, 80 - ci));
        }
        const pointer = " ".repeat(ci) + "^".repeat(count);
        error.message += `:

${lineStr}
${pointer}
`;
      }
    };
    exports.YAMLError = YAMLError;
    exports.YAMLParseError = YAMLParseError;
    exports.YAMLWarning = YAMLWarning;
    exports.prettifyError = prettifyError;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/resolve-props.js
var require_resolve_props = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/resolve-props.js"(exports) {
    "use strict";
    function resolveProps(tokens, { flow, indicator, next, offset, onError, parentIndent, startOnNewline }) {
      let spaceBefore = false;
      let atNewline = startOnNewline;
      let hasSpace = startOnNewline;
      let comment = "";
      let commentSep = "";
      let hasNewline = false;
      let reqSpace = false;
      let tab = null;
      let anchor = null;
      let tag = null;
      let newlineAfterProp = null;
      let comma = null;
      let found = null;
      let start = null;
      for (const token of tokens) {
        if (reqSpace) {
          if (token.type !== "space" && token.type !== "newline" && token.type !== "comma")
            onError(token.offset, "MISSING_CHAR", "Tags and anchors must be separated from the next token by white space");
          reqSpace = false;
        }
        if (tab) {
          if (atNewline && token.type !== "comment" && token.type !== "newline") {
            onError(tab, "TAB_AS_INDENT", "Tabs are not allowed as indentation");
          }
          tab = null;
        }
        switch (token.type) {
          case "space":
            if (!flow && (indicator !== "doc-start" || next?.type !== "flow-collection") && token.source.includes("	")) {
              tab = token;
            }
            hasSpace = true;
            break;
          case "comment": {
            if (!hasSpace)
              onError(token, "MISSING_CHAR", "Comments must be separated from other tokens by white space characters");
            const cb = token.source.substring(1) || " ";
            if (!comment)
              comment = cb;
            else
              comment += commentSep + cb;
            commentSep = "";
            atNewline = false;
            break;
          }
          case "newline":
            if (atNewline) {
              if (comment)
                comment += token.source;
              else if (!found || indicator !== "seq-item-ind")
                spaceBefore = true;
            } else
              commentSep += token.source;
            atNewline = true;
            hasNewline = true;
            if (anchor || tag)
              newlineAfterProp = token;
            hasSpace = true;
            break;
          case "anchor":
            if (anchor)
              onError(token, "MULTIPLE_ANCHORS", "A node can have at most one anchor");
            if (token.source.endsWith(":"))
              onError(token.offset + token.source.length - 1, "BAD_ALIAS", "Anchor ending in : is ambiguous", true);
            anchor = token;
            start ?? (start = token.offset);
            atNewline = false;
            hasSpace = false;
            reqSpace = true;
            break;
          case "tag": {
            if (tag)
              onError(token, "MULTIPLE_TAGS", "A node can have at most one tag");
            tag = token;
            start ?? (start = token.offset);
            atNewline = false;
            hasSpace = false;
            reqSpace = true;
            break;
          }
          case indicator:
            if (anchor || tag)
              onError(token, "BAD_PROP_ORDER", `Anchors and tags must be after the ${token.source} indicator`);
            if (found)
              onError(token, "UNEXPECTED_TOKEN", `Unexpected ${token.source} in ${flow ?? "collection"}`);
            found = token;
            atNewline = indicator === "seq-item-ind" || indicator === "explicit-key-ind";
            hasSpace = false;
            break;
          case "comma":
            if (flow) {
              if (comma)
                onError(token, "UNEXPECTED_TOKEN", `Unexpected , in ${flow}`);
              comma = token;
              atNewline = false;
              hasSpace = false;
              break;
            }
          // else fallthrough
          default:
            onError(token, "UNEXPECTED_TOKEN", `Unexpected ${token.type} token`);
            atNewline = false;
            hasSpace = false;
        }
      }
      const last = tokens[tokens.length - 1];
      const end = last ? last.offset + last.source.length : offset;
      if (reqSpace && next && next.type !== "space" && next.type !== "newline" && next.type !== "comma" && (next.type !== "scalar" || next.source !== "")) {
        onError(next.offset, "MISSING_CHAR", "Tags and anchors must be separated from the next token by white space");
      }
      if (tab && (atNewline && tab.indent <= parentIndent || next?.type === "block-map" || next?.type === "block-seq"))
        onError(tab, "TAB_AS_INDENT", "Tabs are not allowed as indentation");
      return {
        comma,
        found,
        spaceBefore,
        comment,
        hasNewline,
        anchor,
        tag,
        newlineAfterProp,
        end,
        start: start ?? end
      };
    }
    exports.resolveProps = resolveProps;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/util-contains-newline.js
var require_util_contains_newline = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/util-contains-newline.js"(exports) {
    "use strict";
    function containsNewline(key) {
      if (!key)
        return null;
      switch (key.type) {
        case "alias":
        case "scalar":
        case "double-quoted-scalar":
        case "single-quoted-scalar":
          if (key.source.includes("\n"))
            return true;
          if (key.end) {
            for (const st of key.end)
              if (st.type === "newline")
                return true;
          }
          return false;
        case "flow-collection":
          for (const it of key.items) {
            for (const st of it.start)
              if (st.type === "newline")
                return true;
            if (it.sep) {
              for (const st of it.sep)
                if (st.type === "newline")
                  return true;
            }
            if (containsNewline(it.key) || containsNewline(it.value))
              return true;
          }
          return false;
        default:
          return true;
      }
    }
    exports.containsNewline = containsNewline;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/util-flow-indent-check.js
var require_util_flow_indent_check = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/util-flow-indent-check.js"(exports) {
    "use strict";
    var utilContainsNewline = require_util_contains_newline();
    function flowIndentCheck(indent, fc, onError) {
      if (fc?.type === "flow-collection") {
        const end = fc.end[0];
        if (end.indent === indent && (end.source === "]" || end.source === "}") && utilContainsNewline.containsNewline(fc)) {
          const msg = "Flow end indicator should be more indented than parent";
          onError(end, "BAD_INDENT", msg, true);
        }
      }
    }
    exports.flowIndentCheck = flowIndentCheck;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/util-map-includes.js
var require_util_map_includes = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/util-map-includes.js"(exports) {
    "use strict";
    var identity = require_identity();
    function mapIncludes(ctx, items, search) {
      const { uniqueKeys } = ctx.options;
      if (uniqueKeys === false)
        return false;
      const isEqual = typeof uniqueKeys === "function" ? uniqueKeys : (a, b2) => a === b2 || identity.isScalar(a) && identity.isScalar(b2) && a.value === b2.value;
      return items.some((pair) => isEqual(pair.key, search));
    }
    exports.mapIncludes = mapIncludes;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/resolve-block-map.js
var require_resolve_block_map = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/resolve-block-map.js"(exports) {
    "use strict";
    var Pair = require_Pair();
    var YAMLMap = require_YAMLMap();
    var resolveProps = require_resolve_props();
    var utilContainsNewline = require_util_contains_newline();
    var utilFlowIndentCheck = require_util_flow_indent_check();
    var utilMapIncludes = require_util_map_includes();
    var startColMsg = "All mapping items must start at the same column";
    function resolveBlockMap({ composeNode, composeEmptyNode }, ctx, bm, onError, tag) {
      const NodeClass = tag?.nodeClass ?? YAMLMap.YAMLMap;
      const map = new NodeClass(ctx.schema);
      if (ctx.atRoot)
        ctx.atRoot = false;
      let offset = bm.offset;
      let commentEnd = null;
      for (const collItem of bm.items) {
        const { start, key, sep: sep2, value } = collItem;
        const keyProps = resolveProps.resolveProps(start, {
          indicator: "explicit-key-ind",
          next: key ?? sep2?.[0],
          offset,
          onError,
          parentIndent: bm.indent,
          startOnNewline: true
        });
        const implicitKey = !keyProps.found;
        if (implicitKey) {
          if (key) {
            if (key.type === "block-seq")
              onError(offset, "BLOCK_AS_IMPLICIT_KEY", "A block sequence may not be used as an implicit map key");
            else if ("indent" in key && key.indent !== bm.indent)
              onError(offset, "BAD_INDENT", startColMsg);
          }
          if (!keyProps.anchor && !keyProps.tag && !sep2) {
            commentEnd = keyProps.end;
            if (keyProps.comment) {
              if (map.comment)
                map.comment += "\n" + keyProps.comment;
              else
                map.comment = keyProps.comment;
            }
            continue;
          }
          if (keyProps.newlineAfterProp || utilContainsNewline.containsNewline(key)) {
            onError(key ?? start[start.length - 1], "MULTILINE_IMPLICIT_KEY", "Implicit keys need to be on a single line");
          }
        } else if (keyProps.found?.indent !== bm.indent) {
          onError(offset, "BAD_INDENT", startColMsg);
        }
        ctx.atKey = true;
        const keyStart = keyProps.end;
        const keyNode = key ? composeNode(ctx, key, keyProps, onError) : composeEmptyNode(ctx, keyStart, start, null, keyProps, onError);
        if (ctx.schema.compat)
          utilFlowIndentCheck.flowIndentCheck(bm.indent, key, onError);
        ctx.atKey = false;
        if (utilMapIncludes.mapIncludes(ctx, map.items, keyNode))
          onError(keyStart, "DUPLICATE_KEY", "Map keys must be unique");
        const valueProps = resolveProps.resolveProps(sep2 ?? [], {
          indicator: "map-value-ind",
          next: value,
          offset: keyNode.range[2],
          onError,
          parentIndent: bm.indent,
          startOnNewline: !key || key.type === "block-scalar"
        });
        offset = valueProps.end;
        if (valueProps.found) {
          if (implicitKey) {
            if (value?.type === "block-map" && !valueProps.hasNewline)
              onError(offset, "BLOCK_AS_IMPLICIT_KEY", "Nested mappings are not allowed in compact mappings");
            if (ctx.options.strict && keyProps.start < valueProps.found.offset - 1024)
              onError(keyNode.range, "KEY_OVER_1024_CHARS", "The : indicator must be at most 1024 chars after the start of an implicit block mapping key");
          }
          const valueNode = value ? composeNode(ctx, value, valueProps, onError) : composeEmptyNode(ctx, offset, sep2, null, valueProps, onError);
          if (ctx.schema.compat)
            utilFlowIndentCheck.flowIndentCheck(bm.indent, value, onError);
          offset = valueNode.range[2];
          const pair = new Pair.Pair(keyNode, valueNode);
          if (ctx.options.keepSourceTokens)
            pair.srcToken = collItem;
          map.items.push(pair);
        } else {
          if (implicitKey)
            onError(keyNode.range, "MISSING_CHAR", "Implicit map keys need to be followed by map values");
          if (valueProps.comment) {
            if (keyNode.comment)
              keyNode.comment += "\n" + valueProps.comment;
            else
              keyNode.comment = valueProps.comment;
          }
          const pair = new Pair.Pair(keyNode);
          if (ctx.options.keepSourceTokens)
            pair.srcToken = collItem;
          map.items.push(pair);
        }
      }
      if (commentEnd && commentEnd < offset)
        onError(commentEnd, "IMPOSSIBLE", "Map comment with trailing content");
      map.range = [bm.offset, offset, commentEnd ?? offset];
      return map;
    }
    exports.resolveBlockMap = resolveBlockMap;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/resolve-block-seq.js
var require_resolve_block_seq = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/resolve-block-seq.js"(exports) {
    "use strict";
    var YAMLSeq = require_YAMLSeq();
    var resolveProps = require_resolve_props();
    var utilFlowIndentCheck = require_util_flow_indent_check();
    function resolveBlockSeq({ composeNode, composeEmptyNode }, ctx, bs, onError, tag) {
      const NodeClass = tag?.nodeClass ?? YAMLSeq.YAMLSeq;
      const seq = new NodeClass(ctx.schema);
      if (ctx.atRoot)
        ctx.atRoot = false;
      if (ctx.atKey)
        ctx.atKey = false;
      let offset = bs.offset;
      let commentEnd = null;
      for (const { start, value } of bs.items) {
        const props = resolveProps.resolveProps(start, {
          indicator: "seq-item-ind",
          next: value,
          offset,
          onError,
          parentIndent: bs.indent,
          startOnNewline: true
        });
        if (!props.found) {
          if (props.anchor || props.tag || value) {
            if (value?.type === "block-seq")
              onError(props.end, "BAD_INDENT", "All sequence items must start at the same column");
            else
              onError(offset, "MISSING_CHAR", "Sequence item without - indicator");
          } else {
            commentEnd = props.end;
            if (props.comment)
              seq.comment = props.comment;
            continue;
          }
        }
        const node = value ? composeNode(ctx, value, props, onError) : composeEmptyNode(ctx, props.end, start, null, props, onError);
        if (ctx.schema.compat)
          utilFlowIndentCheck.flowIndentCheck(bs.indent, value, onError);
        offset = node.range[2];
        seq.items.push(node);
      }
      seq.range = [bs.offset, offset, commentEnd ?? offset];
      return seq;
    }
    exports.resolveBlockSeq = resolveBlockSeq;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/resolve-end.js
var require_resolve_end = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/resolve-end.js"(exports) {
    "use strict";
    function resolveEnd(end, offset, reqSpace, onError) {
      let comment = "";
      if (end) {
        let hasSpace = false;
        let sep2 = "";
        for (const token of end) {
          const { source, type } = token;
          switch (type) {
            case "space":
              hasSpace = true;
              break;
            case "comment": {
              if (reqSpace && !hasSpace)
                onError(token, "MISSING_CHAR", "Comments must be separated from other tokens by white space characters");
              const cb = source.substring(1) || " ";
              if (!comment)
                comment = cb;
              else
                comment += sep2 + cb;
              sep2 = "";
              break;
            }
            case "newline":
              if (comment)
                sep2 += source;
              hasSpace = true;
              break;
            default:
              onError(token, "UNEXPECTED_TOKEN", `Unexpected ${type} at node end`);
          }
          offset += source.length;
        }
      }
      return { comment, offset };
    }
    exports.resolveEnd = resolveEnd;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/resolve-flow-collection.js
var require_resolve_flow_collection = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/resolve-flow-collection.js"(exports) {
    "use strict";
    var identity = require_identity();
    var Pair = require_Pair();
    var YAMLMap = require_YAMLMap();
    var YAMLSeq = require_YAMLSeq();
    var resolveEnd = require_resolve_end();
    var resolveProps = require_resolve_props();
    var utilContainsNewline = require_util_contains_newline();
    var utilMapIncludes = require_util_map_includes();
    var blockMsg = "Block collections are not allowed within flow collections";
    var isBlock = (token) => token && (token.type === "block-map" || token.type === "block-seq");
    function resolveFlowCollection({ composeNode, composeEmptyNode }, ctx, fc, onError, tag) {
      const isMap = fc.start.source === "{";
      const fcName = isMap ? "flow map" : "flow sequence";
      const NodeClass = tag?.nodeClass ?? (isMap ? YAMLMap.YAMLMap : YAMLSeq.YAMLSeq);
      const coll = new NodeClass(ctx.schema);
      coll.flow = true;
      const atRoot = ctx.atRoot;
      if (atRoot)
        ctx.atRoot = false;
      if (ctx.atKey)
        ctx.atKey = false;
      let offset = fc.offset + fc.start.source.length;
      for (let i = 0; i < fc.items.length; ++i) {
        const collItem = fc.items[i];
        const { start, key, sep: sep2, value } = collItem;
        const props = resolveProps.resolveProps(start, {
          flow: fcName,
          indicator: "explicit-key-ind",
          next: key ?? sep2?.[0],
          offset,
          onError,
          parentIndent: fc.indent,
          startOnNewline: false
        });
        if (!props.found) {
          if (!props.anchor && !props.tag && !sep2 && !value) {
            if (i === 0 && props.comma)
              onError(props.comma, "UNEXPECTED_TOKEN", `Unexpected , in ${fcName}`);
            else if (i < fc.items.length - 1)
              onError(props.start, "UNEXPECTED_TOKEN", `Unexpected empty item in ${fcName}`);
            if (props.comment) {
              if (coll.comment)
                coll.comment += "\n" + props.comment;
              else
                coll.comment = props.comment;
            }
            offset = props.end;
            continue;
          }
          if (!isMap && ctx.options.strict && utilContainsNewline.containsNewline(key))
            onError(
              key,
              // checked by containsNewline()
              "MULTILINE_IMPLICIT_KEY",
              "Implicit keys of flow sequence pairs need to be on a single line"
            );
        }
        if (i === 0) {
          if (props.comma)
            onError(props.comma, "UNEXPECTED_TOKEN", `Unexpected , in ${fcName}`);
        } else {
          if (!props.comma)
            onError(props.start, "MISSING_CHAR", `Missing , between ${fcName} items`);
          if (props.comment) {
            let prevItemComment = "";
            loop: for (const st of start) {
              switch (st.type) {
                case "comma":
                case "space":
                  break;
                case "comment":
                  prevItemComment = st.source.substring(1);
                  break loop;
                default:
                  break loop;
              }
            }
            if (prevItemComment) {
              let prev = coll.items[coll.items.length - 1];
              if (identity.isPair(prev))
                prev = prev.value ?? prev.key;
              if (prev.comment)
                prev.comment += "\n" + prevItemComment;
              else
                prev.comment = prevItemComment;
              props.comment = props.comment.substring(prevItemComment.length + 1);
            }
          }
        }
        if (!isMap && !sep2 && !props.found) {
          const valueNode = value ? composeNode(ctx, value, props, onError) : composeEmptyNode(ctx, props.end, sep2, null, props, onError);
          coll.items.push(valueNode);
          offset = valueNode.range[2];
          if (isBlock(value))
            onError(valueNode.range, "BLOCK_IN_FLOW", blockMsg);
        } else {
          ctx.atKey = true;
          const keyStart = props.end;
          const keyNode = key ? composeNode(ctx, key, props, onError) : composeEmptyNode(ctx, keyStart, start, null, props, onError);
          if (isBlock(key))
            onError(keyNode.range, "BLOCK_IN_FLOW", blockMsg);
          ctx.atKey = false;
          const valueProps = resolveProps.resolveProps(sep2 ?? [], {
            flow: fcName,
            indicator: "map-value-ind",
            next: value,
            offset: keyNode.range[2],
            onError,
            parentIndent: fc.indent,
            startOnNewline: false
          });
          if (valueProps.found) {
            if (!isMap && !props.found && ctx.options.strict) {
              if (sep2)
                for (const st of sep2) {
                  if (st === valueProps.found)
                    break;
                  if (st.type === "newline") {
                    onError(st, "MULTILINE_IMPLICIT_KEY", "Implicit keys of flow sequence pairs need to be on a single line");
                    break;
                  }
                }
              if (props.start < valueProps.found.offset - 1024)
                onError(valueProps.found, "KEY_OVER_1024_CHARS", "The : indicator must be at most 1024 chars after the start of an implicit flow sequence key");
            }
          } else if (value) {
            if ("source" in value && value.source?.[0] === ":")
              onError(value, "MISSING_CHAR", `Missing space after : in ${fcName}`);
            else
              onError(valueProps.start, "MISSING_CHAR", `Missing , or : between ${fcName} items`);
          }
          const valueNode = value ? composeNode(ctx, value, valueProps, onError) : valueProps.found ? composeEmptyNode(ctx, valueProps.end, sep2, null, valueProps, onError) : null;
          if (valueNode) {
            if (isBlock(value))
              onError(valueNode.range, "BLOCK_IN_FLOW", blockMsg);
          } else if (valueProps.comment) {
            if (keyNode.comment)
              keyNode.comment += "\n" + valueProps.comment;
            else
              keyNode.comment = valueProps.comment;
          }
          const pair = new Pair.Pair(keyNode, valueNode);
          if (ctx.options.keepSourceTokens)
            pair.srcToken = collItem;
          if (isMap) {
            const map = coll;
            if (utilMapIncludes.mapIncludes(ctx, map.items, keyNode))
              onError(keyStart, "DUPLICATE_KEY", "Map keys must be unique");
            map.items.push(pair);
          } else {
            const map = new YAMLMap.YAMLMap(ctx.schema);
            map.flow = true;
            map.items.push(pair);
            const endRange = (valueNode ?? keyNode).range;
            map.range = [keyNode.range[0], endRange[1], endRange[2]];
            coll.items.push(map);
          }
          offset = valueNode ? valueNode.range[2] : valueProps.end;
        }
      }
      const expectedEnd = isMap ? "}" : "]";
      const [ce2, ...ee] = fc.end;
      let cePos = offset;
      if (ce2?.source === expectedEnd)
        cePos = ce2.offset + ce2.source.length;
      else {
        const name = fcName[0].toUpperCase() + fcName.substring(1);
        const msg = atRoot ? `${name} must end with a ${expectedEnd}` : `${name} in block collection must be sufficiently indented and end with a ${expectedEnd}`;
        onError(offset, atRoot ? "MISSING_CHAR" : "BAD_INDENT", msg);
        if (ce2 && ce2.source.length !== 1)
          ee.unshift(ce2);
      }
      if (ee.length > 0) {
        const end = resolveEnd.resolveEnd(ee, cePos, ctx.options.strict, onError);
        if (end.comment) {
          if (coll.comment)
            coll.comment += "\n" + end.comment;
          else
            coll.comment = end.comment;
        }
        coll.range = [fc.offset, cePos, end.offset];
      } else {
        coll.range = [fc.offset, cePos, cePos];
      }
      return coll;
    }
    exports.resolveFlowCollection = resolveFlowCollection;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/compose-collection.js
var require_compose_collection = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/compose-collection.js"(exports) {
    "use strict";
    var identity = require_identity();
    var Scalar = require_Scalar();
    var YAMLMap = require_YAMLMap();
    var YAMLSeq = require_YAMLSeq();
    var resolveBlockMap = require_resolve_block_map();
    var resolveBlockSeq = require_resolve_block_seq();
    var resolveFlowCollection = require_resolve_flow_collection();
    function resolveCollection(CN, ctx, token, onError, tagName, tag) {
      const coll = token.type === "block-map" ? resolveBlockMap.resolveBlockMap(CN, ctx, token, onError, tag) : token.type === "block-seq" ? resolveBlockSeq.resolveBlockSeq(CN, ctx, token, onError, tag) : resolveFlowCollection.resolveFlowCollection(CN, ctx, token, onError, tag);
      const Coll = coll.constructor;
      if (tagName === "!" || tagName === Coll.tagName) {
        coll.tag = Coll.tagName;
        return coll;
      }
      if (tagName)
        coll.tag = tagName;
      return coll;
    }
    function composeCollection(CN, ctx, token, props, onError) {
      const tagToken = props.tag;
      const tagName = !tagToken ? null : ctx.directives.tagName(tagToken.source, (msg) => onError(tagToken, "TAG_RESOLVE_FAILED", msg));
      if (token.type === "block-seq") {
        const { anchor, newlineAfterProp: nl } = props;
        const lastProp = anchor && tagToken ? anchor.offset > tagToken.offset ? anchor : tagToken : anchor ?? tagToken;
        if (lastProp && (!nl || nl.offset < lastProp.offset)) {
          const message = "Missing newline after block sequence props";
          onError(lastProp, "MISSING_CHAR", message);
        }
      }
      const expType = token.type === "block-map" ? "map" : token.type === "block-seq" ? "seq" : token.start.source === "{" ? "map" : "seq";
      if (!tagToken || !tagName || tagName === "!" || tagName === YAMLMap.YAMLMap.tagName && expType === "map" || tagName === YAMLSeq.YAMLSeq.tagName && expType === "seq") {
        return resolveCollection(CN, ctx, token, onError, tagName);
      }
      let tag = ctx.schema.tags.find((t) => t.tag === tagName && t.collection === expType);
      if (!tag) {
        const kt = ctx.schema.knownTags[tagName];
        if (kt?.collection === expType) {
          ctx.schema.tags.push(Object.assign({}, kt, { default: false }));
          tag = kt;
        } else {
          if (kt) {
            onError(tagToken, "BAD_COLLECTION_TYPE", `${kt.tag} used for ${expType} collection, but expects ${kt.collection ?? "scalar"}`, true);
          } else {
            onError(tagToken, "TAG_RESOLVE_FAILED", `Unresolved tag: ${tagName}`, true);
          }
          return resolveCollection(CN, ctx, token, onError, tagName);
        }
      }
      const coll = resolveCollection(CN, ctx, token, onError, tagName, tag);
      const res = tag.resolve?.(coll, (msg) => onError(tagToken, "TAG_RESOLVE_FAILED", msg), ctx.options) ?? coll;
      const node = identity.isNode(res) ? res : new Scalar.Scalar(res);
      node.range = coll.range;
      node.tag = tagName;
      if (tag?.format)
        node.format = tag.format;
      return node;
    }
    exports.composeCollection = composeCollection;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/resolve-block-scalar.js
var require_resolve_block_scalar = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/resolve-block-scalar.js"(exports) {
    "use strict";
    var Scalar = require_Scalar();
    function resolveBlockScalar(ctx, scalar, onError) {
      const start = scalar.offset;
      const header = parseBlockScalarHeader(scalar, ctx.options.strict, onError);
      if (!header)
        return { value: "", type: null, comment: "", range: [start, start, start] };
      const type = header.mode === ">" ? Scalar.Scalar.BLOCK_FOLDED : Scalar.Scalar.BLOCK_LITERAL;
      const lines = scalar.source ? splitLines(scalar.source) : [];
      let chompStart = lines.length;
      for (let i = lines.length - 1; i >= 0; --i) {
        const content = lines[i][1];
        if (content === "" || content === "\r")
          chompStart = i;
        else
          break;
      }
      if (chompStart === 0) {
        const value2 = header.chomp === "+" && lines.length > 0 ? "\n".repeat(Math.max(1, lines.length - 1)) : "";
        let end2 = start + header.length;
        if (scalar.source)
          end2 += scalar.source.length;
        return { value: value2, type, comment: header.comment, range: [start, end2, end2] };
      }
      let trimIndent = scalar.indent + header.indent;
      let offset = scalar.offset + header.length;
      let contentStart = 0;
      for (let i = 0; i < chompStart; ++i) {
        const [indent, content] = lines[i];
        if (content === "" || content === "\r") {
          if (header.indent === 0 && indent.length > trimIndent)
            trimIndent = indent.length;
        } else {
          if (indent.length < trimIndent) {
            const message = "Block scalars with more-indented leading empty lines must use an explicit indentation indicator";
            onError(offset + indent.length, "MISSING_CHAR", message);
          }
          if (header.indent === 0)
            trimIndent = indent.length;
          contentStart = i;
          if (trimIndent === 0 && !ctx.atRoot) {
            const message = "Block scalar values in collections must be indented";
            onError(offset, "BAD_INDENT", message);
          }
          break;
        }
        offset += indent.length + content.length + 1;
      }
      for (let i = lines.length - 1; i >= chompStart; --i) {
        if (lines[i][0].length > trimIndent)
          chompStart = i + 1;
      }
      let value = "";
      let sep2 = "";
      let prevMoreIndented = false;
      for (let i = 0; i < contentStart; ++i)
        value += lines[i][0].slice(trimIndent) + "\n";
      for (let i = contentStart; i < chompStart; ++i) {
        let [indent, content] = lines[i];
        offset += indent.length + content.length + 1;
        const crlf = content[content.length - 1] === "\r";
        if (crlf)
          content = content.slice(0, -1);
        if (content && indent.length < trimIndent) {
          const src = header.indent ? "explicit indentation indicator" : "first line";
          const message = `Block scalar lines must not be less indented than their ${src}`;
          onError(offset - content.length - (crlf ? 2 : 1), "BAD_INDENT", message);
          indent = "";
        }
        if (type === Scalar.Scalar.BLOCK_LITERAL) {
          value += sep2 + indent.slice(trimIndent) + content;
          sep2 = "\n";
        } else if (indent.length > trimIndent || content[0] === "	") {
          if (sep2 === " ")
            sep2 = "\n";
          else if (!prevMoreIndented && sep2 === "\n")
            sep2 = "\n\n";
          value += sep2 + indent.slice(trimIndent) + content;
          sep2 = "\n";
          prevMoreIndented = true;
        } else if (content === "") {
          if (sep2 === "\n")
            value += "\n";
          else
            sep2 = "\n";
        } else {
          value += sep2 + content;
          sep2 = " ";
          prevMoreIndented = false;
        }
      }
      switch (header.chomp) {
        case "-":
          break;
        case "+":
          for (let i = chompStart; i < lines.length; ++i)
            value += "\n" + lines[i][0].slice(trimIndent);
          if (value[value.length - 1] !== "\n")
            value += "\n";
          break;
        default:
          value += "\n";
      }
      const end = start + header.length + scalar.source.length;
      return { value, type, comment: header.comment, range: [start, end, end] };
    }
    function parseBlockScalarHeader({ offset, props }, strict, onError) {
      if (props[0].type !== "block-scalar-header") {
        onError(props[0], "IMPOSSIBLE", "Block scalar header not found");
        return null;
      }
      const { source } = props[0];
      const mode = source[0];
      let indent = 0;
      let chomp = "";
      let error = -1;
      for (let i = 1; i < source.length; ++i) {
        const ch = source[i];
        if (!chomp && (ch === "-" || ch === "+"))
          chomp = ch;
        else {
          const n = Number(ch);
          if (!indent && n)
            indent = n;
          else if (error === -1)
            error = offset + i;
        }
      }
      if (error !== -1)
        onError(error, "UNEXPECTED_TOKEN", `Block scalar header includes extra characters: ${source}`);
      let hasSpace = false;
      let comment = "";
      let length = source.length;
      for (let i = 1; i < props.length; ++i) {
        const token = props[i];
        switch (token.type) {
          case "space":
            hasSpace = true;
          // fallthrough
          case "newline":
            length += token.source.length;
            break;
          case "comment":
            if (strict && !hasSpace) {
              const message = "Comments must be separated from other tokens by white space characters";
              onError(token, "MISSING_CHAR", message);
            }
            length += token.source.length;
            comment = token.source.substring(1);
            break;
          case "error":
            onError(token, "UNEXPECTED_TOKEN", token.message);
            length += token.source.length;
            break;
          /* istanbul ignore next should not happen */
          default: {
            const message = `Unexpected token in block scalar header: ${token.type}`;
            onError(token, "UNEXPECTED_TOKEN", message);
            const ts = token.source;
            if (ts && typeof ts === "string")
              length += ts.length;
          }
        }
      }
      return { mode, indent, chomp, comment, length };
    }
    function splitLines(source) {
      const split = source.split(/\n( *)/);
      const first = split[0];
      const m = first.match(/^( *)/);
      const line0 = m?.[1] ? [m[1], first.slice(m[1].length)] : ["", first];
      const lines = [line0];
      for (let i = 1; i < split.length; i += 2)
        lines.push([split[i], split[i + 1]]);
      return lines;
    }
    exports.resolveBlockScalar = resolveBlockScalar;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/resolve-flow-scalar.js
var require_resolve_flow_scalar = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/resolve-flow-scalar.js"(exports) {
    "use strict";
    var Scalar = require_Scalar();
    var resolveEnd = require_resolve_end();
    function resolveFlowScalar(scalar, strict, onError) {
      const { offset, type, source, end } = scalar;
      let _type;
      let value;
      const _onError = (rel, code, msg) => onError(offset + rel, code, msg);
      switch (type) {
        case "scalar":
          _type = Scalar.Scalar.PLAIN;
          value = plainValue(source, _onError);
          break;
        case "single-quoted-scalar":
          _type = Scalar.Scalar.QUOTE_SINGLE;
          value = singleQuotedValue(source, _onError);
          break;
        case "double-quoted-scalar":
          _type = Scalar.Scalar.QUOTE_DOUBLE;
          value = doubleQuotedValue(source, _onError);
          break;
        /* istanbul ignore next should not happen */
        default:
          onError(scalar, "UNEXPECTED_TOKEN", `Expected a flow scalar value, but found: ${type}`);
          return {
            value: "",
            type: null,
            comment: "",
            range: [offset, offset + source.length, offset + source.length]
          };
      }
      const valueEnd = offset + source.length;
      const re = resolveEnd.resolveEnd(end, valueEnd, strict, onError);
      return {
        value,
        type: _type,
        comment: re.comment,
        range: [offset, valueEnd, re.offset]
      };
    }
    function plainValue(source, onError) {
      let badChar = "";
      switch (source[0]) {
        /* istanbul ignore next should not happen */
        case "	":
          badChar = "a tab character";
          break;
        case ",":
          badChar = "flow indicator character ,";
          break;
        case "%":
          badChar = "directive indicator character %";
          break;
        case "|":
        case ">": {
          badChar = `block scalar indicator ${source[0]}`;
          break;
        }
        case "@":
        case "`": {
          badChar = `reserved character ${source[0]}`;
          break;
        }
      }
      if (badChar)
        onError(0, "BAD_SCALAR_START", `Plain value cannot start with ${badChar}`);
      return foldLines(source);
    }
    function singleQuotedValue(source, onError) {
      if (source[source.length - 1] !== "'" || source.length === 1)
        onError(source.length, "MISSING_CHAR", "Missing closing 'quote");
      return foldLines(source.slice(1, -1)).replace(/''/g, "'");
    }
    function foldLines(source) {
      let first, line;
      try {
        first = new RegExp("(.*?)(?<![ 	])[ 	]*\r?\n", "sy");
        line = new RegExp("[ 	]*(.*?)(?:(?<![ 	])[ 	]*)?\r?\n", "sy");
      } catch {
        first = /(.*?)[ \t]*\r?\n/sy;
        line = /[ \t]*(.*?)[ \t]*\r?\n/sy;
      }
      let match = first.exec(source);
      if (!match)
        return source;
      let res = match[1];
      let sep2 = " ";
      let pos = first.lastIndex;
      line.lastIndex = pos;
      while (match = line.exec(source)) {
        if (match[1] === "") {
          if (sep2 === "\n")
            res += sep2;
          else
            sep2 = "\n";
        } else {
          res += sep2 + match[1];
          sep2 = " ";
        }
        pos = line.lastIndex;
      }
      const last = /[ \t]*(.*)/sy;
      last.lastIndex = pos;
      match = last.exec(source);
      return res + sep2 + (match?.[1] ?? "");
    }
    function doubleQuotedValue(source, onError) {
      let res = "";
      for (let i = 1; i < source.length - 1; ++i) {
        const ch = source[i];
        if (ch === "\r" && source[i + 1] === "\n")
          continue;
        if (ch === "\n") {
          const { fold, offset } = foldNewline(source, i);
          res += fold;
          i = offset;
        } else if (ch === "\\") {
          let next = source[++i];
          const cc = escapeCodes[next];
          if (cc)
            res += cc;
          else if (next === "\n") {
            next = source[i + 1];
            while (next === " " || next === "	")
              next = source[++i + 1];
          } else if (next === "\r" && source[i + 1] === "\n") {
            next = source[++i + 1];
            while (next === " " || next === "	")
              next = source[++i + 1];
          } else if (next === "x" || next === "u" || next === "U") {
            const length = next === "x" ? 2 : next === "u" ? 4 : 8;
            res += parseCharCode(source, i + 1, length, onError);
            i += length;
          } else {
            const raw = source.substr(i - 1, 2);
            onError(i - 1, "BAD_DQ_ESCAPE", `Invalid escape sequence ${raw}`);
            res += raw;
          }
        } else if (ch === " " || ch === "	") {
          const wsStart = i;
          let next = source[i + 1];
          while (next === " " || next === "	")
            next = source[++i + 1];
          if (next !== "\n" && !(next === "\r" && source[i + 2] === "\n"))
            res += i > wsStart ? source.slice(wsStart, i + 1) : ch;
        } else {
          res += ch;
        }
      }
      if (source[source.length - 1] !== '"' || source.length === 1)
        onError(source.length, "MISSING_CHAR", 'Missing closing "quote');
      return res;
    }
    function foldNewline(source, offset) {
      let fold = "";
      let ch = source[offset + 1];
      while (ch === " " || ch === "	" || ch === "\n" || ch === "\r") {
        if (ch === "\r" && source[offset + 2] !== "\n")
          break;
        if (ch === "\n")
          fold += "\n";
        offset += 1;
        ch = source[offset + 1];
      }
      if (!fold)
        fold = " ";
      return { fold, offset };
    }
    var escapeCodes = {
      "0": "\0",
      // null character
      a: "\x07",
      // bell character
      b: "\b",
      // backspace
      e: "\x1B",
      // escape character
      f: "\f",
      // form feed
      n: "\n",
      // line feed
      r: "\r",
      // carriage return
      t: "	",
      // horizontal tab
      v: "\v",
      // vertical tab
      N: "\x85",
      // Unicode next line
      _: "\xA0",
      // Unicode non-breaking space
      L: "\u2028",
      // Unicode line separator
      P: "\u2029",
      // Unicode paragraph separator
      " ": " ",
      '"': '"',
      "/": "/",
      "\\": "\\",
      "	": "	"
    };
    function parseCharCode(source, offset, length, onError) {
      const cc = source.substr(offset, length);
      const ok = cc.length === length && /^[0-9a-fA-F]+$/.test(cc);
      const code = ok ? parseInt(cc, 16) : NaN;
      try {
        return String.fromCodePoint(code);
      } catch {
        const raw = source.substr(offset - 2, length + 2);
        onError(offset - 2, "BAD_DQ_ESCAPE", `Invalid escape sequence ${raw}`);
        return raw;
      }
    }
    exports.resolveFlowScalar = resolveFlowScalar;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/compose-scalar.js
var require_compose_scalar = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/compose-scalar.js"(exports) {
    "use strict";
    var identity = require_identity();
    var Scalar = require_Scalar();
    var resolveBlockScalar = require_resolve_block_scalar();
    var resolveFlowScalar = require_resolve_flow_scalar();
    function composeScalar(ctx, token, tagToken, onError) {
      const { value, type, comment, range } = token.type === "block-scalar" ? resolveBlockScalar.resolveBlockScalar(ctx, token, onError) : resolveFlowScalar.resolveFlowScalar(token, ctx.options.strict, onError);
      const tagName = tagToken ? ctx.directives.tagName(tagToken.source, (msg) => onError(tagToken, "TAG_RESOLVE_FAILED", msg)) : null;
      let tag;
      if (ctx.options.stringKeys && ctx.atKey) {
        tag = ctx.schema[identity.SCALAR];
      } else if (tagName)
        tag = findScalarTagByName(ctx.schema, value, tagName, tagToken, onError);
      else if (token.type === "scalar")
        tag = findScalarTagByTest(ctx, value, token, onError);
      else
        tag = ctx.schema[identity.SCALAR];
      let scalar;
      try {
        const res = tag.resolve(value, (msg) => onError(tagToken ?? token, "TAG_RESOLVE_FAILED", msg), ctx.options);
        scalar = identity.isScalar(res) ? res : new Scalar.Scalar(res);
      } catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        onError(tagToken ?? token, "TAG_RESOLVE_FAILED", msg);
        scalar = new Scalar.Scalar(value);
      }
      scalar.range = range;
      scalar.source = value;
      if (type)
        scalar.type = type;
      if (tagName)
        scalar.tag = tagName;
      if (tag.format)
        scalar.format = tag.format;
      if (comment)
        scalar.comment = comment;
      return scalar;
    }
    function findScalarTagByName(schema, value, tagName, tagToken, onError) {
      if (tagName === "!")
        return schema[identity.SCALAR];
      const matchWithTest = [];
      for (const tag of schema.tags) {
        if (!tag.collection && tag.tag === tagName) {
          if (tag.default && tag.test)
            matchWithTest.push(tag);
          else
            return tag;
        }
      }
      for (const tag of matchWithTest)
        if (tag.test?.test(value))
          return tag;
      const kt = schema.knownTags[tagName];
      if (kt && !kt.collection) {
        schema.tags.push(Object.assign({}, kt, { default: false, test: void 0 }));
        return kt;
      }
      onError(tagToken, "TAG_RESOLVE_FAILED", `Unresolved tag: ${tagName}`, tagName !== "tag:yaml.org,2002:str");
      return schema[identity.SCALAR];
    }
    function findScalarTagByTest({ atKey, directives, schema }, value, token, onError) {
      const tag = schema.tags.find((tag2) => (tag2.default === true || atKey && tag2.default === "key") && tag2.test?.test(value)) || schema[identity.SCALAR];
      if (schema.compat) {
        const compat = schema.compat.find((tag2) => tag2.default && tag2.test?.test(value)) ?? schema[identity.SCALAR];
        if (tag.tag !== compat.tag) {
          const ts = directives.tagString(tag.tag);
          const cs = directives.tagString(compat.tag);
          const msg = `Value may be parsed as either ${ts} or ${cs}`;
          onError(token, "TAG_RESOLVE_FAILED", msg, true);
        }
      }
      return tag;
    }
    exports.composeScalar = composeScalar;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/util-empty-scalar-position.js
var require_util_empty_scalar_position = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/util-empty-scalar-position.js"(exports) {
    "use strict";
    function emptyScalarPosition(offset, before, pos) {
      if (before) {
        pos ?? (pos = before.length);
        for (let i = pos - 1; i >= 0; --i) {
          let st = before[i];
          switch (st.type) {
            case "space":
            case "comment":
            case "newline":
              offset -= st.source.length;
              continue;
          }
          st = before[++i];
          while (st?.type === "space") {
            offset += st.source.length;
            st = before[++i];
          }
          break;
        }
      }
      return offset;
    }
    exports.emptyScalarPosition = emptyScalarPosition;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/compose-node.js
var require_compose_node = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/compose-node.js"(exports) {
    "use strict";
    var Alias = require_Alias();
    var identity = require_identity();
    var composeCollection = require_compose_collection();
    var composeScalar = require_compose_scalar();
    var resolveEnd = require_resolve_end();
    var utilEmptyScalarPosition = require_util_empty_scalar_position();
    var CN = { composeNode, composeEmptyNode };
    function composeNode(ctx, token, props, onError) {
      const atKey = ctx.atKey;
      const { spaceBefore, comment, anchor, tag } = props;
      let node;
      let isSrcToken = true;
      switch (token.type) {
        case "alias":
          node = composeAlias(ctx, token, onError);
          if (anchor || tag)
            onError(token, "ALIAS_PROPS", "An alias node must not specify any properties");
          break;
        case "scalar":
        case "single-quoted-scalar":
        case "double-quoted-scalar":
        case "block-scalar":
          node = composeScalar.composeScalar(ctx, token, tag, onError);
          if (anchor)
            node.anchor = anchor.source.substring(1);
          break;
        case "block-map":
        case "block-seq":
        case "flow-collection":
          try {
            node = composeCollection.composeCollection(CN, ctx, token, props, onError);
            if (anchor)
              node.anchor = anchor.source.substring(1);
          } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            onError(token, "RESOURCE_EXHAUSTION", message);
          }
          break;
        default: {
          const message = token.type === "error" ? token.message : `Unsupported token (type: ${token.type})`;
          onError(token, "UNEXPECTED_TOKEN", message);
          isSrcToken = false;
        }
      }
      node ?? (node = composeEmptyNode(ctx, token.offset, void 0, null, props, onError));
      if (anchor && node.anchor === "")
        onError(anchor, "BAD_ALIAS", "Anchor cannot be an empty string");
      if (atKey && ctx.options.stringKeys && (!identity.isScalar(node) || typeof node.value !== "string" || node.tag && node.tag !== "tag:yaml.org,2002:str")) {
        const msg = "With stringKeys, all keys must be strings";
        onError(tag ?? token, "NON_STRING_KEY", msg);
      }
      if (spaceBefore)
        node.spaceBefore = true;
      if (comment) {
        if (token.type === "scalar" && token.source === "")
          node.comment = comment;
        else
          node.commentBefore = comment;
      }
      if (ctx.options.keepSourceTokens && isSrcToken)
        node.srcToken = token;
      return node;
    }
    function composeEmptyNode(ctx, offset, before, pos, { spaceBefore, comment, anchor, tag, end }, onError) {
      const token = {
        type: "scalar",
        offset: utilEmptyScalarPosition.emptyScalarPosition(offset, before, pos),
        indent: -1,
        source: ""
      };
      const node = composeScalar.composeScalar(ctx, token, tag, onError);
      if (anchor) {
        node.anchor = anchor.source.substring(1);
        if (node.anchor === "")
          onError(anchor, "BAD_ALIAS", "Anchor cannot be an empty string");
      }
      if (spaceBefore)
        node.spaceBefore = true;
      if (comment) {
        node.comment = comment;
        node.range[2] = end;
      }
      return node;
    }
    function composeAlias({ options }, { offset, source, end }, onError) {
      const alias = new Alias.Alias(source.substring(1));
      if (alias.source === "")
        onError(offset, "BAD_ALIAS", "Alias cannot be an empty string");
      if (alias.source.endsWith(":"))
        onError(offset + source.length - 1, "BAD_ALIAS", "Alias ending in : is ambiguous", true);
      const valueEnd = offset + source.length;
      const re = resolveEnd.resolveEnd(end, valueEnd, options.strict, onError);
      alias.range = [offset, valueEnd, re.offset];
      if (re.comment)
        alias.comment = re.comment;
      return alias;
    }
    exports.composeEmptyNode = composeEmptyNode;
    exports.composeNode = composeNode;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/compose-doc.js
var require_compose_doc = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/compose-doc.js"(exports) {
    "use strict";
    var Document = require_Document();
    var composeNode = require_compose_node();
    var resolveEnd = require_resolve_end();
    var resolveProps = require_resolve_props();
    function composeDoc(options, directives, { offset, start, value, end }, onError) {
      const opts = Object.assign({ _directives: directives }, options);
      const doc = new Document.Document(void 0, opts);
      const ctx = {
        atKey: false,
        atRoot: true,
        directives: doc.directives,
        options: doc.options,
        schema: doc.schema
      };
      const props = resolveProps.resolveProps(start, {
        indicator: "doc-start",
        next: value ?? end?.[0],
        offset,
        onError,
        parentIndent: 0,
        startOnNewline: true
      });
      if (props.found) {
        doc.directives.docStart = true;
        if (value && (value.type === "block-map" || value.type === "block-seq") && !props.hasNewline)
          onError(props.end, "MISSING_CHAR", "Block collection cannot start on same line with directives-end marker");
      }
      doc.contents = value ? composeNode.composeNode(ctx, value, props, onError) : composeNode.composeEmptyNode(ctx, props.end, start, null, props, onError);
      const contentEnd = doc.contents.range[2];
      const re = resolveEnd.resolveEnd(end, contentEnd, false, onError);
      if (re.comment)
        doc.comment = re.comment;
      doc.range = [offset, contentEnd, re.offset];
      return doc;
    }
    exports.composeDoc = composeDoc;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/composer.js
var require_composer = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/compose/composer.js"(exports) {
    "use strict";
    var node_process = __require("process");
    var directives = require_directives();
    var Document = require_Document();
    var errors = require_errors();
    var identity = require_identity();
    var composeDoc = require_compose_doc();
    var resolveEnd = require_resolve_end();
    function getErrorPos(src) {
      if (typeof src === "number")
        return [src, src + 1];
      if (Array.isArray(src))
        return src.length === 2 ? src : [src[0], src[1]];
      const { offset, source } = src;
      return [offset, offset + (typeof source === "string" ? source.length : 1)];
    }
    function parsePrelude(prelude) {
      let comment = "";
      let atComment = false;
      let afterEmptyLine = false;
      for (let i = 0; i < prelude.length; ++i) {
        const source = prelude[i];
        switch (source[0]) {
          case "#":
            comment += (comment === "" ? "" : afterEmptyLine ? "\n\n" : "\n") + (source.substring(1) || " ");
            atComment = true;
            afterEmptyLine = false;
            break;
          case "%":
            if (prelude[i + 1]?.[0] !== "#")
              i += 1;
            atComment = false;
            break;
          default:
            if (!atComment)
              afterEmptyLine = true;
            atComment = false;
        }
      }
      return { comment, afterEmptyLine };
    }
    var Composer = class {
      constructor(options = {}) {
        this.doc = null;
        this.atDirectives = false;
        this.prelude = [];
        this.errors = [];
        this.warnings = [];
        this.onError = (source, code, message, warning) => {
          const pos = getErrorPos(source);
          if (warning)
            this.warnings.push(new errors.YAMLWarning(pos, code, message));
          else
            this.errors.push(new errors.YAMLParseError(pos, code, message));
        };
        this.directives = new directives.Directives({ version: options.version || "1.2" });
        this.options = options;
      }
      decorate(doc, afterDoc) {
        const { comment, afterEmptyLine } = parsePrelude(this.prelude);
        if (comment) {
          const dc = doc.contents;
          if (afterDoc) {
            doc.comment = doc.comment ? `${doc.comment}
${comment}` : comment;
          } else if (afterEmptyLine || doc.directives.docStart || !dc) {
            doc.commentBefore = comment;
          } else if (identity.isCollection(dc) && !dc.flow && dc.items.length > 0) {
            let it = dc.items[0];
            if (identity.isPair(it))
              it = it.key;
            const cb = it.commentBefore;
            it.commentBefore = cb ? `${comment}
${cb}` : comment;
          } else {
            const cb = dc.commentBefore;
            dc.commentBefore = cb ? `${comment}
${cb}` : comment;
          }
        }
        if (afterDoc) {
          for (let i = 0; i < this.errors.length; ++i)
            doc.errors.push(this.errors[i]);
          for (let i = 0; i < this.warnings.length; ++i)
            doc.warnings.push(this.warnings[i]);
        } else {
          doc.errors = this.errors;
          doc.warnings = this.warnings;
        }
        this.prelude = [];
        this.errors = [];
        this.warnings = [];
      }
      /**
       * Current stream status information.
       *
       * Mostly useful at the end of input for an empty stream.
       */
      streamInfo() {
        return {
          comment: parsePrelude(this.prelude).comment,
          directives: this.directives,
          errors: this.errors,
          warnings: this.warnings
        };
      }
      /**
       * Compose tokens into documents.
       *
       * @param forceDoc - If the stream contains no document, still emit a final document including any comments and directives that would be applied to a subsequent document.
       * @param endOffset - Should be set if `forceDoc` is also set, to set the document range end and to indicate errors correctly.
       */
      *compose(tokens, forceDoc = false, endOffset = -1) {
        for (const token of tokens)
          yield* this.next(token);
        yield* this.end(forceDoc, endOffset);
      }
      /** Advance the composer by one CST token. */
      *next(token) {
        if (node_process.env.LOG_STREAM)
          console.dir(token, { depth: null });
        switch (token.type) {
          case "directive":
            this.directives.add(token.source, (offset, message, warning) => {
              const pos = getErrorPos(token);
              pos[0] += offset;
              this.onError(pos, "BAD_DIRECTIVE", message, warning);
            });
            this.prelude.push(token.source);
            this.atDirectives = true;
            break;
          case "document": {
            const doc = composeDoc.composeDoc(this.options, this.directives, token, this.onError);
            if (this.atDirectives && !doc.directives.docStart)
              this.onError(token, "MISSING_CHAR", "Missing directives-end/doc-start indicator line");
            this.decorate(doc, false);
            if (this.doc)
              yield this.doc;
            this.doc = doc;
            this.atDirectives = false;
            break;
          }
          case "byte-order-mark":
          case "space":
            break;
          case "comment":
          case "newline":
            this.prelude.push(token.source);
            break;
          case "error": {
            const msg = token.source ? `${token.message}: ${JSON.stringify(token.source)}` : token.message;
            const error = new errors.YAMLParseError(getErrorPos(token), "UNEXPECTED_TOKEN", msg);
            if (this.atDirectives || !this.doc)
              this.errors.push(error);
            else
              this.doc.errors.push(error);
            break;
          }
          case "doc-end": {
            if (!this.doc) {
              const msg = "Unexpected doc-end without preceding document";
              this.errors.push(new errors.YAMLParseError(getErrorPos(token), "UNEXPECTED_TOKEN", msg));
              break;
            }
            this.doc.directives.docEnd = true;
            const end = resolveEnd.resolveEnd(token.end, token.offset + token.source.length, this.doc.options.strict, this.onError);
            this.decorate(this.doc, true);
            if (end.comment) {
              const dc = this.doc.comment;
              this.doc.comment = dc ? `${dc}
${end.comment}` : end.comment;
            }
            this.doc.range[2] = end.offset;
            break;
          }
          default:
            this.errors.push(new errors.YAMLParseError(getErrorPos(token), "UNEXPECTED_TOKEN", `Unsupported token ${token.type}`));
        }
      }
      /**
       * Call at end of input to yield any remaining document.
       *
       * @param forceDoc - If the stream contains no document, still emit a final document including any comments and directives that would be applied to a subsequent document.
       * @param endOffset - Should be set if `forceDoc` is also set, to set the document range end and to indicate errors correctly.
       */
      *end(forceDoc = false, endOffset = -1) {
        if (this.doc) {
          this.decorate(this.doc, true);
          yield this.doc;
          this.doc = null;
        } else if (forceDoc) {
          const opts = Object.assign({ _directives: this.directives }, this.options);
          const doc = new Document.Document(void 0, opts);
          if (this.atDirectives)
            this.onError(endOffset, "MISSING_CHAR", "Missing directives-end indicator line");
          doc.range = [0, endOffset, endOffset];
          this.decorate(doc, false);
          yield doc;
        }
      }
    };
    exports.Composer = Composer;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/parse/cst-scalar.js
var require_cst_scalar = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/parse/cst-scalar.js"(exports) {
    "use strict";
    var resolveBlockScalar = require_resolve_block_scalar();
    var resolveFlowScalar = require_resolve_flow_scalar();
    var errors = require_errors();
    var stringifyString = require_stringifyString();
    function resolveAsScalar(token, strict = true, onError) {
      if (token) {
        const _onError = (pos, code, message) => {
          const offset = typeof pos === "number" ? pos : Array.isArray(pos) ? pos[0] : pos.offset;
          if (onError)
            onError(offset, code, message);
          else
            throw new errors.YAMLParseError([offset, offset + 1], code, message);
        };
        switch (token.type) {
          case "scalar":
          case "single-quoted-scalar":
          case "double-quoted-scalar":
            return resolveFlowScalar.resolveFlowScalar(token, strict, _onError);
          case "block-scalar":
            return resolveBlockScalar.resolveBlockScalar({ options: { strict } }, token, _onError);
        }
      }
      return null;
    }
    function createScalarToken(value, context) {
      const { implicitKey = false, indent, inFlow = false, offset = -1, type = "PLAIN" } = context;
      const source = stringifyString.stringifyString({ type, value }, {
        implicitKey,
        indent: indent > 0 ? " ".repeat(indent) : "",
        inFlow,
        options: { blockQuote: true, lineWidth: -1 }
      });
      const end = context.end ?? [
        { type: "newline", offset: -1, indent, source: "\n" }
      ];
      switch (source[0]) {
        case "|":
        case ">": {
          const he = source.indexOf("\n");
          const head = source.substring(0, he);
          const body = source.substring(he + 1) + "\n";
          const props = [
            { type: "block-scalar-header", offset, indent, source: head }
          ];
          if (!addEndtoBlockProps(props, end))
            props.push({ type: "newline", offset: -1, indent, source: "\n" });
          return { type: "block-scalar", offset, indent, props, source: body };
        }
        case '"':
          return { type: "double-quoted-scalar", offset, indent, source, end };
        case "'":
          return { type: "single-quoted-scalar", offset, indent, source, end };
        default:
          return { type: "scalar", offset, indent, source, end };
      }
    }
    function setScalarValue(token, value, context = {}) {
      let { afterKey = false, implicitKey = false, inFlow = false, type } = context;
      let indent = "indent" in token ? token.indent : null;
      if (afterKey && typeof indent === "number")
        indent += 2;
      if (!type)
        switch (token.type) {
          case "single-quoted-scalar":
            type = "QUOTE_SINGLE";
            break;
          case "double-quoted-scalar":
            type = "QUOTE_DOUBLE";
            break;
          case "block-scalar": {
            const header = token.props[0];
            if (header.type !== "block-scalar-header")
              throw new Error("Invalid block scalar header");
            type = header.source[0] === ">" ? "BLOCK_FOLDED" : "BLOCK_LITERAL";
            break;
          }
          default:
            type = "PLAIN";
        }
      const source = stringifyString.stringifyString({ type, value }, {
        implicitKey: implicitKey || indent === null,
        indent: indent !== null && indent > 0 ? " ".repeat(indent) : "",
        inFlow,
        options: { blockQuote: true, lineWidth: -1 }
      });
      switch (source[0]) {
        case "|":
        case ">":
          setBlockScalarValue(token, source);
          break;
        case '"':
          setFlowScalarValue(token, source, "double-quoted-scalar");
          break;
        case "'":
          setFlowScalarValue(token, source, "single-quoted-scalar");
          break;
        default:
          setFlowScalarValue(token, source, "scalar");
      }
    }
    function setBlockScalarValue(token, source) {
      const he = source.indexOf("\n");
      const head = source.substring(0, he);
      const body = source.substring(he + 1) + "\n";
      if (token.type === "block-scalar") {
        const header = token.props[0];
        if (header.type !== "block-scalar-header")
          throw new Error("Invalid block scalar header");
        header.source = head;
        token.source = body;
      } else {
        const { offset } = token;
        const indent = "indent" in token ? token.indent : -1;
        const props = [
          { type: "block-scalar-header", offset, indent, source: head }
        ];
        if (!addEndtoBlockProps(props, "end" in token ? token.end : void 0))
          props.push({ type: "newline", offset: -1, indent, source: "\n" });
        for (const key of Object.keys(token))
          if (key !== "type" && key !== "offset")
            delete token[key];
        Object.assign(token, { type: "block-scalar", indent, props, source: body });
      }
    }
    function addEndtoBlockProps(props, end) {
      if (end)
        for (const st of end)
          switch (st.type) {
            case "space":
            case "comment":
              props.push(st);
              break;
            case "newline":
              props.push(st);
              return true;
          }
      return false;
    }
    function setFlowScalarValue(token, source, type) {
      switch (token.type) {
        case "scalar":
        case "double-quoted-scalar":
        case "single-quoted-scalar":
          token.type = type;
          token.source = source;
          break;
        case "block-scalar": {
          const end = token.props.slice(1);
          let oa = source.length;
          if (token.props[0].type === "block-scalar-header")
            oa -= token.props[0].source.length;
          for (const tok of end)
            tok.offset += oa;
          delete token.props;
          Object.assign(token, { type, source, end });
          break;
        }
        case "block-map":
        case "block-seq": {
          const offset = token.offset + source.length;
          const nl = { type: "newline", offset, indent: token.indent, source: "\n" };
          delete token.items;
          Object.assign(token, { type, source, end: [nl] });
          break;
        }
        default: {
          const indent = "indent" in token ? token.indent : -1;
          const end = "end" in token && Array.isArray(token.end) ? token.end.filter((st) => st.type === "space" || st.type === "comment" || st.type === "newline") : [];
          for (const key of Object.keys(token))
            if (key !== "type" && key !== "offset")
              delete token[key];
          Object.assign(token, { type, indent, source, end });
        }
      }
    }
    exports.createScalarToken = createScalarToken;
    exports.resolveAsScalar = resolveAsScalar;
    exports.setScalarValue = setScalarValue;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/parse/cst-stringify.js
var require_cst_stringify = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/parse/cst-stringify.js"(exports) {
    "use strict";
    var stringify = (cst) => "type" in cst ? stringifyToken(cst) : stringifyItem(cst);
    function stringifyToken(token) {
      switch (token.type) {
        case "block-scalar": {
          let res = "";
          for (const tok of token.props)
            res += stringifyToken(tok);
          return res + token.source;
        }
        case "block-map":
        case "block-seq": {
          let res = "";
          for (const item of token.items)
            res += stringifyItem(item);
          return res;
        }
        case "flow-collection": {
          let res = token.start.source;
          for (const item of token.items)
            res += stringifyItem(item);
          for (const st of token.end)
            res += st.source;
          return res;
        }
        case "document": {
          let res = stringifyItem(token);
          if (token.end)
            for (const st of token.end)
              res += st.source;
          return res;
        }
        default: {
          let res = token.source;
          if ("end" in token && token.end)
            for (const st of token.end)
              res += st.source;
          return res;
        }
      }
    }
    function stringifyItem({ start, key, sep: sep2, value }) {
      let res = "";
      for (const st of start)
        res += st.source;
      if (key)
        res += stringifyToken(key);
      if (sep2)
        for (const st of sep2)
          res += st.source;
      if (value)
        res += stringifyToken(value);
      return res;
    }
    exports.stringify = stringify;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/parse/cst-visit.js
var require_cst_visit = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/parse/cst-visit.js"(exports) {
    "use strict";
    var BREAK = /* @__PURE__ */ Symbol("break visit");
    var SKIP = /* @__PURE__ */ Symbol("skip children");
    var REMOVE = /* @__PURE__ */ Symbol("remove item");
    function visit(cst, visitor) {
      if ("type" in cst && cst.type === "document")
        cst = { start: cst.start, value: cst.value };
      _visit(Object.freeze([]), cst, visitor);
    }
    visit.BREAK = BREAK;
    visit.SKIP = SKIP;
    visit.REMOVE = REMOVE;
    visit.itemAtPath = (cst, path) => {
      let item = cst;
      for (const [field, index] of path) {
        const tok = item?.[field];
        if (tok && "items" in tok) {
          item = tok.items[index];
        } else
          return void 0;
      }
      return item;
    };
    visit.parentCollection = (cst, path) => {
      const parent = visit.itemAtPath(cst, path.slice(0, -1));
      const field = path[path.length - 1][0];
      const coll = parent?.[field];
      if (coll && "items" in coll)
        return coll;
      throw new Error("Parent collection not found");
    };
    function _visit(path, item, visitor) {
      let ctrl = visitor(item, path);
      if (typeof ctrl === "symbol")
        return ctrl;
      for (const field of ["key", "value"]) {
        const token = item[field];
        if (token && "items" in token) {
          for (let i = 0; i < token.items.length; ++i) {
            const ci = _visit(Object.freeze(path.concat([[field, i]])), token.items[i], visitor);
            if (typeof ci === "number")
              i = ci - 1;
            else if (ci === BREAK)
              return BREAK;
            else if (ci === REMOVE) {
              token.items.splice(i, 1);
              i -= 1;
            }
          }
          if (typeof ctrl === "function" && field === "key")
            ctrl = ctrl(item, path);
        }
      }
      return typeof ctrl === "function" ? ctrl(item, path) : ctrl;
    }
    exports.visit = visit;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/parse/cst.js
var require_cst = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/parse/cst.js"(exports) {
    "use strict";
    var cstScalar = require_cst_scalar();
    var cstStringify = require_cst_stringify();
    var cstVisit = require_cst_visit();
    var BOM = "\uFEFF";
    var DOCUMENT = "";
    var FLOW_END = "";
    var SCALAR = "";
    var isCollection = (token) => !!token && "items" in token;
    var isScalar = (token) => !!token && (token.type === "scalar" || token.type === "single-quoted-scalar" || token.type === "double-quoted-scalar" || token.type === "block-scalar");
    function prettyToken(token) {
      switch (token) {
        case BOM:
          return "<BOM>";
        case DOCUMENT:
          return "<DOC>";
        case FLOW_END:
          return "<FLOW_END>";
        case SCALAR:
          return "<SCALAR>";
        default:
          return JSON.stringify(token);
      }
    }
    function tokenType(source) {
      switch (source) {
        case BOM:
          return "byte-order-mark";
        case DOCUMENT:
          return "doc-mode";
        case FLOW_END:
          return "flow-error-end";
        case SCALAR:
          return "scalar";
        case "---":
          return "doc-start";
        case "...":
          return "doc-end";
        case "":
        case "\n":
        case "\r\n":
          return "newline";
        case "-":
          return "seq-item-ind";
        case "?":
          return "explicit-key-ind";
        case ":":
          return "map-value-ind";
        case "{":
          return "flow-map-start";
        case "}":
          return "flow-map-end";
        case "[":
          return "flow-seq-start";
        case "]":
          return "flow-seq-end";
        case ",":
          return "comma";
      }
      switch (source[0]) {
        case " ":
        case "	":
          return "space";
        case "#":
          return "comment";
        case "%":
          return "directive-line";
        case "*":
          return "alias";
        case "&":
          return "anchor";
        case "!":
          return "tag";
        case "'":
          return "single-quoted-scalar";
        case '"':
          return "double-quoted-scalar";
        case "|":
        case ">":
          return "block-scalar-header";
      }
      return null;
    }
    exports.createScalarToken = cstScalar.createScalarToken;
    exports.resolveAsScalar = cstScalar.resolveAsScalar;
    exports.setScalarValue = cstScalar.setScalarValue;
    exports.stringify = cstStringify.stringify;
    exports.visit = cstVisit.visit;
    exports.BOM = BOM;
    exports.DOCUMENT = DOCUMENT;
    exports.FLOW_END = FLOW_END;
    exports.SCALAR = SCALAR;
    exports.isCollection = isCollection;
    exports.isScalar = isScalar;
    exports.prettyToken = prettyToken;
    exports.tokenType = tokenType;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/parse/lexer.js
var require_lexer = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/parse/lexer.js"(exports) {
    "use strict";
    var cst = require_cst();
    function isEmpty(ch) {
      switch (ch) {
        case void 0:
        case " ":
        case "\n":
        case "\r":
        case "	":
          return true;
        default:
          return false;
      }
    }
    var hexDigits = new Set("0123456789ABCDEFabcdef");
    var tagChars = new Set("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-#;/?:@&=+$_.!~*'()");
    var flowIndicatorChars = new Set(",[]{}");
    var invalidAnchorChars = new Set(" ,[]{}\n\r	");
    var isNotAnchorChar = (ch) => !ch || invalidAnchorChars.has(ch);
    var Lexer = class {
      constructor() {
        this.atEnd = false;
        this.blockScalarIndent = -1;
        this.blockScalarKeep = false;
        this.buffer = "";
        this.flowKey = false;
        this.flowLevel = 0;
        this.indentNext = 0;
        this.indentValue = 0;
        this.lineEndPos = null;
        this.next = null;
        this.pos = 0;
      }
      /**
       * Generate YAML tokens from the `source` string. If `incomplete`,
       * a part of the last line may be left as a buffer for the next call.
       *
       * @returns A generator of lexical tokens
       */
      *lex(source, incomplete = false) {
        if (source) {
          if (typeof source !== "string")
            throw TypeError("source is not a string");
          this.buffer = this.buffer ? this.buffer + source : source;
          this.lineEndPos = null;
        }
        this.atEnd = !incomplete;
        let next = this.next ?? "stream";
        while (next && (incomplete || this.hasChars(1)))
          next = yield* this.parseNext(next);
      }
      atLineEnd() {
        let i = this.pos;
        let ch = this.buffer[i];
        while (ch === " " || ch === "	")
          ch = this.buffer[++i];
        if (!ch || ch === "#" || ch === "\n")
          return true;
        if (ch === "\r")
          return this.buffer[i + 1] === "\n";
        return false;
      }
      charAt(n) {
        return this.buffer[this.pos + n];
      }
      continueScalar(offset) {
        let ch = this.buffer[offset];
        if (this.indentNext > 0) {
          let indent = 0;
          while (ch === " ")
            ch = this.buffer[++indent + offset];
          if (ch === "\r") {
            const next = this.buffer[indent + offset + 1];
            if (next === "\n" || !next && !this.atEnd)
              return offset + indent + 1;
          }
          return ch === "\n" || indent >= this.indentNext || !ch && !this.atEnd ? offset + indent : -1;
        }
        if (ch === "-" || ch === ".") {
          const dt = this.buffer.substr(offset, 3);
          if ((dt === "---" || dt === "...") && isEmpty(this.buffer[offset + 3]))
            return -1;
        }
        return offset;
      }
      getLine() {
        let end = this.lineEndPos;
        if (typeof end !== "number" || end !== -1 && end < this.pos) {
          end = this.buffer.indexOf("\n", this.pos);
          this.lineEndPos = end;
        }
        if (end === -1)
          return this.atEnd ? this.buffer.substring(this.pos) : null;
        if (this.buffer[end - 1] === "\r")
          end -= 1;
        return this.buffer.substring(this.pos, end);
      }
      hasChars(n) {
        return this.pos + n <= this.buffer.length;
      }
      setNext(state) {
        this.buffer = this.buffer.substring(this.pos);
        this.pos = 0;
        this.lineEndPos = null;
        this.next = state;
        return null;
      }
      peek(n) {
        return this.buffer.substr(this.pos, n);
      }
      *parseNext(next) {
        switch (next) {
          case "stream":
            return yield* this.parseStream();
          case "line-start":
            return yield* this.parseLineStart();
          case "block-start":
            return yield* this.parseBlockStart();
          case "doc":
            return yield* this.parseDocument();
          case "flow":
            return yield* this.parseFlowCollection();
          case "quoted-scalar":
            return yield* this.parseQuotedScalar();
          case "block-scalar":
            return yield* this.parseBlockScalar();
          case "plain-scalar":
            return yield* this.parsePlainScalar();
        }
      }
      *parseStream() {
        let line = this.getLine();
        if (line === null)
          return this.setNext("stream");
        if (line[0] === cst.BOM) {
          yield* this.pushCount(1);
          line = line.substring(1);
        }
        if (line[0] === "%") {
          let dirEnd = line.length;
          let cs = line.indexOf("#");
          while (cs !== -1) {
            const ch = line[cs - 1];
            if (ch === " " || ch === "	") {
              dirEnd = cs - 1;
              break;
            } else {
              cs = line.indexOf("#", cs + 1);
            }
          }
          while (true) {
            const ch = line[dirEnd - 1];
            if (ch === " " || ch === "	")
              dirEnd -= 1;
            else
              break;
          }
          const n = (yield* this.pushCount(dirEnd)) + (yield* this.pushSpaces(true));
          yield* this.pushCount(line.length - n);
          this.pushNewline();
          return "stream";
        }
        if (this.atLineEnd()) {
          const sp = yield* this.pushSpaces(true);
          yield* this.pushCount(line.length - sp);
          yield* this.pushNewline();
          return "stream";
        }
        yield cst.DOCUMENT;
        return yield* this.parseLineStart();
      }
      *parseLineStart() {
        const ch = this.charAt(0);
        if (!ch && !this.atEnd)
          return this.setNext("line-start");
        if (ch === "-" || ch === ".") {
          if (!this.atEnd && !this.hasChars(4))
            return this.setNext("line-start");
          const s = this.peek(3);
          if ((s === "---" || s === "...") && isEmpty(this.charAt(3))) {
            yield* this.pushCount(3);
            this.indentValue = 0;
            this.indentNext = 0;
            return s === "---" ? "doc" : "stream";
          }
        }
        this.indentValue = yield* this.pushSpaces(false);
        if (this.indentNext > this.indentValue && !isEmpty(this.charAt(1)))
          this.indentNext = this.indentValue;
        return yield* this.parseBlockStart();
      }
      *parseBlockStart() {
        const [ch0, ch1] = this.peek(2);
        if (!ch1 && !this.atEnd)
          return this.setNext("block-start");
        if ((ch0 === "-" || ch0 === "?" || ch0 === ":") && isEmpty(ch1)) {
          const n = (yield* this.pushCount(1)) + (yield* this.pushSpaces(true));
          this.indentNext = this.indentValue + 1;
          this.indentValue += n;
          return "block-start";
        }
        return "doc";
      }
      *parseDocument() {
        yield* this.pushSpaces(true);
        const line = this.getLine();
        if (line === null)
          return this.setNext("doc");
        let n = yield* this.pushIndicators();
        switch (line[n]) {
          case "#":
            yield* this.pushCount(line.length - n);
          // fallthrough
          case void 0:
            yield* this.pushNewline();
            return yield* this.parseLineStart();
          case "{":
          case "[":
            yield* this.pushCount(1);
            this.flowKey = false;
            this.flowLevel = 1;
            return "flow";
          case "}":
          case "]":
            yield* this.pushCount(1);
            return "doc";
          case "*":
            yield* this.pushUntil(isNotAnchorChar);
            return "doc";
          case '"':
          case "'":
            return yield* this.parseQuotedScalar();
          case "|":
          case ">":
            n += yield* this.parseBlockScalarHeader();
            n += yield* this.pushSpaces(true);
            yield* this.pushCount(line.length - n);
            yield* this.pushNewline();
            return yield* this.parseBlockScalar();
          default:
            return yield* this.parsePlainScalar();
        }
      }
      *parseFlowCollection() {
        let nl, sp;
        let indent = -1;
        do {
          nl = yield* this.pushNewline();
          if (nl > 0) {
            sp = yield* this.pushSpaces(false);
            this.indentValue = indent = sp;
          } else {
            sp = 0;
          }
          sp += yield* this.pushSpaces(true);
        } while (nl + sp > 0);
        const line = this.getLine();
        if (line === null)
          return this.setNext("flow");
        if (indent !== -1 && indent < this.indentNext && line[0] !== "#" || indent === 0 && (line.startsWith("---") || line.startsWith("...")) && isEmpty(line[3])) {
          const atFlowEndMarker = indent === this.indentNext - 1 && this.flowLevel === 1 && (line[0] === "]" || line[0] === "}");
          if (!atFlowEndMarker) {
            this.flowLevel = 0;
            yield cst.FLOW_END;
            return yield* this.parseLineStart();
          }
        }
        let n = 0;
        while (line[n] === ",") {
          n += yield* this.pushCount(1);
          n += yield* this.pushSpaces(true);
          this.flowKey = false;
        }
        n += yield* this.pushIndicators();
        switch (line[n]) {
          case void 0:
            return "flow";
          case "#":
            yield* this.pushCount(line.length - n);
            return "flow";
          case "{":
          case "[":
            yield* this.pushCount(1);
            this.flowKey = false;
            this.flowLevel += 1;
            return "flow";
          case "}":
          case "]":
            yield* this.pushCount(1);
            this.flowKey = true;
            this.flowLevel -= 1;
            return this.flowLevel ? "flow" : "doc";
          case "*":
            yield* this.pushUntil(isNotAnchorChar);
            return "flow";
          case '"':
          case "'":
            this.flowKey = true;
            return yield* this.parseQuotedScalar();
          case ":": {
            const next = this.charAt(1);
            if (this.flowKey || isEmpty(next) || next === ",") {
              this.flowKey = false;
              yield* this.pushCount(1);
              yield* this.pushSpaces(true);
              return "flow";
            }
          }
          // fallthrough
          default:
            this.flowKey = false;
            return yield* this.parsePlainScalar();
        }
      }
      *parseQuotedScalar() {
        const quote = this.charAt(0);
        let end = this.buffer.indexOf(quote, this.pos + 1);
        if (quote === "'") {
          while (end !== -1 && this.buffer[end + 1] === "'")
            end = this.buffer.indexOf("'", end + 2);
        } else {
          while (end !== -1) {
            let n = 0;
            while (this.buffer[end - 1 - n] === "\\")
              n += 1;
            if (n % 2 === 0)
              break;
            end = this.buffer.indexOf('"', end + 1);
          }
        }
        const qb = this.buffer.substring(0, end);
        let nl = qb.indexOf("\n", this.pos);
        if (nl !== -1) {
          while (nl !== -1) {
            const cs = this.continueScalar(nl + 1);
            if (cs === -1)
              break;
            nl = qb.indexOf("\n", cs);
          }
          if (nl !== -1) {
            end = nl - (qb[nl - 1] === "\r" ? 2 : 1);
          }
        }
        if (end === -1) {
          if (!this.atEnd)
            return this.setNext("quoted-scalar");
          end = this.buffer.length;
        }
        yield* this.pushToIndex(end + 1, false);
        return this.flowLevel ? "flow" : "doc";
      }
      *parseBlockScalarHeader() {
        this.blockScalarIndent = -1;
        this.blockScalarKeep = false;
        let i = this.pos;
        while (true) {
          const ch = this.buffer[++i];
          if (ch === "+")
            this.blockScalarKeep = true;
          else if (ch > "0" && ch <= "9")
            this.blockScalarIndent = Number(ch) - 1;
          else if (ch !== "-")
            break;
        }
        return yield* this.pushUntil((ch) => isEmpty(ch) || ch === "#");
      }
      *parseBlockScalar() {
        let nl = this.pos - 1;
        let indent = 0;
        let ch;
        loop: for (let i2 = this.pos; ch = this.buffer[i2]; ++i2) {
          switch (ch) {
            case " ":
              indent += 1;
              break;
            case "\n":
              nl = i2;
              indent = 0;
              break;
            case "\r": {
              const next = this.buffer[i2 + 1];
              if (!next && !this.atEnd)
                return this.setNext("block-scalar");
              if (next === "\n")
                break;
            }
            // fallthrough
            default:
              break loop;
          }
        }
        if (!ch && !this.atEnd)
          return this.setNext("block-scalar");
        if (indent >= this.indentNext) {
          if (this.blockScalarIndent === -1)
            this.indentNext = indent;
          else {
            this.indentNext = this.blockScalarIndent + (this.indentNext === 0 ? 1 : this.indentNext);
          }
          do {
            const cs = this.continueScalar(nl + 1);
            if (cs === -1)
              break;
            nl = this.buffer.indexOf("\n", cs);
          } while (nl !== -1);
          if (nl === -1) {
            if (!this.atEnd)
              return this.setNext("block-scalar");
            nl = this.buffer.length;
          }
        }
        let i = nl + 1;
        ch = this.buffer[i];
        while (ch === " ")
          ch = this.buffer[++i];
        if (ch === "	") {
          while (ch === "	" || ch === " " || ch === "\r" || ch === "\n")
            ch = this.buffer[++i];
          nl = i - 1;
        } else if (!this.blockScalarKeep) {
          do {
            let i2 = nl - 1;
            let ch2 = this.buffer[i2];
            if (ch2 === "\r")
              ch2 = this.buffer[--i2];
            const lastChar = i2;
            while (ch2 === " ")
              ch2 = this.buffer[--i2];
            if (ch2 === "\n" && i2 >= this.pos && i2 + 1 + indent > lastChar)
              nl = i2;
            else
              break;
          } while (true);
        }
        yield cst.SCALAR;
        yield* this.pushToIndex(nl + 1, true);
        return yield* this.parseLineStart();
      }
      *parsePlainScalar() {
        const inFlow = this.flowLevel > 0;
        let end = this.pos - 1;
        let i = this.pos - 1;
        let ch;
        while (ch = this.buffer[++i]) {
          if (ch === ":") {
            const next = this.buffer[i + 1];
            if (isEmpty(next) || inFlow && flowIndicatorChars.has(next))
              break;
            end = i;
          } else if (isEmpty(ch)) {
            let next = this.buffer[i + 1];
            if (ch === "\r") {
              if (next === "\n") {
                i += 1;
                ch = "\n";
                next = this.buffer[i + 1];
              } else
                end = i;
            }
            if (next === "#" || inFlow && flowIndicatorChars.has(next))
              break;
            if (ch === "\n") {
              const cs = this.continueScalar(i + 1);
              if (cs === -1)
                break;
              i = Math.max(i, cs - 2);
            }
          } else {
            if (inFlow && flowIndicatorChars.has(ch))
              break;
            end = i;
          }
        }
        if (!ch && !this.atEnd)
          return this.setNext("plain-scalar");
        yield cst.SCALAR;
        yield* this.pushToIndex(end + 1, true);
        return inFlow ? "flow" : "doc";
      }
      *pushCount(n) {
        if (n > 0) {
          yield this.buffer.substr(this.pos, n);
          this.pos += n;
          return n;
        }
        return 0;
      }
      *pushToIndex(i, allowEmpty) {
        const s = this.buffer.slice(this.pos, i);
        if (s) {
          yield s;
          this.pos += s.length;
          return s.length;
        } else if (allowEmpty)
          yield "";
        return 0;
      }
      *pushIndicators() {
        let n = 0;
        loop: while (true) {
          switch (this.charAt(0)) {
            case "!":
              n += yield* this.pushTag();
              n += yield* this.pushSpaces(true);
              continue loop;
            case "&":
              n += yield* this.pushUntil(isNotAnchorChar);
              n += yield* this.pushSpaces(true);
              continue loop;
            case "-":
            // this is an error
            case "?":
            // this is an error outside flow collections
            case ":": {
              const inFlow = this.flowLevel > 0;
              const ch1 = this.charAt(1);
              if (isEmpty(ch1) || inFlow && flowIndicatorChars.has(ch1)) {
                if (!inFlow)
                  this.indentNext = this.indentValue + 1;
                else if (this.flowKey)
                  this.flowKey = false;
                n += yield* this.pushCount(1);
                n += yield* this.pushSpaces(true);
                continue loop;
              }
            }
          }
          break loop;
        }
        return n;
      }
      *pushTag() {
        if (this.charAt(1) === "<") {
          let i = this.pos + 2;
          let ch = this.buffer[i];
          while (!isEmpty(ch) && ch !== ">")
            ch = this.buffer[++i];
          return yield* this.pushToIndex(ch === ">" ? i + 1 : i, false);
        } else {
          let i = this.pos + 1;
          let ch = this.buffer[i];
          while (ch) {
            if (tagChars.has(ch))
              ch = this.buffer[++i];
            else if (ch === "%" && hexDigits.has(this.buffer[i + 1]) && hexDigits.has(this.buffer[i + 2])) {
              ch = this.buffer[i += 3];
            } else
              break;
          }
          return yield* this.pushToIndex(i, false);
        }
      }
      *pushNewline() {
        const ch = this.buffer[this.pos];
        if (ch === "\n")
          return yield* this.pushCount(1);
        else if (ch === "\r" && this.charAt(1) === "\n")
          return yield* this.pushCount(2);
        else
          return 0;
      }
      *pushSpaces(allowTabs) {
        let i = this.pos - 1;
        let ch;
        do {
          ch = this.buffer[++i];
        } while (ch === " " || allowTabs && ch === "	");
        const n = i - this.pos;
        if (n > 0) {
          yield this.buffer.substr(this.pos, n);
          this.pos = i;
        }
        return n;
      }
      *pushUntil(test) {
        let i = this.pos;
        let ch = this.buffer[i];
        while (!test(ch))
          ch = this.buffer[++i];
        return yield* this.pushToIndex(i, false);
      }
    };
    exports.Lexer = Lexer;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/parse/line-counter.js
var require_line_counter = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/parse/line-counter.js"(exports) {
    "use strict";
    var LineCounter = class {
      constructor() {
        this.lineStarts = [];
        this.addNewLine = (offset) => this.lineStarts.push(offset);
        this.linePos = (offset) => {
          let low = 0;
          let high = this.lineStarts.length;
          while (low < high) {
            const mid = low + high >> 1;
            if (this.lineStarts[mid] < offset)
              low = mid + 1;
            else
              high = mid;
          }
          if (this.lineStarts[low] === offset)
            return { line: low + 1, col: 1 };
          if (low === 0)
            return { line: 0, col: offset };
          const start = this.lineStarts[low - 1];
          return { line: low, col: offset - start + 1 };
        };
      }
    };
    exports.LineCounter = LineCounter;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/parse/parser.js
var require_parser = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/parse/parser.js"(exports) {
    "use strict";
    var node_process = __require("process");
    var cst = require_cst();
    var lexer = require_lexer();
    function includesToken(list, type) {
      for (let i = 0; i < list.length; ++i)
        if (list[i].type === type)
          return true;
      return false;
    }
    function findNonEmptyIndex(list) {
      for (let i = 0; i < list.length; ++i) {
        switch (list[i].type) {
          case "space":
          case "comment":
          case "newline":
            break;
          default:
            return i;
        }
      }
      return -1;
    }
    function isFlowToken(token) {
      switch (token?.type) {
        case "alias":
        case "scalar":
        case "single-quoted-scalar":
        case "double-quoted-scalar":
        case "flow-collection":
          return true;
        default:
          return false;
      }
    }
    function getPrevProps(parent) {
      switch (parent.type) {
        case "document":
          return parent.start;
        case "block-map": {
          const it = parent.items[parent.items.length - 1];
          return it.sep ?? it.start;
        }
        case "block-seq":
          return parent.items[parent.items.length - 1].start;
        /* istanbul ignore next should not happen */
        default:
          return [];
      }
    }
    function getFirstKeyStartProps(prev) {
      if (prev.length === 0)
        return [];
      let i = prev.length;
      loop: while (--i >= 0) {
        switch (prev[i].type) {
          case "doc-start":
          case "explicit-key-ind":
          case "map-value-ind":
          case "seq-item-ind":
          case "newline":
            break loop;
        }
      }
      while (prev[++i]?.type === "space") {
      }
      return prev.splice(i, prev.length);
    }
    function arrayPushArray(target, source) {
      if (source.length < 1e5)
        Array.prototype.push.apply(target, source);
      else
        for (let i = 0; i < source.length; ++i)
          target.push(source[i]);
    }
    function fixFlowSeqItems(fc) {
      if (fc.start.type === "flow-seq-start") {
        for (const it of fc.items) {
          if (it.sep && !it.value && !includesToken(it.start, "explicit-key-ind") && !includesToken(it.sep, "map-value-ind")) {
            if (it.key)
              it.value = it.key;
            delete it.key;
            if (isFlowToken(it.value)) {
              if (it.value.end)
                arrayPushArray(it.value.end, it.sep);
              else
                it.value.end = it.sep;
            } else
              arrayPushArray(it.start, it.sep);
            delete it.sep;
          }
        }
      }
    }
    var Parser = class {
      /**
       * @param onNewLine - If defined, called separately with the start position of
       *   each new line (in `parse()`, including the start of input).
       */
      constructor(onNewLine) {
        this.atNewLine = true;
        this.atScalar = false;
        this.indent = 0;
        this.offset = 0;
        this.onKeyLine = false;
        this.stack = [];
        this.source = "";
        this.type = "";
        this.lexer = new lexer.Lexer();
        this.onNewLine = onNewLine;
      }
      /**
       * Parse `source` as a YAML stream.
       * If `incomplete`, a part of the last line may be left as a buffer for the next call.
       *
       * Errors are not thrown, but yielded as `{ type: 'error', message }` tokens.
       *
       * @returns A generator of tokens representing each directive, document, and other structure.
       */
      *parse(source, incomplete = false) {
        if (this.onNewLine && this.offset === 0)
          this.onNewLine(0);
        for (const lexeme of this.lexer.lex(source, incomplete))
          yield* this.next(lexeme);
        if (!incomplete)
          yield* this.end();
      }
      /**
       * Advance the parser by the `source` of one lexical token.
       */
      *next(source) {
        this.source = source;
        if (node_process.env.LOG_TOKENS)
          console.log("|", cst.prettyToken(source));
        if (this.atScalar) {
          this.atScalar = false;
          yield* this.step();
          this.offset += source.length;
          return;
        }
        const type = cst.tokenType(source);
        if (!type) {
          const message = `Not a YAML token: ${source}`;
          yield* this.pop({ type: "error", offset: this.offset, message, source });
          this.offset += source.length;
        } else if (type === "scalar") {
          this.atNewLine = false;
          this.atScalar = true;
          this.type = "scalar";
        } else {
          this.type = type;
          yield* this.step();
          switch (type) {
            case "newline":
              this.atNewLine = true;
              this.indent = 0;
              if (this.onNewLine)
                this.onNewLine(this.offset + source.length);
              break;
            case "space":
              if (this.atNewLine && source[0] === " ")
                this.indent += source.length;
              break;
            case "explicit-key-ind":
            case "map-value-ind":
            case "seq-item-ind":
              if (this.atNewLine)
                this.indent += source.length;
              break;
            case "doc-mode":
            case "flow-error-end":
              return;
            default:
              this.atNewLine = false;
          }
          this.offset += source.length;
        }
      }
      /** Call at end of input to push out any remaining constructions */
      *end() {
        while (this.stack.length > 0)
          yield* this.pop();
      }
      get sourceToken() {
        const st = {
          type: this.type,
          offset: this.offset,
          indent: this.indent,
          source: this.source
        };
        return st;
      }
      *step() {
        const top = this.peek(1);
        if (this.type === "doc-end" && top?.type !== "doc-end") {
          while (this.stack.length > 0)
            yield* this.pop();
          this.stack.push({
            type: "doc-end",
            offset: this.offset,
            source: this.source
          });
          return;
        }
        if (!top)
          return yield* this.stream();
        switch (top.type) {
          case "document":
            return yield* this.document(top);
          case "alias":
          case "scalar":
          case "single-quoted-scalar":
          case "double-quoted-scalar":
            return yield* this.scalar(top);
          case "block-scalar":
            return yield* this.blockScalar(top);
          case "block-map":
            return yield* this.blockMap(top);
          case "block-seq":
            return yield* this.blockSequence(top);
          case "flow-collection":
            return yield* this.flowCollection(top);
          case "doc-end":
            return yield* this.documentEnd(top);
        }
        yield* this.pop();
      }
      peek(n) {
        return this.stack[this.stack.length - n];
      }
      *pop(error) {
        const token = error ?? this.stack.pop();
        if (!token) {
          const message = "Tried to pop an empty stack";
          yield { type: "error", offset: this.offset, source: "", message };
        } else if (this.stack.length === 0) {
          yield token;
        } else {
          const top = this.peek(1);
          if (token.type === "block-scalar") {
            token.indent = "indent" in top ? top.indent : 0;
          } else if (token.type === "flow-collection" && top.type === "document") {
            token.indent = 0;
          }
          if (token.type === "flow-collection")
            fixFlowSeqItems(token);
          switch (top.type) {
            case "document":
              top.value = token;
              break;
            case "block-scalar":
              top.props.push(token);
              break;
            case "block-map": {
              const it = top.items[top.items.length - 1];
              if (it.value) {
                top.items.push({ start: [], key: token, sep: [] });
                this.onKeyLine = true;
                return;
              } else if (it.sep) {
                it.value = token;
              } else {
                Object.assign(it, { key: token, sep: [] });
                this.onKeyLine = !it.explicitKey;
                return;
              }
              break;
            }
            case "block-seq": {
              const it = top.items[top.items.length - 1];
              if (it.value)
                top.items.push({ start: [], value: token });
              else
                it.value = token;
              break;
            }
            case "flow-collection": {
              const it = top.items[top.items.length - 1];
              if (!it || it.value)
                top.items.push({ start: [], key: token, sep: [] });
              else if (it.sep)
                it.value = token;
              else
                Object.assign(it, { key: token, sep: [] });
              return;
            }
            /* istanbul ignore next should not happen */
            default:
              yield* this.pop();
              yield* this.pop(token);
          }
          if ((top.type === "document" || top.type === "block-map" || top.type === "block-seq") && (token.type === "block-map" || token.type === "block-seq")) {
            const last = token.items[token.items.length - 1];
            if (last && !last.sep && !last.value && last.start.length > 0 && findNonEmptyIndex(last.start) === -1 && (token.indent === 0 || last.start.every((st) => st.type !== "comment" || st.indent < token.indent))) {
              if (top.type === "document")
                top.end = last.start;
              else
                top.items.push({ start: last.start });
              token.items.splice(-1, 1);
            }
          }
        }
      }
      *stream() {
        switch (this.type) {
          case "directive-line":
            yield { type: "directive", offset: this.offset, source: this.source };
            return;
          case "byte-order-mark":
          case "space":
          case "comment":
          case "newline":
            yield this.sourceToken;
            return;
          case "doc-mode":
          case "doc-start": {
            const doc = {
              type: "document",
              offset: this.offset,
              start: []
            };
            if (this.type === "doc-start")
              doc.start.push(this.sourceToken);
            this.stack.push(doc);
            return;
          }
        }
        yield {
          type: "error",
          offset: this.offset,
          message: `Unexpected ${this.type} token in YAML stream`,
          source: this.source
        };
      }
      *document(doc) {
        if (doc.value)
          return yield* this.lineEnd(doc);
        switch (this.type) {
          case "doc-start": {
            if (findNonEmptyIndex(doc.start) !== -1) {
              yield* this.pop();
              yield* this.step();
            } else
              doc.start.push(this.sourceToken);
            return;
          }
          case "anchor":
          case "tag":
          case "space":
          case "comment":
          case "newline":
            doc.start.push(this.sourceToken);
            return;
        }
        const bv = this.startBlockValue(doc);
        if (bv)
          this.stack.push(bv);
        else {
          yield {
            type: "error",
            offset: this.offset,
            message: `Unexpected ${this.type} token in YAML document`,
            source: this.source
          };
        }
      }
      *scalar(scalar) {
        if (this.type === "map-value-ind") {
          const prev = getPrevProps(this.peek(2));
          const start = getFirstKeyStartProps(prev);
          let sep2;
          if (scalar.end) {
            sep2 = scalar.end;
            sep2.push(this.sourceToken);
            delete scalar.end;
          } else
            sep2 = [this.sourceToken];
          const map = {
            type: "block-map",
            offset: scalar.offset,
            indent: scalar.indent,
            items: [{ start, key: scalar, sep: sep2 }]
          };
          this.onKeyLine = true;
          this.stack[this.stack.length - 1] = map;
        } else
          yield* this.lineEnd(scalar);
      }
      *blockScalar(scalar) {
        switch (this.type) {
          case "space":
          case "comment":
          case "newline":
            scalar.props.push(this.sourceToken);
            return;
          case "scalar":
            scalar.source = this.source;
            this.atNewLine = true;
            this.indent = 0;
            if (this.onNewLine) {
              let nl = this.source.indexOf("\n") + 1;
              while (nl !== 0) {
                this.onNewLine(this.offset + nl);
                nl = this.source.indexOf("\n", nl) + 1;
              }
            }
            yield* this.pop();
            break;
          /* istanbul ignore next should not happen */
          default:
            yield* this.pop();
            yield* this.step();
        }
      }
      *blockMap(map) {
        const it = map.items[map.items.length - 1];
        switch (this.type) {
          case "newline":
            this.onKeyLine = false;
            if (it.value) {
              const end = "end" in it.value ? it.value.end : void 0;
              const last = Array.isArray(end) ? end[end.length - 1] : void 0;
              if (last?.type === "comment")
                end?.push(this.sourceToken);
              else
                map.items.push({ start: [this.sourceToken] });
            } else if (it.sep) {
              it.sep.push(this.sourceToken);
            } else {
              it.start.push(this.sourceToken);
            }
            return;
          case "space":
          case "comment":
            if (it.value) {
              map.items.push({ start: [this.sourceToken] });
            } else if (it.sep) {
              it.sep.push(this.sourceToken);
            } else {
              if (this.atIndentedComment(it.start, map.indent)) {
                const prev = map.items[map.items.length - 2];
                const end = prev?.value?.end;
                if (Array.isArray(end)) {
                  arrayPushArray(end, it.start);
                  end.push(this.sourceToken);
                  map.items.pop();
                  return;
                }
              }
              it.start.push(this.sourceToken);
            }
            return;
        }
        if (this.indent >= map.indent) {
          const atMapIndent = !this.onKeyLine && this.indent === map.indent;
          const atNextItem = atMapIndent && (it.sep || it.explicitKey) && this.type !== "seq-item-ind";
          let start = [];
          if (atNextItem && it.sep && !it.value) {
            const nl = [];
            for (let i = 0; i < it.sep.length; ++i) {
              const st = it.sep[i];
              switch (st.type) {
                case "newline":
                  nl.push(i);
                  break;
                case "space":
                  break;
                case "comment":
                  if (st.indent > map.indent)
                    nl.length = 0;
                  break;
                default:
                  nl.length = 0;
              }
            }
            if (nl.length >= 2)
              start = it.sep.splice(nl[1]);
          }
          switch (this.type) {
            case "anchor":
            case "tag":
              if (atNextItem || it.value) {
                start.push(this.sourceToken);
                map.items.push({ start });
                this.onKeyLine = true;
              } else if (it.sep) {
                it.sep.push(this.sourceToken);
              } else {
                it.start.push(this.sourceToken);
              }
              return;
            case "explicit-key-ind":
              if (!it.sep && !it.explicitKey) {
                it.start.push(this.sourceToken);
                it.explicitKey = true;
              } else if (atNextItem || it.value) {
                start.push(this.sourceToken);
                map.items.push({ start, explicitKey: true });
              } else {
                this.stack.push({
                  type: "block-map",
                  offset: this.offset,
                  indent: this.indent,
                  items: [{ start: [this.sourceToken], explicitKey: true }]
                });
              }
              this.onKeyLine = true;
              return;
            case "map-value-ind":
              if (it.explicitKey) {
                if (!it.sep) {
                  if (includesToken(it.start, "newline")) {
                    Object.assign(it, { key: null, sep: [this.sourceToken] });
                  } else {
                    const start2 = getFirstKeyStartProps(it.start);
                    this.stack.push({
                      type: "block-map",
                      offset: this.offset,
                      indent: this.indent,
                      items: [{ start: start2, key: null, sep: [this.sourceToken] }]
                    });
                  }
                } else if (it.value) {
                  map.items.push({ start: [], key: null, sep: [this.sourceToken] });
                } else if (includesToken(it.sep, "map-value-ind")) {
                  this.stack.push({
                    type: "block-map",
                    offset: this.offset,
                    indent: this.indent,
                    items: [{ start, key: null, sep: [this.sourceToken] }]
                  });
                } else if (isFlowToken(it.key) && !includesToken(it.sep, "newline")) {
                  const start2 = getFirstKeyStartProps(it.start);
                  const key = it.key;
                  const sep2 = it.sep;
                  sep2.push(this.sourceToken);
                  delete it.key;
                  delete it.sep;
                  this.stack.push({
                    type: "block-map",
                    offset: this.offset,
                    indent: this.indent,
                    items: [{ start: start2, key, sep: sep2 }]
                  });
                } else if (start.length > 0) {
                  it.sep = it.sep.concat(start, this.sourceToken);
                } else {
                  it.sep.push(this.sourceToken);
                }
              } else {
                if (!it.sep) {
                  Object.assign(it, { key: null, sep: [this.sourceToken] });
                } else if (it.value || atNextItem) {
                  map.items.push({ start, key: null, sep: [this.sourceToken] });
                } else if (includesToken(it.sep, "map-value-ind")) {
                  this.stack.push({
                    type: "block-map",
                    offset: this.offset,
                    indent: this.indent,
                    items: [{ start: [], key: null, sep: [this.sourceToken] }]
                  });
                } else {
                  it.sep.push(this.sourceToken);
                }
              }
              this.onKeyLine = true;
              return;
            case "alias":
            case "scalar":
            case "single-quoted-scalar":
            case "double-quoted-scalar": {
              const fs = this.flowScalar(this.type);
              if (atNextItem || it.value) {
                map.items.push({ start, key: fs, sep: [] });
                this.onKeyLine = true;
              } else if (it.sep) {
                this.stack.push(fs);
              } else {
                Object.assign(it, { key: fs, sep: [] });
                this.onKeyLine = true;
              }
              return;
            }
            default: {
              const bv = this.startBlockValue(map);
              if (bv) {
                if (bv.type === "block-seq") {
                  if (!it.explicitKey && it.sep && !includesToken(it.sep, "newline")) {
                    yield* this.pop({
                      type: "error",
                      offset: this.offset,
                      message: "Unexpected block-seq-ind on same line with key",
                      source: this.source
                    });
                    return;
                  }
                } else if (atMapIndent) {
                  map.items.push({ start });
                }
                this.stack.push(bv);
                return;
              }
            }
          }
        }
        yield* this.pop();
        yield* this.step();
      }
      *blockSequence(seq) {
        const it = seq.items[seq.items.length - 1];
        switch (this.type) {
          case "newline":
            if (it.value) {
              const end = "end" in it.value ? it.value.end : void 0;
              const last = Array.isArray(end) ? end[end.length - 1] : void 0;
              if (last?.type === "comment")
                end?.push(this.sourceToken);
              else
                seq.items.push({ start: [this.sourceToken] });
            } else
              it.start.push(this.sourceToken);
            return;
          case "space":
          case "comment":
            if (it.value)
              seq.items.push({ start: [this.sourceToken] });
            else {
              if (this.atIndentedComment(it.start, seq.indent)) {
                const prev = seq.items[seq.items.length - 2];
                const end = prev?.value?.end;
                if (Array.isArray(end)) {
                  arrayPushArray(end, it.start);
                  end.push(this.sourceToken);
                  seq.items.pop();
                  return;
                }
              }
              it.start.push(this.sourceToken);
            }
            return;
          case "anchor":
          case "tag":
            if (it.value || this.indent <= seq.indent)
              break;
            it.start.push(this.sourceToken);
            return;
          case "seq-item-ind":
            if (this.indent !== seq.indent)
              break;
            if (it.value || includesToken(it.start, "seq-item-ind"))
              seq.items.push({ start: [this.sourceToken] });
            else
              it.start.push(this.sourceToken);
            return;
        }
        if (this.indent > seq.indent) {
          const bv = this.startBlockValue(seq);
          if (bv) {
            this.stack.push(bv);
            return;
          }
        }
        yield* this.pop();
        yield* this.step();
      }
      *flowCollection(fc) {
        const it = fc.items[fc.items.length - 1];
        if (this.type === "flow-error-end") {
          let top;
          do {
            yield* this.pop();
            top = this.peek(1);
          } while (top?.type === "flow-collection");
        } else if (fc.end.length === 0) {
          switch (this.type) {
            case "comma":
            case "explicit-key-ind":
              if (!it || it.sep)
                fc.items.push({ start: [this.sourceToken] });
              else
                it.start.push(this.sourceToken);
              return;
            case "map-value-ind":
              if (!it || it.value)
                fc.items.push({ start: [], key: null, sep: [this.sourceToken] });
              else if (it.sep)
                it.sep.push(this.sourceToken);
              else
                Object.assign(it, { key: null, sep: [this.sourceToken] });
              return;
            case "space":
            case "comment":
            case "newline":
            case "anchor":
            case "tag":
              if (!it || it.value)
                fc.items.push({ start: [this.sourceToken] });
              else if (it.sep)
                it.sep.push(this.sourceToken);
              else
                it.start.push(this.sourceToken);
              return;
            case "alias":
            case "scalar":
            case "single-quoted-scalar":
            case "double-quoted-scalar": {
              const fs = this.flowScalar(this.type);
              if (!it || it.value)
                fc.items.push({ start: [], key: fs, sep: [] });
              else if (it.sep)
                this.stack.push(fs);
              else
                Object.assign(it, { key: fs, sep: [] });
              return;
            }
            case "flow-map-end":
            case "flow-seq-end":
              fc.end.push(this.sourceToken);
              return;
          }
          const bv = this.startBlockValue(fc);
          if (bv)
            this.stack.push(bv);
          else {
            yield* this.pop();
            yield* this.step();
          }
        } else {
          const parent = this.peek(2);
          if (parent.type === "block-map" && (this.type === "map-value-ind" && parent.indent === fc.indent || this.type === "newline" && !parent.items[parent.items.length - 1].sep)) {
            yield* this.pop();
            yield* this.step();
          } else if (this.type === "map-value-ind" && parent.type !== "flow-collection") {
            const prev = getPrevProps(parent);
            const start = getFirstKeyStartProps(prev);
            fixFlowSeqItems(fc);
            const sep2 = fc.end.splice(1, fc.end.length);
            sep2.push(this.sourceToken);
            const map = {
              type: "block-map",
              offset: fc.offset,
              indent: fc.indent,
              items: [{ start, key: fc, sep: sep2 }]
            };
            this.onKeyLine = true;
            this.stack[this.stack.length - 1] = map;
          } else {
            yield* this.lineEnd(fc);
          }
        }
      }
      flowScalar(type) {
        if (this.onNewLine) {
          let nl = this.source.indexOf("\n") + 1;
          while (nl !== 0) {
            this.onNewLine(this.offset + nl);
            nl = this.source.indexOf("\n", nl) + 1;
          }
        }
        return {
          type,
          offset: this.offset,
          indent: this.indent,
          source: this.source
        };
      }
      startBlockValue(parent) {
        switch (this.type) {
          case "alias":
          case "scalar":
          case "single-quoted-scalar":
          case "double-quoted-scalar":
            return this.flowScalar(this.type);
          case "block-scalar-header":
            return {
              type: "block-scalar",
              offset: this.offset,
              indent: this.indent,
              props: [this.sourceToken],
              source: ""
            };
          case "flow-map-start":
          case "flow-seq-start":
            return {
              type: "flow-collection",
              offset: this.offset,
              indent: this.indent,
              start: this.sourceToken,
              items: [],
              end: []
            };
          case "seq-item-ind":
            return {
              type: "block-seq",
              offset: this.offset,
              indent: this.indent,
              items: [{ start: [this.sourceToken] }]
            };
          case "explicit-key-ind": {
            this.onKeyLine = true;
            const prev = getPrevProps(parent);
            const start = getFirstKeyStartProps(prev);
            start.push(this.sourceToken);
            return {
              type: "block-map",
              offset: this.offset,
              indent: this.indent,
              items: [{ start, explicitKey: true }]
            };
          }
          case "map-value-ind": {
            this.onKeyLine = true;
            const prev = getPrevProps(parent);
            const start = getFirstKeyStartProps(prev);
            return {
              type: "block-map",
              offset: this.offset,
              indent: this.indent,
              items: [{ start, key: null, sep: [this.sourceToken] }]
            };
          }
        }
        return null;
      }
      atIndentedComment(start, indent) {
        if (this.type !== "comment")
          return false;
        if (this.indent <= indent)
          return false;
        return start.every((st) => st.type === "newline" || st.type === "space");
      }
      *documentEnd(docEnd) {
        if (this.type !== "doc-mode") {
          if (docEnd.end)
            docEnd.end.push(this.sourceToken);
          else
            docEnd.end = [this.sourceToken];
          if (this.type === "newline")
            yield* this.pop();
        }
      }
      *lineEnd(token) {
        switch (this.type) {
          case "comma":
          case "doc-start":
          case "doc-end":
          case "flow-seq-end":
          case "flow-map-end":
          case "map-value-ind":
            yield* this.pop();
            yield* this.step();
            break;
          case "newline":
            this.onKeyLine = false;
          // fallthrough
          case "space":
          case "comment":
          default:
            if (token.end)
              token.end.push(this.sourceToken);
            else
              token.end = [this.sourceToken];
            if (this.type === "newline")
              yield* this.pop();
        }
      }
    };
    exports.Parser = Parser;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/public-api.js
var require_public_api = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/public-api.js"(exports) {
    "use strict";
    var composer = require_composer();
    var Document = require_Document();
    var errors = require_errors();
    var log = require_log();
    var identity = require_identity();
    var lineCounter = require_line_counter();
    var parser = require_parser();
    function parseOptions2(options) {
      const prettyErrors = options.prettyErrors !== false;
      const lineCounter$1 = options.lineCounter || prettyErrors && new lineCounter.LineCounter() || null;
      return { lineCounter: lineCounter$1, prettyErrors };
    }
    function parseAllDocuments(source, options = {}) {
      const { lineCounter: lineCounter2, prettyErrors } = parseOptions2(options);
      const parser$1 = new parser.Parser(lineCounter2?.addNewLine);
      const composer$1 = new composer.Composer(options);
      const docs = Array.from(composer$1.compose(parser$1.parse(source)));
      if (prettyErrors && lineCounter2)
        for (const doc of docs) {
          doc.errors.forEach(errors.prettifyError(source, lineCounter2));
          doc.warnings.forEach(errors.prettifyError(source, lineCounter2));
        }
      if (docs.length > 0)
        return docs;
      return Object.assign([], { empty: true }, composer$1.streamInfo());
    }
    function parseDocument(source, options = {}) {
      const { lineCounter: lineCounter2, prettyErrors } = parseOptions2(options);
      const parser$1 = new parser.Parser(lineCounter2?.addNewLine);
      const composer$1 = new composer.Composer(options);
      let doc = null;
      for (const _doc of composer$1.compose(parser$1.parse(source), true, source.length)) {
        if (!doc)
          doc = _doc;
        else if (doc.options.logLevel !== "silent") {
          doc.errors.push(new errors.YAMLParseError(_doc.range.slice(0, 2), "MULTIPLE_DOCS", "Source contains multiple documents; please use YAML.parseAllDocuments()"));
          break;
        }
      }
      if (prettyErrors && lineCounter2) {
        doc.errors.forEach(errors.prettifyError(source, lineCounter2));
        doc.warnings.forEach(errors.prettifyError(source, lineCounter2));
      }
      return doc;
    }
    function parse3(src, reviver, options) {
      let _reviver = void 0;
      if (typeof reviver === "function") {
        _reviver = reviver;
      } else if (options === void 0 && reviver && typeof reviver === "object") {
        options = reviver;
      }
      const doc = parseDocument(src, options);
      if (!doc)
        return null;
      doc.warnings.forEach((warning) => log.warn(doc.options.logLevel, warning));
      if (doc.errors.length > 0) {
        if (doc.options.logLevel !== "silent")
          throw doc.errors[0];
        else
          doc.errors = [];
      }
      return doc.toJS(Object.assign({ reviver: _reviver }, options));
    }
    function stringify(value, replacer, options) {
      let _replacer = null;
      if (typeof replacer === "function" || Array.isArray(replacer)) {
        _replacer = replacer;
      } else if (options === void 0 && replacer) {
        options = replacer;
      }
      if (typeof options === "string")
        options = options.length;
      if (typeof options === "number") {
        const indent = Math.round(options);
        options = indent < 1 ? void 0 : indent > 8 ? { indent: 8 } : { indent };
      }
      if (value === void 0) {
        const { keepUndefined } = options ?? replacer ?? {};
        if (!keepUndefined)
          return void 0;
      }
      if (identity.isDocument(value) && !_replacer)
        return value.toString(options);
      return new Document.Document(value, _replacer, options).toString(options);
    }
    exports.parse = parse3;
    exports.parseAllDocuments = parseAllDocuments;
    exports.parseDocument = parseDocument;
    exports.stringify = stringify;
  }
});

// node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/index.js
var require_dist = __commonJS({
  "node_modules/.pnpm/yaml@2.9.0/node_modules/yaml/dist/index.js"(exports) {
    "use strict";
    var composer = require_composer();
    var Document = require_Document();
    var Schema = require_Schema();
    var errors = require_errors();
    var Alias = require_Alias();
    var identity = require_identity();
    var Pair = require_Pair();
    var Scalar = require_Scalar();
    var YAMLMap = require_YAMLMap();
    var YAMLSeq = require_YAMLSeq();
    var cst = require_cst();
    var lexer = require_lexer();
    var lineCounter = require_line_counter();
    var parser = require_parser();
    var publicApi = require_public_api();
    var visit = require_visit();
    exports.Composer = composer.Composer;
    exports.Document = Document.Document;
    exports.Schema = Schema.Schema;
    exports.YAMLError = errors.YAMLError;
    exports.YAMLParseError = errors.YAMLParseError;
    exports.YAMLWarning = errors.YAMLWarning;
    exports.Alias = Alias.Alias;
    exports.isAlias = identity.isAlias;
    exports.isCollection = identity.isCollection;
    exports.isDocument = identity.isDocument;
    exports.isMap = identity.isMap;
    exports.isNode = identity.isNode;
    exports.isPair = identity.isPair;
    exports.isScalar = identity.isScalar;
    exports.isSeq = identity.isSeq;
    exports.Pair = Pair.Pair;
    exports.Scalar = Scalar.Scalar;
    exports.YAMLMap = YAMLMap.YAMLMap;
    exports.YAMLSeq = YAMLSeq.YAMLSeq;
    exports.CST = cst;
    exports.Lexer = lexer.Lexer;
    exports.LineCounter = lineCounter.LineCounter;
    exports.Parser = parser.Parser;
    exports.parse = publicApi.parse;
    exports.parseAllDocuments = publicApi.parseAllDocuments;
    exports.parseDocument = publicApi.parseDocument;
    exports.stringify = publicApi.stringify;
    exports.visit = visit.visit;
    exports.visitAsync = visit.visitAsync;
  }
});

// node_modules/.pnpm/sisteransi@1.0.5/node_modules/sisteransi/src/index.js
var require_src = __commonJS({
  "node_modules/.pnpm/sisteransi@1.0.5/node_modules/sisteransi/src/index.js"(exports, module) {
    "use strict";
    var ESC = "\x1B";
    var CSI = `${ESC}[`;
    var beep = "\x07";
    var cursor = {
      to(x, y2) {
        if (!y2) return `${CSI}${x + 1}G`;
        return `${CSI}${y2 + 1};${x + 1}H`;
      },
      move(x, y2) {
        let ret = "";
        if (x < 0) ret += `${CSI}${-x}D`;
        else if (x > 0) ret += `${CSI}${x}C`;
        if (y2 < 0) ret += `${CSI}${-y2}A`;
        else if (y2 > 0) ret += `${CSI}${y2}B`;
        return ret;
      },
      up: (count = 1) => `${CSI}${count}A`,
      down: (count = 1) => `${CSI}${count}B`,
      forward: (count = 1) => `${CSI}${count}C`,
      backward: (count = 1) => `${CSI}${count}D`,
      nextLine: (count = 1) => `${CSI}E`.repeat(count),
      prevLine: (count = 1) => `${CSI}F`.repeat(count),
      left: `${CSI}G`,
      hide: `${CSI}?25l`,
      show: `${CSI}?25h`,
      save: `${ESC}7`,
      restore: `${ESC}8`
    };
    var scroll = {
      up: (count = 1) => `${CSI}S`.repeat(count),
      down: (count = 1) => `${CSI}T`.repeat(count)
    };
    var erase = {
      screen: `${CSI}2J`,
      up: (count = 1) => `${CSI}1J`.repeat(count),
      down: (count = 1) => `${CSI}J`.repeat(count),
      line: `${CSI}2K`,
      lineEnd: `${CSI}K`,
      lineStart: `${CSI}1K`,
      lines(count) {
        let clear = "";
        for (let i = 0; i < count; i++)
          clear += this.line + (i < count - 1 ? cursor.up() : "");
        if (count)
          clear += cursor.left;
        return clear;
      }
    };
    module.exports = { cursor, scroll, erase, beep };
  }
});

// node_modules/.pnpm/picocolors@1.1.1/node_modules/picocolors/picocolors.js
var require_picocolors = __commonJS({
  "node_modules/.pnpm/picocolors@1.1.1/node_modules/picocolors/picocolors.js"(exports, module) {
    "use strict";
    var p = process || {};
    var argv = p.argv || [];
    var env = p.env || {};
    var isColorSupported = !(!!env.NO_COLOR || argv.includes("--no-color")) && (!!env.FORCE_COLOR || argv.includes("--color") || p.platform === "win32" || (p.stdout || {}).isTTY && env.TERM !== "dumb" || !!env.CI);
    var formatter = (open, close, replace = open) => (input) => {
      let string = "" + input, index = string.indexOf(close, open.length);
      return ~index ? open + replaceClose(string, close, replace, index) + close : open + string + close;
    };
    var replaceClose = (string, close, replace, index) => {
      let result = "", cursor = 0;
      do {
        result += string.substring(cursor, index) + replace;
        cursor = index + close.length;
        index = string.indexOf(close, cursor);
      } while (~index);
      return result + string.substring(cursor);
    };
    var createColors = (enabled = isColorSupported) => {
      let f = enabled ? formatter : () => String;
      return {
        isColorSupported: enabled,
        reset: f("\x1B[0m", "\x1B[0m"),
        bold: f("\x1B[1m", "\x1B[22m", "\x1B[22m\x1B[1m"),
        dim: f("\x1B[2m", "\x1B[22m", "\x1B[22m\x1B[2m"),
        italic: f("\x1B[3m", "\x1B[23m"),
        underline: f("\x1B[4m", "\x1B[24m"),
        inverse: f("\x1B[7m", "\x1B[27m"),
        hidden: f("\x1B[8m", "\x1B[28m"),
        strikethrough: f("\x1B[9m", "\x1B[29m"),
        black: f("\x1B[30m", "\x1B[39m"),
        red: f("\x1B[31m", "\x1B[39m"),
        green: f("\x1B[32m", "\x1B[39m"),
        yellow: f("\x1B[33m", "\x1B[39m"),
        blue: f("\x1B[34m", "\x1B[39m"),
        magenta: f("\x1B[35m", "\x1B[39m"),
        cyan: f("\x1B[36m", "\x1B[39m"),
        white: f("\x1B[37m", "\x1B[39m"),
        gray: f("\x1B[90m", "\x1B[39m"),
        bgBlack: f("\x1B[40m", "\x1B[49m"),
        bgRed: f("\x1B[41m", "\x1B[49m"),
        bgGreen: f("\x1B[42m", "\x1B[49m"),
        bgYellow: f("\x1B[43m", "\x1B[49m"),
        bgBlue: f("\x1B[44m", "\x1B[49m"),
        bgMagenta: f("\x1B[45m", "\x1B[49m"),
        bgCyan: f("\x1B[46m", "\x1B[49m"),
        bgWhite: f("\x1B[47m", "\x1B[49m"),
        blackBright: f("\x1B[90m", "\x1B[39m"),
        redBright: f("\x1B[91m", "\x1B[39m"),
        greenBright: f("\x1B[92m", "\x1B[39m"),
        yellowBright: f("\x1B[93m", "\x1B[39m"),
        blueBright: f("\x1B[94m", "\x1B[39m"),
        magentaBright: f("\x1B[95m", "\x1B[39m"),
        cyanBright: f("\x1B[96m", "\x1B[39m"),
        whiteBright: f("\x1B[97m", "\x1B[39m"),
        bgBlackBright: f("\x1B[100m", "\x1B[49m"),
        bgRedBright: f("\x1B[101m", "\x1B[49m"),
        bgGreenBright: f("\x1B[102m", "\x1B[49m"),
        bgYellowBright: f("\x1B[103m", "\x1B[49m"),
        bgBlueBright: f("\x1B[104m", "\x1B[49m"),
        bgMagentaBright: f("\x1B[105m", "\x1B[49m"),
        bgCyanBright: f("\x1B[106m", "\x1B[49m"),
        bgWhiteBright: f("\x1B[107m", "\x1B[49m")
      };
    };
    module.exports = createColors();
    module.exports.createColors = createColors;
  }
});

// node_modules/.pnpm/ws@8.21.0/node_modules/ws/lib/constants.js
var require_constants = __commonJS({
  "node_modules/.pnpm/ws@8.21.0/node_modules/ws/lib/constants.js"(exports, module) {
    "use strict";
    var BINARY_TYPES = ["nodebuffer", "arraybuffer", "fragments"];
    var hasBlob = typeof Blob !== "undefined";
    if (hasBlob) BINARY_TYPES.push("blob");
    module.exports = {
      BINARY_TYPES,
      CLOSE_TIMEOUT: 3e4,
      EMPTY_BUFFER: Buffer.alloc(0),
      GUID: "258EAFA5-E914-47DA-95CA-C5AB0DC85B11",
      hasBlob,
      kForOnEventAttribute: /* @__PURE__ */ Symbol("kIsForOnEventAttribute"),
      kListener: /* @__PURE__ */ Symbol("kListener"),
      kStatusCode: /* @__PURE__ */ Symbol("status-code"),
      kWebSocket: /* @__PURE__ */ Symbol("websocket"),
      NOOP: () => {
      }
    };
  }
});

// node_modules/.pnpm/ws@8.21.0/node_modules/ws/lib/buffer-util.js
var require_buffer_util = __commonJS({
  "node_modules/.pnpm/ws@8.21.0/node_modules/ws/lib/buffer-util.js"(exports, module) {
    "use strict";
    var { EMPTY_BUFFER } = require_constants();
    var FastBuffer = Buffer[Symbol.species];
    function concat(list, totalLength) {
      if (list.length === 0) return EMPTY_BUFFER;
      if (list.length === 1) return list[0];
      const target = Buffer.allocUnsafe(totalLength);
      let offset = 0;
      for (let i = 0; i < list.length; i++) {
        const buf = list[i];
        target.set(buf, offset);
        offset += buf.length;
      }
      if (offset < totalLength) {
        return new FastBuffer(target.buffer, target.byteOffset, offset);
      }
      return target;
    }
    function _mask(source, mask, output, offset, length) {
      for (let i = 0; i < length; i++) {
        output[offset + i] = source[i] ^ mask[i & 3];
      }
    }
    function _unmask(buffer, mask) {
      for (let i = 0; i < buffer.length; i++) {
        buffer[i] ^= mask[i & 3];
      }
    }
    function toArrayBuffer(buf) {
      if (buf.length === buf.buffer.byteLength) {
        return buf.buffer;
      }
      return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.length);
    }
    function toBuffer(data) {
      toBuffer.readOnly = true;
      if (Buffer.isBuffer(data)) return data;
      let buf;
      if (data instanceof ArrayBuffer) {
        buf = new FastBuffer(data);
      } else if (ArrayBuffer.isView(data)) {
        buf = new FastBuffer(data.buffer, data.byteOffset, data.byteLength);
      } else {
        buf = Buffer.from(data);
        toBuffer.readOnly = false;
      }
      return buf;
    }
    module.exports = {
      concat,
      mask: _mask,
      toArrayBuffer,
      toBuffer,
      unmask: _unmask
    };
    if (!process.env.WS_NO_BUFFER_UTIL) {
      try {
        const bufferUtil = __require("bufferutil");
        module.exports.mask = function(source, mask, output, offset, length) {
          if (length < 48) _mask(source, mask, output, offset, length);
          else bufferUtil.mask(source, mask, output, offset, length);
        };
        module.exports.unmask = function(buffer, mask) {
          if (buffer.length < 32) _unmask(buffer, mask);
          else bufferUtil.unmask(buffer, mask);
        };
      } catch (e2) {
      }
    }
  }
});

// node_modules/.pnpm/ws@8.21.0/node_modules/ws/lib/limiter.js
var require_limiter = __commonJS({
  "node_modules/.pnpm/ws@8.21.0/node_modules/ws/lib/limiter.js"(exports, module) {
    "use strict";
    var kDone = /* @__PURE__ */ Symbol("kDone");
    var kRun = /* @__PURE__ */ Symbol("kRun");
    var Limiter = class {
      /**
       * Creates a new `Limiter`.
       *
       * @param {Number} [concurrency=Infinity] The maximum number of jobs allowed
       *     to run concurrently
       */
      constructor(concurrency) {
        this[kDone] = () => {
          this.pending--;
          this[kRun]();
        };
        this.concurrency = concurrency || Infinity;
        this.jobs = [];
        this.pending = 0;
      }
      /**
       * Adds a job to the queue.
       *
       * @param {Function} job The job to run
       * @public
       */
      add(job) {
        this.jobs.push(job);
        this[kRun]();
      }
      /**
       * Removes a job from the queue and runs it if possible.
       *
       * @private
       */
      [kRun]() {
        if (this.pending === this.concurrency) return;
        if (this.jobs.length) {
          const job = this.jobs.shift();
          this.pending++;
          job(this[kDone]);
        }
      }
    };
    module.exports = Limiter;
  }
});

// node_modules/.pnpm/ws@8.21.0/node_modules/ws/lib/permessage-deflate.js
var require_permessage_deflate = __commonJS({
  "node_modules/.pnpm/ws@8.21.0/node_modules/ws/lib/permessage-deflate.js"(exports, module) {
    "use strict";
    var zlib = __require("zlib");
    var bufferUtil = require_buffer_util();
    var Limiter = require_limiter();
    var { kStatusCode } = require_constants();
    var FastBuffer = Buffer[Symbol.species];
    var TRAILER = Buffer.from([0, 0, 255, 255]);
    var kPerMessageDeflate = /* @__PURE__ */ Symbol("permessage-deflate");
    var kTotalLength = /* @__PURE__ */ Symbol("total-length");
    var kCallback = /* @__PURE__ */ Symbol("callback");
    var kBuffers = /* @__PURE__ */ Symbol("buffers");
    var kError = /* @__PURE__ */ Symbol("error");
    var zlibLimiter;
    var PerMessageDeflate2 = class {
      /**
       * Creates a PerMessageDeflate instance.
       *
       * @param {Object} [options] Configuration options
       * @param {(Boolean|Number)} [options.clientMaxWindowBits] Advertise support
       *     for, or request, a custom client window size
       * @param {Boolean} [options.clientNoContextTakeover=false] Advertise/
       *     acknowledge disabling of client context takeover
       * @param {Number} [options.concurrencyLimit=10] The number of concurrent
       *     calls to zlib
       * @param {Boolean} [options.isServer=false] Create the instance in either
       *     server or client mode
       * @param {Number} [options.maxPayload=0] The maximum allowed message length
       * @param {(Boolean|Number)} [options.serverMaxWindowBits] Request/confirm the
       *     use of a custom server window size
       * @param {Boolean} [options.serverNoContextTakeover=false] Request/accept
       *     disabling of server context takeover
       * @param {Number} [options.threshold=1024] Size (in bytes) below which
       *     messages should not be compressed if context takeover is disabled
       * @param {Object} [options.zlibDeflateOptions] Options to pass to zlib on
       *     deflate
       * @param {Object} [options.zlibInflateOptions] Options to pass to zlib on
       *     inflate
       */
      constructor(options) {
        this._options = options || {};
        this._threshold = this._options.threshold !== void 0 ? this._options.threshold : 1024;
        this._maxPayload = this._options.maxPayload | 0;
        this._isServer = !!this._options.isServer;
        this._deflate = null;
        this._inflate = null;
        this.params = null;
        if (!zlibLimiter) {
          const concurrency = this._options.concurrencyLimit !== void 0 ? this._options.concurrencyLimit : 10;
          zlibLimiter = new Limiter(concurrency);
        }
      }
      /**
       * @type {String}
       */
      static get extensionName() {
        return "permessage-deflate";
      }
      /**
       * Create an extension negotiation offer.
       *
       * @return {Object} Extension parameters
       * @public
       */
      offer() {
        const params = {};
        if (this._options.serverNoContextTakeover) {
          params.server_no_context_takeover = true;
        }
        if (this._options.clientNoContextTakeover) {
          params.client_no_context_takeover = true;
        }
        if (this._options.serverMaxWindowBits) {
          params.server_max_window_bits = this._options.serverMaxWindowBits;
        }
        if (this._options.clientMaxWindowBits) {
          params.client_max_window_bits = this._options.clientMaxWindowBits;
        } else if (this._options.clientMaxWindowBits == null) {
          params.client_max_window_bits = true;
        }
        return params;
      }
      /**
       * Accept an extension negotiation offer/response.
       *
       * @param {Array} configurations The extension negotiation offers/reponse
       * @return {Object} Accepted configuration
       * @public
       */
      accept(configurations) {
        configurations = this.normalizeParams(configurations);
        this.params = this._isServer ? this.acceptAsServer(configurations) : this.acceptAsClient(configurations);
        return this.params;
      }
      /**
       * Releases all resources used by the extension.
       *
       * @public
       */
      cleanup() {
        if (this._inflate) {
          this._inflate.close();
          this._inflate = null;
        }
        if (this._deflate) {
          const callback = this._deflate[kCallback];
          this._deflate.close();
          this._deflate = null;
          if (callback) {
            callback(
              new Error(
                "The deflate stream was closed while data was being processed"
              )
            );
          }
        }
      }
      /**
       *  Accept an extension negotiation offer.
       *
       * @param {Array} offers The extension negotiation offers
       * @return {Object} Accepted configuration
       * @private
       */
      acceptAsServer(offers) {
        const opts = this._options;
        const accepted = offers.find((params) => {
          if (opts.serverNoContextTakeover === false && params.server_no_context_takeover || params.server_max_window_bits && (opts.serverMaxWindowBits === false || typeof opts.serverMaxWindowBits === "number" && opts.serverMaxWindowBits > params.server_max_window_bits) || typeof opts.clientMaxWindowBits === "number" && !params.client_max_window_bits) {
            return false;
          }
          return true;
        });
        if (!accepted) {
          throw new Error("None of the extension offers can be accepted");
        }
        if (opts.serverNoContextTakeover) {
          accepted.server_no_context_takeover = true;
        }
        if (opts.clientNoContextTakeover) {
          accepted.client_no_context_takeover = true;
        }
        if (typeof opts.serverMaxWindowBits === "number") {
          accepted.server_max_window_bits = opts.serverMaxWindowBits;
        }
        if (typeof opts.clientMaxWindowBits === "number") {
          accepted.client_max_window_bits = opts.clientMaxWindowBits;
        } else if (accepted.client_max_window_bits === true || opts.clientMaxWindowBits === false) {
          delete accepted.client_max_window_bits;
        }
        return accepted;
      }
      /**
       * Accept the extension negotiation response.
       *
       * @param {Array} response The extension negotiation response
       * @return {Object} Accepted configuration
       * @private
       */
      acceptAsClient(response) {
        const params = response[0];
        if (this._options.clientNoContextTakeover === false && params.client_no_context_takeover) {
          throw new Error('Unexpected parameter "client_no_context_takeover"');
        }
        if (!params.client_max_window_bits) {
          if (typeof this._options.clientMaxWindowBits === "number") {
            params.client_max_window_bits = this._options.clientMaxWindowBits;
          }
        } else if (this._options.clientMaxWindowBits === false || typeof this._options.clientMaxWindowBits === "number" && params.client_max_window_bits > this._options.clientMaxWindowBits) {
          throw new Error(
            'Unexpected or invalid parameter "client_max_window_bits"'
          );
        }
        return params;
      }
      /**
       * Normalize parameters.
       *
       * @param {Array} configurations The extension negotiation offers/reponse
       * @return {Array} The offers/response with normalized parameters
       * @private
       */
      normalizeParams(configurations) {
        configurations.forEach((params) => {
          Object.keys(params).forEach((key) => {
            let value = params[key];
            if (value.length > 1) {
              throw new Error(`Parameter "${key}" must have only a single value`);
            }
            value = value[0];
            if (key === "client_max_window_bits") {
              if (value !== true) {
                const num = +value;
                if (!Number.isInteger(num) || num < 8 || num > 15) {
                  throw new TypeError(
                    `Invalid value for parameter "${key}": ${value}`
                  );
                }
                value = num;
              } else if (!this._isServer) {
                throw new TypeError(
                  `Invalid value for parameter "${key}": ${value}`
                );
              }
            } else if (key === "server_max_window_bits") {
              const num = +value;
              if (!Number.isInteger(num) || num < 8 || num > 15) {
                throw new TypeError(
                  `Invalid value for parameter "${key}": ${value}`
                );
              }
              value = num;
            } else if (key === "client_no_context_takeover" || key === "server_no_context_takeover") {
              if (value !== true) {
                throw new TypeError(
                  `Invalid value for parameter "${key}": ${value}`
                );
              }
            } else {
              throw new Error(`Unknown parameter "${key}"`);
            }
            params[key] = value;
          });
        });
        return configurations;
      }
      /**
       * Decompress data. Concurrency limited.
       *
       * @param {Buffer} data Compressed data
       * @param {Boolean} fin Specifies whether or not this is the last fragment
       * @param {Function} callback Callback
       * @public
       */
      decompress(data, fin, callback) {
        zlibLimiter.add((done) => {
          this._decompress(data, fin, (err, result) => {
            done();
            callback(err, result);
          });
        });
      }
      /**
       * Compress data. Concurrency limited.
       *
       * @param {(Buffer|String)} data Data to compress
       * @param {Boolean} fin Specifies whether or not this is the last fragment
       * @param {Function} callback Callback
       * @public
       */
      compress(data, fin, callback) {
        zlibLimiter.add((done) => {
          this._compress(data, fin, (err, result) => {
            done();
            callback(err, result);
          });
        });
      }
      /**
       * Decompress data.
       *
       * @param {Buffer} data Compressed data
       * @param {Boolean} fin Specifies whether or not this is the last fragment
       * @param {Function} callback Callback
       * @private
       */
      _decompress(data, fin, callback) {
        const endpoint = this._isServer ? "client" : "server";
        if (!this._inflate) {
          const key = `${endpoint}_max_window_bits`;
          const windowBits = typeof this.params[key] !== "number" ? zlib.Z_DEFAULT_WINDOWBITS : this.params[key];
          this._inflate = zlib.createInflateRaw({
            ...this._options.zlibInflateOptions,
            windowBits
          });
          this._inflate[kPerMessageDeflate] = this;
          this._inflate[kTotalLength] = 0;
          this._inflate[kBuffers] = [];
          this._inflate.on("error", inflateOnError);
          this._inflate.on("data", inflateOnData);
        }
        this._inflate[kCallback] = callback;
        this._inflate.write(data);
        if (fin) this._inflate.write(TRAILER);
        this._inflate.flush(() => {
          const err = this._inflate[kError];
          if (err) {
            this._inflate.close();
            this._inflate = null;
            callback(err);
            return;
          }
          const data2 = bufferUtil.concat(
            this._inflate[kBuffers],
            this._inflate[kTotalLength]
          );
          if (this._inflate._readableState.endEmitted) {
            this._inflate.close();
            this._inflate = null;
          } else {
            this._inflate[kTotalLength] = 0;
            this._inflate[kBuffers] = [];
            if (fin && this.params[`${endpoint}_no_context_takeover`]) {
              this._inflate.reset();
            }
          }
          callback(null, data2);
        });
      }
      /**
       * Compress data.
       *
       * @param {(Buffer|String)} data Data to compress
       * @param {Boolean} fin Specifies whether or not this is the last fragment
       * @param {Function} callback Callback
       * @private
       */
      _compress(data, fin, callback) {
        const endpoint = this._isServer ? "server" : "client";
        if (!this._deflate) {
          const key = `${endpoint}_max_window_bits`;
          const windowBits = typeof this.params[key] !== "number" ? zlib.Z_DEFAULT_WINDOWBITS : this.params[key];
          this._deflate = zlib.createDeflateRaw({
            ...this._options.zlibDeflateOptions,
            windowBits
          });
          this._deflate[kTotalLength] = 0;
          this._deflate[kBuffers] = [];
          this._deflate.on("data", deflateOnData);
        }
        this._deflate[kCallback] = callback;
        this._deflate.write(data);
        this._deflate.flush(zlib.Z_SYNC_FLUSH, () => {
          if (!this._deflate) {
            return;
          }
          let data2 = bufferUtil.concat(
            this._deflate[kBuffers],
            this._deflate[kTotalLength]
          );
          if (fin) {
            data2 = new FastBuffer(data2.buffer, data2.byteOffset, data2.length - 4);
          }
          this._deflate[kCallback] = null;
          this._deflate[kTotalLength] = 0;
          this._deflate[kBuffers] = [];
          if (fin && this.params[`${endpoint}_no_context_takeover`]) {
            this._deflate.reset();
          }
          callback(null, data2);
        });
      }
    };
    module.exports = PerMessageDeflate2;
    function deflateOnData(chunk) {
      this[kBuffers].push(chunk);
      this[kTotalLength] += chunk.length;
    }
    function inflateOnData(chunk) {
      this[kTotalLength] += chunk.length;
      if (this[kPerMessageDeflate]._maxPayload < 1 || this[kTotalLength] <= this[kPerMessageDeflate]._maxPayload) {
        this[kBuffers].push(chunk);
        return;
      }
      this[kError] = new RangeError("Max payload size exceeded");
      this[kError].code = "WS_ERR_UNSUPPORTED_MESSAGE_LENGTH";
      this[kError][kStatusCode] = 1009;
      this.removeListener("data", inflateOnData);
      this.reset();
    }
    function inflateOnError(err) {
      this[kPerMessageDeflate]._inflate = null;
      if (this[kError]) {
        this[kCallback](this[kError]);
        return;
      }
      err[kStatusCode] = 1007;
      this[kCallback](err);
    }
  }
});

// node_modules/.pnpm/ws@8.21.0/node_modules/ws/lib/validation.js
var require_validation = __commonJS({
  "node_modules/.pnpm/ws@8.21.0/node_modules/ws/lib/validation.js"(exports, module) {
    "use strict";
    var { isUtf8 } = __require("buffer");
    var { hasBlob } = require_constants();
    var tokenChars = [
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      // 0 - 15
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      // 16 - 31
      0,
      1,
      0,
      1,
      1,
      1,
      1,
      1,
      0,
      0,
      1,
      1,
      0,
      1,
      1,
      0,
      // 32 - 47
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      0,
      0,
      0,
      0,
      0,
      0,
      // 48 - 63
      0,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      // 64 - 79
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      0,
      0,
      0,
      1,
      1,
      // 80 - 95
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      // 96 - 111
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      0,
      1,
      0,
      1,
      0
      // 112 - 127
    ];
    function isValidStatusCode(code) {
      return code >= 1e3 && code <= 1014 && code !== 1004 && code !== 1005 && code !== 1006 || code >= 3e3 && code <= 4999;
    }
    function _isValidUTF8(buf) {
      const len = buf.length;
      let i = 0;
      while (i < len) {
        if ((buf[i] & 128) === 0) {
          i++;
        } else if ((buf[i] & 224) === 192) {
          if (i + 1 === len || (buf[i + 1] & 192) !== 128 || (buf[i] & 254) === 192) {
            return false;
          }
          i += 2;
        } else if ((buf[i] & 240) === 224) {
          if (i + 2 >= len || (buf[i + 1] & 192) !== 128 || (buf[i + 2] & 192) !== 128 || buf[i] === 224 && (buf[i + 1] & 224) === 128 || // Overlong
          buf[i] === 237 && (buf[i + 1] & 224) === 160) {
            return false;
          }
          i += 3;
        } else if ((buf[i] & 248) === 240) {
          if (i + 3 >= len || (buf[i + 1] & 192) !== 128 || (buf[i + 2] & 192) !== 128 || (buf[i + 3] & 192) !== 128 || buf[i] === 240 && (buf[i + 1] & 240) === 128 || // Overlong
          buf[i] === 244 && buf[i + 1] > 143 || buf[i] > 244) {
            return false;
          }
          i += 4;
        } else {
          return false;
        }
      }
      return true;
    }
    function isBlob(value) {
      return hasBlob && typeof value === "object" && typeof value.arrayBuffer === "function" && typeof value.type === "string" && typeof value.stream === "function" && (value[Symbol.toStringTag] === "Blob" || value[Symbol.toStringTag] === "File");
    }
    module.exports = {
      isBlob,
      isValidStatusCode,
      isValidUTF8: _isValidUTF8,
      tokenChars
    };
    if (isUtf8) {
      module.exports.isValidUTF8 = function(buf) {
        return buf.length < 24 ? _isValidUTF8(buf) : isUtf8(buf);
      };
    } else if (!process.env.WS_NO_UTF_8_VALIDATE) {
      try {
        const isValidUTF8 = __require("utf-8-validate");
        module.exports.isValidUTF8 = function(buf) {
          return buf.length < 32 ? _isValidUTF8(buf) : isValidUTF8(buf);
        };
      } catch (e2) {
      }
    }
  }
});

// node_modules/.pnpm/ws@8.21.0/node_modules/ws/lib/receiver.js
var require_receiver = __commonJS({
  "node_modules/.pnpm/ws@8.21.0/node_modules/ws/lib/receiver.js"(exports, module) {
    "use strict";
    var { Writable } = __require("stream");
    var PerMessageDeflate2 = require_permessage_deflate();
    var {
      BINARY_TYPES,
      EMPTY_BUFFER,
      kStatusCode,
      kWebSocket
    } = require_constants();
    var { concat, toArrayBuffer, unmask } = require_buffer_util();
    var { isValidStatusCode, isValidUTF8 } = require_validation();
    var FastBuffer = Buffer[Symbol.species];
    var GET_INFO = 0;
    var GET_PAYLOAD_LENGTH_16 = 1;
    var GET_PAYLOAD_LENGTH_64 = 2;
    var GET_MASK = 3;
    var GET_DATA = 4;
    var INFLATING = 5;
    var DEFER_EVENT = 6;
    var Receiver2 = class extends Writable {
      /**
       * Creates a Receiver instance.
       *
       * @param {Object} [options] Options object
       * @param {Boolean} [options.allowSynchronousEvents=true] Specifies whether
       *     any of the `'message'`, `'ping'`, and `'pong'` events can be emitted
       *     multiple times in the same tick
       * @param {String} [options.binaryType=nodebuffer] The type for binary data
       * @param {Object} [options.extensions] An object containing the negotiated
       *     extensions
       * @param {Boolean} [options.isServer=false] Specifies whether to operate in
       *     client or server mode
       * @param {Number} [options.maxBufferedChunks=0] The maximum number of
       *     buffered data chunks
       * @param {Number} [options.maxFragments=0] The maximum number of message
       *     fragments
       * @param {Number} [options.maxPayload=0] The maximum allowed message length
       * @param {Boolean} [options.skipUTF8Validation=false] Specifies whether or
       *     not to skip UTF-8 validation for text and close messages
       */
      constructor(options = {}) {
        super();
        this._allowSynchronousEvents = options.allowSynchronousEvents !== void 0 ? options.allowSynchronousEvents : true;
        this._binaryType = options.binaryType || BINARY_TYPES[0];
        this._extensions = options.extensions || {};
        this._isServer = !!options.isServer;
        this._maxBufferedChunks = options.maxBufferedChunks | 0;
        this._maxFragments = options.maxFragments | 0;
        this._maxPayload = options.maxPayload | 0;
        this._skipUTF8Validation = !!options.skipUTF8Validation;
        this[kWebSocket] = void 0;
        this._bufferedBytes = 0;
        this._buffers = [];
        this._compressed = false;
        this._payloadLength = 0;
        this._mask = void 0;
        this._fragmented = 0;
        this._masked = false;
        this._fin = false;
        this._opcode = 0;
        this._totalPayloadLength = 0;
        this._messageLength = 0;
        this._fragments = [];
        this._errored = false;
        this._loop = false;
        this._state = GET_INFO;
      }
      /**
       * Implements `Writable.prototype._write()`.
       *
       * @param {Buffer} chunk The chunk of data to write
       * @param {String} encoding The character encoding of `chunk`
       * @param {Function} cb Callback
       * @private
       */
      _write(chunk, encoding, cb) {
        if (this._opcode === 8 && this._state == GET_INFO) return cb();
        if (this._maxBufferedChunks > 0 && this._buffers.length >= this._maxBufferedChunks) {
          cb(
            this.createError(
              RangeError,
              "Too many buffered chunks",
              false,
              1008,
              "WS_ERR_TOO_MANY_BUFFERED_PARTS"
            )
          );
          return;
        }
        this._bufferedBytes += chunk.length;
        this._buffers.push(chunk);
        this.startLoop(cb);
      }
      /**
       * Consumes `n` bytes from the buffered data.
       *
       * @param {Number} n The number of bytes to consume
       * @return {Buffer} The consumed bytes
       * @private
       */
      consume(n) {
        this._bufferedBytes -= n;
        if (n === this._buffers[0].length) return this._buffers.shift();
        if (n < this._buffers[0].length) {
          const buf = this._buffers[0];
          this._buffers[0] = new FastBuffer(
            buf.buffer,
            buf.byteOffset + n,
            buf.length - n
          );
          return new FastBuffer(buf.buffer, buf.byteOffset, n);
        }
        const dst = Buffer.allocUnsafe(n);
        do {
          const buf = this._buffers[0];
          const offset = dst.length - n;
          if (n >= buf.length) {
            dst.set(this._buffers.shift(), offset);
          } else {
            dst.set(new Uint8Array(buf.buffer, buf.byteOffset, n), offset);
            this._buffers[0] = new FastBuffer(
              buf.buffer,
              buf.byteOffset + n,
              buf.length - n
            );
          }
          n -= buf.length;
        } while (n > 0);
        return dst;
      }
      /**
       * Starts the parsing loop.
       *
       * @param {Function} cb Callback
       * @private
       */
      startLoop(cb) {
        this._loop = true;
        do {
          switch (this._state) {
            case GET_INFO:
              this.getInfo(cb);
              break;
            case GET_PAYLOAD_LENGTH_16:
              this.getPayloadLength16(cb);
              break;
            case GET_PAYLOAD_LENGTH_64:
              this.getPayloadLength64(cb);
              break;
            case GET_MASK:
              this.getMask();
              break;
            case GET_DATA:
              this.getData(cb);
              break;
            case INFLATING:
            case DEFER_EVENT:
              this._loop = false;
              return;
          }
        } while (this._loop);
        if (!this._errored) cb();
      }
      /**
       * Reads the first two bytes of a frame.
       *
       * @param {Function} cb Callback
       * @private
       */
      getInfo(cb) {
        if (this._bufferedBytes < 2) {
          this._loop = false;
          return;
        }
        const buf = this.consume(2);
        if ((buf[0] & 48) !== 0) {
          const error = this.createError(
            RangeError,
            "RSV2 and RSV3 must be clear",
            true,
            1002,
            "WS_ERR_UNEXPECTED_RSV_2_3"
          );
          cb(error);
          return;
        }
        const compressed = (buf[0] & 64) === 64;
        if (compressed && !this._extensions[PerMessageDeflate2.extensionName]) {
          const error = this.createError(
            RangeError,
            "RSV1 must be clear",
            true,
            1002,
            "WS_ERR_UNEXPECTED_RSV_1"
          );
          cb(error);
          return;
        }
        this._fin = (buf[0] & 128) === 128;
        this._opcode = buf[0] & 15;
        this._payloadLength = buf[1] & 127;
        if (this._opcode === 0) {
          if (compressed) {
            const error = this.createError(
              RangeError,
              "RSV1 must be clear",
              true,
              1002,
              "WS_ERR_UNEXPECTED_RSV_1"
            );
            cb(error);
            return;
          }
          if (!this._fragmented) {
            const error = this.createError(
              RangeError,
              "invalid opcode 0",
              true,
              1002,
              "WS_ERR_INVALID_OPCODE"
            );
            cb(error);
            return;
          }
          this._opcode = this._fragmented;
        } else if (this._opcode === 1 || this._opcode === 2) {
          if (this._fragmented) {
            const error = this.createError(
              RangeError,
              `invalid opcode ${this._opcode}`,
              true,
              1002,
              "WS_ERR_INVALID_OPCODE"
            );
            cb(error);
            return;
          }
          this._compressed = compressed;
        } else if (this._opcode > 7 && this._opcode < 11) {
          if (!this._fin) {
            const error = this.createError(
              RangeError,
              "FIN must be set",
              true,
              1002,
              "WS_ERR_EXPECTED_FIN"
            );
            cb(error);
            return;
          }
          if (compressed) {
            const error = this.createError(
              RangeError,
              "RSV1 must be clear",
              true,
              1002,
              "WS_ERR_UNEXPECTED_RSV_1"
            );
            cb(error);
            return;
          }
          if (this._payloadLength > 125 || this._opcode === 8 && this._payloadLength === 1) {
            const error = this.createError(
              RangeError,
              `invalid payload length ${this._payloadLength}`,
              true,
              1002,
              "WS_ERR_INVALID_CONTROL_PAYLOAD_LENGTH"
            );
            cb(error);
            return;
          }
        } else {
          const error = this.createError(
            RangeError,
            `invalid opcode ${this._opcode}`,
            true,
            1002,
            "WS_ERR_INVALID_OPCODE"
          );
          cb(error);
          return;
        }
        if (!this._fin && !this._fragmented) this._fragmented = this._opcode;
        this._masked = (buf[1] & 128) === 128;
        if (this._isServer) {
          if (!this._masked) {
            const error = this.createError(
              RangeError,
              "MASK must be set",
              true,
              1002,
              "WS_ERR_EXPECTED_MASK"
            );
            cb(error);
            return;
          }
        } else if (this._masked) {
          const error = this.createError(
            RangeError,
            "MASK must be clear",
            true,
            1002,
            "WS_ERR_UNEXPECTED_MASK"
          );
          cb(error);
          return;
        }
        if (this._payloadLength === 126) this._state = GET_PAYLOAD_LENGTH_16;
        else if (this._payloadLength === 127) this._state = GET_PAYLOAD_LENGTH_64;
        else this.haveLength(cb);
      }
      /**
       * Gets extended payload length (7+16).
       *
       * @param {Function} cb Callback
       * @private
       */
      getPayloadLength16(cb) {
        if (this._bufferedBytes < 2) {
          this._loop = false;
          return;
        }
        this._payloadLength = this.consume(2).readUInt16BE(0);
        this.haveLength(cb);
      }
      /**
       * Gets extended payload length (7+64).
       *
       * @param {Function} cb Callback
       * @private
       */
      getPayloadLength64(cb) {
        if (this._bufferedBytes < 8) {
          this._loop = false;
          return;
        }
        const buf = this.consume(8);
        const num = buf.readUInt32BE(0);
        if (num > Math.pow(2, 53 - 32) - 1) {
          const error = this.createError(
            RangeError,
            "Unsupported WebSocket frame: payload length > 2^53 - 1",
            false,
            1009,
            "WS_ERR_UNSUPPORTED_DATA_PAYLOAD_LENGTH"
          );
          cb(error);
          return;
        }
        this._payloadLength = num * Math.pow(2, 32) + buf.readUInt32BE(4);
        this.haveLength(cb);
      }
      /**
       * Payload length has been read.
       *
       * @param {Function} cb Callback
       * @private
       */
      haveLength(cb) {
        if (this._payloadLength && this._opcode < 8) {
          this._totalPayloadLength += this._payloadLength;
          if (this._totalPayloadLength > this._maxPayload && this._maxPayload > 0) {
            const error = this.createError(
              RangeError,
              "Max payload size exceeded",
              false,
              1009,
              "WS_ERR_UNSUPPORTED_MESSAGE_LENGTH"
            );
            cb(error);
            return;
          }
        }
        if (this._masked) this._state = GET_MASK;
        else this._state = GET_DATA;
      }
      /**
       * Reads mask bytes.
       *
       * @private
       */
      getMask() {
        if (this._bufferedBytes < 4) {
          this._loop = false;
          return;
        }
        this._mask = this.consume(4);
        this._state = GET_DATA;
      }
      /**
       * Reads data bytes.
       *
       * @param {Function} cb Callback
       * @private
       */
      getData(cb) {
        let data = EMPTY_BUFFER;
        if (this._payloadLength) {
          if (this._bufferedBytes < this._payloadLength) {
            this._loop = false;
            return;
          }
          data = this.consume(this._payloadLength);
          if (this._masked && (this._mask[0] | this._mask[1] | this._mask[2] | this._mask[3]) !== 0) {
            unmask(data, this._mask);
          }
        }
        if (this._opcode > 7) {
          this.controlMessage(data, cb);
          return;
        }
        if (this._compressed) {
          this._state = INFLATING;
          this.decompress(data, cb);
          return;
        }
        if (data.length) {
          if (this._maxFragments > 0 && this._fragments.length >= this._maxFragments) {
            const error = this.createError(
              RangeError,
              "Too many message fragments",
              false,
              1008,
              "WS_ERR_TOO_MANY_BUFFERED_PARTS"
            );
            cb(error);
            return;
          }
          this._messageLength = this._totalPayloadLength;
          this._fragments.push(data);
        }
        this.dataMessage(cb);
      }
      /**
       * Decompresses data.
       *
       * @param {Buffer} data Compressed data
       * @param {Function} cb Callback
       * @private
       */
      decompress(data, cb) {
        const perMessageDeflate = this._extensions[PerMessageDeflate2.extensionName];
        perMessageDeflate.decompress(data, this._fin, (err, buf) => {
          if (err) return cb(err);
          if (buf.length) {
            this._messageLength += buf.length;
            if (this._messageLength > this._maxPayload && this._maxPayload > 0) {
              const error = this.createError(
                RangeError,
                "Max payload size exceeded",
                false,
                1009,
                "WS_ERR_UNSUPPORTED_MESSAGE_LENGTH"
              );
              cb(error);
              return;
            }
            if (this._maxFragments > 0 && this._fragments.length >= this._maxFragments) {
              const error = this.createError(
                RangeError,
                "Too many message fragments",
                false,
                1008,
                "WS_ERR_TOO_MANY_BUFFERED_PARTS"
              );
              cb(error);
              return;
            }
            this._fragments.push(buf);
          }
          this.dataMessage(cb);
          if (this._state === GET_INFO) this.startLoop(cb);
        });
      }
      /**
       * Handles a data message.
       *
       * @param {Function} cb Callback
       * @private
       */
      dataMessage(cb) {
        if (!this._fin) {
          this._state = GET_INFO;
          return;
        }
        const messageLength = this._messageLength;
        const fragments = this._fragments;
        this._totalPayloadLength = 0;
        this._messageLength = 0;
        this._fragmented = 0;
        this._fragments = [];
        if (this._opcode === 2) {
          let data;
          if (this._binaryType === "nodebuffer") {
            data = concat(fragments, messageLength);
          } else if (this._binaryType === "arraybuffer") {
            data = toArrayBuffer(concat(fragments, messageLength));
          } else if (this._binaryType === "blob") {
            data = new Blob(fragments);
          } else {
            data = fragments;
          }
          if (this._allowSynchronousEvents) {
            this.emit("message", data, true);
            this._state = GET_INFO;
          } else {
            this._state = DEFER_EVENT;
            setImmediate(() => {
              this.emit("message", data, true);
              this._state = GET_INFO;
              this.startLoop(cb);
            });
          }
        } else {
          const buf = concat(fragments, messageLength);
          if (!this._skipUTF8Validation && !isValidUTF8(buf)) {
            const error = this.createError(
              Error,
              "invalid UTF-8 sequence",
              true,
              1007,
              "WS_ERR_INVALID_UTF8"
            );
            cb(error);
            return;
          }
          if (this._state === INFLATING || this._allowSynchronousEvents) {
            this.emit("message", buf, false);
            this._state = GET_INFO;
          } else {
            this._state = DEFER_EVENT;
            setImmediate(() => {
              this.emit("message", buf, false);
              this._state = GET_INFO;
              this.startLoop(cb);
            });
          }
        }
      }
      /**
       * Handles a control message.
       *
       * @param {Buffer} data Data to handle
       * @return {(Error|RangeError|undefined)} A possible error
       * @private
       */
      controlMessage(data, cb) {
        if (this._opcode === 8) {
          if (data.length === 0) {
            this._loop = false;
            this.emit("conclude", 1005, EMPTY_BUFFER);
            this.end();
          } else {
            const code = data.readUInt16BE(0);
            if (!isValidStatusCode(code)) {
              const error = this.createError(
                RangeError,
                `invalid status code ${code}`,
                true,
                1002,
                "WS_ERR_INVALID_CLOSE_CODE"
              );
              cb(error);
              return;
            }
            const buf = new FastBuffer(
              data.buffer,
              data.byteOffset + 2,
              data.length - 2
            );
            if (!this._skipUTF8Validation && !isValidUTF8(buf)) {
              const error = this.createError(
                Error,
                "invalid UTF-8 sequence",
                true,
                1007,
                "WS_ERR_INVALID_UTF8"
              );
              cb(error);
              return;
            }
            this._loop = false;
            this.emit("conclude", code, buf);
            this.end();
          }
          this._state = GET_INFO;
          return;
        }
        if (this._allowSynchronousEvents) {
          this.emit(this._opcode === 9 ? "ping" : "pong", data);
          this._state = GET_INFO;
        } else {
          this._state = DEFER_EVENT;
          setImmediate(() => {
            this.emit(this._opcode === 9 ? "ping" : "pong", data);
            this._state = GET_INFO;
            this.startLoop(cb);
          });
        }
      }
      /**
       * Builds an error object.
       *
       * @param {function(new:Error|RangeError)} ErrorCtor The error constructor
       * @param {String} message The error message
       * @param {Boolean} prefix Specifies whether or not to add a default prefix to
       *     `message`
       * @param {Number} statusCode The status code
       * @param {String} errorCode The exposed error code
       * @return {(Error|RangeError)} The error
       * @private
       */
      createError(ErrorCtor, message, prefix, statusCode, errorCode2) {
        this._loop = false;
        this._errored = true;
        const err = new ErrorCtor(
          prefix ? `Invalid WebSocket frame: ${message}` : message
        );
        Error.captureStackTrace(err, this.createError);
        err.code = errorCode2;
        err[kStatusCode] = statusCode;
        return err;
      }
    };
    module.exports = Receiver2;
  }
});

// node_modules/.pnpm/ws@8.21.0/node_modules/ws/lib/sender.js
var require_sender = __commonJS({
  "node_modules/.pnpm/ws@8.21.0/node_modules/ws/lib/sender.js"(exports, module) {
    "use strict";
    var { Duplex } = __require("stream");
    var { randomFillSync } = __require("crypto");
    var {
      types: { isUint8Array }
    } = __require("util");
    var PerMessageDeflate2 = require_permessage_deflate();
    var { EMPTY_BUFFER, kWebSocket, NOOP } = require_constants();
    var { isBlob, isValidStatusCode } = require_validation();
    var { mask: applyMask, toBuffer } = require_buffer_util();
    var kByteLength = /* @__PURE__ */ Symbol("kByteLength");
    var maskBuffer = Buffer.alloc(4);
    var RANDOM_POOL_SIZE = 8 * 1024;
    var randomPool;
    var randomPoolPointer = RANDOM_POOL_SIZE;
    var DEFAULT = 0;
    var DEFLATING = 1;
    var GET_BLOB_DATA = 2;
    var Sender2 = class _Sender {
      /**
       * Creates a Sender instance.
       *
       * @param {Duplex} socket The connection socket
       * @param {Object} [extensions] An object containing the negotiated extensions
       * @param {Function} [generateMask] The function used to generate the masking
       *     key
       */
      constructor(socket, extensions, generateMask) {
        this._extensions = extensions || {};
        if (generateMask) {
          this._generateMask = generateMask;
          this._maskBuffer = Buffer.alloc(4);
        }
        this._socket = socket;
        this._firstFragment = true;
        this._compress = false;
        this._bufferedBytes = 0;
        this._queue = [];
        this._state = DEFAULT;
        this.onerror = NOOP;
        this[kWebSocket] = void 0;
      }
      /**
       * Frames a piece of data according to the HyBi WebSocket protocol.
       *
       * @param {(Buffer|String)} data The data to frame
       * @param {Object} options Options object
       * @param {Boolean} [options.fin=false] Specifies whether or not to set the
       *     FIN bit
       * @param {Function} [options.generateMask] The function used to generate the
       *     masking key
       * @param {Boolean} [options.mask=false] Specifies whether or not to mask
       *     `data`
       * @param {Buffer} [options.maskBuffer] The buffer used to store the masking
       *     key
       * @param {Number} options.opcode The opcode
       * @param {Boolean} [options.readOnly=false] Specifies whether `data` can be
       *     modified
       * @param {Boolean} [options.rsv1=false] Specifies whether or not to set the
       *     RSV1 bit
       * @return {(Buffer|String)[]} The framed data
       * @public
       */
      static frame(data, options) {
        let mask;
        let merge = false;
        let offset = 2;
        let skipMasking = false;
        if (options.mask) {
          mask = options.maskBuffer || maskBuffer;
          if (options.generateMask) {
            options.generateMask(mask);
          } else {
            if (randomPoolPointer === RANDOM_POOL_SIZE) {
              if (randomPool === void 0) {
                randomPool = Buffer.alloc(RANDOM_POOL_SIZE);
              }
              randomFillSync(randomPool, 0, RANDOM_POOL_SIZE);
              randomPoolPointer = 0;
            }
            mask[0] = randomPool[randomPoolPointer++];
            mask[1] = randomPool[randomPoolPointer++];
            mask[2] = randomPool[randomPoolPointer++];
            mask[3] = randomPool[randomPoolPointer++];
          }
          skipMasking = (mask[0] | mask[1] | mask[2] | mask[3]) === 0;
          offset = 6;
        }
        let dataLength;
        if (typeof data === "string") {
          if ((!options.mask || skipMasking) && options[kByteLength] !== void 0) {
            dataLength = options[kByteLength];
          } else {
            data = Buffer.from(data);
            dataLength = data.length;
          }
        } else {
          dataLength = data.length;
          merge = options.mask && options.readOnly && !skipMasking;
        }
        let payloadLength = dataLength;
        if (dataLength >= 65536) {
          offset += 8;
          payloadLength = 127;
        } else if (dataLength > 125) {
          offset += 2;
          payloadLength = 126;
        }
        const target = Buffer.allocUnsafe(merge ? dataLength + offset : offset);
        target[0] = options.fin ? options.opcode | 128 : options.opcode;
        if (options.rsv1) target[0] |= 64;
        target[1] = payloadLength;
        if (payloadLength === 126) {
          target.writeUInt16BE(dataLength, 2);
        } else if (payloadLength === 127) {
          target[2] = target[3] = 0;
          target.writeUIntBE(dataLength, 4, 6);
        }
        if (!options.mask) return [target, data];
        target[1] |= 128;
        target[offset - 4] = mask[0];
        target[offset - 3] = mask[1];
        target[offset - 2] = mask[2];
        target[offset - 1] = mask[3];
        if (skipMasking) return [target, data];
        if (merge) {
          applyMask(data, mask, target, offset, dataLength);
          return [target];
        }
        applyMask(data, mask, data, 0, dataLength);
        return [target, data];
      }
      /**
       * Sends a close message to the other peer.
       *
       * @param {Number} [code] The status code component of the body
       * @param {(String|Buffer)} [data] The message component of the body
       * @param {Boolean} [mask=false] Specifies whether or not to mask the message
       * @param {Function} [cb] Callback
       * @public
       */
      close(code, data, mask, cb) {
        let buf;
        if (code === void 0) {
          buf = EMPTY_BUFFER;
        } else if (typeof code !== "number" || !isValidStatusCode(code)) {
          throw new TypeError("First argument must be a valid error code number");
        } else if (data === void 0 || !data.length) {
          buf = Buffer.allocUnsafe(2);
          buf.writeUInt16BE(code, 0);
        } else {
          const length = Buffer.byteLength(data);
          if (length > 123) {
            throw new RangeError("The message must not be greater than 123 bytes");
          }
          buf = Buffer.allocUnsafe(2 + length);
          buf.writeUInt16BE(code, 0);
          if (typeof data === "string") {
            buf.write(data, 2);
          } else if (isUint8Array(data)) {
            buf.set(data, 2);
          } else {
            throw new TypeError("Second argument must be a string or a Uint8Array");
          }
        }
        const options = {
          [kByteLength]: buf.length,
          fin: true,
          generateMask: this._generateMask,
          mask,
          maskBuffer: this._maskBuffer,
          opcode: 8,
          readOnly: false,
          rsv1: false
        };
        if (this._state !== DEFAULT) {
          this.enqueue([this.dispatch, buf, false, options, cb]);
        } else {
          this.sendFrame(_Sender.frame(buf, options), cb);
        }
      }
      /**
       * Sends a ping message to the other peer.
       *
       * @param {*} data The message to send
       * @param {Boolean} [mask=false] Specifies whether or not to mask `data`
       * @param {Function} [cb] Callback
       * @public
       */
      ping(data, mask, cb) {
        let byteLength;
        let readOnly;
        if (typeof data === "string") {
          byteLength = Buffer.byteLength(data);
          readOnly = false;
        } else if (isBlob(data)) {
          byteLength = data.size;
          readOnly = false;
        } else {
          data = toBuffer(data);
          byteLength = data.length;
          readOnly = toBuffer.readOnly;
        }
        if (byteLength > 125) {
          throw new RangeError("The data size must not be greater than 125 bytes");
        }
        const options = {
          [kByteLength]: byteLength,
          fin: true,
          generateMask: this._generateMask,
          mask,
          maskBuffer: this._maskBuffer,
          opcode: 9,
          readOnly,
          rsv1: false
        };
        if (isBlob(data)) {
          if (this._state !== DEFAULT) {
            this.enqueue([this.getBlobData, data, false, options, cb]);
          } else {
            this.getBlobData(data, false, options, cb);
          }
        } else if (this._state !== DEFAULT) {
          this.enqueue([this.dispatch, data, false, options, cb]);
        } else {
          this.sendFrame(_Sender.frame(data, options), cb);
        }
      }
      /**
       * Sends a pong message to the other peer.
       *
       * @param {*} data The message to send
       * @param {Boolean} [mask=false] Specifies whether or not to mask `data`
       * @param {Function} [cb] Callback
       * @public
       */
      pong(data, mask, cb) {
        let byteLength;
        let readOnly;
        if (typeof data === "string") {
          byteLength = Buffer.byteLength(data);
          readOnly = false;
        } else if (isBlob(data)) {
          byteLength = data.size;
          readOnly = false;
        } else {
          data = toBuffer(data);
          byteLength = data.length;
          readOnly = toBuffer.readOnly;
        }
        if (byteLength > 125) {
          throw new RangeError("The data size must not be greater than 125 bytes");
        }
        const options = {
          [kByteLength]: byteLength,
          fin: true,
          generateMask: this._generateMask,
          mask,
          maskBuffer: this._maskBuffer,
          opcode: 10,
          readOnly,
          rsv1: false
        };
        if (isBlob(data)) {
          if (this._state !== DEFAULT) {
            this.enqueue([this.getBlobData, data, false, options, cb]);
          } else {
            this.getBlobData(data, false, options, cb);
          }
        } else if (this._state !== DEFAULT) {
          this.enqueue([this.dispatch, data, false, options, cb]);
        } else {
          this.sendFrame(_Sender.frame(data, options), cb);
        }
      }
      /**
       * Sends a data message to the other peer.
       *
       * @param {*} data The message to send
       * @param {Object} options Options object
       * @param {Boolean} [options.binary=false] Specifies whether `data` is binary
       *     or text
       * @param {Boolean} [options.compress=false] Specifies whether or not to
       *     compress `data`
       * @param {Boolean} [options.fin=false] Specifies whether the fragment is the
       *     last one
       * @param {Boolean} [options.mask=false] Specifies whether or not to mask
       *     `data`
       * @param {Function} [cb] Callback
       * @public
       */
      send(data, options, cb) {
        const perMessageDeflate = this._extensions[PerMessageDeflate2.extensionName];
        let opcode = options.binary ? 2 : 1;
        let rsv1 = options.compress;
        let byteLength;
        let readOnly;
        if (typeof data === "string") {
          byteLength = Buffer.byteLength(data);
          readOnly = false;
        } else if (isBlob(data)) {
          byteLength = data.size;
          readOnly = false;
        } else {
          data = toBuffer(data);
          byteLength = data.length;
          readOnly = toBuffer.readOnly;
        }
        if (this._firstFragment) {
          this._firstFragment = false;
          if (rsv1 && perMessageDeflate && perMessageDeflate.params[perMessageDeflate._isServer ? "server_no_context_takeover" : "client_no_context_takeover"]) {
            rsv1 = byteLength >= perMessageDeflate._threshold;
          }
          this._compress = rsv1;
        } else {
          rsv1 = false;
          opcode = 0;
        }
        if (options.fin) this._firstFragment = true;
        const opts = {
          [kByteLength]: byteLength,
          fin: options.fin,
          generateMask: this._generateMask,
          mask: options.mask,
          maskBuffer: this._maskBuffer,
          opcode,
          readOnly,
          rsv1
        };
        if (isBlob(data)) {
          if (this._state !== DEFAULT) {
            this.enqueue([this.getBlobData, data, this._compress, opts, cb]);
          } else {
            this.getBlobData(data, this._compress, opts, cb);
          }
        } else if (this._state !== DEFAULT) {
          this.enqueue([this.dispatch, data, this._compress, opts, cb]);
        } else {
          this.dispatch(data, this._compress, opts, cb);
        }
      }
      /**
       * Gets the contents of a blob as binary data.
       *
       * @param {Blob} blob The blob
       * @param {Boolean} [compress=false] Specifies whether or not to compress
       *     the data
       * @param {Object} options Options object
       * @param {Boolean} [options.fin=false] Specifies whether or not to set the
       *     FIN bit
       * @param {Function} [options.generateMask] The function used to generate the
       *     masking key
       * @param {Boolean} [options.mask=false] Specifies whether or not to mask
       *     `data`
       * @param {Buffer} [options.maskBuffer] The buffer used to store the masking
       *     key
       * @param {Number} options.opcode The opcode
       * @param {Boolean} [options.readOnly=false] Specifies whether `data` can be
       *     modified
       * @param {Boolean} [options.rsv1=false] Specifies whether or not to set the
       *     RSV1 bit
       * @param {Function} [cb] Callback
       * @private
       */
      getBlobData(blob, compress, options, cb) {
        this._bufferedBytes += options[kByteLength];
        this._state = GET_BLOB_DATA;
        blob.arrayBuffer().then((arrayBuffer) => {
          if (this._socket.destroyed) {
            const err = new Error(
              "The socket was closed while the blob was being read"
            );
            process.nextTick(callCallbacks, this, err, cb);
            return;
          }
          this._bufferedBytes -= options[kByteLength];
          const data = toBuffer(arrayBuffer);
          if (!compress) {
            this._state = DEFAULT;
            this.sendFrame(_Sender.frame(data, options), cb);
            this.dequeue();
          } else {
            this.dispatch(data, compress, options, cb);
          }
        }).catch((err) => {
          process.nextTick(onError, this, err, cb);
        });
      }
      /**
       * Dispatches a message.
       *
       * @param {(Buffer|String)} data The message to send
       * @param {Boolean} [compress=false] Specifies whether or not to compress
       *     `data`
       * @param {Object} options Options object
       * @param {Boolean} [options.fin=false] Specifies whether or not to set the
       *     FIN bit
       * @param {Function} [options.generateMask] The function used to generate the
       *     masking key
       * @param {Boolean} [options.mask=false] Specifies whether or not to mask
       *     `data`
       * @param {Buffer} [options.maskBuffer] The buffer used to store the masking
       *     key
       * @param {Number} options.opcode The opcode
       * @param {Boolean} [options.readOnly=false] Specifies whether `data` can be
       *     modified
       * @param {Boolean} [options.rsv1=false] Specifies whether or not to set the
       *     RSV1 bit
       * @param {Function} [cb] Callback
       * @private
       */
      dispatch(data, compress, options, cb) {
        if (!compress) {
          this.sendFrame(_Sender.frame(data, options), cb);
          return;
        }
        const perMessageDeflate = this._extensions[PerMessageDeflate2.extensionName];
        this._bufferedBytes += options[kByteLength];
        this._state = DEFLATING;
        perMessageDeflate.compress(data, options.fin, (_3, buf) => {
          if (this._socket.destroyed) {
            const err = new Error(
              "The socket was closed while data was being compressed"
            );
            callCallbacks(this, err, cb);
            return;
          }
          this._bufferedBytes -= options[kByteLength];
          this._state = DEFAULT;
          options.readOnly = false;
          this.sendFrame(_Sender.frame(buf, options), cb);
          this.dequeue();
        });
      }
      /**
       * Executes queued send operations.
       *
       * @private
       */
      dequeue() {
        while (this._state === DEFAULT && this._queue.length) {
          const params = this._queue.shift();
          this._bufferedBytes -= params[3][kByteLength];
          Reflect.apply(params[0], this, params.slice(1));
        }
      }
      /**
       * Enqueues a send operation.
       *
       * @param {Array} params Send operation parameters.
       * @private
       */
      enqueue(params) {
        this._bufferedBytes += params[3][kByteLength];
        this._queue.push(params);
      }
      /**
       * Sends a frame.
       *
       * @param {(Buffer | String)[]} list The frame to send
       * @param {Function} [cb] Callback
       * @private
       */
      sendFrame(list, cb) {
        if (list.length === 2) {
          this._socket.cork();
          this._socket.write(list[0]);
          this._socket.write(list[1], cb);
          this._socket.uncork();
        } else {
          this._socket.write(list[0], cb);
        }
      }
    };
    module.exports = Sender2;
    function callCallbacks(sender, err, cb) {
      if (typeof cb === "function") cb(err);
      for (let i = 0; i < sender._queue.length; i++) {
        const params = sender._queue[i];
        const callback = params[params.length - 1];
        if (typeof callback === "function") callback(err);
      }
    }
    function onError(sender, err, cb) {
      callCallbacks(sender, err, cb);
      sender.onerror(err);
    }
  }
});

// node_modules/.pnpm/ws@8.21.0/node_modules/ws/lib/event-target.js
var require_event_target = __commonJS({
  "node_modules/.pnpm/ws@8.21.0/node_modules/ws/lib/event-target.js"(exports, module) {
    "use strict";
    var { kForOnEventAttribute, kListener } = require_constants();
    var kCode = /* @__PURE__ */ Symbol("kCode");
    var kData = /* @__PURE__ */ Symbol("kData");
    var kError = /* @__PURE__ */ Symbol("kError");
    var kMessage = /* @__PURE__ */ Symbol("kMessage");
    var kReason = /* @__PURE__ */ Symbol("kReason");
    var kTarget = /* @__PURE__ */ Symbol("kTarget");
    var kType = /* @__PURE__ */ Symbol("kType");
    var kWasClean = /* @__PURE__ */ Symbol("kWasClean");
    var Event = class {
      /**
       * Create a new `Event`.
       *
       * @param {String} type The name of the event
       * @throws {TypeError} If the `type` argument is not specified
       */
      constructor(type) {
        this[kTarget] = null;
        this[kType] = type;
      }
      /**
       * @type {*}
       */
      get target() {
        return this[kTarget];
      }
      /**
       * @type {String}
       */
      get type() {
        return this[kType];
      }
    };
    Object.defineProperty(Event.prototype, "target", { enumerable: true });
    Object.defineProperty(Event.prototype, "type", { enumerable: true });
    var CloseEvent = class extends Event {
      /**
       * Create a new `CloseEvent`.
       *
       * @param {String} type The name of the event
       * @param {Object} [options] A dictionary object that allows for setting
       *     attributes via object members of the same name
       * @param {Number} [options.code=0] The status code explaining why the
       *     connection was closed
       * @param {String} [options.reason=''] A human-readable string explaining why
       *     the connection was closed
       * @param {Boolean} [options.wasClean=false] Indicates whether or not the
       *     connection was cleanly closed
       */
      constructor(type, options = {}) {
        super(type);
        this[kCode] = options.code === void 0 ? 0 : options.code;
        this[kReason] = options.reason === void 0 ? "" : options.reason;
        this[kWasClean] = options.wasClean === void 0 ? false : options.wasClean;
      }
      /**
       * @type {Number}
       */
      get code() {
        return this[kCode];
      }
      /**
       * @type {String}
       */
      get reason() {
        return this[kReason];
      }
      /**
       * @type {Boolean}
       */
      get wasClean() {
        return this[kWasClean];
      }
    };
    Object.defineProperty(CloseEvent.prototype, "code", { enumerable: true });
    Object.defineProperty(CloseEvent.prototype, "reason", { enumerable: true });
    Object.defineProperty(CloseEvent.prototype, "wasClean", { enumerable: true });
    var ErrorEvent = class extends Event {
      /**
       * Create a new `ErrorEvent`.
       *
       * @param {String} type The name of the event
       * @param {Object} [options] A dictionary object that allows for setting
       *     attributes via object members of the same name
       * @param {*} [options.error=null] The error that generated this event
       * @param {String} [options.message=''] The error message
       */
      constructor(type, options = {}) {
        super(type);
        this[kError] = options.error === void 0 ? null : options.error;
        this[kMessage] = options.message === void 0 ? "" : options.message;
      }
      /**
       * @type {*}
       */
      get error() {
        return this[kError];
      }
      /**
       * @type {String}
       */
      get message() {
        return this[kMessage];
      }
    };
    Object.defineProperty(ErrorEvent.prototype, "error", { enumerable: true });
    Object.defineProperty(ErrorEvent.prototype, "message", { enumerable: true });
    var MessageEvent = class extends Event {
      /**
       * Create a new `MessageEvent`.
       *
       * @param {String} type The name of the event
       * @param {Object} [options] A dictionary object that allows for setting
       *     attributes via object members of the same name
       * @param {*} [options.data=null] The message content
       */
      constructor(type, options = {}) {
        super(type);
        this[kData] = options.data === void 0 ? null : options.data;
      }
      /**
       * @type {*}
       */
      get data() {
        return this[kData];
      }
    };
    Object.defineProperty(MessageEvent.prototype, "data", { enumerable: true });
    var EventTarget = {
      /**
       * Register an event listener.
       *
       * @param {String} type A string representing the event type to listen for
       * @param {(Function|Object)} handler The listener to add
       * @param {Object} [options] An options object specifies characteristics about
       *     the event listener
       * @param {Boolean} [options.once=false] A `Boolean` indicating that the
       *     listener should be invoked at most once after being added. If `true`,
       *     the listener would be automatically removed when invoked.
       * @public
       */
      addEventListener(type, handler, options = {}) {
        for (const listener of this.listeners(type)) {
          if (!options[kForOnEventAttribute] && listener[kListener] === handler && !listener[kForOnEventAttribute]) {
            return;
          }
        }
        let wrapper;
        if (type === "message") {
          wrapper = function onMessage(data, isBinary) {
            const event = new MessageEvent("message", {
              data: isBinary ? data : data.toString()
            });
            event[kTarget] = this;
            callListener(handler, this, event);
          };
        } else if (type === "close") {
          wrapper = function onClose(code, message) {
            const event = new CloseEvent("close", {
              code,
              reason: message.toString(),
              wasClean: this._closeFrameReceived && this._closeFrameSent
            });
            event[kTarget] = this;
            callListener(handler, this, event);
          };
        } else if (type === "error") {
          wrapper = function onError(error) {
            const event = new ErrorEvent("error", {
              error,
              message: error.message
            });
            event[kTarget] = this;
            callListener(handler, this, event);
          };
        } else if (type === "open") {
          wrapper = function onOpen() {
            const event = new Event("open");
            event[kTarget] = this;
            callListener(handler, this, event);
          };
        } else {
          return;
        }
        wrapper[kForOnEventAttribute] = !!options[kForOnEventAttribute];
        wrapper[kListener] = handler;
        if (options.once) {
          this.once(type, wrapper);
        } else {
          this.on(type, wrapper);
        }
      },
      /**
       * Remove an event listener.
       *
       * @param {String} type A string representing the event type to remove
       * @param {(Function|Object)} handler The listener to remove
       * @public
       */
      removeEventListener(type, handler) {
        for (const listener of this.listeners(type)) {
          if (listener[kListener] === handler && !listener[kForOnEventAttribute]) {
            this.removeListener(type, listener);
            break;
          }
        }
      }
    };
    module.exports = {
      CloseEvent,
      ErrorEvent,
      Event,
      EventTarget,
      MessageEvent
    };
    function callListener(listener, thisArg, event) {
      if (typeof listener === "object" && listener.handleEvent) {
        listener.handleEvent.call(listener, event);
      } else {
        listener.call(thisArg, event);
      }
    }
  }
});

// node_modules/.pnpm/ws@8.21.0/node_modules/ws/lib/extension.js
var require_extension = __commonJS({
  "node_modules/.pnpm/ws@8.21.0/node_modules/ws/lib/extension.js"(exports, module) {
    "use strict";
    var { tokenChars } = require_validation();
    function push(dest, name, elem) {
      if (dest[name] === void 0) dest[name] = [elem];
      else dest[name].push(elem);
    }
    function parse3(header) {
      const offers = /* @__PURE__ */ Object.create(null);
      let params = /* @__PURE__ */ Object.create(null);
      let mustUnescape = false;
      let isEscaping = false;
      let inQuotes = false;
      let extensionName;
      let paramName;
      let start = -1;
      let code = -1;
      let end = -1;
      let i = 0;
      for (; i < header.length; i++) {
        code = header.charCodeAt(i);
        if (extensionName === void 0) {
          if (end === -1 && tokenChars[code] === 1) {
            if (start === -1) start = i;
          } else if (i !== 0 && (code === 32 || code === 9)) {
            if (end === -1 && start !== -1) end = i;
          } else if (code === 59 || code === 44) {
            if (start === -1) {
              throw new SyntaxError(`Unexpected character at index ${i}`);
            }
            if (end === -1) end = i;
            const name = header.slice(start, end);
            if (code === 44) {
              push(offers, name, params);
              params = /* @__PURE__ */ Object.create(null);
            } else {
              extensionName = name;
            }
            start = end = -1;
          } else {
            throw new SyntaxError(`Unexpected character at index ${i}`);
          }
        } else if (paramName === void 0) {
          if (end === -1 && tokenChars[code] === 1) {
            if (start === -1) start = i;
          } else if (code === 32 || code === 9) {
            if (end === -1 && start !== -1) end = i;
          } else if (code === 59 || code === 44) {
            if (start === -1) {
              throw new SyntaxError(`Unexpected character at index ${i}`);
            }
            if (end === -1) end = i;
            push(params, header.slice(start, end), true);
            if (code === 44) {
              push(offers, extensionName, params);
              params = /* @__PURE__ */ Object.create(null);
              extensionName = void 0;
            }
            start = end = -1;
          } else if (code === 61 && start !== -1 && end === -1) {
            paramName = header.slice(start, i);
            start = end = -1;
          } else {
            throw new SyntaxError(`Unexpected character at index ${i}`);
          }
        } else {
          if (isEscaping) {
            if (tokenChars[code] !== 1) {
              throw new SyntaxError(`Unexpected character at index ${i}`);
            }
            if (start === -1) start = i;
            else if (!mustUnescape) mustUnescape = true;
            isEscaping = false;
          } else if (inQuotes) {
            if (tokenChars[code] === 1) {
              if (start === -1) start = i;
            } else if (code === 34 && start !== -1) {
              inQuotes = false;
              end = i;
            } else if (code === 92) {
              isEscaping = true;
            } else {
              throw new SyntaxError(`Unexpected character at index ${i}`);
            }
          } else if (code === 34 && header.charCodeAt(i - 1) === 61) {
            inQuotes = true;
          } else if (end === -1 && tokenChars[code] === 1) {
            if (start === -1) start = i;
          } else if (start !== -1 && (code === 32 || code === 9)) {
            if (end === -1) end = i;
          } else if (code === 59 || code === 44) {
            if (start === -1) {
              throw new SyntaxError(`Unexpected character at index ${i}`);
            }
            if (end === -1) end = i;
            let value = header.slice(start, end);
            if (mustUnescape) {
              value = value.replace(/\\/g, "");
              mustUnescape = false;
            }
            push(params, paramName, value);
            if (code === 44) {
              push(offers, extensionName, params);
              params = /* @__PURE__ */ Object.create(null);
              extensionName = void 0;
            }
            paramName = void 0;
            start = end = -1;
          } else {
            throw new SyntaxError(`Unexpected character at index ${i}`);
          }
        }
      }
      if (start === -1 || inQuotes || code === 32 || code === 9) {
        throw new SyntaxError("Unexpected end of input");
      }
      if (end === -1) end = i;
      const token = header.slice(start, end);
      if (extensionName === void 0) {
        push(offers, token, params);
      } else {
        if (paramName === void 0) {
          push(params, token, true);
        } else if (mustUnescape) {
          push(params, paramName, token.replace(/\\/g, ""));
        } else {
          push(params, paramName, token);
        }
        push(offers, extensionName, params);
      }
      return offers;
    }
    function format(extensions) {
      return Object.keys(extensions).map((extension3) => {
        let configurations = extensions[extension3];
        if (!Array.isArray(configurations)) configurations = [configurations];
        return configurations.map((params) => {
          return [extension3].concat(
            Object.keys(params).map((k2) => {
              let values = params[k2];
              if (!Array.isArray(values)) values = [values];
              return values.map((v) => v === true ? k2 : `${k2}=${v}`).join("; ");
            })
          ).join("; ");
        }).join(", ");
      }).join(", ");
    }
    module.exports = { format, parse: parse3 };
  }
});

// node_modules/.pnpm/ws@8.21.0/node_modules/ws/lib/websocket.js
var require_websocket = __commonJS({
  "node_modules/.pnpm/ws@8.21.0/node_modules/ws/lib/websocket.js"(exports, module) {
    "use strict";
    var EventEmitter = __require("events");
    var https = __require("https");
    var http = __require("http");
    var net = __require("net");
    var tls = __require("tls");
    var { randomBytes: randomBytes2, createHash: createHash10 } = __require("crypto");
    var { Duplex, Readable } = __require("stream");
    var { URL: URL2 } = __require("url");
    var PerMessageDeflate2 = require_permessage_deflate();
    var Receiver2 = require_receiver();
    var Sender2 = require_sender();
    var { isBlob } = require_validation();
    var {
      BINARY_TYPES,
      CLOSE_TIMEOUT,
      EMPTY_BUFFER,
      GUID,
      kForOnEventAttribute,
      kListener,
      kStatusCode,
      kWebSocket,
      NOOP
    } = require_constants();
    var {
      EventTarget: { addEventListener, removeEventListener }
    } = require_event_target();
    var { format, parse: parse3 } = require_extension();
    var { toBuffer } = require_buffer_util();
    var kAborted = /* @__PURE__ */ Symbol("kAborted");
    var protocolVersions = [8, 13];
    var readyStates = ["CONNECTING", "OPEN", "CLOSING", "CLOSED"];
    var subprotocolRegex = /^[!#$%&'*+\-.0-9A-Z^_`|a-z~]+$/;
    var WebSocket2 = class _WebSocket extends EventEmitter {
      /**
       * Create a new `WebSocket`.
       *
       * @param {(String|URL)} address The URL to which to connect
       * @param {(String|String[])} [protocols] The subprotocols
       * @param {Object} [options] Connection options
       */
      constructor(address, protocols, options) {
        super();
        this._binaryType = BINARY_TYPES[0];
        this._closeCode = 1006;
        this._closeFrameReceived = false;
        this._closeFrameSent = false;
        this._closeMessage = EMPTY_BUFFER;
        this._closeTimer = null;
        this._errorEmitted = false;
        this._extensions = {};
        this._paused = false;
        this._protocol = "";
        this._readyState = _WebSocket.CONNECTING;
        this._receiver = null;
        this._sender = null;
        this._socket = null;
        if (address !== null) {
          this._bufferedAmount = 0;
          this._isServer = false;
          this._redirects = 0;
          if (protocols === void 0) {
            protocols = [];
          } else if (!Array.isArray(protocols)) {
            if (typeof protocols === "object" && protocols !== null) {
              options = protocols;
              protocols = [];
            } else {
              protocols = [protocols];
            }
          }
          initAsClient(this, address, protocols, options);
        } else {
          this._autoPong = options.autoPong;
          this._closeTimeout = options.closeTimeout;
          this._isServer = true;
        }
      }
      /**
       * For historical reasons, the custom "nodebuffer" type is used by the default
       * instead of "blob".
       *
       * @type {String}
       */
      get binaryType() {
        return this._binaryType;
      }
      set binaryType(type) {
        if (!BINARY_TYPES.includes(type)) return;
        this._binaryType = type;
        if (this._receiver) this._receiver._binaryType = type;
      }
      /**
       * @type {Number}
       */
      get bufferedAmount() {
        if (!this._socket) return this._bufferedAmount;
        return this._socket._writableState.length + this._sender._bufferedBytes;
      }
      /**
       * @type {String}
       */
      get extensions() {
        return Object.keys(this._extensions).join();
      }
      /**
       * @type {Boolean}
       */
      get isPaused() {
        return this._paused;
      }
      /**
       * @type {Function}
       */
      /* istanbul ignore next */
      get onclose() {
        return null;
      }
      /**
       * @type {Function}
       */
      /* istanbul ignore next */
      get onerror() {
        return null;
      }
      /**
       * @type {Function}
       */
      /* istanbul ignore next */
      get onopen() {
        return null;
      }
      /**
       * @type {Function}
       */
      /* istanbul ignore next */
      get onmessage() {
        return null;
      }
      /**
       * @type {String}
       */
      get protocol() {
        return this._protocol;
      }
      /**
       * @type {Number}
       */
      get readyState() {
        return this._readyState;
      }
      /**
       * @type {String}
       */
      get url() {
        return this._url;
      }
      /**
       * Set up the socket and the internal resources.
       *
       * @param {Duplex} socket The network socket between the server and client
       * @param {Buffer} head The first packet of the upgraded stream
       * @param {Object} options Options object
       * @param {Boolean} [options.allowSynchronousEvents=false] Specifies whether
       *     any of the `'message'`, `'ping'`, and `'pong'` events can be emitted
       *     multiple times in the same tick
       * @param {Function} [options.generateMask] The function used to generate the
       *     masking key
       * @param {Number} [options.maxBufferedChunks=0] The maximum number of
       *     buffered data chunks
       * @param {Number} [options.maxFragments=0] The maximum number of message
       *     fragments
       * @param {Number} [options.maxPayload=0] The maximum allowed message size
       * @param {Boolean} [options.skipUTF8Validation=false] Specifies whether or
       *     not to skip UTF-8 validation for text and close messages
       * @private
       */
      setSocket(socket, head, options) {
        const receiver = new Receiver2({
          allowSynchronousEvents: options.allowSynchronousEvents,
          binaryType: this.binaryType,
          extensions: this._extensions,
          isServer: this._isServer,
          maxBufferedChunks: options.maxBufferedChunks,
          maxFragments: options.maxFragments,
          maxPayload: options.maxPayload,
          skipUTF8Validation: options.skipUTF8Validation
        });
        const sender = new Sender2(socket, this._extensions, options.generateMask);
        this._receiver = receiver;
        this._sender = sender;
        this._socket = socket;
        receiver[kWebSocket] = this;
        sender[kWebSocket] = this;
        socket[kWebSocket] = this;
        receiver.on("conclude", receiverOnConclude);
        receiver.on("drain", receiverOnDrain);
        receiver.on("error", receiverOnError);
        receiver.on("message", receiverOnMessage);
        receiver.on("ping", receiverOnPing);
        receiver.on("pong", receiverOnPong);
        sender.onerror = senderOnError;
        if (socket.setTimeout) socket.setTimeout(0);
        if (socket.setNoDelay) socket.setNoDelay();
        if (head.length > 0) socket.unshift(head);
        socket.on("close", socketOnClose);
        socket.on("data", socketOnData);
        socket.on("end", socketOnEnd);
        socket.on("error", socketOnError);
        this._readyState = _WebSocket.OPEN;
        this.emit("open");
      }
      /**
       * Emit the `'close'` event.
       *
       * @private
       */
      emitClose() {
        if (!this._socket) {
          this._readyState = _WebSocket.CLOSED;
          this.emit("close", this._closeCode, this._closeMessage);
          return;
        }
        if (this._extensions[PerMessageDeflate2.extensionName]) {
          this._extensions[PerMessageDeflate2.extensionName].cleanup();
        }
        this._receiver.removeAllListeners();
        this._readyState = _WebSocket.CLOSED;
        this.emit("close", this._closeCode, this._closeMessage);
      }
      /**
       * Start a closing handshake.
       *
       *          +----------+   +-----------+   +----------+
       *     - - -|ws.close()|-->|close frame|-->|ws.close()|- - -
       *    |     +----------+   +-----------+   +----------+     |
       *          +----------+   +-----------+         |
       * CLOSING  |ws.close()|<--|close frame|<--+-----+       CLOSING
       *          +----------+   +-----------+   |
       *    |           |                        |   +---+        |
       *                +------------------------+-->|fin| - - - -
       *    |         +---+                      |   +---+
       *     - - - - -|fin|<---------------------+
       *              +---+
       *
       * @param {Number} [code] Status code explaining why the connection is closing
       * @param {(String|Buffer)} [data] The reason why the connection is
       *     closing
       * @public
       */
      close(code, data) {
        if (this.readyState === _WebSocket.CLOSED) return;
        if (this.readyState === _WebSocket.CONNECTING) {
          const msg = "WebSocket was closed before the connection was established";
          abortHandshake(this, this._req, msg);
          return;
        }
        if (this.readyState === _WebSocket.CLOSING) {
          if (this._closeFrameSent && (this._closeFrameReceived || this._receiver._writableState.errorEmitted)) {
            this._socket.end();
          }
          return;
        }
        this._readyState = _WebSocket.CLOSING;
        this._sender.close(code, data, !this._isServer, (err) => {
          if (err) return;
          this._closeFrameSent = true;
          if (this._closeFrameReceived || this._receiver._writableState.errorEmitted) {
            this._socket.end();
          }
        });
        setCloseTimer(this);
      }
      /**
       * Pause the socket.
       *
       * @public
       */
      pause() {
        if (this.readyState === _WebSocket.CONNECTING || this.readyState === _WebSocket.CLOSED) {
          return;
        }
        this._paused = true;
        this._socket.pause();
      }
      /**
       * Send a ping.
       *
       * @param {*} [data] The data to send
       * @param {Boolean} [mask] Indicates whether or not to mask `data`
       * @param {Function} [cb] Callback which is executed when the ping is sent
       * @public
       */
      ping(data, mask, cb) {
        if (this.readyState === _WebSocket.CONNECTING) {
          throw new Error("WebSocket is not open: readyState 0 (CONNECTING)");
        }
        if (typeof data === "function") {
          cb = data;
          data = mask = void 0;
        } else if (typeof mask === "function") {
          cb = mask;
          mask = void 0;
        }
        if (typeof data === "number") data = data.toString();
        if (this.readyState !== _WebSocket.OPEN) {
          sendAfterClose(this, data, cb);
          return;
        }
        if (mask === void 0) mask = !this._isServer;
        this._sender.ping(data || EMPTY_BUFFER, mask, cb);
      }
      /**
       * Send a pong.
       *
       * @param {*} [data] The data to send
       * @param {Boolean} [mask] Indicates whether or not to mask `data`
       * @param {Function} [cb] Callback which is executed when the pong is sent
       * @public
       */
      pong(data, mask, cb) {
        if (this.readyState === _WebSocket.CONNECTING) {
          throw new Error("WebSocket is not open: readyState 0 (CONNECTING)");
        }
        if (typeof data === "function") {
          cb = data;
          data = mask = void 0;
        } else if (typeof mask === "function") {
          cb = mask;
          mask = void 0;
        }
        if (typeof data === "number") data = data.toString();
        if (this.readyState !== _WebSocket.OPEN) {
          sendAfterClose(this, data, cb);
          return;
        }
        if (mask === void 0) mask = !this._isServer;
        this._sender.pong(data || EMPTY_BUFFER, mask, cb);
      }
      /**
       * Resume the socket.
       *
       * @public
       */
      resume() {
        if (this.readyState === _WebSocket.CONNECTING || this.readyState === _WebSocket.CLOSED) {
          return;
        }
        this._paused = false;
        if (!this._receiver._writableState.needDrain) this._socket.resume();
      }
      /**
       * Send a data message.
       *
       * @param {*} data The message to send
       * @param {Object} [options] Options object
       * @param {Boolean} [options.binary] Specifies whether `data` is binary or
       *     text
       * @param {Boolean} [options.compress] Specifies whether or not to compress
       *     `data`
       * @param {Boolean} [options.fin=true] Specifies whether the fragment is the
       *     last one
       * @param {Boolean} [options.mask] Specifies whether or not to mask `data`
       * @param {Function} [cb] Callback which is executed when data is written out
       * @public
       */
      send(data, options, cb) {
        if (this.readyState === _WebSocket.CONNECTING) {
          throw new Error("WebSocket is not open: readyState 0 (CONNECTING)");
        }
        if (typeof options === "function") {
          cb = options;
          options = {};
        }
        if (typeof data === "number") data = data.toString();
        if (this.readyState !== _WebSocket.OPEN) {
          sendAfterClose(this, data, cb);
          return;
        }
        const opts = {
          binary: typeof data !== "string",
          mask: !this._isServer,
          compress: true,
          fin: true,
          ...options
        };
        if (!this._extensions[PerMessageDeflate2.extensionName]) {
          opts.compress = false;
        }
        this._sender.send(data || EMPTY_BUFFER, opts, cb);
      }
      /**
       * Forcibly close the connection.
       *
       * @public
       */
      terminate() {
        if (this.readyState === _WebSocket.CLOSED) return;
        if (this.readyState === _WebSocket.CONNECTING) {
          const msg = "WebSocket was closed before the connection was established";
          abortHandshake(this, this._req, msg);
          return;
        }
        if (this._socket) {
          this._readyState = _WebSocket.CLOSING;
          this._socket.destroy();
        }
      }
    };
    Object.defineProperty(WebSocket2, "CONNECTING", {
      enumerable: true,
      value: readyStates.indexOf("CONNECTING")
    });
    Object.defineProperty(WebSocket2.prototype, "CONNECTING", {
      enumerable: true,
      value: readyStates.indexOf("CONNECTING")
    });
    Object.defineProperty(WebSocket2, "OPEN", {
      enumerable: true,
      value: readyStates.indexOf("OPEN")
    });
    Object.defineProperty(WebSocket2.prototype, "OPEN", {
      enumerable: true,
      value: readyStates.indexOf("OPEN")
    });
    Object.defineProperty(WebSocket2, "CLOSING", {
      enumerable: true,
      value: readyStates.indexOf("CLOSING")
    });
    Object.defineProperty(WebSocket2.prototype, "CLOSING", {
      enumerable: true,
      value: readyStates.indexOf("CLOSING")
    });
    Object.defineProperty(WebSocket2, "CLOSED", {
      enumerable: true,
      value: readyStates.indexOf("CLOSED")
    });
    Object.defineProperty(WebSocket2.prototype, "CLOSED", {
      enumerable: true,
      value: readyStates.indexOf("CLOSED")
    });
    [
      "binaryType",
      "bufferedAmount",
      "extensions",
      "isPaused",
      "protocol",
      "readyState",
      "url"
    ].forEach((property) => {
      Object.defineProperty(WebSocket2.prototype, property, { enumerable: true });
    });
    ["open", "error", "close", "message"].forEach((method) => {
      Object.defineProperty(WebSocket2.prototype, `on${method}`, {
        enumerable: true,
        get() {
          for (const listener of this.listeners(method)) {
            if (listener[kForOnEventAttribute]) return listener[kListener];
          }
          return null;
        },
        set(handler) {
          for (const listener of this.listeners(method)) {
            if (listener[kForOnEventAttribute]) {
              this.removeListener(method, listener);
              break;
            }
          }
          if (typeof handler !== "function") return;
          this.addEventListener(method, handler, {
            [kForOnEventAttribute]: true
          });
        }
      });
    });
    WebSocket2.prototype.addEventListener = addEventListener;
    WebSocket2.prototype.removeEventListener = removeEventListener;
    module.exports = WebSocket2;
    function initAsClient(websocket, address, protocols, options) {
      const opts = {
        allowSynchronousEvents: true,
        autoPong: true,
        closeTimeout: CLOSE_TIMEOUT,
        protocolVersion: protocolVersions[1],
        maxBufferedChunks: 1024 * 1024,
        maxFragments: 128 * 1024,
        maxPayload: 100 * 1024 * 1024,
        skipUTF8Validation: false,
        perMessageDeflate: true,
        followRedirects: false,
        maxRedirects: 10,
        ...options,
        socketPath: void 0,
        hostname: void 0,
        protocol: void 0,
        timeout: void 0,
        method: "GET",
        host: void 0,
        path: void 0,
        port: void 0
      };
      websocket._autoPong = opts.autoPong;
      websocket._closeTimeout = opts.closeTimeout;
      if (!protocolVersions.includes(opts.protocolVersion)) {
        throw new RangeError(
          `Unsupported protocol version: ${opts.protocolVersion} (supported versions: ${protocolVersions.join(", ")})`
        );
      }
      let parsedUrl;
      if (address instanceof URL2) {
        parsedUrl = address;
      } else {
        try {
          parsedUrl = new URL2(address);
        } catch {
          throw new SyntaxError(`Invalid URL: ${address}`);
        }
      }
      if (parsedUrl.protocol === "http:") {
        parsedUrl.protocol = "ws:";
      } else if (parsedUrl.protocol === "https:") {
        parsedUrl.protocol = "wss:";
      }
      websocket._url = parsedUrl.href;
      const isSecure = parsedUrl.protocol === "wss:";
      const isIpcUrl = parsedUrl.protocol === "ws+unix:";
      let invalidUrlMessage;
      if (parsedUrl.protocol !== "ws:" && !isSecure && !isIpcUrl) {
        invalidUrlMessage = `The URL's protocol must be one of "ws:", "wss:", "http:", "https:", or "ws+unix:"`;
      } else if (isIpcUrl && !parsedUrl.pathname) {
        invalidUrlMessage = "The URL's pathname is empty";
      } else if (parsedUrl.hash) {
        invalidUrlMessage = "The URL contains a fragment identifier";
      }
      if (invalidUrlMessage) {
        const err = new SyntaxError(invalidUrlMessage);
        if (websocket._redirects === 0) {
          throw err;
        } else {
          emitErrorAndClose(websocket, err);
          return;
        }
      }
      const defaultPort = isSecure ? 443 : 80;
      const key = randomBytes2(16).toString("base64");
      const request = isSecure ? https.request : http.request;
      const protocolSet = /* @__PURE__ */ new Set();
      let perMessageDeflate;
      opts.createConnection = opts.createConnection || (isSecure ? tlsConnect : netConnect);
      opts.defaultPort = opts.defaultPort || defaultPort;
      opts.port = parsedUrl.port || defaultPort;
      opts.host = parsedUrl.hostname.startsWith("[") ? parsedUrl.hostname.slice(1, -1) : parsedUrl.hostname;
      opts.headers = {
        ...opts.headers,
        "Sec-WebSocket-Version": opts.protocolVersion,
        "Sec-WebSocket-Key": key,
        Connection: "Upgrade",
        Upgrade: "websocket"
      };
      opts.path = parsedUrl.pathname + parsedUrl.search;
      opts.timeout = opts.handshakeTimeout;
      if (opts.perMessageDeflate) {
        perMessageDeflate = new PerMessageDeflate2({
          ...opts.perMessageDeflate,
          isServer: false,
          maxPayload: opts.maxPayload
        });
        opts.headers["Sec-WebSocket-Extensions"] = format({
          [PerMessageDeflate2.extensionName]: perMessageDeflate.offer()
        });
      }
      if (protocols.length) {
        for (const protocol of protocols) {
          if (typeof protocol !== "string" || !subprotocolRegex.test(protocol) || protocolSet.has(protocol)) {
            throw new SyntaxError(
              "An invalid or duplicated subprotocol was specified"
            );
          }
          protocolSet.add(protocol);
        }
        opts.headers["Sec-WebSocket-Protocol"] = protocols.join(",");
      }
      if (opts.origin) {
        if (opts.protocolVersion < 13) {
          opts.headers["Sec-WebSocket-Origin"] = opts.origin;
        } else {
          opts.headers.Origin = opts.origin;
        }
      }
      if (parsedUrl.username || parsedUrl.password) {
        opts.auth = `${parsedUrl.username}:${parsedUrl.password}`;
      }
      if (isIpcUrl) {
        const parts = opts.path.split(":");
        opts.socketPath = parts[0];
        opts.path = parts[1];
      }
      let req;
      if (opts.followRedirects) {
        if (websocket._redirects === 0) {
          websocket._originalIpc = isIpcUrl;
          websocket._originalSecure = isSecure;
          websocket._originalHostOrSocketPath = isIpcUrl ? opts.socketPath : parsedUrl.host;
          const headers = options && options.headers;
          options = { ...options, headers: {} };
          if (headers) {
            for (const [key2, value] of Object.entries(headers)) {
              options.headers[key2.toLowerCase()] = value;
            }
          }
        } else if (websocket.listenerCount("redirect") === 0) {
          const isSameHost = isIpcUrl ? websocket._originalIpc ? opts.socketPath === websocket._originalHostOrSocketPath : false : websocket._originalIpc ? false : parsedUrl.host === websocket._originalHostOrSocketPath;
          if (!isSameHost || websocket._originalSecure && !isSecure) {
            delete opts.headers.authorization;
            delete opts.headers.cookie;
            if (!isSameHost) delete opts.headers.host;
            opts.auth = void 0;
          }
        }
        if (opts.auth && !options.headers.authorization) {
          options.headers.authorization = "Basic " + Buffer.from(opts.auth).toString("base64");
        }
        req = websocket._req = request(opts);
        if (websocket._redirects) {
          websocket.emit("redirect", websocket.url, req);
        }
      } else {
        req = websocket._req = request(opts);
      }
      if (opts.timeout) {
        req.on("timeout", () => {
          abortHandshake(websocket, req, "Opening handshake has timed out");
        });
      }
      req.on("error", (err) => {
        if (req === null || req[kAborted]) return;
        req = websocket._req = null;
        emitErrorAndClose(websocket, err);
      });
      req.on("response", (res) => {
        const location = res.headers.location;
        const statusCode = res.statusCode;
        if (location && opts.followRedirects && statusCode >= 300 && statusCode < 400) {
          if (++websocket._redirects > opts.maxRedirects) {
            abortHandshake(websocket, req, "Maximum redirects exceeded");
            return;
          }
          req.abort();
          let addr;
          try {
            addr = new URL2(location, address);
          } catch (e2) {
            const err = new SyntaxError(`Invalid URL: ${location}`);
            emitErrorAndClose(websocket, err);
            return;
          }
          initAsClient(websocket, addr, protocols, options);
        } else if (!websocket.emit("unexpected-response", req, res)) {
          abortHandshake(
            websocket,
            req,
            `Unexpected server response: ${res.statusCode}`
          );
        }
      });
      req.on("upgrade", (res, socket, head) => {
        websocket.emit("upgrade", res);
        if (websocket.readyState !== WebSocket2.CONNECTING) return;
        req = websocket._req = null;
        const upgrade = res.headers.upgrade;
        if (upgrade === void 0 || upgrade.toLowerCase() !== "websocket") {
          abortHandshake(websocket, socket, "Invalid Upgrade header");
          return;
        }
        const digest = createHash10("sha1").update(key + GUID).digest("base64");
        if (res.headers["sec-websocket-accept"] !== digest) {
          abortHandshake(websocket, socket, "Invalid Sec-WebSocket-Accept header");
          return;
        }
        const serverProt = res.headers["sec-websocket-protocol"];
        let protError;
        if (serverProt !== void 0) {
          if (!protocolSet.size) {
            protError = "Server sent a subprotocol but none was requested";
          } else if (!protocolSet.has(serverProt)) {
            protError = "Server sent an invalid subprotocol";
          }
        } else if (protocolSet.size) {
          protError = "Server sent no subprotocol";
        }
        if (protError) {
          abortHandshake(websocket, socket, protError);
          return;
        }
        if (serverProt) websocket._protocol = serverProt;
        const secWebSocketExtensions = res.headers["sec-websocket-extensions"];
        if (secWebSocketExtensions !== void 0) {
          if (!perMessageDeflate) {
            const message = "Server sent a Sec-WebSocket-Extensions header but no extension was requested";
            abortHandshake(websocket, socket, message);
            return;
          }
          let extensions;
          try {
            extensions = parse3(secWebSocketExtensions);
          } catch (err) {
            const message = "Invalid Sec-WebSocket-Extensions header";
            abortHandshake(websocket, socket, message);
            return;
          }
          const extensionNames = Object.keys(extensions);
          if (extensionNames.length !== 1 || extensionNames[0] !== PerMessageDeflate2.extensionName) {
            const message = "Server indicated an extension that was not requested";
            abortHandshake(websocket, socket, message);
            return;
          }
          try {
            perMessageDeflate.accept(extensions[PerMessageDeflate2.extensionName]);
          } catch (err) {
            const message = "Invalid Sec-WebSocket-Extensions header";
            abortHandshake(websocket, socket, message);
            return;
          }
          websocket._extensions[PerMessageDeflate2.extensionName] = perMessageDeflate;
        }
        websocket.setSocket(socket, head, {
          allowSynchronousEvents: opts.allowSynchronousEvents,
          generateMask: opts.generateMask,
          maxBufferedChunks: opts.maxBufferedChunks,
          maxFragments: opts.maxFragments,
          maxPayload: opts.maxPayload,
          skipUTF8Validation: opts.skipUTF8Validation
        });
      });
      if (opts.finishRequest) {
        opts.finishRequest(req, websocket);
      } else {
        req.end();
      }
    }
    function emitErrorAndClose(websocket, err) {
      websocket._readyState = WebSocket2.CLOSING;
      websocket._errorEmitted = true;
      websocket.emit("error", err);
      websocket.emitClose();
    }
    function netConnect(options) {
      options.path = options.socketPath;
      return net.connect(options);
    }
    function tlsConnect(options) {
      options.path = void 0;
      if (!options.servername && options.servername !== "") {
        options.servername = net.isIP(options.host) ? "" : options.host;
      }
      return tls.connect(options);
    }
    function abortHandshake(websocket, stream, message) {
      websocket._readyState = WebSocket2.CLOSING;
      const err = new Error(message);
      Error.captureStackTrace(err, abortHandshake);
      if (stream.setHeader) {
        stream[kAborted] = true;
        stream.abort();
        if (stream.socket && !stream.socket.destroyed) {
          stream.socket.destroy();
        }
        process.nextTick(emitErrorAndClose, websocket, err);
      } else {
        stream.destroy(err);
        stream.once("error", websocket.emit.bind(websocket, "error"));
        stream.once("close", websocket.emitClose.bind(websocket));
      }
    }
    function sendAfterClose(websocket, data, cb) {
      if (data) {
        const length = isBlob(data) ? data.size : toBuffer(data).length;
        if (websocket._socket) websocket._sender._bufferedBytes += length;
        else websocket._bufferedAmount += length;
      }
      if (cb) {
        const err = new Error(
          `WebSocket is not open: readyState ${websocket.readyState} (${readyStates[websocket.readyState]})`
        );
        process.nextTick(cb, err);
      }
    }
    function receiverOnConclude(code, reason) {
      const websocket = this[kWebSocket];
      websocket._closeFrameReceived = true;
      websocket._closeMessage = reason;
      websocket._closeCode = code;
      if (websocket._socket[kWebSocket] === void 0) return;
      websocket._socket.removeListener("data", socketOnData);
      process.nextTick(resume, websocket._socket);
      if (code === 1005) websocket.close();
      else websocket.close(code, reason);
    }
    function receiverOnDrain() {
      const websocket = this[kWebSocket];
      if (!websocket.isPaused) websocket._socket.resume();
    }
    function receiverOnError(err) {
      const websocket = this[kWebSocket];
      if (websocket._socket[kWebSocket] !== void 0) {
        websocket._socket.removeListener("data", socketOnData);
        process.nextTick(resume, websocket._socket);
        websocket.close(err[kStatusCode]);
      }
      if (!websocket._errorEmitted) {
        websocket._errorEmitted = true;
        websocket.emit("error", err);
      }
    }
    function receiverOnFinish() {
      this[kWebSocket].emitClose();
    }
    function receiverOnMessage(data, isBinary) {
      this[kWebSocket].emit("message", data, isBinary);
    }
    function receiverOnPing(data) {
      const websocket = this[kWebSocket];
      if (websocket._autoPong) websocket.pong(data, !this._isServer, NOOP);
      websocket.emit("ping", data);
    }
    function receiverOnPong(data) {
      this[kWebSocket].emit("pong", data);
    }
    function resume(stream) {
      stream.resume();
    }
    function senderOnError(err) {
      const websocket = this[kWebSocket];
      if (websocket.readyState === WebSocket2.CLOSED) return;
      if (websocket.readyState === WebSocket2.OPEN) {
        websocket._readyState = WebSocket2.CLOSING;
        setCloseTimer(websocket);
      }
      this._socket.end();
      if (!websocket._errorEmitted) {
        websocket._errorEmitted = true;
        websocket.emit("error", err);
      }
    }
    function setCloseTimer(websocket) {
      websocket._closeTimer = setTimeout(
        websocket._socket.destroy.bind(websocket._socket),
        websocket._closeTimeout
      );
    }
    function socketOnClose() {
      const websocket = this[kWebSocket];
      this.removeListener("close", socketOnClose);
      this.removeListener("data", socketOnData);
      this.removeListener("end", socketOnEnd);
      websocket._readyState = WebSocket2.CLOSING;
      if (!this._readableState.endEmitted && !websocket._closeFrameReceived && !websocket._receiver._writableState.errorEmitted && this._readableState.length !== 0) {
        const chunk = this.read(this._readableState.length);
        websocket._receiver.write(chunk);
      }
      websocket._receiver.end();
      this[kWebSocket] = void 0;
      clearTimeout(websocket._closeTimer);
      if (websocket._receiver._writableState.finished || websocket._receiver._writableState.errorEmitted) {
        websocket.emitClose();
      } else {
        websocket._receiver.on("error", receiverOnFinish);
        websocket._receiver.on("finish", receiverOnFinish);
      }
    }
    function socketOnData(chunk) {
      if (!this[kWebSocket]._receiver.write(chunk)) {
        this.pause();
      }
    }
    function socketOnEnd() {
      const websocket = this[kWebSocket];
      websocket._readyState = WebSocket2.CLOSING;
      websocket._receiver.end();
      this.end();
    }
    function socketOnError() {
      const websocket = this[kWebSocket];
      this.removeListener("error", socketOnError);
      this.on("error", NOOP);
      if (websocket) {
        websocket._readyState = WebSocket2.CLOSING;
        this.destroy();
      }
    }
  }
});

// node_modules/.pnpm/ws@8.21.0/node_modules/ws/lib/stream.js
var require_stream = __commonJS({
  "node_modules/.pnpm/ws@8.21.0/node_modules/ws/lib/stream.js"(exports, module) {
    "use strict";
    var WebSocket2 = require_websocket();
    var { Duplex } = __require("stream");
    function emitClose(stream) {
      stream.emit("close");
    }
    function duplexOnEnd() {
      if (!this.destroyed && this._writableState.finished) {
        this.destroy();
      }
    }
    function duplexOnError(err) {
      this.removeListener("error", duplexOnError);
      this.destroy();
      if (this.listenerCount("error") === 0) {
        this.emit("error", err);
      }
    }
    function createWebSocketStream2(ws, options) {
      let terminateOnDestroy = true;
      const duplex = new Duplex({
        ...options,
        autoDestroy: false,
        emitClose: false,
        objectMode: false,
        writableObjectMode: false
      });
      ws.on("message", function message(msg, isBinary) {
        const data = !isBinary && duplex._readableState.objectMode ? msg.toString() : msg;
        if (!duplex.push(data)) ws.pause();
      });
      ws.once("error", function error(err) {
        if (duplex.destroyed) return;
        terminateOnDestroy = false;
        duplex.destroy(err);
      });
      ws.once("close", function close() {
        if (duplex.destroyed) return;
        duplex.push(null);
      });
      duplex._destroy = function(err, callback) {
        if (ws.readyState === ws.CLOSED) {
          callback(err);
          process.nextTick(emitClose, duplex);
          return;
        }
        let called = false;
        ws.once("error", function error(err2) {
          called = true;
          callback(err2);
        });
        ws.once("close", function close() {
          if (!called) callback(err);
          process.nextTick(emitClose, duplex);
        });
        if (terminateOnDestroy) ws.terminate();
      };
      duplex._final = function(callback) {
        if (ws.readyState === ws.CONNECTING) {
          ws.once("open", function open() {
            duplex._final(callback);
          });
          return;
        }
        if (ws._socket === null) return;
        if (ws._socket._writableState.finished) {
          callback();
          if (duplex._readableState.endEmitted) duplex.destroy();
        } else {
          ws._socket.once("finish", function finish() {
            callback();
          });
          ws.close();
        }
      };
      duplex._read = function() {
        if (ws.isPaused) ws.resume();
      };
      duplex._write = function(chunk, encoding, callback) {
        if (ws.readyState === ws.CONNECTING) {
          ws.once("open", function open() {
            duplex._write(chunk, encoding, callback);
          });
          return;
        }
        ws.send(chunk, callback);
      };
      duplex.on("end", duplexOnEnd);
      duplex.on("error", duplexOnError);
      return duplex;
    }
    module.exports = createWebSocketStream2;
  }
});

// node_modules/.pnpm/ws@8.21.0/node_modules/ws/lib/subprotocol.js
var require_subprotocol = __commonJS({
  "node_modules/.pnpm/ws@8.21.0/node_modules/ws/lib/subprotocol.js"(exports, module) {
    "use strict";
    var { tokenChars } = require_validation();
    function parse3(header) {
      const protocols = /* @__PURE__ */ new Set();
      let start = -1;
      let end = -1;
      let i = 0;
      for (i; i < header.length; i++) {
        const code = header.charCodeAt(i);
        if (end === -1 && tokenChars[code] === 1) {
          if (start === -1) start = i;
        } else if (i !== 0 && (code === 32 || code === 9)) {
          if (end === -1 && start !== -1) end = i;
        } else if (code === 44) {
          if (start === -1) {
            throw new SyntaxError(`Unexpected character at index ${i}`);
          }
          if (end === -1) end = i;
          const protocol2 = header.slice(start, end);
          if (protocols.has(protocol2)) {
            throw new SyntaxError(`The "${protocol2}" subprotocol is duplicated`);
          }
          protocols.add(protocol2);
          start = end = -1;
        } else {
          throw new SyntaxError(`Unexpected character at index ${i}`);
        }
      }
      if (start === -1 || end !== -1) {
        throw new SyntaxError("Unexpected end of input");
      }
      const protocol = header.slice(start, i);
      if (protocols.has(protocol)) {
        throw new SyntaxError(`The "${protocol}" subprotocol is duplicated`);
      }
      protocols.add(protocol);
      return protocols;
    }
    module.exports = { parse: parse3 };
  }
});

// node_modules/.pnpm/ws@8.21.0/node_modules/ws/lib/websocket-server.js
var require_websocket_server = __commonJS({
  "node_modules/.pnpm/ws@8.21.0/node_modules/ws/lib/websocket-server.js"(exports, module) {
    "use strict";
    var EventEmitter = __require("events");
    var http = __require("http");
    var { Duplex } = __require("stream");
    var { createHash: createHash10 } = __require("crypto");
    var extension3 = require_extension();
    var PerMessageDeflate2 = require_permessage_deflate();
    var subprotocol2 = require_subprotocol();
    var WebSocket2 = require_websocket();
    var { CLOSE_TIMEOUT, GUID, kWebSocket } = require_constants();
    var keyRegex = /^[+/0-9A-Za-z]{22}==$/;
    var RUNNING = 0;
    var CLOSING = 1;
    var CLOSED = 2;
    var WebSocketServer2 = class extends EventEmitter {
      /**
       * Create a `WebSocketServer` instance.
       *
       * @param {Object} options Configuration options
       * @param {Boolean} [options.allowSynchronousEvents=true] Specifies whether
       *     any of the `'message'`, `'ping'`, and `'pong'` events can be emitted
       *     multiple times in the same tick
       * @param {Boolean} [options.autoPong=true] Specifies whether or not to
       *     automatically send a pong in response to a ping
       * @param {Number} [options.backlog=511] The maximum length of the queue of
       *     pending connections
       * @param {Boolean} [options.clientTracking=true] Specifies whether or not to
       *     track clients
       * @param {Number} [options.closeTimeout=30000] Duration in milliseconds to
       *     wait for the closing handshake to finish after `websocket.close()` is
       *     called
       * @param {Function} [options.handleProtocols] A hook to handle protocols
       * @param {String} [options.host] The hostname where to bind the server
       * @param {Number} [options.maxBufferedChunks=1048576] The maximum number of
       *     buffered data chunks
       * @param {Number} [options.maxFragments=131072] The maximum number of message
       *     fragments
       * @param {Number} [options.maxPayload=104857600] The maximum allowed message
       *     size
       * @param {Boolean} [options.noServer=false] Enable no server mode
       * @param {String} [options.path] Accept only connections matching this path
       * @param {(Boolean|Object)} [options.perMessageDeflate=false] Enable/disable
       *     permessage-deflate
       * @param {Number} [options.port] The port where to bind the server
       * @param {(http.Server|https.Server)} [options.server] A pre-created HTTP/S
       *     server to use
       * @param {Boolean} [options.skipUTF8Validation=false] Specifies whether or
       *     not to skip UTF-8 validation for text and close messages
       * @param {Function} [options.verifyClient] A hook to reject connections
       * @param {Function} [options.WebSocket=WebSocket] Specifies the `WebSocket`
       *     class to use. It must be the `WebSocket` class or class that extends it
       * @param {Function} [callback] A listener for the `listening` event
       */
      constructor(options, callback) {
        super();
        options = {
          allowSynchronousEvents: true,
          autoPong: true,
          maxBufferedChunks: 1024 * 1024,
          maxFragments: 128 * 1024,
          maxPayload: 100 * 1024 * 1024,
          skipUTF8Validation: false,
          perMessageDeflate: false,
          handleProtocols: null,
          clientTracking: true,
          closeTimeout: CLOSE_TIMEOUT,
          verifyClient: null,
          noServer: false,
          backlog: null,
          // use default (511 as implemented in net.js)
          server: null,
          host: null,
          path: null,
          port: null,
          WebSocket: WebSocket2,
          ...options
        };
        if (options.port == null && !options.server && !options.noServer || options.port != null && (options.server || options.noServer) || options.server && options.noServer) {
          throw new TypeError(
            'One and only one of the "port", "server", or "noServer" options must be specified'
          );
        }
        if (options.port != null) {
          this._server = http.createServer((req, res) => {
            const body = http.STATUS_CODES[426];
            res.writeHead(426, {
              "Content-Length": body.length,
              "Content-Type": "text/plain"
            });
            res.end(body);
          });
          this._server.listen(
            options.port,
            options.host,
            options.backlog,
            callback
          );
        } else if (options.server) {
          this._server = options.server;
        }
        if (this._server) {
          const emitConnection = this.emit.bind(this, "connection");
          this._removeListeners = addListeners(this._server, {
            listening: this.emit.bind(this, "listening"),
            error: this.emit.bind(this, "error"),
            upgrade: (req, socket, head) => {
              this.handleUpgrade(req, socket, head, emitConnection);
            }
          });
        }
        if (options.perMessageDeflate === true) options.perMessageDeflate = {};
        if (options.clientTracking) {
          this.clients = /* @__PURE__ */ new Set();
          this._shouldEmitClose = false;
        }
        this.options = options;
        this._state = RUNNING;
      }
      /**
       * Returns the bound address, the address family name, and port of the server
       * as reported by the operating system if listening on an IP socket.
       * If the server is listening on a pipe or UNIX domain socket, the name is
       * returned as a string.
       *
       * @return {(Object|String|null)} The address of the server
       * @public
       */
      address() {
        if (this.options.noServer) {
          throw new Error('The server is operating in "noServer" mode');
        }
        if (!this._server) return null;
        return this._server.address();
      }
      /**
       * Stop the server from accepting new connections and emit the `'close'` event
       * when all existing connections are closed.
       *
       * @param {Function} [cb] A one-time listener for the `'close'` event
       * @public
       */
      close(cb) {
        if (this._state === CLOSED) {
          if (cb) {
            this.once("close", () => {
              cb(new Error("The server is not running"));
            });
          }
          process.nextTick(emitClose, this);
          return;
        }
        if (cb) this.once("close", cb);
        if (this._state === CLOSING) return;
        this._state = CLOSING;
        if (this.options.noServer || this.options.server) {
          if (this._server) {
            this._removeListeners();
            this._removeListeners = this._server = null;
          }
          if (this.clients) {
            if (!this.clients.size) {
              process.nextTick(emitClose, this);
            } else {
              this._shouldEmitClose = true;
            }
          } else {
            process.nextTick(emitClose, this);
          }
        } else {
          const server = this._server;
          this._removeListeners();
          this._removeListeners = this._server = null;
          server.close(() => {
            emitClose(this);
          });
        }
      }
      /**
       * See if a given request should be handled by this server instance.
       *
       * @param {http.IncomingMessage} req Request object to inspect
       * @return {Boolean} `true` if the request is valid, else `false`
       * @public
       */
      shouldHandle(req) {
        if (this.options.path) {
          const index = req.url.indexOf("?");
          const pathname = index !== -1 ? req.url.slice(0, index) : req.url;
          if (pathname !== this.options.path) return false;
        }
        return true;
      }
      /**
       * Handle a HTTP Upgrade request.
       *
       * @param {http.IncomingMessage} req The request object
       * @param {Duplex} socket The network socket between the server and client
       * @param {Buffer} head The first packet of the upgraded stream
       * @param {Function} cb Callback
       * @public
       */
      handleUpgrade(req, socket, head, cb) {
        socket.on("error", socketOnError);
        const key = req.headers["sec-websocket-key"];
        const upgrade = req.headers.upgrade;
        const version = +req.headers["sec-websocket-version"];
        if (req.method !== "GET") {
          const message = "Invalid HTTP method";
          abortHandshakeOrEmitwsClientError(this, req, socket, 405, message);
          return;
        }
        if (upgrade === void 0 || upgrade.toLowerCase() !== "websocket") {
          const message = "Invalid Upgrade header";
          abortHandshakeOrEmitwsClientError(this, req, socket, 400, message);
          return;
        }
        if (key === void 0 || !keyRegex.test(key)) {
          const message = "Missing or invalid Sec-WebSocket-Key header";
          abortHandshakeOrEmitwsClientError(this, req, socket, 400, message);
          return;
        }
        if (version !== 13 && version !== 8) {
          const message = "Missing or invalid Sec-WebSocket-Version header";
          abortHandshakeOrEmitwsClientError(this, req, socket, 400, message, {
            "Sec-WebSocket-Version": "13, 8"
          });
          return;
        }
        if (!this.shouldHandle(req)) {
          abortHandshake(socket, 400);
          return;
        }
        const secWebSocketProtocol = req.headers["sec-websocket-protocol"];
        let protocols = /* @__PURE__ */ new Set();
        if (secWebSocketProtocol !== void 0) {
          try {
            protocols = subprotocol2.parse(secWebSocketProtocol);
          } catch (err) {
            const message = "Invalid Sec-WebSocket-Protocol header";
            abortHandshakeOrEmitwsClientError(this, req, socket, 400, message);
            return;
          }
        }
        const secWebSocketExtensions = req.headers["sec-websocket-extensions"];
        const extensions = {};
        if (this.options.perMessageDeflate && secWebSocketExtensions !== void 0) {
          const perMessageDeflate = new PerMessageDeflate2({
            ...this.options.perMessageDeflate,
            isServer: true,
            maxPayload: this.options.maxPayload
          });
          try {
            const offers = extension3.parse(secWebSocketExtensions);
            if (offers[PerMessageDeflate2.extensionName]) {
              perMessageDeflate.accept(offers[PerMessageDeflate2.extensionName]);
              extensions[PerMessageDeflate2.extensionName] = perMessageDeflate;
            }
          } catch (err) {
            const message = "Invalid or unacceptable Sec-WebSocket-Extensions header";
            abortHandshakeOrEmitwsClientError(this, req, socket, 400, message);
            return;
          }
        }
        if (this.options.verifyClient) {
          const info = {
            origin: req.headers[`${version === 8 ? "sec-websocket-origin" : "origin"}`],
            secure: !!(req.socket.authorized || req.socket.encrypted),
            req
          };
          if (this.options.verifyClient.length === 2) {
            this.options.verifyClient(info, (verified, code, message, headers) => {
              if (!verified) {
                return abortHandshake(socket, code || 401, message, headers);
              }
              this.completeUpgrade(
                extensions,
                key,
                protocols,
                req,
                socket,
                head,
                cb
              );
            });
            return;
          }
          if (!this.options.verifyClient(info)) return abortHandshake(socket, 401);
        }
        this.completeUpgrade(extensions, key, protocols, req, socket, head, cb);
      }
      /**
       * Upgrade the connection to WebSocket.
       *
       * @param {Object} extensions The accepted extensions
       * @param {String} key The value of the `Sec-WebSocket-Key` header
       * @param {Set} protocols The subprotocols
       * @param {http.IncomingMessage} req The request object
       * @param {Duplex} socket The network socket between the server and client
       * @param {Buffer} head The first packet of the upgraded stream
       * @param {Function} cb Callback
       * @throws {Error} If called more than once with the same socket
       * @private
       */
      completeUpgrade(extensions, key, protocols, req, socket, head, cb) {
        if (!socket.readable || !socket.writable) return socket.destroy();
        if (socket[kWebSocket]) {
          throw new Error(
            "server.handleUpgrade() was called more than once with the same socket, possibly due to a misconfiguration"
          );
        }
        if (this._state > RUNNING) return abortHandshake(socket, 503);
        const digest = createHash10("sha1").update(key + GUID).digest("base64");
        const headers = [
          "HTTP/1.1 101 Switching Protocols",
          "Upgrade: websocket",
          "Connection: Upgrade",
          `Sec-WebSocket-Accept: ${digest}`
        ];
        const ws = new this.options.WebSocket(null, void 0, this.options);
        if (protocols.size) {
          const protocol = this.options.handleProtocols ? this.options.handleProtocols(protocols, req) : protocols.values().next().value;
          if (protocol) {
            headers.push(`Sec-WebSocket-Protocol: ${protocol}`);
            ws._protocol = protocol;
          }
        }
        if (extensions[PerMessageDeflate2.extensionName]) {
          const params = extensions[PerMessageDeflate2.extensionName].params;
          const value = extension3.format({
            [PerMessageDeflate2.extensionName]: [params]
          });
          headers.push(`Sec-WebSocket-Extensions: ${value}`);
          ws._extensions = extensions;
        }
        this.emit("headers", headers, req);
        socket.write(headers.concat("\r\n").join("\r\n"));
        socket.removeListener("error", socketOnError);
        ws.setSocket(socket, head, {
          allowSynchronousEvents: this.options.allowSynchronousEvents,
          maxBufferedChunks: this.options.maxBufferedChunks,
          maxFragments: this.options.maxFragments,
          maxPayload: this.options.maxPayload,
          skipUTF8Validation: this.options.skipUTF8Validation
        });
        if (this.clients) {
          this.clients.add(ws);
          ws.on("close", () => {
            this.clients.delete(ws);
            if (this._shouldEmitClose && !this.clients.size) {
              process.nextTick(emitClose, this);
            }
          });
        }
        cb(ws, req);
      }
    };
    module.exports = WebSocketServer2;
    function addListeners(server, map) {
      for (const event of Object.keys(map)) server.on(event, map[event]);
      return function removeListeners() {
        for (const event of Object.keys(map)) {
          server.removeListener(event, map[event]);
        }
      };
    }
    function emitClose(server) {
      server._state = CLOSED;
      server.emit("close");
    }
    function socketOnError() {
      this.destroy();
    }
    function abortHandshake(socket, code, message, headers) {
      message = message || http.STATUS_CODES[code];
      headers = {
        Connection: "close",
        "Content-Type": "text/html",
        "Content-Length": Buffer.byteLength(message),
        ...headers
      };
      socket.once("finish", socket.destroy);
      socket.end(
        `HTTP/1.1 ${code} ${http.STATUS_CODES[code]}\r
` + Object.keys(headers).map((h) => `${h}: ${headers[h]}`).join("\r\n") + "\r\n\r\n" + message
      );
    }
    function abortHandshakeOrEmitwsClientError(server, req, socket, code, message, headers) {
      if (server.listenerCount("wsClientError")) {
        const err = new Error(message);
        Error.captureStackTrace(err, abortHandshakeOrEmitwsClientError);
        server.emit("wsClientError", err, socket, req);
      } else {
        abortHandshake(socket, code, message, headers);
      }
    }
  }
});

// src/migrate-runner/types.ts
var MIGRATION_RUNNER_SCHEMA_VERSION = 1;
var MIGRATION_RUNNER_PHASES = [
  "detecting",
  "planning",
  "migrating",
  "validating",
  "packaging"
];
var MIGRATION_RUNNER_FRAMEWORKS = [
  "langchain",
  "langgraph",
  "adk",
  "strands",
  "agentcore",
  "dify",
  "any"
];

// src/migrate-runner/events.ts
var NdjsonMigrationRunnerEventSink = class {
  constructor(request, writer = process.stdout, sequenceStart = 0, clock = () => /* @__PURE__ */ new Date()) {
    this.request = request;
    this.writer = writer;
    this.clock = clock;
    this.sequence = sequenceStart;
  }
  request;
  writer;
  clock;
  sequence;
  emit(input) {
    const event = {
      ...input,
      schema_version: MIGRATION_RUNNER_SCHEMA_VERSION,
      task_id: this.request.task_id,
      attempt_id: this.request.attempt_id,
      sequence: this.sequence,
      created_at: this.clock().toISOString()
    };
    this.sequence += 1;
    this.writer.write(`${JSON.stringify(event)}
`);
  }
};

// src/migrate-runner/request.ts
import { readFileSync } from "fs";
import { isAbsolute, relative, resolve } from "path";

// src/migrate/types.ts
var COMPAT_PROFILES = ["none", "langserve", "fastapi-mount"];
var SERVER_MODES = ["langgraph"];
function isCompatProfile(value) {
  return COMPAT_PROFILES.includes(value);
}

// src/migrate-runner/request.ts
var REQUEST_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;
var FINGERPRINT_PATTERN = /^[a-f0-9]{64}$/;
var ENV_NAME_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/;
var MAX_REQUEST_BYTES = 1024 * 1024;
function record(value, path) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${path} must be an object.`);
  }
  return value;
}
function assertKnownKeys(value, allowed, path) {
  const allowedKeys = new Set(allowed);
  const unknown = Object.keys(value).filter((key) => !allowedKeys.has(key));
  if (unknown.length > 0) {
    throw new Error(`${path} contains unsupported field(s): ${unknown.join(", ")}.`);
  }
}
function requiredString(value, key, path, maxLength = 4096) {
  const raw = value[key];
  if (typeof raw !== "string" || !raw.trim()) {
    throw new Error(`${path}.${key} must be a non-empty string.`);
  }
  const normalized = raw.trim();
  if (normalized.length > maxLength || /[\u0000]/.test(normalized)) {
    throw new Error(`${path}.${key} is invalid.`);
  }
  return normalized;
}
function optionalString(value, key, path, maxLength = 4096) {
  if (value[key] === void 0) return void 0;
  return requiredString(value, key, path, maxLength);
}
function optionalBoolean(value, key, path) {
  const raw = value[key];
  if (raw === void 0) return void 0;
  if (typeof raw !== "boolean") throw new Error(`${path}.${key} must be boolean.`);
  return raw;
}
function assertSafeRelativePath(value, label) {
  if (!value || isAbsolute(value) || value.includes("\\") || value.split("/").some((part) => !part || part === "." || part === "..") || /[\u0000-\u001f\u007f]/.test(value)) {
    throw new Error(`${label} must be a safe relative path.`);
  }
  return value;
}
function resolveWorkspacePath(workspace, value, label) {
  const safe = assertSafeRelativePath(value, label);
  const root = resolve(workspace);
  const target = resolve(root, safe);
  const rel = relative(root, target);
  if (!rel || rel.startsWith("..") || isAbsolute(rel)) {
    throw new Error(`${label} must resolve below the Runner workspace.`);
  }
  return target;
}
function parseOptions(raw) {
  const value = record(raw, "request.options");
  assertKnownKeys(
    value,
    [
      "entry",
      "input_key",
      "stream_nodes",
      "compat",
      "compat_prefix",
      "legacy_app",
      "server_mode",
      "allow_blocking",
      "verify",
      "force",
      "name"
    ],
    "request.options"
  );
  const streamNodes = value.stream_nodes;
  if (streamNodes !== void 0 && (!Array.isArray(streamNodes) || streamNodes.some(
    (item) => typeof item !== "string" || !item.trim() || item.length > 256
  ))) {
    throw new Error("request.options.stream_nodes must be an array of strings.");
  }
  const compat = optionalString(value, "compat", "request.options", 64);
  if (compat !== void 0 && compat !== "auto" && !COMPAT_PROFILES.includes(compat)) {
    throw new Error(`request.options.compat is unsupported: ${compat}.`);
  }
  const serverMode = optionalString(value, "server_mode", "request.options", 64);
  if (serverMode !== void 0 && !SERVER_MODES.includes(serverMode)) {
    throw new Error(`request.options.server_mode is unsupported: ${serverMode}.`);
  }
  return {
    entry: optionalString(value, "entry", "request.options", 1024),
    input_key: optionalString(value, "input_key", "request.options", 256),
    stream_nodes: streamNodes?.map((item) => String(item).trim()),
    compat,
    compat_prefix: optionalString(value, "compat_prefix", "request.options", 512),
    legacy_app: optionalString(value, "legacy_app", "request.options", 1024),
    server_mode: serverMode,
    allow_blocking: optionalBoolean(value, "allow_blocking", "request.options"),
    verify: optionalBoolean(value, "verify", "request.options"),
    force: optionalBoolean(value, "force", "request.options"),
    name: optionalString(value, "name", "request.options", 128)
  };
}
function parseMigrationRunnerRequest(value) {
  const root = record(value, "request");
  assertKnownKeys(
    root,
    [
      "schema_version",
      "task_id",
      "attempt_id",
      "sequence_start",
      "source",
      "strategy",
      "framework",
      "user",
      "target",
      "options",
      "output"
    ],
    "request"
  );
  if (root.schema_version !== MIGRATION_RUNNER_SCHEMA_VERSION) {
    throw new Error(
      `Unsupported migration Runner schema_version: ${String(root.schema_version)}.`
    );
  }
  const taskId = requiredString(root, "task_id", "request", 128);
  const attemptId = requiredString(root, "attempt_id", "request", 128);
  if (!REQUEST_ID_PATTERN.test(taskId) || !REQUEST_ID_PATTERN.test(attemptId)) {
    throw new Error("request task_id and attempt_id contain unsupported characters.");
  }
  const sequenceStart = root.sequence_start;
  if (sequenceStart !== void 0 && (!Number.isSafeInteger(sequenceStart) || Number(sequenceStart) < 0)) {
    throw new Error("request.sequence_start must be a non-negative integer.");
  }
  const source = record(root.source, "request.source");
  assertKnownKeys(source, ["root", "fingerprint"], "request.source");
  const sourceRoot = assertSafeRelativePath(
    requiredString(source, "root", "request.source", 1024),
    "request.source.root"
  );
  const fingerprint = requiredString(
    source,
    "fingerprint",
    "request.source",
    64
  ).toLowerCase();
  if (!FINGERPRINT_PATTERN.test(fingerprint)) {
    throw new Error("request.source.fingerprint must be a SHA-256 hex digest.");
  }
  const strategy = requiredString(root, "strategy", "request", 32);
  if (!["auto", "structured", "agentic"].includes(strategy)) {
    throw new Error(`request.strategy is unsupported: ${strategy}.`);
  }
  const framework = requiredString(root, "framework", "request", 32);
  if (framework !== "auto" && !MIGRATION_RUNNER_FRAMEWORKS.includes(framework)) {
    throw new Error(`request.framework is unsupported: ${framework}.`);
  }
  const user = record(root.user, "request.user");
  assertKnownKeys(user, ["language", "request"], "request.user");
  const language = requiredString(user, "language", "request.user", 32);
  const userRequest = typeof user.request === "string" && user.request.length <= 2e4 ? user.request.trim() : (() => {
    throw new Error("request.user.request must be a string up to 20000 characters.");
  })();
  const target = record(root.target, "request.target");
  assertKnownKeys(
    target,
    [
      "cloud_provider",
      "region",
      "project",
      "model_id",
      "model_base_url",
      "model_api_key_env"
    ],
    "request.target"
  );
  const cloudProvider = requiredString(
    target,
    "cloud_provider",
    "request.target",
    32
  );
  if (!["volcengine", "byteplus"].includes(cloudProvider)) {
    throw new Error(`request.target.cloud_provider is unsupported: ${cloudProvider}.`);
  }
  const modelApiKeyEnv = optionalString(
    target,
    "model_api_key_env",
    "request.target",
    128
  );
  if (modelApiKeyEnv && !ENV_NAME_PATTERN.test(modelApiKeyEnv)) {
    throw new Error("request.target.model_api_key_env must be an environment name.");
  }
  const modelBaseUrl = optionalString(
    target,
    "model_base_url",
    "request.target",
    2048
  );
  if (modelBaseUrl) {
    let parsedUrl;
    try {
      parsedUrl = new URL(modelBaseUrl);
    } catch {
      throw new Error("request.target.model_base_url must be a valid URL.");
    }
    if (!["http:", "https:"].includes(parsedUrl.protocol)) {
      throw new Error("request.target.model_base_url must use http or https.");
    }
  }
  const output = record(root.output, "request.output");
  assertKnownKeys(output, ["root", "manifest"], "request.output");
  const outputRoot = assertSafeRelativePath(
    requiredString(output, "root", "request.output", 1024),
    "request.output.root"
  );
  const outputManifest = assertSafeRelativePath(
    requiredString(output, "manifest", "request.output", 1024),
    "request.output.manifest"
  );
  if (outputManifest !== `${outputRoot}/migration-result.json`) {
    throw new Error(
      "request.output.manifest must be migration-result.json at request.output.root."
    );
  }
  return {
    schema_version: MIGRATION_RUNNER_SCHEMA_VERSION,
    task_id: taskId,
    attempt_id: attemptId,
    sequence_start: sequenceStart === void 0 ? void 0 : Number(sequenceStart),
    source: { root: sourceRoot, fingerprint },
    strategy,
    framework,
    user: { language, request: userRequest },
    target: {
      cloud_provider: cloudProvider,
      region: requiredString(target, "region", "request.target", 64),
      project: requiredString(target, "project", "request.target", 256),
      model_id: optionalString(target, "model_id", "request.target", 512),
      model_base_url: modelBaseUrl,
      model_api_key_env: modelApiKeyEnv
    },
    options: parseOptions(root.options),
    output: { root: outputRoot, manifest: outputManifest }
  };
}
function readMigrationRunnerRequest(path) {
  const content = readFileSync(path);
  if (content.length > MAX_REQUEST_BYTES) {
    throw new Error("Migration Runner request exceeds 1 MiB.");
  }
  let parsed;
  try {
    parsed = JSON.parse(content.toString("utf8"));
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`Migration Runner request is not valid JSON: ${message}`);
  }
  return parseMigrationRunnerRequest(parsed);
}

// src/migrate-runner/runner.ts
import { createHash as createHash9 } from "crypto";
import {
  cpSync,
  existsSync as existsSync28,
  mkdirSync as mkdirSync13,
  rmSync as rmSync10,
  statSync as statSync10
} from "fs";
import { dirname as dirname10, join as join26, relative as relative11, resolve as resolve13 } from "path";

// package.json
var package_default = {
  name: "agentkit-cli",
  version: "0.51.1",
  description: "Smart CLI for AgentKit",
  type: "module",
  bin: {
    agentkit: "./dist/index.js",
    ak: "./dist/index.js",
    "agentkit-migration-runner": "./dist/migrate-runner/cli.js"
  },
  files: [
    "dist",
    "lifecycle-templates",
    "templates",
    "harness",
    "skills",
    "im-proxies"
  ],
  scripts: {
    dev: "tsx src/index.ts",
    build: "tsup",
    start: "node dist/index.js",
    "verify:migrate-runner-build": "node scripts/verify-migrate-runner-build.mjs",
    typecheck: "tsc --noEmit",
    test: "vitest run",
    "test:coverage": "vitest run --coverage",
    "test:e2e:migrate": "vitest run src/migrate/pythonSmoke.test.ts src/migrate/pythonServerE2e.test.ts",
    "test:e2e:migrate:ark": "AGENTKIT_MIGRATE_ARK_E2E=1 vitest run src/migrate/pythonServerE2e.test.ts",
    "test:watch": "vitest",
    "test:cloud": "vitest run -c vitest.cloud.config.ts",
    "build:binary": "bun build src/index.ts --compile --outfile dist/ak",
    "build:binaries": "bash scripts/build-binaries.sh"
  },
  keywords: [
    "agentkit",
    "cli",
    "agent"
  ],
  license: "MIT",
  packageManager: "pnpm@10.16.1",
  dependencies: {
    "@clack/prompts": "^0.11.0",
    "@xterm/addon-fit": "^0.11.0",
    "@xterm/xterm": "^6.0.0",
    "cli-table3": "^0.6.5",
    commander: "^15.0.0",
    ws: "^8.21.0",
    yaml: "^2.9.0"
  },
  devDependencies: {
    "@types/node": "^26.0.1",
    "@types/ws": "^8.18.1",
    "@vitest/coverage-v8": "4.1.9",
    tsup: "^8.5.1",
    tsx: "^4.22.4",
    typescript: "^6.0.3",
    vitest: "^4.1.9"
  },
  pnpm: {
    overrides: {
      postcss: "8.5.23"
    },
    onlyBuiltDependencies: [
      "esbuild"
    ]
  }
};

// src/migrate/index.ts
var import_yaml = __toESM(require_dist(), 1);
import { existsSync as existsSync3, lstatSync, mkdirSync, readFileSync as readFileSync4, readdirSync as readdirSync2, realpathSync as realpathSync2, statSync as statSync2, writeFileSync } from "fs";
import { basename, join as join3, relative as relative3, resolve as resolve3 } from "path";

// src/migrate/requirements.ts
import { existsSync, readFileSync as readFileSync2 } from "fs";
import { join } from "path";
var AGENTKIT_SDK_BRIDGE_MIN_VERSION = "0.7.12";
var BASE_REQUIREMENTS = [
  `agentkit-sdk-python>=${AGENTKIT_SDK_BRIDGE_MIN_VERSION}`,
  "google-adk>=1.32"
];
function requiredPackages(framework) {
  if (framework === "langchain") return [...BASE_REQUIREMENTS, "langchain"];
  if (framework === "langgraph") return [...BASE_REQUIREMENTS, "langgraph"];
  if (framework === "strands") return [...BASE_REQUIREMENTS, "strands-agents"];
  if (framework === "agentcore") return [...BASE_REQUIREMENTS, "bedrock-agentcore"];
  return [...BASE_REQUIREMENTS];
}
function requiredLangGraphServerPackages() {
  return [`agentkit-sdk-python>=${AGENTKIT_SDK_BRIDGE_MIN_VERSION}`, "langgraph-cli[inmem]"];
}
function normalizeRequirementName(line) {
  const trimmed = line.trim();
  if (!trimmed || trimmed.startsWith("#") || trimmed.startsWith("-")) return void 0;
  const withoutComment = trimmed.split("#", 1)[0].trim();
  const match = withoutComment.match(/^([A-Za-z0-9_.-]+)/);
  return match?.[1]?.replace(/[_.-]+/g, "-").toLowerCase();
}
function normalizePackageName(name) {
  const requirementName = normalizeRequirementName(name);
  return (requirementName ?? name).replace(/[_.-]+/g, "-").toLowerCase();
}
function compareVersions(left, right) {
  const leftParts = left.split(/[^\d]+/).filter(Boolean).map(Number);
  const rightParts = right.split(/[^\d]+/).filter(Boolean).map(Number);
  const length = Math.max(leftParts.length, rightParts.length);
  for (let index = 0; index < length; index += 1) {
    const leftPart = leftParts[index] ?? 0;
    const rightPart = rightParts[index] ?? 0;
    if (leftPart > rightPart) return 1;
    if (leftPart < rightPart) return -1;
  }
  return 0;
}
function minVersionFromRequiredPackage(pkg) {
  const name = normalizePackageName(pkg);
  const match = pkg.match(/>=\s*([0-9][A-Za-z0-9.!+_-]*)/);
  return { name, minVersion: match?.[1] };
}
function requirementSatisfiesMinimum(line, minVersion) {
  const withoutComment = line.split("#", 1)[0].trim();
  const withoutMarker = withoutComment.split(";", 1)[0].trim();
  const specMatch = withoutMarker.match(/(?:>=|==|~=|>)\s*([0-9][A-Za-z0-9.!+_-]*)/);
  if (!specMatch) return false;
  return compareVersions(specMatch[1], minVersion) >= 0;
}
function replaceRequirementLine(line, replacement) {
  const markerIndex = line.indexOf(";");
  const commentIndex = line.indexOf("#");
  const suffixStartCandidates = [markerIndex, commentIndex].filter((index) => index >= 0);
  if (suffixStartCandidates.length === 0) return replacement;
  const suffixStart = Math.min(...suffixStartCandidates);
  const suffix = line.slice(suffixStart);
  const separator = suffix.startsWith(";") ? " " : " ";
  return `${replacement}${separator}${suffix.trimStart()}`;
}
function mergeRequirements(existing, packages) {
  const lines = existing.split(/\r?\n/);
  const present = /* @__PURE__ */ new Map();
  for (const [index, line] of lines.entries()) {
    const name = normalizeRequirementName(line);
    if (name && !present.has(name)) present.set(name, index);
  }
  const added = [];
  const alreadyPresent = [];
  const updated = [];
  for (const pkg of packages) {
    const required = minVersionFromRequiredPackage(pkg);
    const lineIndex = present.get(required.name);
    if (lineIndex === void 0) {
      added.push(pkg);
      continue;
    }
    if (required.minVersion && !requirementSatisfiesMinimum(lines[lineIndex], required.minVersion)) {
      lines[lineIndex] = replaceRequirementLine(lines[lineIndex], pkg);
      updated.push(pkg);
      continue;
    }
    alreadyPresent.push(pkg);
  }
  if (added.length === 0 && updated.length === 0) return { content: existing, added, alreadyPresent, updated };
  const updatedContent = updated.length > 0 ? lines.join("\n") : existing;
  const prefix = updatedContent.length > 0 && !updatedContent.endsWith("\n") ? `${updatedContent}
` : updatedContent;
  const content = added.length > 0 ? `${prefix}${added.join("\n")}
` : prefix;
  return {
    content,
    added,
    alreadyPresent,
    updated
  };
}
function readRequirements(projectDir) {
  const path = join(projectDir, "requirements.txt");
  return existsSync(path) ? readFileSync2(path, "utf8") : "";
}

// src/migrate/scan.ts
import { existsSync as existsSync2, readdirSync, readFileSync as readFileSync3, realpathSync, statSync } from "fs";
import { isAbsolute as isAbsolute2, join as join2, relative as relative2, resolve as resolve2 } from "path";
var EXCLUDED_DIRS = /* @__PURE__ */ new Set([
  ".agentkit",
  ".git",
  ".mypy_cache",
  ".pytest_cache",
  ".ruff_cache",
  ".venv",
  "__pycache__",
  "dist",
  "node_modules",
  "venv"
]);
function toPosix(path) {
  return path.split(/[\\/]+/).join("/");
}
function assertInside(parent, child, label) {
  const rel = relative2(parent, child);
  if (rel === "" || !rel.startsWith("..") && !isAbsolute2(rel)) return;
  throw new Error(`${label} must be inside the project directory.`);
}
function parseEntryReference(entry) {
  const sep2 = entry.lastIndexOf(":");
  if (sep2 <= 0 || sep2 === entry.length - 1) {
    throw new Error("Entry must use the form <file.py:object>, for example agent.py:agent.");
  }
  const file = entry.slice(0, sep2);
  const object = entry.slice(sep2 + 1);
  if (!file.endsWith(".py")) throw new Error("Entry file must be a Python file ending in .py.");
  if (!/^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$/.test(object)) {
    throw new Error("Entry object must be a Python identifier path, for example agent or factory.root_agent.");
  }
  return { file, object };
}
function resolveProjectPath(projectDir, file) {
  return resolve2(projectDir, file);
}
function listPythonFiles(dir, out = []) {
  if (!existsSync2(dir)) return out;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      if (!EXCLUDED_DIRS.has(entry.name)) listPythonFiles(join2(dir, entry.name), out);
      continue;
    }
    if (entry.isFile() && entry.name.endsWith(".py")) out.push(join2(dir, entry.name));
  }
  return out;
}
function frameworkPattern(framework) {
  if (framework === "langchain") return /\blangchain(_core|_community|_openai)?\b/;
  if (framework === "langgraph") return /\blanggraph\b/;
  if (framework === "strands") return /\bstrands\b/;
  if (framework === "agentcore") return /\bbedrock_agentcore\b|\bBedrockAgentCoreApp\b/;
  return /\bgoogle\.adk\b|\bveadk\b/;
}
function objectPattern(object) {
  const root = object.split(".")[0];
  return new RegExp(
    [
      `(^|\\n)\\s*(class|def|async\\s+def)\\s+${root}\\b`,
      `(^|\\n)\\s*${root}\\s*=`,
      `(^|\\n)\\s*from\\s+[A-Za-z0-9_.]+\\s+import\\s+.*\\b${root}\\b`,
      `(^|\\n)\\s*import\\s+.*\\bas\\s+${root}\\b`,
      `(^|\\n)\\s*import\\s+${root}\\b`
    ].join("|"),
    "m"
  );
}
function scanProject(input) {
  const projectDir = resolve2(input.projectDir);
  if (!existsSync2(projectDir) || !statSync(projectDir).isDirectory()) {
    throw new Error(`Project directory does not exist: ${projectDir}`);
  }
  const projectDirReal = realpathSync(projectDir);
  const entryAbs = resolveProjectPath(projectDir, input.entry.file);
  assertInside(projectDir, entryAbs, "Entry file");
  if (!existsSync2(entryAbs) || !statSync(entryAbs).isFile()) {
    throw new Error(`Entry file does not exist: ${input.entry.file}`);
  }
  assertInside(projectDirReal, realpathSync(entryAbs), "Entry file");
  const entrySource = readFileSync3(entryAbs, "utf8");
  if (!objectPattern(input.entry.object).test(entrySource)) {
    throw new Error(`Entry object "${input.entry.object}" was not found by static scan in ${input.entry.file}.`);
  }
  const pattern = frameworkPattern(input.framework);
  const hasFrameworkSignal = listPythonFiles(projectDir).some((file) => pattern.test(readFileSync3(file, "utf8")));
  const warnings = [];
  if (!hasFrameworkSignal) {
    const message = `No ${input.framework} import was found by static scan.`;
    if (!input.force) {
      throw new Error(`${message} Re-run with --force if the entry is generated dynamically.`);
    }
    warnings.push(message);
  }
  return { warnings };
}

// src/runtime/defaults.ts
var DEFAULT_RUNTIME_RESOURCES = {
  cpuMilli: 2e3,
  memoryMb: 4096,
  minInstance: 1
};

// src/release/dockerfile.ts
var PYTHON_BASE_IMAGE_BY_PROVIDER = {
  volcengine: "agentkit-prod-public-cn-beijing.cr.volces.com/base/py-simple:python3.12-bookworm-slim-latest",
  byteplus: "agentkit-prod-public-ap-southeast-1.cr.bytepluses.com/base/py-simple:python3.12-bookworm-slim-latest"
};

// src/migrate/render.ts
function pyString(value) {
  return JSON.stringify(value);
}
function pyTuple(values) {
  return `(${values.map(pyString).join(", ")}${values.length === 1 ? "," : ""})`;
}
function renderEnvBlock(envs) {
  const entries = Object.entries(envs ?? {});
  if (entries.length === 0) return "envs: {}";
  return ["envs:", ...entries.map(([key, value]) => `  ${key}: ${pyString(value)}`)].join("\n");
}
function renderAgentkitYaml(input) {
  const cloudProvider = input.cloudProvider ?? "volcengine";
  const region = input.region ?? (cloudProvider === "byteplus" ? "ap-southeast-1" : "cn-beijing");
  return `# agentkit.yaml - generated by agentkit migrate.
name: ${pyString(input.name)}
cloud_provider: ${cloudProvider}
region: ${region}
project: ${pyString(input.project)}
dockerfile: .agentkit/Dockerfile

runtime:
  cpu_milli: ${DEFAULT_RUNTIME_RESOURCES.cpuMilli}
  memory_mb: ${DEFAULT_RUNTIME_RESOURCES.memoryMb}
  min_instance: ${DEFAULT_RUNTIME_RESOURCES.minInstance}
  max_instance: 5
  max_concurrency: 20

# Add environment variables required by the original agent, using
# \${VAR:?message} for secrets that must be supplied at deploy time.
${renderEnvBlock(input.envs)}

infrastructure:
  container_registry:
    instance_name: Auto
    namespace_name: agentkit
    repo_name: ${pyString(input.name)}
  tos:
    bucket_name: Auto
    object_prefix: agentkit-builds
`;
}
function renderDockerfile(input) {
  const workdir = input.outputDir === "." ? "" : `WORKDIR /app/${input.outputDir}
`;
  const cloudProvider = input.cloudProvider ?? "volcengine";
  const baseImage = PYTHON_BASE_IMAGE_BY_PROVIDER[cloudProvider];
  if (input.installStrategy === "uv-sync") {
    return `# Cloud builds use the provider-hosted Python base image from agentkit init.
FROM ${baseImage}

ENV UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY . .
RUN uv sync --no-dev --all-packages \\
    && uv pip install --python /app/.venv/bin/python -r requirements.txt
${workdir}
EXPOSE 8000
CMD ["/app/.venv/bin/python", "agentkit_app.py"]
`;
  }
  return `# Cloud builds use the provider-hosted Python base image from agentkit init.
FROM ${baseImage}

ENV UV_SYSTEM_PYTHON=1 UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY . .
RUN uv pip install -r requirements.txt
${workdir}
EXPOSE 8000
CMD ["python", "agentkit_app.py"]
`;
}
function renderDockerignore() {
  return `.git
.agentkit
node_modules
.venv
venv
__pycache__/
*.py[cod]
.pytest_cache
.ruff_cache
.mypy_cache
dist
target
coverage
.DS_Store
.env
.env.*
*.log
`;
}
function renderEntryLoader(input) {
  return `_source_agent = load_entry_object(
    file=${pyString(input.entryFileFromApp)},
    module=${input.entryModule ? pyString(input.entryModule) : "None"},
    object_path=${pyString(input.entryObject)},
    call_factory=${input.callFactory ? "True" : "False"},
    project_root=${pyString(input.projectRootFromApp)},
    base_dir=Path(__file__).resolve().parent,
)
`;
}
function renderObjectLoader(input) {
  return `def _load_${input.name}():
    return load_entry_object(
        file=${pyString(input.fileFromApp)},
        module=${input.module ? pyString(input.module) : "None"},
        object_path=${pyString(input.object)},
        project_root=${pyString(input.projectRootFromApp)},
        base_dir=Path(__file__).resolve().parent,
        import_name=${pyString(`agentkit_migrated_${input.name}`)},
    )
`;
}
function renderRootAgent(input) {
  if (input.framework === "langchain") {
    const inputKey = input.inputKey ? `
    input_key=${pyString(input.inputKey)},` : "";
    return `root_agent = LangChainAgentkitBridge(
    _source_agent,
    name=${pyString(input.agentName)},
    description="LangChain agent adapted for AgentKit runtime",${inputKey}
)`;
  }
  if (input.framework === "langgraph") {
    const inputKey = input.inputKey ? `
    input_key=${pyString(input.inputKey)},` : "";
    const streamNodes = input.streamNodes && input.streamNodes.length > 0 ? `
    stream_nodes=${pyTuple(input.streamNodes)},` : "";
    const graphFactory = input.graphFactory ? `
    graph_factory=True,` : "";
    return `root_agent = LangGraphAgentkitBridge(
    _source_agent,
    name=${pyString(input.agentName)},
    description="LangGraph agent adapted for AgentKit runtime",${inputKey}${streamNodes}${graphFactory}
)`;
  }
  if (input.framework === "strands") {
    return `root_agent = StrandsAgentkitBridge(
    _source_agent,
    name=${pyString(input.agentName)},
    description="Strands agent adapted for AgentKit runtime",
    agent_factory=${input.callFactory ? "True" : "False"},
)`;
  }
  if (input.framework === "agentcore") {
    return `root_agent = BedrockAgentCoreAgentkitBridge(
    _source_agent,
    name=${pyString(input.agentName)},
    description="Bedrock AgentCore entrypoint adapted for AgentKit runtime",
)`;
  }
  return "root_agent = _source_agent";
}
function renderCompatImports(input) {
  if (input.compat?.profile === "langserve") {
    return "from agentkit.frameworks.serving.langserve import attach_langserve_compat_routes\n";
  }
  if (input.compat?.profile === "fastapi-mount") {
    return "from agentkit.frameworks.serving.fastapi_mount import mount_legacy_fastapi_app\n";
  }
  return "";
}
function renderCompatAttach(input) {
  if (!input.compat) return "";
  if (input.compat.profile === "langserve") {
    const prefix = input.compat.prefix === "/" ? "" : input.compat.prefix;
    return `
attach_langserve_compat_routes(
    app,
    _source_agent,
    input_key=${pyString(input.compat.inputKey ?? "input")},
    prefix=${pyString(prefix)},
)
`;
  }
  if (input.compat.profile === "fastapi-mount") {
    return `
mount_legacy_fastapi_app(
    app,
    _load_legacy_app(),
    prefix=${pyString(input.compat.prefix)},
    allow_root=${input.compat.prefix === "/" ? "True" : "False"},
)
`;
  }
  return "";
}
function renderModelReplacementBootstrap(input) {
  if (!input) return "";
  const lines = [`os.environ.setdefault("ARK_MODEL_REPLACEMENT", "ark")`];
  if (input.modelId) {
    lines.push(`os.environ.setdefault("ARK_MODEL_ID", ${pyString(input.modelId)})`);
  }
  const defaultBaseUrl = input.cloudProvider === "byteplus" ? "https://ark.ap-southeast.bytepluses.com/api/v3" : "https://ark.cn-beijing.volces.com/api/v3";
  lines.push(`os.environ.setdefault("ARK_BASE_URL", ${pyString(input.modelBaseUrl ?? defaultBaseUrl)})`);
  if (input.apiKeyEnv && input.apiKeyEnv !== "ARK_API_KEY") {
    lines.push(
      `if "ARK_API_KEY" not in os.environ and ${pyString(input.apiKeyEnv)} in os.environ:`,
      `    os.environ["ARK_API_KEY"] = os.environ[${pyString(input.apiKeyEnv)}]`
    );
  }
  lines.push("apply_agentkit_model_replacement()");
  return `
${lines.join("\n")}
`;
}
function renderLangGraphServerApp(input) {
  const modelReplacementImport = input.modelReplacement ? "from agentkit.frameworks.model_replacement import apply_agentkit_model_replacement\n" : "";
  const frameworkBootstrap = renderModelReplacementBootstrap(input.modelReplacement);
  const osImport = input.modelReplacement ? "import os\n" : "";
  const graphId = input.graphId ? `,
    graph_id=${pyString(input.graphId)}` : "";
  const inputKey = input.inputKey ? `,
    input_key=${pyString(input.inputKey)}` : "";
  const allowBlocking = input.allowBlocking ? ",\n    allow_blocking=True" : "";
  return `"""AgentKit LangGraph Server wrapper generated by \`agentkit migrate\`."""

${osImport}

from agentkit.apps import AgentkitLangGraphServerApp
${modelReplacementImport}
${frameworkBootstrap}

server = AgentkitLangGraphServerApp(
    config_path=${pyString(input.configPathFromApp)}${graphId}${inputKey}${allowBlocking}
)
app = server.app


if __name__ == "__main__":
    server.run(host="0.0.0.0", port=8000)
`;
}
function renderAgentkitApp(input) {
  const loader = renderEntryLoader({
    entryFileFromApp: input.entryFileFromApp,
    entryModule: input.entryModule,
    entryObject: input.entryObject,
    callFactory: input.framework === "strands" ? false : input.callFactory,
    projectRootFromApp: input.projectRootFromApp
  });
  const legacyLoader = input.compat?.legacyApp ? renderObjectLoader({
    name: "legacy_app",
    fileFromApp: input.compat.legacyApp.fileFromApp,
    module: input.compat.legacyApp.module,
    object: input.compat.legacyApp.object,
    projectRootFromApp: input.projectRootFromApp
  }) : "";
  const bridgeImport = input.framework === "langchain" ? "from agentkit.frameworks.langchain import LangChainAgentkitBridge\n" : input.framework === "langgraph" ? "from agentkit.frameworks.langgraph import LangGraphAgentkitBridge\n" : input.framework === "strands" ? "from agentkit.frameworks.strands import StrandsAgentkitBridge\n" : input.framework === "agentcore" ? "from agentkit.frameworks.agentcore import BedrockAgentCoreAgentkitBridge, attach_bedrock_agentcore_compat_routes\n" : "";
  const modelReplacementImport = input.modelReplacement ? "from agentkit.frameworks.model_replacement import apply_agentkit_model_replacement\n" : "";
  const compatImport = renderCompatImports({ compat: input.compat });
  const rootAgent = renderRootAgent({
    framework: input.framework,
    agentName: input.agentName,
    inputKey: input.inputKey,
    streamNodes: input.streamNodes,
    callFactory: input.callFactory,
    graphFactory: input.graphFactory
  });
  const compatAttach = renderCompatAttach({ compat: input.compat });
  const frameworkAttach = input.framework === "agentcore" ? "\nattach_bedrock_agentcore_compat_routes(app, _source_agent)\n" : "";
  const frameworkBootstrap = renderModelReplacementBootstrap(input.modelReplacement);
  const osImport = input.modelReplacement ? "import os\n" : "";
  return `"""AgentKit runtime wrapper generated by \`agentkit migrate\`."""

from pathlib import Path
${osImport}

from agentkit.apps import AgentkitAgentServerApp
from agentkit.frameworks.migration import load_entry_object
${bridgeImport}
${modelReplacementImport}
${compatImport}
${frameworkBootstrap}
${loader}
${legacyLoader}

${rootAgent}

server = AgentkitAgentServerApp(agent=root_agent)
app = server.app
${compatAttach}
${frameworkAttach}


if __name__ == "__main__":
    server.run(host="0.0.0.0", port=8000)
`;
}

// src/migrate/project.ts
var DEFAULT_MIGRATION_PROJECT = "default";
function resolveMigrationProject(value) {
  const project = value === void 0 ? DEFAULT_MIGRATION_PROJECT : value.trim();
  if (!project) throw new Error("Project must not be empty.");
  if (/[\r\n\u0000]/.test(project)) throw new Error("Project must not contain line breaks.");
  return project;
}

// src/migrate/verify.ts
import { execFileSync } from "child_process";
var DEFAULT_VERIFY_TIMEOUT_SECONDS = 180;
function verifyTimeoutSeconds() {
  const value = Number(process.env.AGENTKIT_MIGRATE_VERIFY_TIMEOUT_SECONDS);
  if (Number.isFinite(value) && value > 0) return value;
  return DEFAULT_VERIFY_TIMEOUT_SECONDS;
}
function verificationScript(framework, timeoutSeconds, serverMode) {
  const frameworkLiteral = JSON.stringify(framework);
  const serverModeLiteral = JSON.stringify(serverMode);
  return `
import asyncio
import json
import sys
import traceback


checks = []
VERIFY_PROMPT = "\u8BF7\u53EA\u56DE\u590D OK\u3002\u4E0D\u8981\u8C03\u7528\u5DE5\u5177\uFF0C\u4E0D\u8981\u89E3\u91CA\u3002"


def record(name, passed, detail=None):
    item = {"name": name, "status": "passed" if passed else "failed"}
    if detail:
        item["detail"] = str(detail)[:1000]
    checks.append(item)


def response_failure_detail(body):
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            event = json.loads(data)
        except Exception:
            continue
        event_type = str(event.get("type") or event.get("event") or "").lower()
        if "failed" in event_type or event_type == "error":
            return json.dumps(event, ensure_ascii=False)[:1000]
        if event.get("error") or event.get("exception"):
            return json.dumps(event, ensure_ascii=False)[:1000]
        payload = event.get("payload")
        if isinstance(payload, dict) and payload.get("reason") in {"error", "timeout", "aborted"}:
            return json.dumps(event, ensure_ascii=False)[:1000]
    return None


async def main():
    try:
        import agentkit_app

        record("import agentkit_app", True)
        server = getattr(agentkit_app, "server", None)
        app = getattr(agentkit_app, "app", None)
        expected_server = "AgentkitLangGraphServerApp" if ${serverModeLiteral} == "langgraph" else "AgentkitAgentServerApp"
        record(f"{expected_server} is exposed", type(server).__name__ == expected_server, type(server).__name__)
        if app is None:
            raise RuntimeError("agentkit_app.app is missing")

        routes = {getattr(route, "path", "") for route in app.router.routes}
        record("/run_sse route is mounted", "/run_sse" in routes)
        if ${serverModeLiteral} == "langgraph":
            from starlette.testclient import TestClient
            from google.genai import types

            has_native_mount = any(
                type(route).__name__ == "Mount" and getattr(route, "path", None) in ("", "/")
                for route in app.router.routes
            )
            record("LangGraph native route mount is preserved", has_native_mount)
            with TestClient(app) as client:
                native = client.get("/ok")
                record("LangGraph native /ok route returns 2xx", 200 <= native.status_code < 300, f"HTTP {native.status_code}: {native.text[:300]}")
                apps = client.get("/list-apps")
                record("AgentKit /list-apps route returns 2xx", 200 <= apps.status_code < 300, f"HTTP {apps.status_code}: {apps.text[:300]}")
                app_payload = apps.json() if 200 <= apps.status_code < 300 else []
                app_name = app_payload[0] if isinstance(app_payload, list) and app_payload else "agent"
                session = client.post(f"/apps/{app_name}/users/agentkit-verify-user/sessions/agentkit-verify-session", json={})
                record("AgentKit session create route returns 2xx", 200 <= session.status_code < 300, f"HTTP {session.status_code}: {session.text[:300]}")
                response = client.post(
                    "/run_sse",
                    json={
                        "appName": app_name,
                        "userId": "agentkit-verify-user",
                        "sessionId": "agentkit-verify-session",
                        "newMessage": types.UserContent(parts=[types.Part(text=VERIFY_PROMPT)]).model_dump(exclude_none=True, by_alias=True),
                        "streaming": True,
                    },
                )
                failure = response_failure_detail(response.text)
                record(
                    "AgentKit /run_sse executes through LangGraph Server",
                    bool(response.text) and 200 <= response.status_code < 300 and failure is None,
                    "empty response" if not response.text else failure or f"HTTP {response.status_code}: {response.text[:300]}",
                )
            return
        if ${frameworkLiteral} == "agentcore":
            record("/invocations route is mounted", "/invocations" in routes)
            record("/ping route is mounted", "/ping" in routes)

        import httpx
        from google.genai import types
        from google.adk.cli.adk_web_server import RunAgentRequest

        agent_loader = agentkit_app.server.server.agent_loader
        app_name = agent_loader.list_agents()[0]
        await agentkit_app.server.server.session_service.create_session(
            app_name=app_name,
            user_id="agentkit-verify-user",
            session_id="agentkit-verify-session",
        )

        endpoint = next(
            route.endpoint
            for route in app.router.routes
            if getattr(route, "path", None) == "/run_sse" and "POST" in getattr(route, "methods", set())
        )
        response = await endpoint(
            RunAgentRequest(
                appName=app_name,
                userId="agentkit-verify-user",
                sessionId="agentkit-verify-session",
                newMessage=types.UserContent(parts=[types.Part(text=VERIFY_PROMPT)]),
                streaming=True,
            )
        )
        body_parts = []
        async for chunk in response.body_iterator:
            body_parts.append(chunk.decode() if isinstance(chunk, bytes) else str(chunk))
        body = "".join(body_parts)
        failure = response_failure_detail(body)
        record(
            "/run_sse executes successfully",
            bool(body) and failure is None,
            "empty response" if not body else failure,
        )

        if ${frameworkLiteral} == "agentcore":
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://agentkit-verify") as client:
                ping = await client.get("/ping")
                record("/ping returns 2xx", 200 <= ping.status_code < 300, f"HTTP {ping.status_code}: {ping.text[:300]}")
                invocation = await client.post(
                    "/invocations",
                    headers={"X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": "agentkit-verify-agentcore-session"},
                    json={"prompt": VERIFY_PROMPT},
                )
                invocation_failure = response_failure_detail(invocation.text)
                record(
                    "/invocations accepts JSON payload",
                    200 <= invocation.status_code < 300 and invocation_failure is None,
                    invocation_failure or f"HTTP {invocation.status_code}: {invocation.text[:300]}",
                )
    except Exception as exc:
        record("verification runtime", False, f"{type(exc).__name__}: {exc}\\n{traceback.format_exc(limit=8)}")

async def run_verify():
    try:
        await asyncio.wait_for(main(), timeout=${timeoutSeconds})
    except Exception as exc:
        record("verification runtime", False, f"{type(exc).__name__}: {exc}\\n{traceback.format_exc(limit=8)}")

    ok = all(item["status"] == "passed" for item in checks)
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False))
    if not ok:
        sys.exit(1)


asyncio.run(run_verify())
`;
}
function parseVerificationOutput(output) {
  const line = output.trim().split(/\r?\n/).reverse().find((item) => item.startsWith("{"));
  if (!line) return void 0;
  const parsed = JSON.parse(line);
  if (typeof parsed.ok !== "boolean" || !Array.isArray(parsed.checks)) return void 0;
  return {
    ok: parsed.ok,
    checks: parsed.checks.map((item) => {
      const value = item;
      return {
        name: typeof value.name === "string" ? value.name : "unknown",
        status: value.status === "passed" ? "passed" : "failed",
        ...typeof value.detail === "string" ? { detail: value.detail } : {}
      };
    })
  };
}
function verifyGeneratedMigration(input) {
  const python = input.python || process.env.AGENTKIT_MIGRATE_PYTHON || "python3";
  const timeoutSeconds = verifyTimeoutSeconds();
  let output = "";
  try {
    output = execFileSync(python, ["-c", verificationScript(input.framework, timeoutSeconds, input.serverMode ?? "agentkit")], {
      cwd: input.outputDirAbs,
      encoding: "utf8",
      env: {
        ...process.env,
        PYTHONWARNINGS: process.env.PYTHONWARNINGS || "ignore"
      },
      timeout: (timeoutSeconds + 10) * 1e3
    });
  } catch (err) {
    const failedOutput = err instanceof Error && "stdout" in err ? String(err.stdout ?? "") : "";
    const failedParsed = parseVerificationOutput(failedOutput);
    if (failedParsed) {
      return {
        status: "failed",
        python,
        checks: failedParsed.checks
      };
    }
    const message = err instanceof Error ? err.message : String(err);
    return {
      status: "failed",
      python,
      checks: [
        {
          name: "verification process",
          status: "failed",
          detail: message
        }
      ]
    };
  }
  const parsed = parseVerificationOutput(output);
  if (!parsed) {
    return {
      status: "failed",
      python,
      checks: [
        {
          name: "verification output",
          status: "failed",
          detail: output.slice(-1e3)
        }
      ]
    };
  }
  return {
    status: parsed.ok ? "passed" : "failed",
    python,
    checks: parsed.checks
  };
}

// src/platform/constants.ts
var DEFAULT_REGION = "cn-beijing";
var DEFAULT_REGION_BY_PROVIDER = {
  volcengine: DEFAULT_REGION,
  byteplus: "ap-southeast-1"
};

// src/migrate/index.ts
var EXCLUDED_OUTPUT_ROOTS = /* @__PURE__ */ new Set([".agentkit", ".git", ".venv", "__pycache__", "dist", "node_modules", "target", "venv"]);
var RUNTIME_NAME_PATTERN = /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/;
var PY_IDENTIFIER_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/;
var ENV_IDENTIFIER_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/;
var COMPAT_PREFIX_PATTERN = /^\/[A-Za-z0-9._~!$&'()*+,;=:@%/-]*$/;
var DEPRECATED_AGENTCORE_MODEL_ENV_KEYS = /* @__PURE__ */ new Set([
  "AGENTKIT_MODEL_ID",
  "AGENTKIT_MODEL_API_KEY",
  "AGENTKIT_MODEL_BASE_URL",
  "AGENTKIT_MODEL_REPLACEMENT"
]);
var MODEL_REPLACEMENT_ALIAS_ENV_KEYS = /* @__PURE__ */ new Set([
  "BEDROCK_MODEL_ID",
  "DEFAULT_MODEL",
  "MODEL_ID",
  "MODEL_NAME",
  "OPENAI_BASE_URL",
  "OPENAI_API_BASE",
  "OPENAI_API_KEY"
]);
var CONFIG_ENV_REFERENCE_PATTERN = /\$(?:\{([A-Z_][A-Z0-9_]*)(?::[-?][^}]*)?\}|([A-Z_][A-Z0-9_]*))/g;
var CONFIG_ENV_FILE_PATTERN = /^(?:[A-Za-z0-9_.-]+)\.(?:ya?ml|json|toml)$/;
var IGNORED_CONFIG_ENV_FILES = /* @__PURE__ */ new Set(["package-lock.json", "pnpm-lock.yaml", "uv.lock"]);
var LANGGRAPH_CUSTOM_CHECKPOINTER_PATTERN = /\.compile\s*\([\s\S]*?checkpointer\s*=/m;
function parseLangGraphServerEntry(projectDir, rawEntry) {
  const sep2 = rawEntry.lastIndexOf(":");
  const file = sep2 > 0 ? rawEntry.slice(0, sep2) : rawEntry;
  const requestedGraphId = sep2 > 0 ? rawEntry.slice(sep2 + 1) : void 0;
  if (!file.endsWith(".json")) {
    throw new Error("LangGraph server mode entry must be a langgraph.json file, optionally followed by :graph_id.");
  }
  if (requestedGraphId !== void 0 && requestedGraphId.length === 0) {
    throw new Error("LangGraph server mode graph id must not be empty.");
  }
  const configPath = resolveProjectPath(projectDir, file);
  assertInside(projectDir, configPath, "LangGraph config file");
  if (!existsSync3(configPath) || !statSync2(configPath).isFile()) {
    throw new Error(`LangGraph config file does not exist: ${file}`);
  }
  let config;
  try {
    config = JSON.parse(readFileSync4(configPath, "utf8"));
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    throw new Error(`LangGraph config file is not valid JSON: ${message}`);
  }
  const graphs = config && typeof config === "object" ? config.graphs : void 0;
  if (!graphs || typeof graphs !== "object" || Array.isArray(graphs)) {
    throw new Error("LangGraph server mode requires langgraph.json to define a graphs object.");
  }
  const graphIds = Object.keys(graphs);
  if (graphIds.length === 0) {
    throw new Error("LangGraph server mode requires at least one graph in langgraph.json.");
  }
  if (requestedGraphId) {
    if (!Object.prototype.hasOwnProperty.call(graphs, requestedGraphId)) {
      throw new Error(`Graph id "${requestedGraphId}" was not found in ${file}. Available: ${graphIds.join(", ")}.`);
    }
    return { file, object: requestedGraphId };
  }
  if (graphIds.length > 1) {
    throw new Error(`Multiple graphs found in ${file}. Use --entry ${file}:<graph_id>. Available: ${graphIds.join(", ")}.`);
  }
  return { file, object: graphIds[0] };
}
function langGraphServerGraphSource(value) {
  if (typeof value === "string") return value;
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const path = value.path;
    if (typeof path === "string") return path;
  }
  return void 0;
}
function langGraphServerSourceWarnings(projectDir, configFile) {
  const configPath = resolveProjectPath(projectDir, configFile);
  let config;
  try {
    config = JSON.parse(readFileSync4(configPath, "utf8"));
  } catch {
    return [];
  }
  const graphs = config && typeof config === "object" ? config.graphs : void 0;
  if (!graphs || typeof graphs !== "object" || Array.isArray(graphs)) return [];
  const graphIdsWithCustomCheckpointer = [];
  const scannedFiles = /* @__PURE__ */ new Set();
  for (const [graphId, graphConfig] of Object.entries(graphs)) {
    const source = langGraphServerGraphSource(graphConfig);
    if (!source || !source.includes(":")) continue;
    const moduleOrPath = source.slice(0, source.lastIndexOf(":"));
    if (!moduleOrPath.endsWith(".py") && !moduleOrPath.includes("/")) continue;
    const graphFile = resolveProjectPath(projectDir, moduleOrPath);
    try {
      assertInside(projectDir, graphFile, "LangGraph graph source file");
    } catch {
      continue;
    }
    if (scannedFiles.has(graphFile)) continue;
    scannedFiles.add(graphFile);
    if (!existsSync3(graphFile) || !statSync2(graphFile).isFile()) continue;
    if (LANGGRAPH_CUSTOM_CHECKPOINTER_PATTERN.test(readFileSync4(graphFile, "utf8"))) {
      graphIdsWithCustomCheckpointer.push(graphId);
    }
  }
  if (graphIdsWithCustomCheckpointer.length === 0) return [];
  return [
    `Detected custom checkpointer usage in LangGraph Server graph source (${graphIdsWithCustomCheckpointer.join(", ")}). Official LangGraph Server manages persistence; remove graph.compile(checkpointer=...) or verify that the source project can be loaded by LangGraph Server before deploying.`
  ];
}
function runtimeName(name) {
  const normalized = name.trim().toLowerCase().replace(/\s+/g, "-");
  const nonEmpty = normalized || "agent";
  if (!RUNTIME_NAME_PATTERN.test(nonEmpty)) {
    throw new Error(
      `AgentKit runtime name "${name}" is invalid. Use 1-63 lowercase letters, digits, or hyphens, starting and ending with a letter or digit.`
    );
  }
  return nonEmpty;
}
function agentName(name) {
  const sanitized = name.replace(/[^A-Za-z0-9_]/g, "_").replace(/^([0-9])/, "_$1");
  const nonEmpty = sanitized || "agent";
  return nonEmpty === "user" ? "agent_user" : nonEmpty;
}
function bridgeInputKey(input) {
  const value = input.inputKey?.trim();
  if (!value) return void 0;
  if (input.framework !== "langchain" && input.framework !== "langgraph") {
    throw new Error("--input-key is only supported for LangChain and LangGraph migrations.");
  }
  if (input.framework === "langgraph" && value === "messages") {
    throw new Error(
      [
        "--input-key messages is not valid for standard LangGraph message graphs.",
        "Omit --input-key so AgentKit can pass {'messages': [HumanMessage(...)]}.",
        "Use --input-key only for custom state fields such as question or input."
      ].join(" ")
    );
  }
  return value;
}
function bridgeStreamNodes(input) {
  const values = (input.streamNodes ?? []).map((value) => value.trim()).filter(Boolean);
  if (values.length === 0) return void 0;
  if (input.framework !== "langgraph") {
    throw new Error("--stream-node is only supported for LangGraph migrations.");
  }
  return [...new Set(values)];
}
function normalizeCompatPrefix(prefix) {
  const value = prefix.trim();
  if (!value || !COMPAT_PREFIX_PATTERN.test(value)) {
    throw new Error(`Compatibility prefix "${prefix}" is invalid. Use an absolute URL path such as /compat or /legacy.`);
  }
  return value === "/" ? "/" : value.replace(/\/+$/, "");
}
function compatDefaultPrefix(profile) {
  if (profile === "fastapi-mount") return "/legacy";
  return "/";
}
function compatEndpoints(profile, prefix) {
  const joinPrefix = (path) => prefix === "/" ? path : `${prefix}${path}`;
  if (profile === "langserve") {
    return ["/invoke", "/batch", "/stream", "/stream_events", "/stream_log"].map(joinPrefix);
  }
  if (profile === "fastapi-mount") return [prefix];
  return [];
}
function resolveCompat(input) {
  const profile = input.compat ?? "none";
  if (!isCompatProfile(profile)) {
    throw new Error(`Unsupported compat profile "${String(profile)}".`);
  }
  if (profile === "none") {
    if (input.compatPrefix) throw new Error("--compat-prefix requires --compat.");
    if (input.legacyApp) throw new Error("--legacy-app requires --compat fastapi-mount.");
    return { profile, warnings: [] };
  }
  if (profile === "langserve" && input.framework !== "langchain") {
    throw new Error("--compat langserve is only supported for LangChain migrations.");
  }
  if (profile === "fastapi-mount" && !input.legacyApp) {
    throw new Error("--compat fastapi-mount requires --legacy-app <file.py:app>.");
  }
  if (profile !== "fastapi-mount" && input.legacyApp) {
    throw new Error("--legacy-app is only supported with --compat fastapi-mount.");
  }
  const prefix = normalizeCompatPrefix(input.compatPrefix ?? compatDefaultPrefix(profile));
  const legacyApp = input.legacyApp ? parseEntryReference(input.legacyApp) : void 0;
  const warnings = [];
  if (profile === "fastapi-mount" && prefix === "/") {
    warnings.push("Mounting a legacy FastAPI app at / can shadow AgentKit routes. Prefer --compat-prefix /legacy unless full root compatibility is required.");
  }
  return { profile, prefix, legacyApp, warnings };
}
function artifact(path, exists, force) {
  return { path, action: exists && force ? "overwrite" : exists ? "update" : "create" };
}
function assertNoConflicts(projectDir, artifacts, force) {
  if (force) return;
  const conflicts = artifacts.filter((item) => item.action === "update" && item.path !== "requirements.txt");
  if (conflicts.length > 0) {
    throw new Error(
      [
        `This project already contains AgentKit migration artifacts: ${conflicts.map((item) => item.path).join(", ")}.`,
        "agentkit migrate does not overwrite generated files by default.",
        "Re-run with --force to regenerate the selected output.",
        "For side-by-side app code, use --output <dir> --force; .agentkit config is shared per project and will be refreshed."
      ].join(" ")
    );
  }
  for (const item of artifacts) {
    if (item.path === "requirements.txt") continue;
    const abs = join3(projectDir, item.path);
    if (existsSync3(abs)) {
      throw new Error(
        [
          `Generated file already exists: ${item.path}.`,
          "agentkit migrate does not overwrite generated files by default.",
          "Re-run with --force to regenerate the selected output.",
          "For side-by-side app code, use --output <dir> --force; .agentkit config is shared per project and will be refreshed."
        ].join(" ")
      );
    }
  }
}
function entryModuleName(projectDir, entryAbs) {
  const rel = toPosix(relative3(projectDir, entryAbs));
  if (!rel.endsWith(".py")) return void 0;
  const modulePath = rel.slice(0, -3);
  const parts = modulePath.endsWith("/__init__") ? modulePath.slice(0, -"/__init__".length).split("/") : modulePath.split("/");
  const moduleParts = parts.filter(Boolean);
  if (moduleParts.length === 0 || !moduleParts.every((part) => PY_IDENTIFIER_PATTERN.test(part))) return void 0;
  return moduleParts.join(".");
}
function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
function matchingParenIndex(source, openIndex) {
  let depth = 0;
  let quote;
  let tripleQuote = false;
  for (let index = openIndex; index < source.length; index += 1) {
    const char = source[index];
    const next3 = source.slice(index, index + 3);
    if (quote) {
      if (char === "\\" && !tripleQuote) {
        index += 1;
        continue;
      }
      if (tripleQuote && next3 === quote.repeat(3)) {
        index += 2;
        quote = void 0;
        tripleQuote = false;
        continue;
      }
      if (!tripleQuote && char === quote) quote = void 0;
      continue;
    }
    if (next3 === "'''" || next3 === '"""') {
      quote = char;
      tripleQuote = true;
      index += 2;
      continue;
    }
    if (char === "'" || char === '"') {
      quote = char;
      continue;
    }
    if (char === "(") depth += 1;
    if (char === ")") {
      depth -= 1;
      if (depth === 0) return index;
    }
  }
  return -1;
}
function splitTopLevelCommas(value) {
  const parts = [];
  let start = 0;
  let depth = 0;
  let quote;
  let tripleQuote = false;
  for (let index = 0; index < value.length; index += 1) {
    const char = value[index];
    const next3 = value.slice(index, index + 3);
    if (quote) {
      if (char === "\\" && !tripleQuote) {
        index += 1;
        continue;
      }
      if (tripleQuote && next3 === quote.repeat(3)) {
        index += 2;
        quote = void 0;
        tripleQuote = false;
        continue;
      }
      if (!tripleQuote && char === quote) quote = void 0;
      continue;
    }
    if (next3 === "'''" || next3 === '"""') {
      quote = char;
      tripleQuote = true;
      index += 2;
      continue;
    }
    if (char === "'" || char === '"') {
      quote = char;
      continue;
    }
    if ("([{".includes(char)) depth += 1;
    if (")]}".includes(char)) depth -= 1;
    if (char === "," && depth === 0) {
      parts.push(value.slice(start, index));
      start = index + 1;
    }
  }
  parts.push(value.slice(start));
  return parts;
}
function hasTopLevelEquals(value) {
  let depth = 0;
  let quote;
  for (let index = 0; index < value.length; index += 1) {
    const char = value[index];
    if (quote) {
      if (char === "\\") {
        index += 1;
        continue;
      }
      if (char === quote) quote = void 0;
      continue;
    }
    if (char === "'" || char === '"') {
      quote = char;
      continue;
    }
    if ("([{".includes(char)) depth += 1;
    if (")]}".includes(char)) depth -= 1;
    if (char === "=" && depth === 0) return true;
  }
  return false;
}
function factoryParamName(param) {
  const name = param.split(":", 1)[0]?.split("=", 1)[0]?.trim();
  return name || void 0;
}
function factoryParamAnalysis(signature) {
  const names = [];
  const required = [];
  for (const rawParam of splitTopLevelCommas(signature)) {
    const param = rawParam.trim();
    if (!param || param === "/" || param === "*" || param.startsWith("*")) continue;
    const name = factoryParamName(param);
    if (!name) continue;
    names.push(name);
    if (hasTopLevelEquals(param)) continue;
    required.push(name);
  }
  return { names, required };
}
function entryFactoryAnalysis(entryAbs, entryObject) {
  const rootObject = entryObject.split(".")[0];
  if (entryObject.includes(".")) {
    return { callFactory: false, graphFactory: false, paramNames: [], requiredParams: [], isAsync: false, warnings: [] };
  }
  const source = readFileSync4(entryAbs, "utf8");
  const functionPattern = new RegExp(`(^|\\n)(async\\s+)?def\\s+${escapeRegExp(rootObject)}\\s*\\(`);
  const match = functionPattern.exec(source);
  if (!match) return { callFactory: false, graphFactory: false, paramNames: [], requiredParams: [], isAsync: false, warnings: [] };
  const openIndex = match.index + match[0].lastIndexOf("(");
  const closeIndex = matchingParenIndex(source, openIndex);
  if (closeIndex < 0) {
    return {
      callFactory: false,
      graphFactory: false,
      paramNames: [],
      requiredParams: [],
      isAsync: false,
      warnings: [
        `Entry object "${entryObject}" looks like a Python function, but its signature could not be parsed. The generated app will load it without calling it.`
      ]
    };
  }
  const signature = source.slice(openIndex + 1, closeIndex);
  const params = factoryParamAnalysis(signature);
  const requiredParams = params.required;
  const isAsync = Boolean(match[2]);
  if (requiredParams.length > 0) {
    return {
      callFactory: false,
      graphFactory: false,
      paramNames: params.names,
      requiredParams,
      isAsync,
      warnings: [
        `Entry object "${entryObject}" looks like a factory function but requires parameters (${requiredParams.join(", ")}). The generated app will load it without calling it; expose a zero-argument entry if this is meant to build the agent.`
      ]
    };
  }
  if (isAsync) {
    return {
      callFactory: false,
      graphFactory: false,
      paramNames: params.names,
      requiredParams,
      isAsync,
      warnings: [
        `Entry object "${entryObject}" looks like an async zero-argument factory. Generated migration apps cannot await entry factories; expose a synchronous factory or constructed agent object.`
      ]
    };
  }
  return { callFactory: true, graphFactory: false, paramNames: params.names, requiredParams, isAsync, warnings: [] };
}
function isSecretEnvName(name) {
  return /(KEY|SECRET|TOKEN|PASSWORD|PASSWD|CREDENTIAL|ACCESS_KEY|PRIVATE)/i.test(name);
}
function looksLikePlaceholder(value) {
  const normalized = value.trim().toLowerCase();
  return !normalized || /your|todo|example|placeholder|changeme|xxx|<.*>|你的|示例/.test(normalized);
}
function hasNonAscii(value) {
  return /[^\x00-\x7F]/.test(value);
}
function deployRequiredEnv(name) {
  return `\${${name}:?set ${name} before running agentkit release}`;
}
function parseEnvExample(projectDir) {
  const envPath = join3(projectDir, ".env.example");
  if (!existsSync3(envPath)) return { envs: {}, warnings: [] };
  const envs = {};
  const warnings = [];
  for (const line of readFileSync4(envPath, "utf8").split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) continue;
    const [rawKey, ...rawValueParts] = trimmed.split("=");
    const key = rawKey.trim();
    if (!ENV_IDENTIFIER_PATTERN.test(key)) continue;
    const value = rawValueParts.join("=").trim().replace(/^['"]|['"]$/g, "");
    const isSecret = isSecretEnvName(key);
    const isPlaceholder = looksLikePlaceholder(value);
    if (isSecret || isPlaceholder) {
      envs[key] = deployRequiredEnv(key);
    } else {
      envs[key] = `\${${key}:-${value}}`;
    }
    if (isSecret && isPlaceholder) {
      warnings.push(
        `Detected placeholder-like secret value in .env.example for ${key}. Do not source .env.example for deploy; export a real ${key} value or use a local secret env file.`
      );
    }
    if (isSecret && hasNonAscii(value)) {
      warnings.push(
        `Detected non-ASCII secret value in .env.example for ${key}. HTTP auth headers require ASCII-safe secrets; export a real ${key} value before deploy.`
      );
    }
  }
  return { envs, warnings };
}
function parseConfigEnvReferences(projectDir) {
  const keys = /* @__PURE__ */ new Set();
  for (const name of readdirSync2(projectDir)) {
    if (IGNORED_CONFIG_ENV_FILES.has(name) || !CONFIG_ENV_FILE_PATTERN.test(name)) continue;
    const path = join3(projectDir, name);
    if (!statSync2(path).isFile()) continue;
    const content = readFileSync4(path, "utf8");
    for (const match of content.matchAll(CONFIG_ENV_REFERENCE_PATTERN)) {
      keys.add(match[1] ?? match[2]);
    }
  }
  return {
    envs: Object.fromEntries([...keys].sort().map((key) => [key, deployRequiredEnv(key)])),
    keys: [...keys].sort()
  };
}
function validateModelOptions(input) {
  if (input.verify && input.dryRun) {
    throw new Error("--verify cannot be used with --dry-run because no migration files are written.");
  }
  if (input.serverMode === "langgraph" && input.framework !== "langgraph") {
    throw new Error("--server-mode langgraph is only supported with --framework langgraph.");
  }
  if (input.serverMode === "langgraph" && input.compat && input.compat !== "none") {
    throw new Error("--compat is not supported with --server-mode langgraph because LangGraph Server native routes remain mounted.");
  }
  if (input.serverMode === "langgraph" && input.legacyApp) {
    throw new Error("--legacy-app is not supported with --server-mode langgraph.");
  }
  if (input.serverMode === "langgraph" && input.streamNodes && input.streamNodes.length > 0) {
    throw new Error("--stream-node is only supported by the default LangGraph AgentKit bridge mode.");
  }
  if (input.allowBlocking && input.serverMode !== "langgraph") {
    throw new Error("--allow-blocking is only supported with --server-mode langgraph.");
  }
  if (input.modelApiKeyEnv && !ENV_IDENTIFIER_PATTERN.test(input.modelApiKeyEnv)) {
    throw new Error("--model-api-key-env must be a valid environment variable name.");
  }
  if (input.modelBaseUrl && !/^https?:\/\//.test(input.modelBaseUrl)) {
    throw new Error("--model-base-url must start with http:// or https://.");
  }
}
function envDefaultOrRequired(name, value, message) {
  return value ? `\${${name}:-${value}}` : `\${${name}:?${message}}`;
}
function modelReplacementEnabled(input) {
  return Boolean(input.modelId || input.modelBaseUrl || input.modelApiKeyEnv);
}
function targetModelEnvs(input) {
  if (!modelReplacementEnabled(input)) return {};
  const modelId = envDefaultOrRequired(
    "ARK_MODEL_ID",
    input.modelId,
    "set ARK_MODEL_ID or pass --model-id before running agentkit release"
  );
  const modelBaseUrl = envDefaultOrRequired(
    "ARK_BASE_URL",
    input.modelBaseUrl ?? (input.cloudProvider === "byteplus" ? "https://ark.ap-southeast.bytepluses.com/api/v3" : "https://ark.cn-beijing.volces.com/api/v3"),
    "set ARK_BASE_URL before running agentkit release"
  );
  const apiKeyEnv = input.modelApiKeyEnv || "ARK_API_KEY";
  return {
    ARK_MODEL_REPLACEMENT: "${ARK_MODEL_REPLACEMENT:-ark}",
    ARK_MODEL_ID: modelId,
    ARK_BASE_URL: modelBaseUrl,
    ARK_API_KEY: `\${${apiKeyEnv}:?set ${apiKeyEnv} before running agentkit release}`
  };
}
function readExistingAgentkitEnvs(yamlPath) {
  if (!existsSync3(yamlPath)) return {};
  try {
    const parsed = (0, import_yaml.parse)(readFileSync4(yamlPath, "utf8")) ?? {};
    if (!parsed.envs || typeof parsed.envs !== "object" || Array.isArray(parsed.envs)) return {};
    return Object.fromEntries(Object.entries(parsed.envs).map(([key, value]) => [key, String(value)]));
  } catch {
    return {};
  }
}
function omitEnvKeys(envs, keys) {
  return Object.fromEntries(Object.entries(envs).filter(([key]) => !keys.has(key)));
}
function envKeys(envs, keys) {
  return Object.keys(envs).filter((key) => keys.has(key));
}
function outputDirRel(projectDir, outputDirAbs) {
  return toPosix(relative3(projectDir, outputDirAbs)) || ".";
}
function assertDeployableOutputDir(projectDir, outputDirAbs) {
  const rel = outputDirRel(projectDir, outputDirAbs);
  if (rel === ".") return;
  const [root] = rel.split("/");
  if (EXCLUDED_OUTPUT_ROOTS.has(root)) {
    throw new Error(
      `Output directory "${rel}" is excluded from AgentKit deploy archives. Use "." or a deployable directory such as "runtime".`
    );
  }
}
function assertNoSymlinkedOutputPath(projectDir, outputDirAbs) {
  const rel = relative3(projectDir, outputDirAbs);
  if (!rel) return;
  const projectDirReal = realpathSync2(projectDir);
  let current = projectDir;
  for (const segment of rel.split(/[\\/]+/).filter(Boolean)) {
    current = join3(current, segment);
    if (!existsSync3(current)) return;
    const stat = lstatSync(current);
    const currentRel = toPosix(relative3(projectDir, current));
    if (stat.isSymbolicLink()) {
      throw new Error(`Output directory must not pass through a symlink: ${currentRel}.`);
    }
    assertInside(projectDirReal, realpathSync2(current), "Output directory");
    if (!stat.isDirectory()) {
      throw new Error(`Output path exists but is not a directory: ${currentRel}.`);
    }
  }
}
function listPythonFiles2(dir, out = []) {
  if (!existsSync3(dir)) return out;
  for (const entry of readdirSync2(dir, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      if (!EXCLUDED_OUTPUT_ROOTS.has(entry.name)) listPythonFiles2(join3(dir, entry.name), out);
      continue;
    }
    if (entry.isFile() && entry.name.endsWith(".py")) out.push(join3(dir, entry.name));
  }
  return out;
}
function hasLangServeSignal(projectDir) {
  return listPythonFiles2(projectDir).some((file) => {
    const content = readFileSync4(file, "utf8");
    return /from\s+langserve\s+import\s+add_routes\b/.test(content) || /\blangserve\.add_routes\b/.test(content);
  });
}
function pythonContents(projectDir) {
  return listPythonFiles2(projectDir).map((file) => readFileSync4(file, "utf8"));
}
function hasAdkConfigSignal(projectDir) {
  const candidates = [
    "agent.yaml",
    "agent.yml",
    "agent_config.yaml",
    "agent_config.yml",
    join3(".adk", "agent.yaml"),
    join3(".adk", "agent.yml")
  ];
  return candidates.some((candidate) => existsSync3(join3(projectDir, candidate)));
}
function hasAnyPattern(contents, patterns) {
  return contents.some((content) => patterns.some((pattern) => pattern.test(content)));
}
function agentcoreReadiness(contents, modelReplacement) {
  const usesBedrockOrAnthropicModel = hasAnyPattern(contents, [
    /\bBedrockModel\b/,
    /\bAnthropicModel\b/,
    /\bstrands\.models\.bedrock\b/,
    /\bstrands\.models\.anthropic\b/
  ]);
  const usesTaskActions = hasAnyPattern(contents, [
    /\b_handle_task_action\b/,
    /\btaskAction\b/,
    /@app\.(async_)?task\b/
  ]);
  const usesAgentCoreContext = hasAnyPattern(contents, [
    /\bBedrockAgentCoreContext\b/,
    /\bRequestContext\b/,
    /\bWorkloadAccessToken\b/,
    /\bX-Amzn-Bedrock-AgentCore-Runtime-/
  ]);
  const usesObservability = hasAnyPattern(contents, [
    /\btrace\b/i,
    /\btracer\b/i,
    /\btelemetry\b/i,
    /\bobservability\b/i
  ]);
  const supported = [
    "Bedrock AgentCore entrypoint is wrapped as an AgentKit root agent.",
    "AgentKit native /run, /run_sse, session, and A2A routes remain available.",
    "Bedrock AgentCore-compatible /invocations and /ping routes are generated.",
    "JSON payloads, sync/async return values, and generator/async-generator streaming are supported.",
    "Request id, session id, headers, and WorkloadAccessToken are forwarded to a best-effort AgentCore request context."
  ];
  if (modelReplacement) {
    supported.push("ARK target-model replacement is enabled before loading the source entry.");
  }
  const warnings = [];
  if (usesBedrockOrAnthropicModel && !modelReplacement) {
    warnings.push(
      "Detected BedrockModel or AnthropicModel usage. Pass --model-id to enable ARK replacement if those providers are unavailable in AgentKit runtime."
    );
  }
  if (usesTaskActions) {
    warnings.push(
      "Detected AgentCore task/action signals. The compatibility route passes _handle_task_action through when present, but does not implement the full Bedrock AgentCore task protocol."
    );
  }
  if (usesAgentCoreContext) {
    warnings.push(
      "Detected AgentCore context/header usage. Request/session headers are forwarded best-effort; validate workload identity and platform-specific context semantics after migration."
    );
  }
  if (usesObservability) {
    warnings.push(
      "Detected observability or tracing signals. AgentKit runtime telemetry is not a byte-for-byte Bedrock AgentCore observability replacement."
    );
  }
  const unsupported = [
    "Full Bedrock AgentCore Runtime platform protocol compatibility is not guaranteed.",
    "IAM, workload identity, deployment configuration, and platform observability semantics are not emulated.",
    "Byte-for-byte SSE event schema, error format, and header behavior compatibility is not guaranteed."
  ];
  return {
    readiness: {
      supported,
      warnings,
      unsupported
    },
    compatibility: {
      profile: "agentcore-entrypoint",
      endpoints: ["/invocations", "/ping", "/run", "/run_sse", "session API", "A2A"],
      supported,
      unsupported
    }
  };
}
function capabilityWarnings(input, projectDir) {
  const warnings = [];
  const contents = pythonContents(projectDir);
  if (input.framework === "langgraph") {
    const hasCheckpointer = contents.some((content) => /\bcheckpointer\s*=/.test(content));
    const hasInterrupt = contents.some((content) => /\binterrupt\s*\(/.test(content));
    if (hasCheckpointer) {
      warnings.push(
        "Detected LangGraph checkpointer usage. AgentKit app/user/session identity is mapped to LangGraph configurable.thread_id by the SDK bridge; keep the original checkpointer dependencies and storage configuration available at runtime."
      );
    }
    if (hasInterrupt && hasCheckpointer) {
      warnings.push(
        "Detected LangGraph interrupt usage. Migrated apps expose LANGGRAPH_INTERRUPT events and resume automatically from the next input in the same AgentKit session."
      );
    }
    if (hasInterrupt && !hasCheckpointer) {
      warnings.push(
        "Detected LangGraph interrupt usage without an obvious checkpointer= compile option. AgentKit can resume interrupts through the same session only when the original graph persists checkpoints."
      );
    }
  }
  if (input.framework === "adk") {
    if (hasAdkConfigSignal(projectDir)) {
      warnings.push(
        "Detected ADK agent config files. agentkit migrate wraps a Python entry object; ensure --entry points to a root_agent that loads or represents the config-based agent."
      );
    }
    if (contents.some((content) => /\b(SequentialAgent|ParallelAgent|LoopAgent)\b/.test(content))) {
      warnings.push(
        "Detected ADK workflow agents. The native ADK root_agent is preserved; verify workflow session state and sub-agent dependencies in the generated AgentKit app."
      );
    }
    if (contents.some((content) => /\bFunctionTool\b|\btools\s*=|before_tool_callback|after_tool_callback|on_tool_error_callback/.test(content))) {
      warnings.push(
        "Detected ADK tools or tool callbacks. The native ADK execution path is preserved; ensure tool credentials, services, and callback side effects are available in the migrated runtime."
      );
    }
  }
  if (input.framework === "strands") {
    if (contents.some((content) => /\b(GraphBuilder|Graph|Swarm|A2AAgent)\b/.test(content))) {
      warnings.push(
        "Detected Strands multi-agent or A2A usage. The SDK bridge adapts stream_async/invoke_async entries and filters lifecycle events while preserving final user-facing output."
      );
    }
    if (contents.some((content) => /\b(interrupt|HumanInTheLoop|Confirm)\b/.test(content))) {
      warnings.push(
        "Detected Strands interrupt/HITL usage. Migrated apps expose STRANDS_INTERRUPT events and resume from the next input in the same AgentKit session."
      );
    }
    if (contents.some((content) => /\bsession_manager\s*=/.test(content))) {
      warnings.push(
        "Detected Strands session_manager usage. Ensure its storage backend is available in the migrated runtime; for Graph/Swarm, session persistence should be configured on the orchestrator."
      );
    }
  }
  return warnings;
}
function createMigrationPlan(input) {
  validateModelOptions(input);
  const project = resolveMigrationProject(input.project);
  const cloudProvider = input.cloudProvider ?? "volcengine";
  const region = input.region ?? DEFAULT_REGION_BY_PROVIDER[cloudProvider];
  const projectDir = resolve3(input.projectDir);
  const serverMode = input.serverMode ?? "agentkit";
  const langGraphServerMode = serverMode === "langgraph";
  const entry = langGraphServerMode ? parseLangGraphServerEntry(projectDir, input.entry) : parseEntryReference(input.entry);
  const entryAbs = resolveProjectPath(projectDir, entry.file);
  const compat = resolveCompat(input);
  const scan = langGraphServerMode ? { warnings: [] } : scanProject({ projectDir, framework: input.framework, entry, force: input.force });
  const outputDirAbs = resolve3(projectDir, input.output ?? ".");
  assertInside(projectDir, outputDirAbs, "Output directory");
  assertDeployableOutputDir(projectDir, outputDirAbs);
  assertNoSymlinkedOutputPath(projectDir, outputDirAbs);
  const name = runtimeName(input.name ?? basename(projectDir));
  const pyAgentName = agentName(name);
  const inputKey = bridgeInputKey(input);
  const streamNodes = bridgeStreamNodes(input);
  const entryAnalysis = input.framework === "agentcore" || langGraphServerMode ? { callFactory: false, graphFactory: false, paramNames: [], requiredParams: [], isAsync: false, warnings: [] } : entryFactoryAnalysis(entryAbs, entry.object);
  const hasRunnableConfigParam = entryAnalysis.paramNames.some((name2) => ["config", "runnable_config"].includes(name2));
  const isLangGraphServerFactory = input.framework === "langgraph" && hasRunnableConfigParam && entryAnalysis.requiredParams.length <= 1 && entryAnalysis.requiredParams.every((name2) => ["config", "runnable_config"].includes(name2));
  const effectiveEntryAnalysis = {
    ...entryAnalysis,
    callFactory: isLangGraphServerFactory ? false : entryAnalysis.callFactory,
    graphFactory: isLangGraphServerFactory,
    warnings: isLangGraphServerFactory ? [] : entryAnalysis.warnings
  };
  const outputRel = outputDirRel(projectDir, outputDirAbs);
  const entryFileFromApp = toPosix(relative3(outputDirAbs, entryAbs));
  const entryModule = entryModuleName(projectDir, entryAbs);
  const projectRootFromApp = toPosix(relative3(outputDirAbs, projectDir)) || ".";
  const legacyAppAbs = compat.legacyApp ? resolveProjectPath(projectDir, compat.legacyApp.file) : void 0;
  if (legacyAppAbs) {
    assertInside(projectDir, legacyAppAbs, "Legacy app file");
    if (!existsSync3(legacyAppAbs) || !statSync2(legacyAppAbs).isFile()) {
      throw new Error(`Legacy app file does not exist: ${compat.legacyApp?.file}`);
    }
    assertInside(realpathSync2(projectDir), realpathSync2(legacyAppAbs), "Legacy app file");
  }
  const appPath = join3(outputDirAbs, "agentkit_app.py");
  const yamlPath = join3(projectDir, ".agentkit", "agentkit.yaml");
  const dockerfilePath = join3(projectDir, ".agentkit", "Dockerfile");
  const dockerignorePath = join3(projectDir, ".dockerignore");
  const planPath = join3(projectDir, ".agentkit", "migration-plan.json");
  const requirementsPath = join3(projectDir, "requirements.txt");
  const enableModelReplacement = modelReplacementEnabled(input);
  const parsedEnvExample = parseEnvExample(projectDir);
  const parsedConfigEnvRefs = parseConfigEnvReferences(projectDir);
  const existingAgentkitEnvs = readExistingAgentkitEnvs(yamlPath);
  const targetModelEnvMap = targetModelEnvs(input);
  const deprecatedModelEnvKeys = input.framework === "agentcore" ? DEPRECATED_AGENTCORE_MODEL_ENV_KEYS : /* @__PURE__ */ new Set();
  const modelAliasEnvKeys = enableModelReplacement ? MODEL_REPLACEMENT_ALIAS_ENV_KEYS : /* @__PURE__ */ new Set();
  const droppedEnvKeys = /* @__PURE__ */ new Set([...deprecatedModelEnvKeys, ...modelAliasEnvKeys]);
  const inferredEnvs = omitEnvKeys({ ...parsedEnvExample.envs, ...parsedConfigEnvRefs.envs }, droppedEnvKeys);
  const preservedEnvs = omitEnvKeys(existingAgentkitEnvs, droppedEnvKeys);
  const targetModelEnvKeySet = new Set(Object.keys(targetModelEnvMap));
  const envs = { ...inferredEnvs, ...preservedEnvs, ...targetModelEnvMap };
  const preservedEnvKeys = Object.keys(preservedEnvs).filter((key) => !targetModelEnvKeySet.has(key));
  const inferredEnvKeys = Object.keys(inferredEnvs).filter((key) => !(key in preservedEnvs) && !targetModelEnvKeySet.has(key));
  const targetModelEnvKeys = Object.keys(targetModelEnvMap);
  const droppedDeprecatedEnvKeys = input.framework === "agentcore" ? [
    .../* @__PURE__ */ new Set([
      ...Object.keys(parsedEnvExample.envs).filter((key) => DEPRECATED_AGENTCORE_MODEL_ENV_KEYS.has(key)),
      ...Object.keys(existingAgentkitEnvs).filter((key) => DEPRECATED_AGENTCORE_MODEL_ENV_KEYS.has(key))
    ])
  ] : [];
  const droppedModelAliasEnvKeys = enableModelReplacement ? [.../* @__PURE__ */ new Set([...envKeys(parsedEnvExample.envs, MODEL_REPLACEMENT_ALIAS_ENV_KEYS), ...envKeys(existingAgentkitEnvs, MODEL_REPLACEMENT_ALIAS_ENV_KEYS)])] : [];
  const hadRequirements = existsSync3(requirementsPath);
  const hasPyproject = existsSync3(join3(projectDir, "pyproject.toml"));
  const usesUvSync = hasPyproject && existsSync3(join3(projectDir, "uv.lock"));
  const installStrategy = usesUvSync ? "uv-sync" : "requirements";
  const localProjectRequirement = !hadRequirements && hasPyproject && !usesUvSync ? ["-e ."] : [];
  const requirements = mergeRequirements(readRequirements(projectDir), [
    ...localProjectRequirement,
    ...langGraphServerMode ? requiredLangGraphServerPackages() : requiredPackages(input.framework)
  ]);
  const contents = pythonContents(projectDir);
  const warnings = [...scan.warnings];
  const agentcore = input.framework === "agentcore" ? agentcoreReadiness(contents, enableModelReplacement) : void 0;
  warnings.push(...effectiveEntryAnalysis.warnings);
  warnings.push(...compat.warnings);
  warnings.push(...langGraphServerMode ? [] : capabilityWarnings(input, projectDir));
  if (langGraphServerMode) {
    warnings.push(
      "LangGraph server mode keeps LangGraph Server as the execution runtime and mounts AgentKit /run, /run_sse, /invoke, and session routes on the same app while preserving native LangGraph Server routes."
    );
    warnings.push(
      "LangGraph server mode uses in-memory LangGraph runtime defaults unless the source project configures durable DATABASE_URI/REDIS_URI/store/checkpointer settings. Configure production persistence before relying on cross-restart sessions, checkpoints, or scale-out."
    );
    if (input.allowBlocking) {
      warnings.push(
        "LangGraph blocking I/O detection is explicitly relaxed via the official LANGGRAPH_ALLOW_BLOCKING setting. Prefer async I/O or thread offloading for high-concurrency production paths."
      );
    }
    warnings.push(...langGraphServerSourceWarnings(projectDir, entry.file));
  }
  if (effectiveEntryAnalysis.graphFactory) {
    warnings.push(
      "Detected LangGraph Server-style graph factory. The SDK bridge will invoke it with RunnableConfig for each AgentKit run."
    );
  }
  if (agentcore) {
    warnings.push(...agentcore.readiness.warnings);
  }
  warnings.push(...parsedEnvExample.warnings);
  if (usesUvSync) {
    warnings.push(
      "Detected uv project metadata. Generated Dockerfile uses uv sync before installing AgentKit migration requirements."
    );
  } else if (!hadRequirements && hasPyproject) {
    warnings.push(
      "No requirements.txt was found. Detected pyproject.toml, so generated requirements.txt installs the project with -e . before AgentKit bridge dependencies."
    );
  } else if (!hadRequirements) {
    warnings.push("No requirements.txt was found. Add the original agent's Python dependencies before deploying.");
  }
  if (input.framework === "strands") {
    if (effectiveEntryAnalysis.callFactory) {
      warnings.push(
        "Strands zero-argument factory entry will be used per AgentKit session for conversation isolation and better concurrency."
      );
    } else {
      warnings.push(
        "Strands entries keep mutable conversation state. The SDK bridge isolates singleton entries with Strands snapshots when available; expose a zero-argument factory for best per-session concurrency."
      );
    }
  }
  if (input.framework === "agentcore") {
    warnings.push(
      "Bedrock AgentCore /invocations and /ping compatibility routes are generated by default while AgentKit native /run, /run_sse, session, and A2A routes remain available."
    );
    if (!enableModelReplacement) {
      warnings.push(
        "Detected Bedrock AgentCore migration without model replacement. If the source app constructs Bedrock or Anthropic model clients that are unavailable in AgentKit runtime, pass --model-id to enable ARK replacement."
      );
    }
    if (droppedDeprecatedEnvKeys.length > 0) {
      warnings.push(
        "Dropped deprecated AgentCore model envs from generated config. Use ARK_MODEL_ID, ARK_API_KEY, and ARK_BASE_URL instead."
      );
    }
  }
  if (enableModelReplacement) {
    warnings.push(
      "Model replacement is explicitly enabled. The generated app sets ARK target-model envs and calls the SDK replacement hook before loading the entry; it does not rewrite source code or patch arbitrary model SDK constructors."
    );
    if (droppedModelAliasEnvKeys.length > 0) {
      warnings.push(
        `Dropped model alias envs from generated config because ARK_* is the source of truth for explicit model replacement: ${droppedModelAliasEnvKeys.join(", ")}.`
      );
    }
  }
  const envExampleKeys = Object.keys(parsedEnvExample.envs).filter(
    (key) => !droppedEnvKeys.has(key) && !(key in preservedEnvs) && !targetModelEnvKeySet.has(key)
  );
  if (envExampleKeys.length > 0) {
    warnings.push(`Detected deploy environment variables from .env.example: ${envExampleKeys.join(", ")}.`);
  }
  const configEnvKeys = parsedConfigEnvRefs.keys.filter(
    (key) => !droppedEnvKeys.has(key) && !(key in parsedEnvExample.envs) && !(key in preservedEnvs) && !targetModelEnvKeySet.has(key)
  );
  if (configEnvKeys.length > 0) {
    warnings.push(`Detected deploy environment variable references from config files: ${configEnvKeys.join(", ")}.`);
  }
  if (preservedEnvKeys.length > 0) {
    warnings.push(`Preserved existing .agentkit/agentkit.yaml envs: ${preservedEnvKeys.join(", ")}.`);
  }
  if (input.framework === "langchain" && compat.profile === "none" && hasLangServeSignal(projectDir)) {
    warnings.push("Detected LangServe route setup. Use --compat langserve to keep /invoke, /batch, and /stream-style callers during migration.");
  }
  const artifacts = [
    artifact(toPosix(relative3(projectDir, appPath)), existsSync3(appPath), input.force),
    artifact(".agentkit/agentkit.yaml", existsSync3(yamlPath), input.force),
    artifact(".agentkit/Dockerfile", existsSync3(dockerfilePath), input.force),
    artifact(".agentkit/migration-plan.json", existsSync3(planPath), input.force),
    ...!existsSync3(dockerignorePath) ? [artifact(".dockerignore", false, input.force)] : [],
    { path: "requirements.txt", action: existsSync3(requirementsPath) ? "update" : "create" }
  ];
  assertNoConflicts(projectDir, artifacts, input.force);
  const plan = {
    version: 1,
    createdAt: (/* @__PURE__ */ new Date()).toISOString(),
    framework: input.framework,
    name,
    agentName: pyAgentName,
    entry: {
      file: toPosix(relative3(projectDir, entryAbs)),
      object: entry.object,
      ...effectiveEntryAnalysis.callFactory && input.framework === "strands" ? { sessionFactory: true } : {},
      ...effectiveEntryAnalysis.callFactory && input.framework !== "strands" ? { callFactory: true } : {},
      ...effectiveEntryAnalysis.graphFactory ? { graphFactory: true } : {}
    },
    outputDir: outputRel,
    defaults: {
      cloudProvider,
      region,
      project,
      a2a: true,
      appClass: langGraphServerMode ? "AgentkitLangGraphServerApp" : "AgentkitAgentServerApp",
      ...langGraphServerMode ? { serverMode: "langgraph" } : {},
      ...langGraphServerMode && input.allowBlocking ? { allowBlocking: true } : {}
    },
    artifacts,
    requirements: {
      path: "requirements.txt",
      added: requirements.added,
      alreadyPresent: requirements.alreadyPresent,
      updated: requirements.updated,
      installStrategy
    },
    ...Object.keys(envs).length > 0 ? {
      envs: {
        path: ".agentkit/agentkit.yaml",
        keys: Object.keys(envs),
        inferred: [...inferredEnvKeys, ...targetModelEnvKeys],
        preserved: preservedEnvKeys
      }
    } : {},
    ...input.framework === "adk" || langGraphServerMode ? {} : {
      bridge: {
        source: "agentkit-sdk-python",
        framework: input.framework,
        minVersion: AGENTKIT_SDK_BRIDGE_MIN_VERSION,
        ...inputKey ? { inputKey } : {},
        ...streamNodes ? { streamNodes } : {},
        ...effectiveEntryAnalysis.graphFactory ? { graphFactory: true } : {}
      }
    },
    ...compat.profile === "none" ? {} : {
      compat: {
        enabled: true,
        profile: compat.profile,
        prefix: compat.prefix ?? "/",
        source: "agentkit-sdk-python",
        endpoints: compatEndpoints(compat.profile, compat.prefix ?? "/"),
        ...compat.legacyApp ? { legacyApp: { file: toPosix(relative3(projectDir, legacyAppAbs)), object: compat.legacyApp.object } } : {},
        warnings: compat.warnings
      }
    },
    ...agentcore ? { agentcore } : {},
    warnings
  };
  const files = /* @__PURE__ */ new Map();
  files.set(
    appPath,
    langGraphServerMode ? renderLangGraphServerApp({
      configPathFromApp: entryFileFromApp,
      graphId: entry.object,
      inputKey,
      allowBlocking: input.allowBlocking,
      modelReplacement: enableModelReplacement ? {
        modelId: input.modelId,
        cloudProvider,
        modelBaseUrl: input.modelBaseUrl ?? (cloudProvider === "byteplus" ? "https://ark.ap-southeast.bytepluses.com/api/v3" : void 0),
        apiKeyEnv: input.modelApiKeyEnv || "ARK_API_KEY"
      } : void 0
    }) : renderAgentkitApp({
      framework: input.framework,
      entryFileFromApp,
      entryModule,
      entryObject: entry.object,
      callFactory: effectiveEntryAnalysis.callFactory,
      graphFactory: effectiveEntryAnalysis.graphFactory,
      projectRootFromApp,
      agentName: pyAgentName,
      inputKey,
      streamNodes,
      modelReplacement: enableModelReplacement ? {
        modelId: input.modelId,
        cloudProvider,
        modelBaseUrl: input.modelBaseUrl ?? (cloudProvider === "byteplus" ? "https://ark.ap-southeast.bytepluses.com/api/v3" : void 0),
        apiKeyEnv: input.modelApiKeyEnv || "ARK_API_KEY"
      } : void 0,
      compat: compat.profile === "none" ? void 0 : {
        profile: compat.profile,
        prefix: compat.prefix ?? "/",
        legacyApp: compat.legacyApp ? {
          fileFromApp: toPosix(relative3(outputDirAbs, legacyAppAbs)),
          module: entryModuleName(projectDir, legacyAppAbs),
          object: compat.legacyApp.object
        } : void 0,
        inputKey
      }
    })
  );
  files.set(yamlPath, renderAgentkitYaml({ name, project, cloudProvider, region, envs }));
  files.set(dockerfilePath, renderDockerfile({ outputDir: outputRel, cloudProvider, installStrategy }));
  if (!existsSync3(dockerignorePath)) files.set(dockerignorePath, renderDockerignore());
  files.set(planPath, `${JSON.stringify(plan, null, 2)}
`);
  files.set(requirementsPath, requirements.content);
  return {
    plan,
    paths: { projectDir, outputDirAbs, appPath, yamlPath, dockerfilePath, planPath, requirementsPath, entryAbs },
    requirementsContent: requirements.content,
    files
  };
}
function runMigration(input) {
  const prepared = createMigrationPlan(input);
  if (!input.dryRun) {
    mkdirSync(prepared.paths.outputDirAbs, { recursive: true });
    mkdirSync(join3(prepared.paths.projectDir, ".agentkit"), { recursive: true });
    for (const [path, content] of prepared.files) {
      writeFileSync(path, content, "utf8");
    }
    if (input.verify) {
      const verification = verifyGeneratedMigration({
        outputDirAbs: prepared.paths.outputDirAbs,
        framework: prepared.plan.framework,
        serverMode: prepared.plan.defaults.serverMode
      });
      prepared.plan.verification = verification;
      writeFileSync(prepared.paths.planPath, `${JSON.stringify(prepared.plan, null, 2)}
`, "utf8");
      if (verification.status !== "passed") {
        const failed = verification.checks.filter((check) => check.status === "failed").map((check) => `${check.name}${check.detail ? `: ${check.detail}` : ""}`).join("; ");
        throw new Error(`Migration verification failed with ${verification.python}: ${failed}`);
      }
    }
  }
  return { plan: prepared.plan, dryRun: Boolean(input.dryRun) };
}

// src/migrate-runner/agentic.ts
import { spawn as spawn2 } from "child_process";
import {
  createWriteStream,
  existsSync as existsSync25,
  mkdirSync as mkdirSync11,
  readFileSync as readFileSync20,
  rmSync as rmSync9,
  writeFileSync as writeFileSync12
} from "fs";
import { dirname as dirname8, join as join23 } from "path";

// src/commands/migrate/any.ts
import { existsSync as existsSync23, statSync as statSync6 } from "fs";
import { resolve as resolve9 } from "path";

// src/commands/migrate/remote/config.ts
import { existsSync as existsSync5 } from "fs";
import { join as join5 } from "path";

// src/utils/assets.ts
import { fileURLToPath } from "url";
import { dirname, join as join4 } from "path";
import { existsSync as existsSync4 } from "fs";
function findAssetDir(name, isValid) {
  const bases = [];
  try {
    bases.push(dirname(fileURLToPath(import.meta.url)));
  } catch {
  }
  try {
    bases.push(dirname(process.execPath));
  } catch {
  }
  bases.push(process.cwd());
  for (const start of bases) {
    let dir = start;
    for (let i = 0; i < 7; i++) {
      const candidate = join4(dir, name);
      if (existsSync4(candidate) && isValid(candidate)) return candidate;
      const parent = dirname(dir);
      if (parent === dir) break;
      dir = parent;
    }
  }
  return join4(process.cwd(), name);
}

// src/commands/migrate/remote/config.ts
var DEFAULT_REMOTE_TTL_SECONDS = 8 * 60 * 60;
var REMOTE_EXPIRY_WARNING_MS = 60 * 60 * 1e3;
var AGENTKIT_MIGRATE_SKILLS_ROOT = "/home/gem/.codex/skills";
var SOURCE_TO_VEADK_SKILL_DIR = `${AGENTKIT_MIGRATE_SKILLS_ROOT}/source-to-veadk`;
var SOURCE_TO_VEADK_PROMPT_PATH = `${SOURCE_TO_VEADK_SKILL_DIR}/prompts/migrate.md`;
var REQUIRED_REMOTE_MIGRATION_SKILL_FILES = [
  "source-to-veadk/SKILL.md",
  "source-to-veadk/prompts/migrate.md",
  "source-to-veadk/scripts/bootstrap_runtime.sh",
  "source-to-veadk/scripts/detect_source_capabilities.py",
  "source-to-veadk/scripts/validate_runtime.sh",
  "agentkit-cli/SKILL.md",
  "veadk-agent-development/SKILL.md"
];
function hasRequiredRemoteMigrationSkillFiles(skillsRoot, files = REQUIRED_REMOTE_MIGRATION_SKILL_FILES) {
  return files.every((file) => existsSync5(join5(skillsRoot, file)));
}
function resolveBundledMigrationSkillsDir(files = REQUIRED_REMOTE_MIGRATION_SKILL_FILES) {
  const skillsRoot = findAssetDir("skills", (candidate) => hasRequiredRemoteMigrationSkillFiles(candidate, files));
  if (!hasRequiredRemoteMigrationSkillFiles(skillsRoot, files)) {
    throw new Error(`Bundled migration skills are incomplete or missing: ${files.join(", ")}`);
  }
  return skillsRoot;
}
var REMOTE_MIGRATE_TOOL_TYPE = "DevEnv";
function remoteMigrateToolPreset(options) {
  return {
    ToolType: REMOTE_MIGRATE_TOOL_TYPE,
    ModelProvider: options.modelProvider,
    ModelApiKey: options.modelApiKey
  };
}

// src/commands/migrate/remote/handlers.ts
import { createHash as createHash6, randomUUID as randomUUID5 } from "crypto";
import { existsSync as existsSync22, mkdtempSync as mkdtempSync2, rmSync as rmSync8, writeFileSync as writeFileSync11 } from "fs";
import { tmpdir as tmpdir2 } from "os";
import { isAbsolute as isAbsolute4, join as join21, relative as relative8 } from "path";

// node_modules/.pnpm/@clack+prompts@0.11.0/node_modules/@clack/prompts/dist/index.mjs
import { stripVTControlCharacters as S } from "util";

// node_modules/.pnpm/@clack+core@0.5.0/node_modules/@clack/core/dist/index.mjs
var import_sisteransi = __toESM(require_src(), 1);
import { stdin as j, stdout as M } from "process";
import * as g from "readline";
import O from "readline";
import { Writable as X } from "stream";
function DD({ onlyFirst: e2 = false } = {}) {
  const t = ["[\\u001B\\u009B][[\\]()#;?]*(?:(?:(?:(?:;[-a-zA-Z\\d\\/#&.:=?%@~_]+)*|[a-zA-Z\\d]+(?:;[-a-zA-Z\\d\\/#&.:=?%@~_]*)*)?(?:\\u0007|\\u001B\\u005C|\\u009C))", "(?:(?:\\d{1,4}(?:;\\d{0,4})*)?[\\dA-PR-TZcf-nq-uy=><~]))"].join("|");
  return new RegExp(t, e2 ? void 0 : "g");
}
var uD = DD();
function L(e2) {
  return e2 && e2.__esModule && Object.prototype.hasOwnProperty.call(e2, "default") ? e2.default : e2;
}
var W = { exports: {} };
(function(e2) {
  var u2 = {};
  e2.exports = u2, u2.eastAsianWidth = function(F2) {
    var s = F2.charCodeAt(0), i = F2.length == 2 ? F2.charCodeAt(1) : 0, D2 = s;
    return 55296 <= s && s <= 56319 && 56320 <= i && i <= 57343 && (s &= 1023, i &= 1023, D2 = s << 10 | i, D2 += 65536), D2 == 12288 || 65281 <= D2 && D2 <= 65376 || 65504 <= D2 && D2 <= 65510 ? "F" : D2 == 8361 || 65377 <= D2 && D2 <= 65470 || 65474 <= D2 && D2 <= 65479 || 65482 <= D2 && D2 <= 65487 || 65490 <= D2 && D2 <= 65495 || 65498 <= D2 && D2 <= 65500 || 65512 <= D2 && D2 <= 65518 ? "H" : 4352 <= D2 && D2 <= 4447 || 4515 <= D2 && D2 <= 4519 || 4602 <= D2 && D2 <= 4607 || 9001 <= D2 && D2 <= 9002 || 11904 <= D2 && D2 <= 11929 || 11931 <= D2 && D2 <= 12019 || 12032 <= D2 && D2 <= 12245 || 12272 <= D2 && D2 <= 12283 || 12289 <= D2 && D2 <= 12350 || 12353 <= D2 && D2 <= 12438 || 12441 <= D2 && D2 <= 12543 || 12549 <= D2 && D2 <= 12589 || 12593 <= D2 && D2 <= 12686 || 12688 <= D2 && D2 <= 12730 || 12736 <= D2 && D2 <= 12771 || 12784 <= D2 && D2 <= 12830 || 12832 <= D2 && D2 <= 12871 || 12880 <= D2 && D2 <= 13054 || 13056 <= D2 && D2 <= 19903 || 19968 <= D2 && D2 <= 42124 || 42128 <= D2 && D2 <= 42182 || 43360 <= D2 && D2 <= 43388 || 44032 <= D2 && D2 <= 55203 || 55216 <= D2 && D2 <= 55238 || 55243 <= D2 && D2 <= 55291 || 63744 <= D2 && D2 <= 64255 || 65040 <= D2 && D2 <= 65049 || 65072 <= D2 && D2 <= 65106 || 65108 <= D2 && D2 <= 65126 || 65128 <= D2 && D2 <= 65131 || 110592 <= D2 && D2 <= 110593 || 127488 <= D2 && D2 <= 127490 || 127504 <= D2 && D2 <= 127546 || 127552 <= D2 && D2 <= 127560 || 127568 <= D2 && D2 <= 127569 || 131072 <= D2 && D2 <= 194367 || 177984 <= D2 && D2 <= 196605 || 196608 <= D2 && D2 <= 262141 ? "W" : 32 <= D2 && D2 <= 126 || 162 <= D2 && D2 <= 163 || 165 <= D2 && D2 <= 166 || D2 == 172 || D2 == 175 || 10214 <= D2 && D2 <= 10221 || 10629 <= D2 && D2 <= 10630 ? "Na" : D2 == 161 || D2 == 164 || 167 <= D2 && D2 <= 168 || D2 == 170 || 173 <= D2 && D2 <= 174 || 176 <= D2 && D2 <= 180 || 182 <= D2 && D2 <= 186 || 188 <= D2 && D2 <= 191 || D2 == 198 || D2 == 208 || 215 <= D2 && D2 <= 216 || 222 <= D2 && D2 <= 225 || D2 == 230 || 232 <= D2 && D2 <= 234 || 236 <= D2 && D2 <= 237 || D2 == 240 || 242 <= D2 && D2 <= 243 || 247 <= D2 && D2 <= 250 || D2 == 252 || D2 == 254 || D2 == 257 || D2 == 273 || D2 == 275 || D2 == 283 || 294 <= D2 && D2 <= 295 || D2 == 299 || 305 <= D2 && D2 <= 307 || D2 == 312 || 319 <= D2 && D2 <= 322 || D2 == 324 || 328 <= D2 && D2 <= 331 || D2 == 333 || 338 <= D2 && D2 <= 339 || 358 <= D2 && D2 <= 359 || D2 == 363 || D2 == 462 || D2 == 464 || D2 == 466 || D2 == 468 || D2 == 470 || D2 == 472 || D2 == 474 || D2 == 476 || D2 == 593 || D2 == 609 || D2 == 708 || D2 == 711 || 713 <= D2 && D2 <= 715 || D2 == 717 || D2 == 720 || 728 <= D2 && D2 <= 731 || D2 == 733 || D2 == 735 || 768 <= D2 && D2 <= 879 || 913 <= D2 && D2 <= 929 || 931 <= D2 && D2 <= 937 || 945 <= D2 && D2 <= 961 || 963 <= D2 && D2 <= 969 || D2 == 1025 || 1040 <= D2 && D2 <= 1103 || D2 == 1105 || D2 == 8208 || 8211 <= D2 && D2 <= 8214 || 8216 <= D2 && D2 <= 8217 || 8220 <= D2 && D2 <= 8221 || 8224 <= D2 && D2 <= 8226 || 8228 <= D2 && D2 <= 8231 || D2 == 8240 || 8242 <= D2 && D2 <= 8243 || D2 == 8245 || D2 == 8251 || D2 == 8254 || D2 == 8308 || D2 == 8319 || 8321 <= D2 && D2 <= 8324 || D2 == 8364 || D2 == 8451 || D2 == 8453 || D2 == 8457 || D2 == 8467 || D2 == 8470 || 8481 <= D2 && D2 <= 8482 || D2 == 8486 || D2 == 8491 || 8531 <= D2 && D2 <= 8532 || 8539 <= D2 && D2 <= 8542 || 8544 <= D2 && D2 <= 8555 || 8560 <= D2 && D2 <= 8569 || D2 == 8585 || 8592 <= D2 && D2 <= 8601 || 8632 <= D2 && D2 <= 8633 || D2 == 8658 || D2 == 8660 || D2 == 8679 || D2 == 8704 || 8706 <= D2 && D2 <= 8707 || 8711 <= D2 && D2 <= 8712 || D2 == 8715 || D2 == 8719 || D2 == 8721 || D2 == 8725 || D2 == 8730 || 8733 <= D2 && D2 <= 8736 || D2 == 8739 || D2 == 8741 || 8743 <= D2 && D2 <= 8748 || D2 == 8750 || 8756 <= D2 && D2 <= 8759 || 8764 <= D2 && D2 <= 8765 || D2 == 8776 || D2 == 8780 || D2 == 8786 || 8800 <= D2 && D2 <= 8801 || 8804 <= D2 && D2 <= 8807 || 8810 <= D2 && D2 <= 8811 || 8814 <= D2 && D2 <= 8815 || 8834 <= D2 && D2 <= 8835 || 8838 <= D2 && D2 <= 8839 || D2 == 8853 || D2 == 8857 || D2 == 8869 || D2 == 8895 || D2 == 8978 || 9312 <= D2 && D2 <= 9449 || 9451 <= D2 && D2 <= 9547 || 9552 <= D2 && D2 <= 9587 || 9600 <= D2 && D2 <= 9615 || 9618 <= D2 && D2 <= 9621 || 9632 <= D2 && D2 <= 9633 || 9635 <= D2 && D2 <= 9641 || 9650 <= D2 && D2 <= 9651 || 9654 <= D2 && D2 <= 9655 || 9660 <= D2 && D2 <= 9661 || 9664 <= D2 && D2 <= 9665 || 9670 <= D2 && D2 <= 9672 || D2 == 9675 || 9678 <= D2 && D2 <= 9681 || 9698 <= D2 && D2 <= 9701 || D2 == 9711 || 9733 <= D2 && D2 <= 9734 || D2 == 9737 || 9742 <= D2 && D2 <= 9743 || 9748 <= D2 && D2 <= 9749 || D2 == 9756 || D2 == 9758 || D2 == 9792 || D2 == 9794 || 9824 <= D2 && D2 <= 9825 || 9827 <= D2 && D2 <= 9829 || 9831 <= D2 && D2 <= 9834 || 9836 <= D2 && D2 <= 9837 || D2 == 9839 || 9886 <= D2 && D2 <= 9887 || 9918 <= D2 && D2 <= 9919 || 9924 <= D2 && D2 <= 9933 || 9935 <= D2 && D2 <= 9953 || D2 == 9955 || 9960 <= D2 && D2 <= 9983 || D2 == 10045 || D2 == 10071 || 10102 <= D2 && D2 <= 10111 || 11093 <= D2 && D2 <= 11097 || 12872 <= D2 && D2 <= 12879 || 57344 <= D2 && D2 <= 63743 || 65024 <= D2 && D2 <= 65039 || D2 == 65533 || 127232 <= D2 && D2 <= 127242 || 127248 <= D2 && D2 <= 127277 || 127280 <= D2 && D2 <= 127337 || 127344 <= D2 && D2 <= 127386 || 917760 <= D2 && D2 <= 917999 || 983040 <= D2 && D2 <= 1048573 || 1048576 <= D2 && D2 <= 1114109 ? "A" : "N";
  }, u2.characterLength = function(F2) {
    var s = this.eastAsianWidth(F2);
    return s == "F" || s == "W" || s == "A" ? 2 : 1;
  };
  function t(F2) {
    return F2.match(/[\uD800-\uDBFF][\uDC00-\uDFFF]|[^\uD800-\uDFFF]/g) || [];
  }
  u2.length = function(F2) {
    for (var s = t(F2), i = 0, D2 = 0; D2 < s.length; D2++) i = i + this.characterLength(s[D2]);
    return i;
  }, u2.slice = function(F2, s, i) {
    textLen = u2.length(F2), s = s || 0, i = i || 1, s < 0 && (s = textLen + s), i < 0 && (i = textLen + i);
    for (var D2 = "", C2 = 0, n = t(F2), E = 0; E < n.length; E++) {
      var a = n[E], o2 = u2.length(a);
      if (C2 >= s - (o2 == 2 ? 1 : 0)) if (C2 + o2 <= i) D2 += a;
      else break;
      C2 += o2;
    }
    return D2;
  };
})(W);
var tD = W.exports;
var eD = L(tD);
var FD = function() {
  return /\uD83C\uDFF4\uDB40\uDC67\uDB40\uDC62(?:\uDB40\uDC77\uDB40\uDC6C\uDB40\uDC73|\uDB40\uDC73\uDB40\uDC63\uDB40\uDC74|\uDB40\uDC65\uDB40\uDC6E\uDB40\uDC67)\uDB40\uDC7F|(?:\uD83E\uDDD1\uD83C\uDFFF\u200D\u2764\uFE0F\u200D(?:\uD83D\uDC8B\u200D)?\uD83E\uDDD1|\uD83D\uDC69\uD83C\uDFFF\u200D\uD83E\uDD1D\u200D(?:\uD83D[\uDC68\uDC69]))(?:\uD83C[\uDFFB-\uDFFE])|(?:\uD83E\uDDD1\uD83C\uDFFE\u200D\u2764\uFE0F\u200D(?:\uD83D\uDC8B\u200D)?\uD83E\uDDD1|\uD83D\uDC69\uD83C\uDFFE\u200D\uD83E\uDD1D\u200D(?:\uD83D[\uDC68\uDC69]))(?:\uD83C[\uDFFB-\uDFFD\uDFFF])|(?:\uD83E\uDDD1\uD83C\uDFFD\u200D\u2764\uFE0F\u200D(?:\uD83D\uDC8B\u200D)?\uD83E\uDDD1|\uD83D\uDC69\uD83C\uDFFD\u200D\uD83E\uDD1D\u200D(?:\uD83D[\uDC68\uDC69]))(?:\uD83C[\uDFFB\uDFFC\uDFFE\uDFFF])|(?:\uD83E\uDDD1\uD83C\uDFFC\u200D\u2764\uFE0F\u200D(?:\uD83D\uDC8B\u200D)?\uD83E\uDDD1|\uD83D\uDC69\uD83C\uDFFC\u200D\uD83E\uDD1D\u200D(?:\uD83D[\uDC68\uDC69]))(?:\uD83C[\uDFFB\uDFFD-\uDFFF])|(?:\uD83E\uDDD1\uD83C\uDFFB\u200D\u2764\uFE0F\u200D(?:\uD83D\uDC8B\u200D)?\uD83E\uDDD1|\uD83D\uDC69\uD83C\uDFFB\u200D\uD83E\uDD1D\u200D(?:\uD83D[\uDC68\uDC69]))(?:\uD83C[\uDFFC-\uDFFF])|\uD83D\uDC68(?:\uD83C\uDFFB(?:\u200D(?:\u2764\uFE0F\u200D(?:\uD83D\uDC8B\u200D\uD83D\uDC68(?:\uD83C[\uDFFB-\uDFFF])|\uD83D\uDC68(?:\uD83C[\uDFFB-\uDFFF]))|\uD83E\uDD1D\u200D\uD83D\uDC68(?:\uD83C[\uDFFC-\uDFFF])|[\u2695\u2696\u2708]\uFE0F|\uD83C[\uDF3E\uDF73\uDF7C\uDF93\uDFA4\uDFA8\uDFEB\uDFED]|\uD83D[\uDCBB\uDCBC\uDD27\uDD2C\uDE80\uDE92]|\uD83E[\uDDAF-\uDDB3\uDDBC\uDDBD]))?|(?:\uD83C[\uDFFC-\uDFFF])\u200D\u2764\uFE0F\u200D(?:\uD83D\uDC8B\u200D\uD83D\uDC68(?:\uD83C[\uDFFB-\uDFFF])|\uD83D\uDC68(?:\uD83C[\uDFFB-\uDFFF]))|\u200D(?:\u2764\uFE0F\u200D(?:\uD83D\uDC8B\u200D)?\uD83D\uDC68|(?:\uD83D[\uDC68\uDC69])\u200D(?:\uD83D\uDC66\u200D\uD83D\uDC66|\uD83D\uDC67\u200D(?:\uD83D[\uDC66\uDC67]))|\uD83D\uDC66\u200D\uD83D\uDC66|\uD83D\uDC67\u200D(?:\uD83D[\uDC66\uDC67])|\uD83C[\uDF3E\uDF73\uDF7C\uDF93\uDFA4\uDFA8\uDFEB\uDFED]|\uD83D[\uDCBB\uDCBC\uDD27\uDD2C\uDE80\uDE92]|\uD83E[\uDDAF-\uDDB3\uDDBC\uDDBD])|\uD83C\uDFFF\u200D(?:\uD83E\uDD1D\u200D\uD83D\uDC68(?:\uD83C[\uDFFB-\uDFFE])|\uD83C[\uDF3E\uDF73\uDF7C\uDF93\uDFA4\uDFA8\uDFEB\uDFED]|\uD83D[\uDCBB\uDCBC\uDD27\uDD2C\uDE80\uDE92]|\uD83E[\uDDAF-\uDDB3\uDDBC\uDDBD])|\uD83C\uDFFE\u200D(?:\uD83E\uDD1D\u200D\uD83D\uDC68(?:\uD83C[\uDFFB-\uDFFD\uDFFF])|\uD83C[\uDF3E\uDF73\uDF7C\uDF93\uDFA4\uDFA8\uDFEB\uDFED]|\uD83D[\uDCBB\uDCBC\uDD27\uDD2C\uDE80\uDE92]|\uD83E[\uDDAF-\uDDB3\uDDBC\uDDBD])|\uD83C\uDFFD\u200D(?:\uD83E\uDD1D\u200D\uD83D\uDC68(?:\uD83C[\uDFFB\uDFFC\uDFFE\uDFFF])|\uD83C[\uDF3E\uDF73\uDF7C\uDF93\uDFA4\uDFA8\uDFEB\uDFED]|\uD83D[\uDCBB\uDCBC\uDD27\uDD2C\uDE80\uDE92]|\uD83E[\uDDAF-\uDDB3\uDDBC\uDDBD])|\uD83C\uDFFC\u200D(?:\uD83E\uDD1D\u200D\uD83D\uDC68(?:\uD83C[\uDFFB\uDFFD-\uDFFF])|\uD83C[\uDF3E\uDF73\uDF7C\uDF93\uDFA4\uDFA8\uDFEB\uDFED]|\uD83D[\uDCBB\uDCBC\uDD27\uDD2C\uDE80\uDE92]|\uD83E[\uDDAF-\uDDB3\uDDBC\uDDBD])|(?:\uD83C\uDFFF\u200D[\u2695\u2696\u2708]|\uD83C\uDFFE\u200D[\u2695\u2696\u2708]|\uD83C\uDFFD\u200D[\u2695\u2696\u2708]|\uD83C\uDFFC\u200D[\u2695\u2696\u2708]|\u200D[\u2695\u2696\u2708])\uFE0F|\u200D(?:(?:\uD83D[\uDC68\uDC69])\u200D(?:\uD83D[\uDC66\uDC67])|\uD83D[\uDC66\uDC67])|\uD83C\uDFFF|\uD83C\uDFFE|\uD83C\uDFFD|\uD83C\uDFFC)?|(?:\uD83D\uDC69(?:\uD83C\uDFFB\u200D\u2764\uFE0F\u200D(?:\uD83D\uDC8B\u200D(?:\uD83D[\uDC68\uDC69])|\uD83D[\uDC68\uDC69])|(?:\uD83C[\uDFFC-\uDFFF])\u200D\u2764\uFE0F\u200D(?:\uD83D\uDC8B\u200D(?:\uD83D[\uDC68\uDC69])|\uD83D[\uDC68\uDC69]))|\uD83E\uDDD1(?:\uD83C[\uDFFB-\uDFFF])\u200D\uD83E\uDD1D\u200D\uD83E\uDDD1)(?:\uD83C[\uDFFB-\uDFFF])|\uD83D\uDC69\u200D\uD83D\uDC69\u200D(?:\uD83D\uDC66\u200D\uD83D\uDC66|\uD83D\uDC67\u200D(?:\uD83D[\uDC66\uDC67]))|\uD83D\uDC69(?:\u200D(?:\u2764\uFE0F\u200D(?:\uD83D\uDC8B\u200D(?:\uD83D[\uDC68\uDC69])|\uD83D[\uDC68\uDC69])|\uD83C[\uDF3E\uDF73\uDF7C\uDF93\uDFA4\uDFA8\uDFEB\uDFED]|\uD83D[\uDCBB\uDCBC\uDD27\uDD2C\uDE80\uDE92]|\uD83E[\uDDAF-\uDDB3\uDDBC\uDDBD])|\uD83C\uDFFF\u200D(?:\uD83C[\uDF3E\uDF73\uDF7C\uDF93\uDFA4\uDFA8\uDFEB\uDFED]|\uD83D[\uDCBB\uDCBC\uDD27\uDD2C\uDE80\uDE92]|\uD83E[\uDDAF-\uDDB3\uDDBC\uDDBD])|\uD83C\uDFFE\u200D(?:\uD83C[\uDF3E\uDF73\uDF7C\uDF93\uDFA4\uDFA8\uDFEB\uDFED]|\uD83D[\uDCBB\uDCBC\uDD27\uDD2C\uDE80\uDE92]|\uD83E[\uDDAF-\uDDB3\uDDBC\uDDBD])|\uD83C\uDFFD\u200D(?:\uD83C[\uDF3E\uDF73\uDF7C\uDF93\uDFA4\uDFA8\uDFEB\uDFED]|\uD83D[\uDCBB\uDCBC\uDD27\uDD2C\uDE80\uDE92]|\uD83E[\uDDAF-\uDDB3\uDDBC\uDDBD])|\uD83C\uDFFC\u200D(?:\uD83C[\uDF3E\uDF73\uDF7C\uDF93\uDFA4\uDFA8\uDFEB\uDFED]|\uD83D[\uDCBB\uDCBC\uDD27\uDD2C\uDE80\uDE92]|\uD83E[\uDDAF-\uDDB3\uDDBC\uDDBD])|\uD83C\uDFFB\u200D(?:\uD83C[\uDF3E\uDF73\uDF7C\uDF93\uDFA4\uDFA8\uDFEB\uDFED]|\uD83D[\uDCBB\uDCBC\uDD27\uDD2C\uDE80\uDE92]|\uD83E[\uDDAF-\uDDB3\uDDBC\uDDBD]))|\uD83E\uDDD1(?:\u200D(?:\uD83E\uDD1D\u200D\uD83E\uDDD1|\uD83C[\uDF3E\uDF73\uDF7C\uDF84\uDF93\uDFA4\uDFA8\uDFEB\uDFED]|\uD83D[\uDCBB\uDCBC\uDD27\uDD2C\uDE80\uDE92]|\uD83E[\uDDAF-\uDDB3\uDDBC\uDDBD])|\uD83C\uDFFF\u200D(?:\uD83C[\uDF3E\uDF73\uDF7C\uDF84\uDF93\uDFA4\uDFA8\uDFEB\uDFED]|\uD83D[\uDCBB\uDCBC\uDD27\uDD2C\uDE80\uDE92]|\uD83E[\uDDAF-\uDDB3\uDDBC\uDDBD])|\uD83C\uDFFE\u200D(?:\uD83C[\uDF3E\uDF73\uDF7C\uDF84\uDF93\uDFA4\uDFA8\uDFEB\uDFED]|\uD83D[\uDCBB\uDCBC\uDD27\uDD2C\uDE80\uDE92]|\uD83E[\uDDAF-\uDDB3\uDDBC\uDDBD])|\uD83C\uDFFD\u200D(?:\uD83C[\uDF3E\uDF73\uDF7C\uDF84\uDF93\uDFA4\uDFA8\uDFEB\uDFED]|\uD83D[\uDCBB\uDCBC\uDD27\uDD2C\uDE80\uDE92]|\uD83E[\uDDAF-\uDDB3\uDDBC\uDDBD])|\uD83C\uDFFC\u200D(?:\uD83C[\uDF3E\uDF73\uDF7C\uDF84\uDF93\uDFA4\uDFA8\uDFEB\uDFED]|\uD83D[\uDCBB\uDCBC\uDD27\uDD2C\uDE80\uDE92]|\uD83E[\uDDAF-\uDDB3\uDDBC\uDDBD])|\uD83C\uDFFB\u200D(?:\uD83C[\uDF3E\uDF73\uDF7C\uDF84\uDF93\uDFA4\uDFA8\uDFEB\uDFED]|\uD83D[\uDCBB\uDCBC\uDD27\uDD2C\uDE80\uDE92]|\uD83E[\uDDAF-\uDDB3\uDDBC\uDDBD]))|\uD83D\uDC69\u200D\uD83D\uDC66\u200D\uD83D\uDC66|\uD83D\uDC69\u200D\uD83D\uDC69\u200D(?:\uD83D[\uDC66\uDC67])|\uD83D\uDC69\u200D\uD83D\uDC67\u200D(?:\uD83D[\uDC66\uDC67])|(?:\uD83D\uDC41\uFE0F\u200D\uD83D\uDDE8|\uD83E\uDDD1(?:\uD83C\uDFFF\u200D[\u2695\u2696\u2708]|\uD83C\uDFFE\u200D[\u2695\u2696\u2708]|\uD83C\uDFFD\u200D[\u2695\u2696\u2708]|\uD83C\uDFFC\u200D[\u2695\u2696\u2708]|\uD83C\uDFFB\u200D[\u2695\u2696\u2708]|\u200D[\u2695\u2696\u2708])|\uD83D\uDC69(?:\uD83C\uDFFF\u200D[\u2695\u2696\u2708]|\uD83C\uDFFE\u200D[\u2695\u2696\u2708]|\uD83C\uDFFD\u200D[\u2695\u2696\u2708]|\uD83C\uDFFC\u200D[\u2695\u2696\u2708]|\uD83C\uDFFB\u200D[\u2695\u2696\u2708]|\u200D[\u2695\u2696\u2708])|\uD83D\uDE36\u200D\uD83C\uDF2B|\uD83C\uDFF3\uFE0F\u200D\u26A7|\uD83D\uDC3B\u200D\u2744|(?:(?:\uD83C[\uDFC3\uDFC4\uDFCA]|\uD83D[\uDC6E\uDC70\uDC71\uDC73\uDC77\uDC81\uDC82\uDC86\uDC87\uDE45-\uDE47\uDE4B\uDE4D\uDE4E\uDEA3\uDEB4-\uDEB6]|\uD83E[\uDD26\uDD35\uDD37-\uDD39\uDD3D\uDD3E\uDDB8\uDDB9\uDDCD-\uDDCF\uDDD4\uDDD6-\uDDDD])(?:\uD83C[\uDFFB-\uDFFF])|\uD83D\uDC6F|\uD83E[\uDD3C\uDDDE\uDDDF])\u200D[\u2640\u2642]|(?:\u26F9|\uD83C[\uDFCB\uDFCC]|\uD83D\uDD75)(?:\uFE0F|\uD83C[\uDFFB-\uDFFF])\u200D[\u2640\u2642]|\uD83C\uDFF4\u200D\u2620|(?:\uD83C[\uDFC3\uDFC4\uDFCA]|\uD83D[\uDC6E\uDC70\uDC71\uDC73\uDC77\uDC81\uDC82\uDC86\uDC87\uDE45-\uDE47\uDE4B\uDE4D\uDE4E\uDEA3\uDEB4-\uDEB6]|\uD83E[\uDD26\uDD35\uDD37-\uDD39\uDD3D\uDD3E\uDDB8\uDDB9\uDDCD-\uDDCF\uDDD4\uDDD6-\uDDDD])\u200D[\u2640\u2642]|[\xA9\xAE\u203C\u2049\u2122\u2139\u2194-\u2199\u21A9\u21AA\u2328\u23CF\u23ED-\u23EF\u23F1\u23F2\u23F8-\u23FA\u24C2\u25AA\u25AB\u25B6\u25C0\u25FB\u25FC\u2600-\u2604\u260E\u2611\u2618\u2620\u2622\u2623\u2626\u262A\u262E\u262F\u2638-\u263A\u2640\u2642\u265F\u2660\u2663\u2665\u2666\u2668\u267B\u267E\u2692\u2694-\u2697\u2699\u269B\u269C\u26A0\u26A7\u26B0\u26B1\u26C8\u26CF\u26D1\u26D3\u26E9\u26F0\u26F1\u26F4\u26F7\u26F8\u2702\u2708\u2709\u270F\u2712\u2714\u2716\u271D\u2721\u2733\u2734\u2744\u2747\u2763\u27A1\u2934\u2935\u2B05-\u2B07\u3030\u303D\u3297\u3299]|\uD83C[\uDD70\uDD71\uDD7E\uDD7F\uDE02\uDE37\uDF21\uDF24-\uDF2C\uDF36\uDF7D\uDF96\uDF97\uDF99-\uDF9B\uDF9E\uDF9F\uDFCD\uDFCE\uDFD4-\uDFDF\uDFF5\uDFF7]|\uD83D[\uDC3F\uDCFD\uDD49\uDD4A\uDD6F\uDD70\uDD73\uDD76-\uDD79\uDD87\uDD8A-\uDD8D\uDDA5\uDDA8\uDDB1\uDDB2\uDDBC\uDDC2-\uDDC4\uDDD1-\uDDD3\uDDDC-\uDDDE\uDDE1\uDDE3\uDDE8\uDDEF\uDDF3\uDDFA\uDECB\uDECD-\uDECF\uDEE0-\uDEE5\uDEE9\uDEF0\uDEF3])\uFE0F|\uD83C\uDFF3\uFE0F\u200D\uD83C\uDF08|\uD83D\uDC69\u200D\uD83D\uDC67|\uD83D\uDC69\u200D\uD83D\uDC66|\uD83D\uDE35\u200D\uD83D\uDCAB|\uD83D\uDE2E\u200D\uD83D\uDCA8|\uD83D\uDC15\u200D\uD83E\uDDBA|\uD83E\uDDD1(?:\uD83C\uDFFF|\uD83C\uDFFE|\uD83C\uDFFD|\uD83C\uDFFC|\uD83C\uDFFB)?|\uD83D\uDC69(?:\uD83C\uDFFF|\uD83C\uDFFE|\uD83C\uDFFD|\uD83C\uDFFC|\uD83C\uDFFB)?|\uD83C\uDDFD\uD83C\uDDF0|\uD83C\uDDF6\uD83C\uDDE6|\uD83C\uDDF4\uD83C\uDDF2|\uD83D\uDC08\u200D\u2B1B|\u2764\uFE0F\u200D(?:\uD83D\uDD25|\uD83E\uDE79)|\uD83D\uDC41\uFE0F|\uD83C\uDFF3\uFE0F|\uD83C\uDDFF(?:\uD83C[\uDDE6\uDDF2\uDDFC])|\uD83C\uDDFE(?:\uD83C[\uDDEA\uDDF9])|\uD83C\uDDFC(?:\uD83C[\uDDEB\uDDF8])|\uD83C\uDDFB(?:\uD83C[\uDDE6\uDDE8\uDDEA\uDDEC\uDDEE\uDDF3\uDDFA])|\uD83C\uDDFA(?:\uD83C[\uDDE6\uDDEC\uDDF2\uDDF3\uDDF8\uDDFE\uDDFF])|\uD83C\uDDF9(?:\uD83C[\uDDE6\uDDE8\uDDE9\uDDEB-\uDDED\uDDEF-\uDDF4\uDDF7\uDDF9\uDDFB\uDDFC\uDDFF])|\uD83C\uDDF8(?:\uD83C[\uDDE6-\uDDEA\uDDEC-\uDDF4\uDDF7-\uDDF9\uDDFB\uDDFD-\uDDFF])|\uD83C\uDDF7(?:\uD83C[\uDDEA\uDDF4\uDDF8\uDDFA\uDDFC])|\uD83C\uDDF5(?:\uD83C[\uDDE6\uDDEA-\uDDED\uDDF0-\uDDF3\uDDF7-\uDDF9\uDDFC\uDDFE])|\uD83C\uDDF3(?:\uD83C[\uDDE6\uDDE8\uDDEA-\uDDEC\uDDEE\uDDF1\uDDF4\uDDF5\uDDF7\uDDFA\uDDFF])|\uD83C\uDDF2(?:\uD83C[\uDDE6\uDDE8-\uDDED\uDDF0-\uDDFF])|\uD83C\uDDF1(?:\uD83C[\uDDE6-\uDDE8\uDDEE\uDDF0\uDDF7-\uDDFB\uDDFE])|\uD83C\uDDF0(?:\uD83C[\uDDEA\uDDEC-\uDDEE\uDDF2\uDDF3\uDDF5\uDDF7\uDDFC\uDDFE\uDDFF])|\uD83C\uDDEF(?:\uD83C[\uDDEA\uDDF2\uDDF4\uDDF5])|\uD83C\uDDEE(?:\uD83C[\uDDE8-\uDDEA\uDDF1-\uDDF4\uDDF6-\uDDF9])|\uD83C\uDDED(?:\uD83C[\uDDF0\uDDF2\uDDF3\uDDF7\uDDF9\uDDFA])|\uD83C\uDDEC(?:\uD83C[\uDDE6\uDDE7\uDDE9-\uDDEE\uDDF1-\uDDF3\uDDF5-\uDDFA\uDDFC\uDDFE])|\uD83C\uDDEB(?:\uD83C[\uDDEE-\uDDF0\uDDF2\uDDF4\uDDF7])|\uD83C\uDDEA(?:\uD83C[\uDDE6\uDDE8\uDDEA\uDDEC\uDDED\uDDF7-\uDDFA])|\uD83C\uDDE9(?:\uD83C[\uDDEA\uDDEC\uDDEF\uDDF0\uDDF2\uDDF4\uDDFF])|\uD83C\uDDE8(?:\uD83C[\uDDE6\uDDE8\uDDE9\uDDEB-\uDDEE\uDDF0-\uDDF5\uDDF7\uDDFA-\uDDFF])|\uD83C\uDDE7(?:\uD83C[\uDDE6\uDDE7\uDDE9-\uDDEF\uDDF1-\uDDF4\uDDF6-\uDDF9\uDDFB\uDDFC\uDDFE\uDDFF])|\uD83C\uDDE6(?:\uD83C[\uDDE8-\uDDEC\uDDEE\uDDF1\uDDF2\uDDF4\uDDF6-\uDDFA\uDDFC\uDDFD\uDDFF])|[#\*0-9]\uFE0F\u20E3|\u2764\uFE0F|(?:\uD83C[\uDFC3\uDFC4\uDFCA]|\uD83D[\uDC6E\uDC70\uDC71\uDC73\uDC77\uDC81\uDC82\uDC86\uDC87\uDE45-\uDE47\uDE4B\uDE4D\uDE4E\uDEA3\uDEB4-\uDEB6]|\uD83E[\uDD26\uDD35\uDD37-\uDD39\uDD3D\uDD3E\uDDB8\uDDB9\uDDCD-\uDDCF\uDDD4\uDDD6-\uDDDD])(?:\uD83C[\uDFFB-\uDFFF])|(?:\u26F9|\uD83C[\uDFCB\uDFCC]|\uD83D\uDD75)(?:\uFE0F|\uD83C[\uDFFB-\uDFFF])|\uD83C\uDFF4|(?:[\u270A\u270B]|\uD83C[\uDF85\uDFC2\uDFC7]|\uD83D[\uDC42\uDC43\uDC46-\uDC50\uDC66\uDC67\uDC6B-\uDC6D\uDC72\uDC74-\uDC76\uDC78\uDC7C\uDC83\uDC85\uDC8F\uDC91\uDCAA\uDD7A\uDD95\uDD96\uDE4C\uDE4F\uDEC0\uDECC]|\uD83E[\uDD0C\uDD0F\uDD18-\uDD1C\uDD1E\uDD1F\uDD30-\uDD34\uDD36\uDD77\uDDB5\uDDB6\uDDBB\uDDD2\uDDD3\uDDD5])(?:\uD83C[\uDFFB-\uDFFF])|(?:[\u261D\u270C\u270D]|\uD83D[\uDD74\uDD90])(?:\uFE0F|\uD83C[\uDFFB-\uDFFF])|[\u270A\u270B]|\uD83C[\uDF85\uDFC2\uDFC7]|\uD83D[\uDC08\uDC15\uDC3B\uDC42\uDC43\uDC46-\uDC50\uDC66\uDC67\uDC6B-\uDC6D\uDC72\uDC74-\uDC76\uDC78\uDC7C\uDC83\uDC85\uDC8F\uDC91\uDCAA\uDD7A\uDD95\uDD96\uDE2E\uDE35\uDE36\uDE4C\uDE4F\uDEC0\uDECC]|\uD83E[\uDD0C\uDD0F\uDD18-\uDD1C\uDD1E\uDD1F\uDD30-\uDD34\uDD36\uDD77\uDDB5\uDDB6\uDDBB\uDDD2\uDDD3\uDDD5]|\uD83C[\uDFC3\uDFC4\uDFCA]|\uD83D[\uDC6E\uDC70\uDC71\uDC73\uDC77\uDC81\uDC82\uDC86\uDC87\uDE45-\uDE47\uDE4B\uDE4D\uDE4E\uDEA3\uDEB4-\uDEB6]|\uD83E[\uDD26\uDD35\uDD37-\uDD39\uDD3D\uDD3E\uDDB8\uDDB9\uDDCD-\uDDCF\uDDD4\uDDD6-\uDDDD]|\uD83D\uDC6F|\uD83E[\uDD3C\uDDDE\uDDDF]|[\u231A\u231B\u23E9-\u23EC\u23F0\u23F3\u25FD\u25FE\u2614\u2615\u2648-\u2653\u267F\u2693\u26A1\u26AA\u26AB\u26BD\u26BE\u26C4\u26C5\u26CE\u26D4\u26EA\u26F2\u26F3\u26F5\u26FA\u26FD\u2705\u2728\u274C\u274E\u2753-\u2755\u2757\u2795-\u2797\u27B0\u27BF\u2B1B\u2B1C\u2B50\u2B55]|\uD83C[\uDC04\uDCCF\uDD8E\uDD91-\uDD9A\uDE01\uDE1A\uDE2F\uDE32-\uDE36\uDE38-\uDE3A\uDE50\uDE51\uDF00-\uDF20\uDF2D-\uDF35\uDF37-\uDF7C\uDF7E-\uDF84\uDF86-\uDF93\uDFA0-\uDFC1\uDFC5\uDFC6\uDFC8\uDFC9\uDFCF-\uDFD3\uDFE0-\uDFF0\uDFF8-\uDFFF]|\uD83D[\uDC00-\uDC07\uDC09-\uDC14\uDC16-\uDC3A\uDC3C-\uDC3E\uDC40\uDC44\uDC45\uDC51-\uDC65\uDC6A\uDC79-\uDC7B\uDC7D-\uDC80\uDC84\uDC88-\uDC8E\uDC90\uDC92-\uDCA9\uDCAB-\uDCFC\uDCFF-\uDD3D\uDD4B-\uDD4E\uDD50-\uDD67\uDDA4\uDDFB-\uDE2D\uDE2F-\uDE34\uDE37-\uDE44\uDE48-\uDE4A\uDE80-\uDEA2\uDEA4-\uDEB3\uDEB7-\uDEBF\uDEC1-\uDEC5\uDED0-\uDED2\uDED5-\uDED7\uDEEB\uDEEC\uDEF4-\uDEFC\uDFE0-\uDFEB]|\uD83E[\uDD0D\uDD0E\uDD10-\uDD17\uDD1D\uDD20-\uDD25\uDD27-\uDD2F\uDD3A\uDD3F-\uDD45\uDD47-\uDD76\uDD78\uDD7A-\uDDB4\uDDB7\uDDBA\uDDBC-\uDDCB\uDDD0\uDDE0-\uDDFF\uDE70-\uDE74\uDE78-\uDE7A\uDE80-\uDE86\uDE90-\uDEA8\uDEB0-\uDEB6\uDEC0-\uDEC2\uDED0-\uDED6]|(?:[\u231A\u231B\u23E9-\u23EC\u23F0\u23F3\u25FD\u25FE\u2614\u2615\u2648-\u2653\u267F\u2693\u26A1\u26AA\u26AB\u26BD\u26BE\u26C4\u26C5\u26CE\u26D4\u26EA\u26F2\u26F3\u26F5\u26FA\u26FD\u2705\u270A\u270B\u2728\u274C\u274E\u2753-\u2755\u2757\u2795-\u2797\u27B0\u27BF\u2B1B\u2B1C\u2B50\u2B55]|\uD83C[\uDC04\uDCCF\uDD8E\uDD91-\uDD9A\uDDE6-\uDDFF\uDE01\uDE1A\uDE2F\uDE32-\uDE36\uDE38-\uDE3A\uDE50\uDE51\uDF00-\uDF20\uDF2D-\uDF35\uDF37-\uDF7C\uDF7E-\uDF93\uDFA0-\uDFCA\uDFCF-\uDFD3\uDFE0-\uDFF0\uDFF4\uDFF8-\uDFFF]|\uD83D[\uDC00-\uDC3E\uDC40\uDC42-\uDCFC\uDCFF-\uDD3D\uDD4B-\uDD4E\uDD50-\uDD67\uDD7A\uDD95\uDD96\uDDA4\uDDFB-\uDE4F\uDE80-\uDEC5\uDECC\uDED0-\uDED2\uDED5-\uDED7\uDEEB\uDEEC\uDEF4-\uDEFC\uDFE0-\uDFEB]|\uD83E[\uDD0C-\uDD3A\uDD3C-\uDD45\uDD47-\uDD78\uDD7A-\uDDCB\uDDCD-\uDDFF\uDE70-\uDE74\uDE78-\uDE7A\uDE80-\uDE86\uDE90-\uDEA8\uDEB0-\uDEB6\uDEC0-\uDEC2\uDED0-\uDED6])|(?:[#\*0-9\xA9\xAE\u203C\u2049\u2122\u2139\u2194-\u2199\u21A9\u21AA\u231A\u231B\u2328\u23CF\u23E9-\u23F3\u23F8-\u23FA\u24C2\u25AA\u25AB\u25B6\u25C0\u25FB-\u25FE\u2600-\u2604\u260E\u2611\u2614\u2615\u2618\u261D\u2620\u2622\u2623\u2626\u262A\u262E\u262F\u2638-\u263A\u2640\u2642\u2648-\u2653\u265F\u2660\u2663\u2665\u2666\u2668\u267B\u267E\u267F\u2692-\u2697\u2699\u269B\u269C\u26A0\u26A1\u26A7\u26AA\u26AB\u26B0\u26B1\u26BD\u26BE\u26C4\u26C5\u26C8\u26CE\u26CF\u26D1\u26D3\u26D4\u26E9\u26EA\u26F0-\u26F5\u26F7-\u26FA\u26FD\u2702\u2705\u2708-\u270D\u270F\u2712\u2714\u2716\u271D\u2721\u2728\u2733\u2734\u2744\u2747\u274C\u274E\u2753-\u2755\u2757\u2763\u2764\u2795-\u2797\u27A1\u27B0\u27BF\u2934\u2935\u2B05-\u2B07\u2B1B\u2B1C\u2B50\u2B55\u3030\u303D\u3297\u3299]|\uD83C[\uDC04\uDCCF\uDD70\uDD71\uDD7E\uDD7F\uDD8E\uDD91-\uDD9A\uDDE6-\uDDFF\uDE01\uDE02\uDE1A\uDE2F\uDE32-\uDE3A\uDE50\uDE51\uDF00-\uDF21\uDF24-\uDF93\uDF96\uDF97\uDF99-\uDF9B\uDF9E-\uDFF0\uDFF3-\uDFF5\uDFF7-\uDFFF]|\uD83D[\uDC00-\uDCFD\uDCFF-\uDD3D\uDD49-\uDD4E\uDD50-\uDD67\uDD6F\uDD70\uDD73-\uDD7A\uDD87\uDD8A-\uDD8D\uDD90\uDD95\uDD96\uDDA4\uDDA5\uDDA8\uDDB1\uDDB2\uDDBC\uDDC2-\uDDC4\uDDD1-\uDDD3\uDDDC-\uDDDE\uDDE1\uDDE3\uDDE8\uDDEF\uDDF3\uDDFA-\uDE4F\uDE80-\uDEC5\uDECB-\uDED2\uDED5-\uDED7\uDEE0-\uDEE5\uDEE9\uDEEB\uDEEC\uDEF0\uDEF3-\uDEFC\uDFE0-\uDFEB]|\uD83E[\uDD0C-\uDD3A\uDD3C-\uDD45\uDD47-\uDD78\uDD7A-\uDDCB\uDDCD-\uDDFF\uDE70-\uDE74\uDE78-\uDE7A\uDE80-\uDE86\uDE90-\uDEA8\uDEB0-\uDEB6\uDEC0-\uDEC2\uDED0-\uDED6])\uFE0F|(?:[\u261D\u26F9\u270A-\u270D]|\uD83C[\uDF85\uDFC2-\uDFC4\uDFC7\uDFCA-\uDFCC]|\uD83D[\uDC42\uDC43\uDC46-\uDC50\uDC66-\uDC78\uDC7C\uDC81-\uDC83\uDC85-\uDC87\uDC8F\uDC91\uDCAA\uDD74\uDD75\uDD7A\uDD90\uDD95\uDD96\uDE45-\uDE47\uDE4B-\uDE4F\uDEA3\uDEB4-\uDEB6\uDEC0\uDECC]|\uD83E[\uDD0C\uDD0F\uDD18-\uDD1F\uDD26\uDD30-\uDD39\uDD3C-\uDD3E\uDD77\uDDB5\uDDB6\uDDB8\uDDB9\uDDBB\uDDCD-\uDDCF\uDDD1-\uDDDD])/g;
};
var sD = L(FD);
var w = 10;
var N = (e2 = 0) => (u2) => `\x1B[${u2 + e2}m`;
var I = (e2 = 0) => (u2) => `\x1B[${38 + e2};5;${u2}m`;
var R = (e2 = 0) => (u2, t, F2) => `\x1B[${38 + e2};2;${u2};${t};${F2}m`;
var r = { modifier: { reset: [0, 0], bold: [1, 22], dim: [2, 22], italic: [3, 23], underline: [4, 24], overline: [53, 55], inverse: [7, 27], hidden: [8, 28], strikethrough: [9, 29] }, color: { black: [30, 39], red: [31, 39], green: [32, 39], yellow: [33, 39], blue: [34, 39], magenta: [35, 39], cyan: [36, 39], white: [37, 39], blackBright: [90, 39], gray: [90, 39], grey: [90, 39], redBright: [91, 39], greenBright: [92, 39], yellowBright: [93, 39], blueBright: [94, 39], magentaBright: [95, 39], cyanBright: [96, 39], whiteBright: [97, 39] }, bgColor: { bgBlack: [40, 49], bgRed: [41, 49], bgGreen: [42, 49], bgYellow: [43, 49], bgBlue: [44, 49], bgMagenta: [45, 49], bgCyan: [46, 49], bgWhite: [47, 49], bgBlackBright: [100, 49], bgGray: [100, 49], bgGrey: [100, 49], bgRedBright: [101, 49], bgGreenBright: [102, 49], bgYellowBright: [103, 49], bgBlueBright: [104, 49], bgMagentaBright: [105, 49], bgCyanBright: [106, 49], bgWhiteBright: [107, 49] } };
Object.keys(r.modifier);
var iD = Object.keys(r.color);
var CD = Object.keys(r.bgColor);
[...iD, ...CD];
function rD() {
  const e2 = /* @__PURE__ */ new Map();
  for (const [u2, t] of Object.entries(r)) {
    for (const [F2, s] of Object.entries(t)) r[F2] = { open: `\x1B[${s[0]}m`, close: `\x1B[${s[1]}m` }, t[F2] = r[F2], e2.set(s[0], s[1]);
    Object.defineProperty(r, u2, { value: t, enumerable: false });
  }
  return Object.defineProperty(r, "codes", { value: e2, enumerable: false }), r.color.close = "\x1B[39m", r.bgColor.close = "\x1B[49m", r.color.ansi = N(), r.color.ansi256 = I(), r.color.ansi16m = R(), r.bgColor.ansi = N(w), r.bgColor.ansi256 = I(w), r.bgColor.ansi16m = R(w), Object.defineProperties(r, { rgbToAnsi256: { value: (u2, t, F2) => u2 === t && t === F2 ? u2 < 8 ? 16 : u2 > 248 ? 231 : Math.round((u2 - 8) / 247 * 24) + 232 : 16 + 36 * Math.round(u2 / 255 * 5) + 6 * Math.round(t / 255 * 5) + Math.round(F2 / 255 * 5), enumerable: false }, hexToRgb: { value: (u2) => {
    const t = /[a-f\d]{6}|[a-f\d]{3}/i.exec(u2.toString(16));
    if (!t) return [0, 0, 0];
    let [F2] = t;
    F2.length === 3 && (F2 = [...F2].map((i) => i + i).join(""));
    const s = Number.parseInt(F2, 16);
    return [s >> 16 & 255, s >> 8 & 255, s & 255];
  }, enumerable: false }, hexToAnsi256: { value: (u2) => r.rgbToAnsi256(...r.hexToRgb(u2)), enumerable: false }, ansi256ToAnsi: { value: (u2) => {
    if (u2 < 8) return 30 + u2;
    if (u2 < 16) return 90 + (u2 - 8);
    let t, F2, s;
    if (u2 >= 232) t = ((u2 - 232) * 10 + 8) / 255, F2 = t, s = t;
    else {
      u2 -= 16;
      const C2 = u2 % 36;
      t = Math.floor(u2 / 36) / 5, F2 = Math.floor(C2 / 6) / 5, s = C2 % 6 / 5;
    }
    const i = Math.max(t, F2, s) * 2;
    if (i === 0) return 30;
    let D2 = 30 + (Math.round(s) << 2 | Math.round(F2) << 1 | Math.round(t));
    return i === 2 && (D2 += 60), D2;
  }, enumerable: false }, rgbToAnsi: { value: (u2, t, F2) => r.ansi256ToAnsi(r.rgbToAnsi256(u2, t, F2)), enumerable: false }, hexToAnsi: { value: (u2) => r.ansi256ToAnsi(r.hexToAnsi256(u2)), enumerable: false } }), r;
}
var ED = rD();
var nD = "]";
var _ = `${nD}8;;`;
var xD = ["up", "down", "left", "right", "space", "enter", "cancel"];
var B = { actions: new Set(xD), aliases: /* @__PURE__ */ new Map([["k", "up"], ["j", "down"], ["h", "left"], ["l", "right"], ["", "cancel"], ["escape", "cancel"]]) };
var AD = globalThis.process.platform.startsWith("win");
var A;
A = /* @__PURE__ */ new WeakMap();

// node_modules/.pnpm/@clack+prompts@0.11.0/node_modules/@clack/prompts/dist/index.mjs
var import_picocolors = __toESM(require_picocolors(), 1);
var import_sisteransi2 = __toESM(require_src(), 1);
import y from "process";
function ce() {
  return y.platform !== "win32" ? y.env.TERM !== "linux" : !!y.env.CI || !!y.env.WT_SESSION || !!y.env.TERMINUS_SUBLIME || y.env.ConEmuTask === "{cmd::Cmder}" || y.env.TERM_PROGRAM === "Terminus-Sublime" || y.env.TERM_PROGRAM === "vscode" || y.env.TERM === "xterm-256color" || y.env.TERM === "alacritty" || y.env.TERMINAL_EMULATOR === "JetBrains-JediTerm";
}
var V = ce();
var u = (t, n) => V ? t : n;
var le = u("\u25C6", "*");
var L2 = u("\u25A0", "x");
var W2 = u("\u25B2", "x");
var C = u("\u25C7", "o");
var ue = u("\u250C", "T");
var o = u("\u2502", "|");
var d = u("\u2514", "\u2014");
var k = u("\u25CF", ">");
var P = u("\u25CB", " ");
var A2 = u("\u25FB", "[\u2022]");
var T = u("\u25FC", "[+]");
var F = u("\u25FB", "[ ]");
var $e = u("\u25AA", "\u2022");
var _2 = u("\u2500", "-");
var me = u("\u256E", "+");
var de = u("\u251C", "+");
var pe = u("\u256F", "+");
var q = u("\u25CF", "\u2022");
var D = u("\u25C6", "*");
var U = u("\u25B2", "!");
var K = u("\u25A0", "x");
var J = `${import_picocolors.default.gray(o)}  `;

// src/utils/volcengineSign.ts
import { createHash, createHmac } from "crypto";

// src/auth/profile.ts
import { existsSync as existsSync6, mkdirSync as mkdirSync2, readFileSync as readFileSync5, readdirSync as readdirSync3, writeFileSync as writeFileSync2, rmSync } from "fs";
import { join as join7 } from "path";

// src/auth/paths.ts
import { homedir } from "os";
import { join as join6 } from "path";

// src/auth/resolve.ts
import { existsSync as existsSync7, readFileSync as readFileSync6 } from "fs";

// src/auth/oauth.ts
import { createHash as createHash2, randomBytes } from "crypto";
import { createServer } from "http";

// src/utils/openBrowser.ts
import { spawn } from "child_process";
import { platform } from "os";

// src/platform/configuration.ts
var import_yaml3 = __toESM(require_dist(), 1);
import { existsSync as existsSync9, readFileSync as readFileSync8 } from "fs";
import { join as join9 } from "path";

// src/platform/globalConfig.ts
var import_yaml2 = __toESM(require_dist(), 1);
import { existsSync as existsSync8, mkdirSync as mkdirSync3, readFileSync as readFileSync7, writeFileSync as writeFileSync3 } from "fs";
import { homedir as homedir2 } from "os";
import { dirname as dirname2, join as join8 } from "path";

// src/auth/session.ts
import { closeSync, existsSync as existsSync10, mkdirSync as mkdirSync4, openSync, readFileSync as readFileSync9, renameSync, rmSync as rmSync2, writeFileSync as writeFileSync4 } from "fs";
import { execFileSync as execFileSync2 } from "child_process";
import { platform as platform2 } from "os";
import { join as join10 } from "path";

// src/sandbox/resolve.ts
import { randomUUID } from "crypto";

// src/sandbox/envConfig.ts
import { existsSync as existsSync11, readFileSync as readFileSync10 } from "fs";

// src/sandbox/modelConfig.ts
var CODE_ENV_CODEX_HOME = "/home/gem/.codex";
var CODEX_MODEL_CATALOG_PATH = `${CODE_ENV_CODEX_HOME}/model-catalog.json`;
var ModelProviderType = {
  MODEL_SQUARE: "model_square",
  CODING_PLAN: "coding_plan",
  AGENT_PLAN: "agent_plan",
  BYTEPLUS_MODEL_SQUARE: "byteplus_model_square",
  BYTEPLUS_CODING_PLAN: "byteplus_coding_plan"
};
var DEFAULT_MODEL_CONTEXT_WINDOW = 1e6;
var LIMITED_MODEL_CONTEXT_WINDOW = 2e5;
var DEFAULT_MODEL_PROVIDER = ModelProviderType.MODEL_SQUARE;
var BYTEPLUS_DEFAULT_MODEL_PROVIDER = ModelProviderType.BYTEPLUS_MODEL_SQUARE;
var MODEL_PROVIDER_CONFIGS = {
  [ModelProviderType.MODEL_SQUARE]: {
    modelBaseUrl: "https://ark.cn-beijing.volces.com/api/v3",
    anthropicBaseUrl: "https://ark.cn-beijing.volces.com/api/compatible",
    defaultModelName: "deepseek-v4-flash-ga-260731",
    models: {
      "deepseek-v4-flash-ga-260731": { supportsReasoningSummaries: true, contextWindow: DEFAULT_MODEL_CONTEXT_WINDOW },
      "glm-5-2-260617": { supportsReasoningSummaries: true, contextWindow: DEFAULT_MODEL_CONTEXT_WINDOW },
      "doubao-seed-2-0-pro-260215": { supportsReasoningSummaries: true, contextWindow: LIMITED_MODEL_CONTEXT_WINDOW },
      "deepseek-v4-flash-260425": { supportsReasoningSummaries: true, contextWindow: DEFAULT_MODEL_CONTEXT_WINDOW },
      "deepseek-v4-pro-260425": { supportsReasoningSummaries: true, contextWindow: DEFAULT_MODEL_CONTEXT_WINDOW }
    }
  },
  [ModelProviderType.CODING_PLAN]: {
    modelBaseUrl: "https://ark.cn-beijing.volces.com/api/coding/v3",
    anthropicBaseUrl: "https://ark.cn-beijing.volces.com/api/coding",
    defaultModelName: "deepseek-v4-flash",
    models: {
      "doubao-seed-2.0-pro": { supportsReasoningSummaries: true, contextWindow: LIMITED_MODEL_CONTEXT_WINDOW },
      "deepseek-v4-flash": { supportsReasoningSummaries: true, contextWindow: DEFAULT_MODEL_CONTEXT_WINDOW },
      "deepseek-v4-pro": { supportsReasoningSummaries: true, contextWindow: DEFAULT_MODEL_CONTEXT_WINDOW }
    }
  },
  [ModelProviderType.AGENT_PLAN]: {
    modelBaseUrl: "https://ark.cn-beijing.volces.com/api/plan/v3",
    anthropicBaseUrl: "https://ark.cn-beijing.volces.com/api/plan",
    defaultModelName: "deepseek-v4-flash",
    models: {
      "doubao-seed-2.0-pro": { supportsReasoningSummaries: true, contextWindow: LIMITED_MODEL_CONTEXT_WINDOW },
      "deepseek-v4-flash": { supportsReasoningSummaries: true, contextWindow: DEFAULT_MODEL_CONTEXT_WINDOW },
      "deepseek-v4-pro": { supportsReasoningSummaries: true, contextWindow: DEFAULT_MODEL_CONTEXT_WINDOW }
    }
  },
  [ModelProviderType.BYTEPLUS_MODEL_SQUARE]: {
    modelBaseUrl: "https://ark.ap-southeast.bytepluses.com/api/v3",
    anthropicBaseUrl: "https://ark.ap-southeast.bytepluses.com/api/compatible",
    defaultModelName: "deepseek-v4-flash-ga-260731",
    models: {
      "deepseek-v4-flash-ga-260731": { supportsReasoningSummaries: true, contextWindow: DEFAULT_MODEL_CONTEXT_WINDOW },
      "doubao-seed-2-0-pro-260215": { supportsReasoningSummaries: true, contextWindow: LIMITED_MODEL_CONTEXT_WINDOW },
      "deepseek-v4-flash-260425": { supportsReasoningSummaries: true, contextWindow: DEFAULT_MODEL_CONTEXT_WINDOW },
      "deepseek-v4-pro-260425": { supportsReasoningSummaries: true, contextWindow: DEFAULT_MODEL_CONTEXT_WINDOW }
    }
  },
  [ModelProviderType.BYTEPLUS_CODING_PLAN]: {
    modelBaseUrl: "https://ark.ap-southeast.bytepluses.com/api/coding/v3",
    anthropicBaseUrl: "https://ark.ap-southeast.bytepluses.com/api/coding",
    defaultModelName: "dola-seed-2.0-pro",
    models: {
      "dola-seed-2.0-pro": { supportsReasoningSummaries: true, contextWindow: LIMITED_MODEL_CONTEXT_WINDOW },
      "dola-seed-2.0-lite": { supportsReasoningSummaries: true, contextWindow: LIMITED_MODEL_CONTEXT_WINDOW },
      "dola-seed-2.0-code": { supportsReasoningSummaries: true, contextWindow: LIMITED_MODEL_CONTEXT_WINDOW }
    }
  }
};
var DEFAULT_MODEL_NAME = MODEL_PROVIDER_CONFIGS[DEFAULT_MODEL_PROVIDER].defaultModelName;
var DEFAULT_MODEL_BASE_URL = MODEL_PROVIDER_CONFIGS[DEFAULT_MODEL_PROVIDER].modelBaseUrl;
var DEFAULT_ANTHROPIC_BASE_URL = MODEL_PROVIDER_CONFIGS[DEFAULT_MODEL_PROVIDER].anthropicBaseUrl;
var BUILTIN_MODEL_BASE_URL_PROVIDERS = new Map(
  Object.entries(MODEL_PROVIDER_CONFIGS).map(([provider, config]) => [config.modelBaseUrl, provider])
);
var BUILTIN_MODEL_BASE_URLS = new Set(BUILTIN_MODEL_BASE_URL_PROVIDERS.keys());

// src/integrations/tos/sign.ts
import { createHash as createHash3, createHmac as createHmac2 } from "crypto";

// src/utils/credentials.ts
import { readFileSync as readFileSync11, existsSync as existsSync12 } from "fs";
import { join as join11 } from "path";

// src/sandbox/tosConfig.ts
var EMPTY_BODY = Buffer.alloc(0);

// src/sandbox/gitConfig.ts
import { execFileSync as execFileSync3 } from "child_process";
import { existsSync as existsSync13, readFileSync as readFileSync12, statSync as statSync3 } from "fs";
import { homedir as homedir3 } from "os";
import { join as join12, resolve as resolve4 } from "path";

// node_modules/.pnpm/ws@8.21.0/node_modules/ws/wrapper.mjs
var import_stream = __toESM(require_stream(), 1);
var import_extension = __toESM(require_extension(), 1);
var import_permessage_deflate = __toESM(require_permessage_deflate(), 1);
var import_receiver = __toESM(require_receiver(), 1);
var import_sender = __toESM(require_sender(), 1);
var import_subprotocol = __toESM(require_subprotocol(), 1);
var import_websocket = __toESM(require_websocket(), 1);
var import_websocket_server = __toESM(require_websocket_server(), 1);

// src/sandbox/terminal.ts
import { platform as platform3 } from "os";

// src/sandbox/files.ts
import { execFileSync as execFileSync4, spawnSync } from "child_process";
import {
  copyFileSync,
  existsSync as existsSync14,
  mkdirSync as mkdirSync5,
  mkdtempSync,
  readdirSync as readdirSync4,
  readFileSync as readFileSync13,
  rmSync as rmSync3,
  statSync as statSync4,
  writeFileSync as writeFileSync5
} from "fs";
import { tmpdir } from "os";
import { basename as basename2, dirname as dirname3, isAbsolute as isAbsolute3, join as join13, posix, relative as relative4, resolve as resolve5, sep } from "path";
import { randomUUID as randomUUID2 } from "crypto";

// src/sandbox/inject.ts
import { existsSync as existsSync15, readFileSync as readFileSync14 } from "fs";
import { homedir as homedir4 } from "os";
import { join as join14 } from "path";
import { spawnSync as spawnSync2 } from "child_process";

// src/sandbox/a2aClient.ts
import { randomUUID as nodeRandomUUID } from "crypto";

// src/sandbox/configStore.ts
var import_yaml4 = __toESM(require_dist(), 1);
import { existsSync as existsSync16, mkdirSync as mkdirSync6, readFileSync as readFileSync15, renameSync as renameSync2, rmSync as rmSync4, writeFileSync as writeFileSync6 } from "fs";
import { dirname as dirname4, join as join15 } from "path";
var SANDBOX_CONFIG_PATH = join15(".agentkit", "sandbox.yaml");
var VALID_TOOL_TYPES = [
  "All-in-one",
  "Skill",
  "CodeEnv",
  "DevEnv",
  "ArkClawEnv",
  "HermesEnv",
  "Private"
];
var VALID_CPU_VALUES = [2, 4, 8, 16];
var SandboxConfigError = class extends Error {
  constructor(message) {
    super(message);
    this.name = "SandboxConfigError";
  }
};
function strValue(value) {
  const resolved = value.trim();
  if (!resolved) throw new SandboxConfigError("value must not be empty");
  return resolved;
}
function intValue(value) {
  const resolved = Number.parseInt(value.trim(), 10);
  if (!Number.isFinite(resolved) || String(resolved) !== value.trim()) {
    throw new SandboxConfigError("value must be an integer");
  }
  return resolved;
}
function positiveIntValue(value) {
  const resolved = intValue(value);
  if (resolved <= 0) throw new SandboxConfigError("value must be greater than 0");
  return resolved;
}
function boolValue(value) {
  const resolved = value.trim().toLowerCase();
  if (["true", "1", "yes", "y", "on"].includes(resolved)) return true;
  if (["false", "0", "no", "n", "off"].includes(resolved)) return false;
  throw new SandboxConfigError("value must be a boolean");
}
function stringListValue(value) {
  const resolved = value.trim();
  if (!resolved) throw new SandboxConfigError("value must not be empty");
  const rawItems = resolved.startsWith("[") ? parseJsonArray(resolved) : resolved.split(",").map((item) => item.trim());
  const result = [];
  for (const [index, item] of rawItems.entries()) {
    if (typeof item !== "string" || !item.trim()) {
      throw new SandboxConfigError(`list item #${index + 1} must be a non-empty string`);
    }
    result.push(item.trim());
  }
  if (result.length === 0) throw new SandboxConfigError("value must contain at least one item");
  return result;
}
function parseJsonArray(value) {
  try {
    const parsed = JSON.parse(value);
    if (!Array.isArray(parsed)) throw new SandboxConfigError("value must be a JSON array");
    return parsed;
  } catch (err) {
    if (err instanceof SandboxConfigError) throw err;
    throw new SandboxConfigError("value must be a JSON array or CSV list");
  }
}
var CONFIG_KEY_SPECS = {
  "model-name": { path: ["model", "name"], parser: strValue },
  "model-base-url": { path: ["model", "base_url"], parser: strValue },
  "model-provider": { path: ["model", "provider"], parser: strValue },
  "model-api-key": { path: ["model", "api_key"], parser: strValue },
  "network-public": { path: ["network", "enable_public"], parser: boolValue },
  "network-private": { path: ["network", "enable_private"], parser: boolValue },
  "network-shared-internet": {
    path: ["network", "enable_shared_internet"],
    parser: boolValue
  },
  "network-vpc-id": { path: ["network", "vpc_id"], parser: strValue },
  "network-subnet-ids": { path: ["network", "subnet_ids"], parser: stringListValue },
  "tool-type": { path: ["tool", "type"], parser: strValue, allowed: VALID_TOOL_TYPES },
  "tool-id": { path: ["session", "tool_id"], parser: strValue },
  "tool-name": { path: ["session", "tool_name"], parser: strValue },
  region: { path: ["tool", "region"], parser: strValue },
  cpu: { path: ["tool", "cpu"], parser: intValue, allowed: VALID_CPU_VALUES },
  "tos-bucket": { path: ["tool", "tos_bucket"], parser: strValue },
  "tos-mount": { path: ["tool", "tos_mount"], parser: strValue },
  "role-name": { path: ["tool", "role_name"], parser: strValue },
  "enable-snapshot": { path: ["tool", "enable_snapshot"], parser: boolValue },
  "websearch-apikey": { path: ["tool", "websearch_apikey"], parser: strValue },
  "image-url": { path: ["tool", "image_url"], parser: strValue },
  "tool-image-url": { path: ["tool", "image_url"], parser: strValue },
  "session-id": { path: ["session", "id"], parser: strValue },
  ttl: { path: ["session", "ttl"], parser: positiveIntValue },
  "git-config": { path: ["session", "git_config"], parser: strValue }
};
var CONFIG_KEY_ALIASES = Object.fromEntries(
  Object.keys(CONFIG_KEY_SPECS).map((key) => [key.replaceAll("-", "_"), key])
);
Object.assign(CONFIG_KEY_ALIASES, {
  "websearch-api-key": "websearch-apikey",
  websearch_api_key: "websearch-apikey",
  "network-enable-public": "network-public",
  network_enable_public: "network-public",
  "network-enable-private": "network-private",
  network_enable_private: "network-private",
  "network-enable-shared-internet": "network-shared-internet",
  network_enable_shared_internet: "network-shared-internet",
  tool_type: "tool-type",
  tool_id: "tool-id",
  tool_name: "tool-name",
  model_name: "model-name",
  model_base_url: "model-base-url",
  model_provider: "model-provider",
  model_api_key: "model-api-key",
  session_id: "session-id"
});

// src/sandbox/sessionStore.ts
import { existsSync as existsSync17, mkdirSync as mkdirSync7, readFileSync as readFileSync16, renameSync as renameSync3, rmSync as rmSync5, writeFileSync as writeFileSync7 } from "fs";
import { dirname as dirname5, join as join16 } from "path";
var SANDBOX_SESSION_STORE_PATH = join16(".agentkit", "sandbox", "sessions.json");

// src/sandbox/toolStore.ts
import { existsSync as existsSync18, mkdirSync as mkdirSync8, readFileSync as readFileSync17, renameSync as renameSync4, rmSync as rmSync6, writeFileSync as writeFileSync8 } from "fs";
import { dirname as dirname6, join as join17 } from "path";
var SANDBOX_TOOL_STORE_PATH = join17(".agentkit", "sandbox", "tools.json");

// src/sandbox/sessionCreate.ts
import { randomUUID as randomUUID3 } from "crypto";

// src/commands/migrate/remote/artifact.ts
import { execFileSync as execFileSync5 } from "child_process";
import { createHash as createHash5 } from "crypto";
import { existsSync as existsSync21, mkdirSync as mkdirSync10, readdirSync as readdirSync6, readFileSync as readFileSync19, rmSync as rmSync7, statSync as statSync5, writeFileSync as writeFileSync10 } from "fs";
import { join as join20, relative as relative7, resolve as resolve8 } from "path";

// src/commands/migrate/remote/store.ts
import { createHash as createHash4 } from "crypto";
import { existsSync as existsSync20, mkdirSync as mkdirSync9, readdirSync as readdirSync5, readFileSync as readFileSync18, writeFileSync as writeFileSync9 } from "fs";
import { dirname as dirname7, join as join19, relative as relative6, resolve as resolve7 } from "path";

// src/commands/migrate/remote/source-filter.ts
import { existsSync as existsSync19 } from "fs";
import { join as join18, relative as relative5, resolve as resolve6 } from "path";

// src/commands/migrate/remote/store.ts
var STORE_DIR = join19(".agentkit", "migrate", "jobs");

// src/commands/migrate/remote/shell.ts
import { randomUUID as randomUUID4 } from "crypto";
import { basename as basename3 } from "path";
function shellQuote(value) {
  return `'${value.replace(/'/g, "'\\''")}'`;
}
function shellVar(name) {
  return `"$${name}"`;
}
function remoteSkillRoot(spec, job) {
  return job.remoteSkillDir ?? job.remoteImageFileDir ?? spec.remoteSkillDir;
}
function remoteSourceToVeadkDir(spec, job) {
  return `${remoteSkillRoot(spec, job)}/source-to-veadk`;
}
function remoteStateDir(job) {
  return `${job.remoteDir}/state`;
}
function remoteLogsDir(job) {
  return `${job.remoteDir}/logs`;
}
function remoteArtifactDir(job) {
  return `${job.remoteDir}/artifacts`;
}
function remoteCodexSessionPath(job) {
  return `${remoteStateDir(job)}/codex_session_id`;
}
function remoteValidationFindingsPath(job) {
  return `${job.remoteProjectDir}/validation_findings.json`;
}
function remoteStatusWriteCommand(job, state, extra = "") {
  return [
    `printf '{"job_id":"%s","state":"%s","updated_at":"%s"%s}\\n'`,
    shellQuote(job.jobId),
    shellQuote(state),
    `"$(date -u +%Y-%m-%dT%H:%M:%SZ)"`,
    shellQuote(extra),
    `> ${shellQuote(job.remoteStatusPath)}`
  ].join(" ");
}
function remoteFailCommand(spec, job, message) {
  return [
    `printf '%s\\n\\n%s\\n' ${shellQuote(spec.failureReportTitle)} ${shellQuote(message)} > ${shellQuote(job.remoteFailureReportPath)}`,
    remoteStatusWriteCommand(job, "Failed", `,"failure_report":"${job.remoteFailureReportPath}"`)
  ].join("; ");
}
function remoteEnvEntries(spec, job) {
  const skillRoot = remoteSkillRoot(spec, job);
  const sourceToVeadkDir = remoteSourceToVeadkDir(spec, job);
  const envs = [
    `HOME=${shellQuote("/home/gem")}`,
    `AGENTKIT_MIGRATE_ASSET_DIR=${shellQuote(sourceToVeadkDir)}`,
    `AGENTKIT_MIGRATE_SKILL_PATH=${shellQuote(skillRoot)}`,
    `AGENTKIT_MIGRATE_INPUT_DIR=${shellQuote(job.remoteInputDir)}`,
    `AGENTKIT_MIGRATE_OUTPUT_DIR=${shellQuote(job.remoteProjectDir)}`,
    `AGENTKIT_MIGRATE_STATUS_DIR=${shellQuote(remoteStateDir(job))}`,
    `AGENTKIT_MIGRATE_STATUS_PATH=${shellQuote(job.remoteStatusPath)}`,
    `AGENTKIT_MIGRATE_SOURCE_CAPABILITIES=${shellQuote(`${remoteStateDir(job)}/source_capabilities.json`)}`,
    `AGENTKIT_MIGRATE_CONTEXT_JSON=${shellQuote(`${remoteStateDir(job)}/migration_context.json`)}`,
    `AGENTKIT_MIGRATE_CONTEXT_MD=${shellQuote(`${remoteStateDir(job)}/migration_context.md`)}`,
    `AGENTKIT_TARGET_PROJECT=${shellQuote(job.project)}`
  ];
  if (job.cloudProvider) {
    envs.push(
      `AGENTKIT_TARGET_CLOUD_PROVIDER=${shellQuote(job.cloudProvider)}`,
      `AGENTKIT_CLOUD_PROVIDER=${shellQuote(job.cloudProvider)}`,
      `CLOUD_PROVIDER=${shellQuote(job.cloudProvider)}`
    );
  }
  if (job.region) {
    envs.push(`AGENTKIT_TARGET_REGION=${shellQuote(job.region)}`);
    if (job.cloudProvider === "byteplus") {
      envs.push(`BYTEPLUS_REGION=${shellQuote(job.region)}`);
    } else if (job.cloudProvider === "volcengine") {
      envs.push(`VOLCENGINE_REGION=${shellQuote(job.region)}`);
    }
  }
  if (job.modelProvider) {
    envs.push(
      `AGENTKIT_MIGRATE_MODEL_PROVIDER=${shellQuote(job.modelProvider)}`,
      `AGENTKIT_SANDBOX_MODEL_PROVIDER=${shellQuote(job.modelProvider)}`
    );
  }
  if (job.modelName) {
    envs.push(
      `AGENTKIT_MIGRATE_MODEL_NAME=${shellQuote(job.modelName)}`,
      `CODEX_MODEL=${shellQuote(job.modelName)}`,
      `OPENCODE_MODEL=${shellQuote(job.modelName)}`,
      `ANTHROPIC_MODEL=${shellQuote(job.modelName)}`,
      `ARK_MODEL_ID=${shellQuote(job.modelName)}`,
      `ARK_MODEL=${shellQuote(job.modelName)}`,
      `MODEL_NAME=${shellQuote(job.modelName)}`,
      `MODEL_AGENT_NAME=${shellQuote(job.modelName)}`,
      `codex_model=${shellQuote(job.modelName)}`
    );
  }
  if (job.appName) {
    envs.push(`AGENTKIT_MIGRATE_APP_NAME=${shellQuote(job.appName)}`);
  }
  if (job.targetModelId) {
    envs.push(`AGENTKIT_TARGET_MODEL_ID=${shellQuote(job.targetModelId)}`);
  }
  if (job.targetModelBaseUrl) {
    envs.push(`AGENTKIT_TARGET_MODEL_BASE_URL=${shellQuote(job.targetModelBaseUrl)}`);
  }
  if (job.targetModelApiKeyEnv) {
    envs.push(`AGENTKIT_TARGET_MODEL_API_KEY_ENV=${shellQuote(job.targetModelApiKeyEnv)}`);
  }
  envs.push(...spec.additionalRemoteEnv?.(job) ?? []);
  return envs;
}
function remoteEnvExportLines(spec, job) {
  return remoteEnvEntries(spec, job).map((entry) => `export ${entry}`).join("\n");
}
function remotePrepareCommand(job) {
  return [job.remoteProjectDir, remoteArtifactDir(job), remoteLogsDir(job), remoteStateDir(job)].map((dir) => `mkdir -p ${shellQuote(dir)}`).join("; ");
}
function remoteRequireCodexCommand(spec, job) {
  return `command -v codex >/dev/null 2>&1 || { ${remoteFailCommand(spec, job, "codex executable not found in sandbox PATH.")}; exit 0; }`;
}
function remoteEnsureAgentkitCommand(spec, job) {
  const wrapperPath = "/home/gem/.local/bin/agentkit";
  const bootstrap = [
    `python_bin=$([ -x /home/gem/venv_veadk/bin/python ] && printf '%s' /home/gem/venv_veadk/bin/python || command -v python3 || command -v python || true)`,
    `test -n "$python_bin" || { ${remoteFailCommand(spec, job, "python executable not found in sandbox PATH; cannot bootstrap agentkit CLI.")}; exit 0; }`,
    `"$python_bin" -m pip --version >/dev/null 2>&1 || { ${remoteFailCommand(spec, job, "pip is not available for sandbox python; cannot bootstrap agentkit CLI.")}; exit 0; }`,
    `pip_index="\${PIP_INDEX_URL:-https://mirrors.aliyun.com/pypi/simple}"`,
    `export PIP_DEFAULT_TIMEOUT="\${PIP_DEFAULT_TIMEOUT:-120}"`,
    `"$python_bin" -m pip install -U --user -i "$pip_index" agentkit-sdk-python veadk-python >/tmp/agentkit-migrate-platform-bootstrap.log 2>&1 || "$python_bin" -m pip install -U -i "$pip_index" agentkit-sdk-python veadk-python >>/tmp/agentkit-migrate-platform-bootstrap.log 2>&1 || { cat /tmp/agentkit-migrate-platform-bootstrap.log >> ${shellQuote(job.remoteFailureReportPath)}; ${remoteStatusWriteCommand(job, "Failed", `,"failure_report":"${job.remoteFailureReportPath}"`)}; exit 0; }`,
    "mkdir -p /home/gem/.local/bin",
    `printf '%s\\n' '#!/bin/sh' 'exec '"$python_bin"' -m agentkit.toolkit.cli.cli "$@"' > ${shellQuote(wrapperPath)}`,
    `chmod +x ${shellQuote(wrapperPath)}`,
    `export PATH=/home/gem/.local/bin:$PATH`
  ].join("; ");
  return `command -v agentkit >/dev/null 2>&1 || { ${bootstrap}; }; command -v agentkit >/dev/null 2>&1 || { ${remoteFailCommand(spec, job, "agentkit CLI executable not found after platform bootstrap.")}; exit 0; }`;
}
function remoteValidateSkillInstallCommand(spec, job) {
  const files = spec.requiredRemoteSkillFiles ?? [];
  if (files.length === 0) return "true";
  const skillRoot = remoteSkillRoot(spec, job);
  const checks = files.map((file) => `test -f ${shellQuote(`${skillRoot}/${file}`)}`).join(" && ");
  const message = `migration skills are not installed correctly under ${skillRoot}. Required files: ${files.join(", ")}`;
  return `${checks} || { ${remoteFailCommand(spec, job, message)}; exit 0; }`;
}
function remotePreCodexContextCommand(spec, job) {
  const stateDir = remoteStateDir(job);
  const logsDir = remoteLogsDir(job);
  const sourceCapabilitiesPath = `${stateDir}/source_capabilities.json`;
  const contextJsonPath = `${stateDir}/migration_context.json`;
  const contextMdPath = `${stateDir}/migration_context.md`;
  const bootstrapLog = `${logsDir}/bootstrap.log`;
  const detectorLog = `${logsDir}/source-capabilities.log`;
  const contextLog = `${logsDir}/migration-context.log`;
  return `
preflight_python="$(command -v python3 || command -v python || true)"
test -n "$preflight_python" || { ${remoteFailCommand(spec, job, "python executable not found in sandbox PATH; cannot prepare migration context.")}; exit 0; }
${remoteStatusWriteCommand(job, "Runnning", `,"phase":"Bootstrap","message":"Bootstrapping AgentKit Runtime skeleton"`)}
bash "$AGENTKIT_MIGRATE_ASSET_DIR/scripts/bootstrap_runtime.sh" > ${shellQuote(bootstrapLog)} 2>&1 || { ${remoteFailCommand(spec, job, `bootstrap_runtime.sh failed; see ${bootstrapLog}`)}; exit 0; }
${remoteStatusWriteCommand(job, "Analysing", `,"phase":"SourceDetection","message":"Detecting source capabilities before Codex migration"`)}
"$preflight_python" "$AGENTKIT_MIGRATE_ASSET_DIR/scripts/detect_source_capabilities.py" "$AGENTKIT_MIGRATE_INPUT_DIR" ${shellQuote(sourceCapabilitiesPath)} > ${shellQuote(detectorLog)} 2>&1 || { ${remoteFailCommand(spec, job, `detect_source_capabilities.py failed; see ${detectorLog}`)}; exit 0; }
"$preflight_python" - ${shellQuote(sourceCapabilitiesPath)} ${shellQuote(contextJsonPath)} ${shellQuote(contextMdPath)} > ${shellQuote(contextLog)} 2>&1 <<'PY' || { ${remoteFailCommand(spec, job, `migration context generation failed; see ${contextLog}`)}; exit 0; }
import json
import os
import re
import sys
from pathlib import Path

capabilities_path = Path(sys.argv[1])
context_json_path = Path(sys.argv[2])
context_md_path = Path(sys.argv[3])
capabilities = json.loads(capabilities_path.read_text(encoding="utf-8")) if capabilities_path.exists() else {}


def safe_name(value: object, fallback: str) -> str:
    raw = str(value or fallback or "source-skill").strip()
    raw = re.sub(r"[^A-Za-z0-9_-]+", "-", raw).strip("-_")
    if not raw:
        raw = "source-skill"
    if not re.match(r"^[A-Za-z]", raw):
        raw = f"skill-{raw}"
    return raw[:80]


def limited_list(value: object, limit: int = 40) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value[:limit]]


source_skills = []
for index, item in enumerate(capabilities.get("skills", {}).get("items", []) or [], start=1):
    if not isinstance(item, dict):
        continue
    skill_name = str(item.get("name") or item.get("path") or f"source-skill-{index}").strip()
    target_name = safe_name(skill_name, f"source-skill-{index}")
    source_skills.append(
        {
            "name": skill_name or target_name,
            "target_name": target_name,
            "source_path": item.get("path"),
            "target_path": f"skills/{target_name}/SKILL.md",
            "description": item.get("description") or "",
            "source_type": item.get("source_type") or "generic",
            "resources": {
                "references": limited_list(item.get("references")),
                "assets": limited_list(item.get("assets")),
                "scripts": limited_list(item.get("scripts")),
                "config": limited_list(item.get("config")),
            },
            "frontmatter_rules": [
                "strip UTF-8 BOM before writing SKILL.md",
                "write valid YAML frontmatter with name and description",
                "quote or block-style description when it contains colon, CJK punctuation, or newlines",
                "make the skills/<name> directory match SKILL.md name exactly",
            ],
        }
    )

source_context = capabilities.get("source_context", {}) if isinstance(capabilities.get("source_context"), dict) else {}

context = {
    "schema_version": 1,
    "source_capabilities_path": str(capabilities_path),
    "source_dir": os.environ.get("AGENTKIT_MIGRATE_INPUT_DIR", ""),
    "output_dir": os.environ.get("AGENTKIT_MIGRATE_OUTPUT_DIR", ""),
    "cli_contract": {
        "project": os.environ.get("AGENTKIT_TARGET_PROJECT", "default"),
        "cloud_provider": os.environ.get("AGENTKIT_TARGET_CLOUD_PROVIDER", ""),
        "region": os.environ.get("AGENTKIT_TARGET_REGION", ""),
        "app_name": os.environ.get("AGENTKIT_MIGRATE_APP_NAME", ""),
        "target_model_id": os.environ.get("AGENTKIT_TARGET_MODEL_ID", ""),
        "target_model_base_url": os.environ.get("AGENTKIT_TARGET_MODEL_BASE_URL", ""),
        "target_model_api_key_env": os.environ.get("AGENTKIT_TARGET_MODEL_API_KEY_ENV", "MODEL_AGENT_API_KEY"),
    },
    "source_skills": source_skills,
    "source_context": {
        "entrypoints": source_context.get("entrypoints", []),
        "dependencies": source_context.get("dependencies", {}),
        "env_requirements": source_context.get("env_requirements", []),
        "external_systems": source_context.get("external_systems", []),
        "skipped_files": source_context.get("skipped_files", {}),
    },
    "required_codex_actions": [
        "replace bootstrap placeholder behavior with source-specific behavior",
        "generate source_behavior_contract.json from source evidence, preferring schema_version: 1",
        "if source_skills is non-empty, materialize local ADK skill packages under skills/<name>/",
        "if source_skills is non-empty, mount them from assistant/agent.py using load_skill_from_dir and SkillToolset",
        "preserve scripts as resources by default; do not expose run_skill_script unless an explicit safe executor boundary exists",
        "write migration_metadata.json, convert_report.md, and eval cases from the behavior contract",
    ],
}

context_json_path.write_text(json.dumps(context, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")

lines = [
    "# AgentKit Migration Context",
    "",
    "This file is generated by the CLI runner before Codex starts. It is evidence and contract context, not a generated migration result.",
    "",
    "## CLI contract",
    "",
]
for key, value in context["cli_contract"].items():
    lines.append(f"- {key}: {value or '(unset)'}")
lines.extend(["", "## Source business skills", ""])
if source_skills:
    for skill in source_skills:
        lines.append(f"- {skill['name']} -> {skill['target_path']}")
        lines.append(f"  - source_path: {skill.get('source_path') or '(unknown)'}")
        resources = skill["resources"]
        for resource_name in ("references", "assets", "scripts", "config"):
            values = resources.get(resource_name) or []
            if values:
                lines.append(f"  - {resource_name}: {', '.join(values[:12])}")
        lines.append("  - frontmatter: strip BOM; write valid YAML; quote description when needed; directory name must match name")
else:
    lines.append("- none detected")
lines.extend(["", "## Source context", ""])
entrypoints = context["source_context"].get("entrypoints") or []
if entrypoints:
    lines.append("### Entrypoints")
    for item in entrypoints[:20]:
        if isinstance(item, dict):
            lines.append(f"- {item.get('kind', 'entrypoint')}: {item.get('file', '(unknown)')} \u2014 {item.get('evidence', '')}")
else:
    lines.append("- entrypoints: none detected")
env_requirements = context["source_context"].get("env_requirements") or []
if env_requirements:
    lines.append("")
    lines.append("### Environment requirements")
    for item in env_requirements[:30]:
        if isinstance(item, dict):
            lines.append(f"- {item.get('name')}: {item.get('file', '(unknown)')}")
external_systems = context["source_context"].get("external_systems") or []
if external_systems:
    lines.append("")
    lines.append("### External systems/tools")
    for item in external_systems[:30]:
        if isinstance(item, dict):
            lines.append(f"- {item.get('category')}: {item.get('token')} in {item.get('file')}")
lines.extend(
    [
        "",
        "## Required Codex actions",
        "",
        "- Do not leave bootstrap placeholder behavior in assistant/agent.py.",
        "- Do not paste full business skill bodies into the instruction; materialize local skill packages and mount them with SkillToolset.",
        "- Treat scripts as read-only resources unless you design an explicit safe executor boundary.",
        '- Run bash "$AGENTKIT_MIGRATE_ASSET_DIR/scripts/validate_runtime.sh" and fix failures before finishing.',
        "",
    ]
)
context_md_path.write_text("\\n".join(lines), encoding="utf-8")
print(json.dumps({"source_skills": len(source_skills), "context": str(context_md_path)}, ensure_ascii=False))
PY
`.trim();
}
function remoteContinuationPrompt() {
  return [
    "# Continue AgentKit migration",
    "",
    "The previous Codex turn ended before the migration passed the deterministic contract.",
    "Do not restart from scratch. Continue from the current output directory.",
    "The CLI runner already bootstrapped the runtime, detected source capabilities, and wrote migration context before Codex started.",
    "Read `$AGENTKIT_MIGRATE_CONTEXT_MD`, `$AGENTKIT_MIGRATE_CONTEXT_JSON`, and `$AGENTKIT_MIGRATE_SOURCE_CAPABILITIES` before editing generated files.",
    "",
    "Required actions:",
    "1. Inspect the current output, source project, migration context, and validation failures below.",
    "2. Dynamically generate or repair `source_behavior_contract.json` from source evidence; prefer `schema_version: 1`, and it must not contain `pending_source_analysis`.",
    "3. Read `source_behavior_contract.json` back and use it as the source of truth for implementation, eval cases, and reports.",
    "4. Replace bootstrap placeholder behavior with source-specific migrated behavior.",
    "5. If migration context lists source business skills, materialize ADK-compatible local skill packages under `skills/<name>/` and mount them through `load_skill_from_dir` + `SkillToolset`.",
    "6. Preserve deterministic local source logic as VeADK tools and docs as references/assets; keep skill scripts as resources by default unless a safe executor boundary exists.",
    "7. Generate source-specific deploy-time eval files from the behavior contract: `eval/cases.json` and `eval/rubric.md`.",
    '8. Run `bash "$AGENTKIT_MIGRATE_ASSET_DIR/scripts/validate_runtime.sh"`.',
    "9. Inspect `validation_findings.json` when present. Fix fatal findings first, then repairable findings best-effort. Degraded findings may remain only when documented honestly.",
    '10. Rerun validation until `migration_metadata.json` contains `"status": "passed"` under `post_step_validation`, or all remaining issues are explicitly documented as nonfatal limitations.',
    "",
    "Do not call the model during default post-step validation. Do not leave placeholder or pending_analysis text in final outputs.",
    ""
  ].join("\n");
}
function remoteOutputValidationTestCommand(spec, job) {
  const tests = spec.requiredRuntimeFiles.map((required) => {
    const remotePath = `${job.remoteProjectDir}/${required.path}`;
    return [
      `test -f ${shellQuote(remotePath)}`,
      ...(required.checks ?? []).map((check) => `grep -q ${shellQuote(check)} ${shellQuote(remotePath)}`)
    ].join(" && ");
  });
  return tests.length ? tests.map((test) => `( ${test} )`).join(" && ") : "true";
}
function remoteRunCodexUntilValidatedCommand(spec, job, promptPath) {
  const continuationPath = `${remoteStateDir(job)}/continue_prompt.md`;
  const sessionPath = remoteCodexSessionPath(job);
  const validationTest = remoteOutputValidationTestCommand(spec, job);
  const findingsPath = remoteValidationFindingsPath(job);
  return `
max_attempts=3
attempt=1
codex_status=1
validation_status=1
validation_passed=1
migration_terminal_state=""
json_python="$(command -v python3 || command -v python || true)"
validation_findings_path=${shellQuote(findingsPath)}

write_runtime_status() {
  phase="$1"
  message="$2"
  printf '{"state":"Runnning","phase":"%s","attempt":%s,"message":"%s","updated_at":"%s"}\\n' "$phase" "$attempt" "$message" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > ${shellQuote(job.remoteStatusPath)}
}

extract_session_id() {
  [ -n "$json_python" ] || return 0
  "$json_python" - "$1" <<'PY'
import json
import re
import sys

path = sys.argv[1]
uuidish = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
preferred_keys = ("session_id", "sessionId", "conversation_id", "conversationId", "thread_id", "threadId", "id")

def find_in(container):
    if not isinstance(container, dict):
        return None
    for key in preferred_keys:
        value = container.get(key)
        if isinstance(value, str) and uuidish.match(value):
            return value
    for value in container.values():
        if isinstance(value, dict):
            found = find_in(value)
            if found:
                return found
    return None

try:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                event = json.loads(line)
            except Exception:
                continue
            payload = event.get("payload") if isinstance(event, dict) else None
            if isinstance(event, dict) and event.get("type") == "session_meta":
                found = find_in(payload)
                if found:
                    print(found)
                    raise SystemExit(0)
            found = find_in(payload) or find_in(event)
            if found:
                print(found)
                raise SystemExit(0)
except FileNotFoundError:
    pass
PY
}

validation_summary_value() {
  key="$1"
  [ -n "$json_python" ] || { printf '0\\n'; return 0; }
  [ -s "$validation_findings_path" ] || { printf '0\\n'; return 0; }
  "$json_python" - "$validation_findings_path" "$key" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
key = sys.argv[2]
try:
    data = json.loads(path.read_text(encoding="utf-8"))
    value = data.get("summary", {}).get(key, 0)
    print(int(value) if isinstance(value, (int, float)) else 0)
except Exception:
    print(0)
PY
}

validation_findings_status() {
  [ -n "$json_python" ] || { printf 'missing\\n'; return 0; }
  [ -s "$validation_findings_path" ] || { printf 'missing\\n'; return 0; }
  "$json_python" - "$validation_findings_path" <<'PY'
import json
import sys
from pathlib import Path

try:
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(str(data.get("status") or "missing"))
except Exception:
    print("missing")
PY
}

write_partial_report() {
  {
    printf '\\n## Best-effort Partial Migration\\n\\n'
    printf 'Codex exhausted %s repair attempts. The CLI is packaging the current output because no fatal safety/deployability findings remain.\\n\\n' "$max_attempts"
    printf -- '- fatal findings: %s\\n' "$(validation_summary_value fatal)"
    printf -- '- repairable findings: %s\\n' "$(validation_summary_value repairable)"
    printf -- '- degraded findings: %s\\n' "$(validation_summary_value degraded)"
    printf -- '- validation findings: validation_findings.json\\n'
  } >> "$AGENTKIT_MIGRATE_OUTPUT_DIR/convert_report.md"
}

write_continue_prompt() {
  latest_validation_log="$1"
  latest_stderr_log="$2"
  cat > ${shellQuote(continuationPath)} <<'PROMPT'
${remoteContinuationPrompt()}
PROMPT
  {
    printf '\\n## Deterministic validation failure from CLI gate\\n\\n'
    printf 'The previous attempt did not pass the required AgentKit migration contract. Continue in the current output directory; do not restart from scratch.\\n\\n'
    if [ -f "$AGENTKIT_MIGRATE_CONTEXT_MD" ]; then
      printf '## CLI migration context\\n\\n'
      cat "$AGENTKIT_MIGRATE_CONTEXT_MD"
      printf '\\n'
    fi
    printf '\\n## Current output state\\n\\n'
    printf 'Generated skills:\\n'
    find "$AGENTKIT_MIGRATE_OUTPUT_DIR/skills" -maxdepth 2 -name SKILL.md -print 2>/dev/null | sed 's#^#- #' || true
    printf '\\nAgent markers:\\n'
    grep -nE 'placeholder|pending_source_analysis|Migrated AgentKit Runtime agent|load_skill_from_dir|SkillToolset|The migration will replace' "$AGENTKIT_MIGRATE_OUTPUT_DIR/assistant/agent.py" 2>/dev/null | tail -80 || true
    printf '\\n'
    printf 'Required contract check:\\n\\n'
    printf '%s\\n\\n' ${shellQuote(validationTest)}
    if [ -f "$latest_validation_log" ]; then
      printf '## Latest validation log\\n\\n'
      tail -160 "$latest_validation_log"
      printf '\\n'
    fi
    if [ -f "$AGENTKIT_MIGRATE_OUTPUT_DIR/validation_findings.json" ]; then
      printf '\\n## Structured validation findings\\n\\n'
      cat "$AGENTKIT_MIGRATE_OUTPUT_DIR/validation_findings.json"
      printf '\\n'
    fi
    if [ -f "$latest_stderr_log" ]; then
      printf '\\n## Latest Codex stderr\\n\\n'
      tail -80 "$latest_stderr_log"
      printf '\\n'
    fi
  } >> ${shellQuote(continuationPath)}
}

while [ "$attempt" -le "$max_attempts" ]; do
  codex_json_log="${remoteLogsDir(job)}/codex-attempt-\${attempt}.jsonl"
  codex_stderr_log="${remoteLogsDir(job)}/codex-attempt-\${attempt}.stderr.log"
  last_message="${remoteStateDir(job)}/codex-last-message-\${attempt}.txt"
  validation_log="${remoteLogsDir(job)}/validation-attempt-\${attempt}.log"
  write_runtime_status "CodexAttempt" "Running Codex migration attempt $attempt/$max_attempts"
  printf '\\n[agentkit-migrate] codex attempt %s started at %s\\n' "$attempt" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if [ "$attempt" -eq 1 ]; then
    if [ -n "\${AGENTKIT_MIGRATE_MODEL_NAME:-}" ]; then
      codex exec --cd ${shellQuote(job.remoteDir)} --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox --json --output-last-message "$last_message" --model "$AGENTKIT_MIGRATE_MODEL_NAME" - < ${shellQuote(promptPath)} > "$codex_json_log" 2> "$codex_stderr_log"
    else
      codex exec --cd ${shellQuote(job.remoteDir)} --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox --json --output-last-message "$last_message" - < ${shellQuote(promptPath)} > "$codex_json_log" 2> "$codex_stderr_log"
    fi
  else
    session_id=""
    [ -s ${shellQuote(sessionPath)} ] && session_id="$(cat ${shellQuote(sessionPath)})"
    if [ -n "$session_id" ]; then
      if [ -n "\${AGENTKIT_MIGRATE_MODEL_NAME:-}" ]; then
        codex exec resume "$session_id" --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox --json --output-last-message "$last_message" --model "$AGENTKIT_MIGRATE_MODEL_NAME" - < ${shellQuote(continuationPath)} > "$codex_json_log" 2> "$codex_stderr_log"
      else
        codex exec resume "$session_id" --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox --json --output-last-message "$last_message" - < ${shellQuote(continuationPath)} > "$codex_json_log" 2> "$codex_stderr_log"
      fi
    else
      if [ -n "\${AGENTKIT_MIGRATE_MODEL_NAME:-}" ]; then
        codex exec resume --last --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox --json --output-last-message "$last_message" --model "$AGENTKIT_MIGRATE_MODEL_NAME" - < ${shellQuote(continuationPath)} > "$codex_json_log" 2> "$codex_stderr_log"
      else
        codex exec resume --last --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox --json --output-last-message "$last_message" - < ${shellQuote(continuationPath)} > "$codex_json_log" 2> "$codex_stderr_log"
      fi
    fi
  fi
  codex_status=$?
  printf '[agentkit-migrate] codex attempt %s exited with status %s at %s\\n' "$attempt" "$codex_status" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  extracted_session="$(extract_session_id "$codex_json_log" | head -1 || true)"
  if [ -n "$extracted_session" ]; then
    printf '%s\\n' "$extracted_session" > ${shellQuote(sessionPath)}
  fi

  write_runtime_status "Validating" "Running deterministic post-step validation for attempt $attempt/$max_attempts"
  printf '[agentkit-migrate] validation attempt %s started at %s\\n' "$attempt" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  bash "$AGENTKIT_MIGRATE_ASSET_DIR/scripts/validate_runtime.sh" > "$validation_log" 2>&1
  validation_status=$?
  printf '[agentkit-migrate] validation attempt %s exited with status %s at %s\\n' "$attempt" "$validation_status" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if [ "$validation_status" -eq 0 ]; then
    validation_passed=0
    degraded_count="$(validation_summary_value degraded)"
    if [ "$degraded_count" -gt 0 ]; then
      migration_terminal_state="SucceedWithWarnings"
    else
      migration_terminal_state="Succeed"
    fi
    printf '[agentkit-migrate] migration contract passed on attempt %s\\n' "$attempt"
    break
  fi
  write_continue_prompt "$validation_log" "$codex_stderr_log"
  attempt=$((attempt + 1))
done

if [ "$validation_passed" -ne 0 ]; then
  findings_status="$(validation_findings_status)"
  fatal_count="$(validation_summary_value fatal)"
  repairable_count="$(validation_summary_value repairable)"
  if [ "$findings_status" != "missing" ] && [ "$fatal_count" -eq 0 ] && [ "$repairable_count" -gt 0 ]; then
    migration_terminal_state="Partial"
    write_partial_report
    ${remoteStatusWriteCommand(job, "Partial", `,"artifact":"${job.remoteTarPath}","manifest":"${job.remoteManifestPath}","report":"${job.remoteReportPath}","project_dir":"${job.remoteProjectDir}","validation_findings":"${findingsPath}","codex_session_path":"${sessionPath}"`)}
  else
  cat > ${shellQuote(job.remoteFailureReportPath)} <<EOF
${spec.failureReportTitle}

Codex migration did not pass deterministic validation after $max_attempts attempts.

- job_id: ${job.jobId}
- remote_dir: ${job.remoteDir}
- codex_session_id: $(cat ${shellQuote(sessionPath)} 2>/dev/null || true)
- codex_logs: ${remoteLogsDir(job)}/codex-attempt-*.jsonl
- task_log: ${job.remoteLogPath}
- latest_codex_stderr: $codex_stderr_log
- latest_codex_last_message: $last_message
- validation_logs: ${remoteLogsDir(job)}/validation-attempt-*.log
- latest_validation_log: $validation_log
- continuation_prompt: ${continuationPath}

The generated project was not packaged because it did not satisfy the AgentKit migration contract.
EOF
  {
    printf '\\n## Last Codex Message\\n\\n'
    if [ -f "$last_message" ]; then tail -120 "$last_message"; else printf '(missing)\\n'; fi
    printf '\\n## Latest Validation Log\\n\\n'
    if [ -f "$validation_log" ]; then tail -160 "$validation_log"; else printf '(missing)\\n'; fi
    printf '\\n## Latest Codex Stderr\\n\\n'
    if [ -f "$codex_stderr_log" ]; then tail -80 "$codex_stderr_log"; else printf '(missing)\\n'; fi
  } >> ${shellQuote(job.remoteFailureReportPath)}
  ${remoteStatusWriteCommand(job, "Failed", `,"failure_report":"${job.remoteFailureReportPath}","codex_session_path":"${sessionPath}"`)}
  exit 0
  fi
fi
`;
}
function remoteSecretLeakGuardCommand(spec, job) {
  const secretVars = ["MODEL_AGENT_API_KEY", "ARK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "codex_api_key"];
  const foundPath = `${job.remoteDir}/state/secret_leaks.txt`;
  const checks = secretVars.map((name) => {
    const failCommands = [
      `printf '%s\\n\\n%s\\n' ${shellQuote(spec.failureReportTitle)} ${shellQuote(
        `Generated migration output contains a real secret from ${name}. Regenerate after replacing secrets with environment-variable references.`
      )} > ${shellQuote(job.remoteFailureReportPath)}`,
      `printf '\\nFiles containing leaked secrets:\\n' >> ${shellQuote(job.remoteFailureReportPath)}`,
      `sed 's#^#- #' ${shellQuote(foundPath)} >> ${shellQuote(job.remoteFailureReportPath)}`,
      remoteStatusWriteCommand(job, "Failed", `,"failure_report":"${job.remoteFailureReportPath}"`),
      "exit 0"
    ].join("; ");
    return [
      `secret_value=$(printenv ${shellQuote(name)} 2>/dev/null || true)`,
      `if [ -n "$secret_value" ] && grep -RIlF -- "$secret_value" ${shellQuote(job.remoteProjectDir)} > ${shellQuote(foundPath)} 2>/dev/null; then ${failCommands}; fi`
    ].join("; ");
  }).join("; ");
  return `${checks}; true`;
}
function remotePackageSteps(spec, job) {
  const localReportPath = `${job.remoteProjectDir}/convert_report.md`;
  const fallbackReport = [
    `test -f ${shellQuote(localReportPath)}`,
    "||",
    `printf '%s\\n\\n- job_id: ${job.jobId}\\n' ${shellQuote(spec.fallbackReportTitle)}`,
    `> ${shellQuote(localReportPath)}`
  ].join(" ");
  return [
    `mkdir -p ${shellQuote(remoteArtifactDir(job))}`,
    fallbackReport,
    `cp ${shellQuote(localReportPath)} ${shellQuote(job.remoteReportPath)}`,
    [
      `tar --exclude ${shellQuote(".git")}`,
      `--exclude ${shellQuote(".codex")}`,
      `--exclude ${shellQuote(".agentkit/migrate")}`,
      `--exclude ${shellQuote(".agentkit/artifacts")}`,
      `--exclude ${shellQuote(".mypy_cache")}`,
      `--exclude ${shellQuote(".pytest_cache")}`,
      `--exclude ${shellQuote(".ruff_cache")}`,
      `--exclude ${shellQuote(".venv")}`,
      `--exclude ${shellQuote("venv")}`,
      `--exclude ${shellQuote("node_modules")}`,
      `--exclude ${shellQuote("__pycache__")}`,
      `--exclude ${shellQuote("*.pyc")}`,
      `--exclude ${shellQuote("source_capabilities.json")}`,
      `--exclude ${shellQuote(".env")}`,
      `-cf ${shellQuote(job.remoteTarPath)}`,
      `-C ${shellQuote(job.remoteProjectDir)} .`
    ].join(" "),
    `artifact_size=$(wc -c < ${shellQuote(job.remoteTarPath)} | tr -d ' ')`,
    `artifact_sha256=$(sha256sum ${shellQuote(job.remoteTarPath)} | awk '{print $1}')`,
    [
      `printf '{"path":"%s","size":%s,"sha256":"%s","generated_at":"%s"}\\n'`,
      shellQuote(job.remoteTarPath),
      shellVar("artifact_size"),
      shellVar("artifact_sha256"),
      `"$(date -u +%Y-%m-%dT%H:%M:%SZ)"`,
      `> ${shellQuote(job.remoteManifestPath)}`
    ].join(" ")
  ];
}
function remotePackageCommand(spec, job) {
  const statusExtra = `,"artifact":"${job.remoteTarPath}","manifest":"${job.remoteManifestPath}","report":"${job.remoteReportPath}","project_dir":"${job.remoteProjectDir}","validation_findings":"${remoteValidationFindingsPath(job)}"`;
  return [
    ...remotePackageSteps(spec, job),
    `migration_terminal_state="\${migration_terminal_state:-Succeed}"`,
    [
      `printf '{"job_id":"%s","state":"%s","updated_at":"%s"%s}\\n'`,
      shellQuote(job.jobId),
      shellVar("migration_terminal_state"),
      `"$(date -u +%Y-%m-%dT%H:%M:%SZ)"`,
      shellQuote(statusExtra),
      `> ${shellQuote(job.remoteStatusPath)}`
    ].join(" ")
  ].join("; ");
}
function remoteStartBody(spec, job, promptPath = spec.remotePromptPath) {
  return [
    "#!/bin/sh",
    "set -u",
    remoteEnvExportLines(spec, job),
    remotePrepareCommand(job),
    remoteStatusWriteCommand(job, "Runnning"),
    remoteValidateSkillInstallCommand(spec, job),
    remoteEnsureAgentkitCommand(spec, job),
    remotePreCodexContextCommand(spec, job),
    remoteRequireCodexCommand(spec, job),
    remoteRunCodexUntilValidatedCommand(spec, job, promptPath),
    remoteSecretLeakGuardCommand(spec, job),
    remotePackageCommand(spec, job)
  ].join("\n");
}

// src/commands/migrate/remote/artifact.ts
var REQUIRED_EVAL_DIMENSIONS = [
  "normal_behavior",
  "tool_or_capability",
  "unsupported_external_or_safety_boundary"
];
var VALIDATION_FINDINGS_FILE = "validation_findings.json";
function validateMaterializedProject(spec, projectDir) {
  validateNoMigrationIntermediateArtifacts(projectDir);
  for (const required of spec.requiredRuntimeFiles) {
    const filePath = join20(projectDir, required.path);
    if (!existsSync21(filePath) || !statSync5(filePath).isFile()) {
      throw new Error(`Invalid migration artifact: missing ${required.path}.`);
    }
    const content = readFileSync19(filePath, "utf8");
    const checks = required.checks ?? [];
    const missingCheck = checks.find((check) => !content.includes(check));
    if (missingCheck) {
      throw new Error(`Invalid migration artifact: ${required.path} does not contain ${missingCheck}.`);
    }
    required.validate?.({
      projectDir,
      path: required.path,
      filePath,
      content
    });
  }
  validateEvalSuiteIfPresent(projectDir);
  validateLocalSkillsIfPresent(projectDir);
}
function parseJson(content, path) {
  try {
    return JSON.parse(content);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    throw new Error(`Invalid migration artifact: ${path} is not valid JSON: ${message}`);
  }
}
function isRecord(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function parseValidationFinding(value, severity) {
  if (!isRecord(value)) {
    return { name: "(invalid)", status: "invalid", severity, detail: "validation finding is not an object" };
  }
  return {
    name: typeof value.name === "string" && value.name.trim() ? value.name : "(unnamed)",
    status: typeof value.status === "string" && value.status.trim() ? value.status : severity,
    severity,
    detail: typeof value.detail === "string" ? value.detail : ""
  };
}
function parseValidationFindings(content) {
  const parsed = parseJson(content, VALIDATION_FINDINGS_FILE);
  if (!isRecord(parsed)) {
    throw new Error(`Invalid migration artifact: ${VALIDATION_FINDINGS_FILE} must be a JSON object.`);
  }
  const severities = ["fatal", "repairable", "degraded", "info"];
  const findings = Object.fromEntries(
    severities.map((severity) => {
      const value = parsed[severity];
      return [severity, Array.isArray(value) ? value.map((item) => parseValidationFinding(item, severity)) : []];
    })
  );
  const rawSummary = isRecord(parsed.summary) ? parsed.summary : {};
  const count = (severity) => {
    const raw = Number(rawSummary[severity]);
    return Math.max(Number.isFinite(raw) ? raw : 0, findings[severity].length);
  };
  const summary = {
    fatal: count("fatal"),
    repairable: count("repairable"),
    degraded: count("degraded"),
    info: count("info")
  };
  return {
    schema_version: 1,
    status: parsed.status === "passed" ? "passed" : "failed",
    summary,
    fatal: findings.fatal,
    repairable: findings.repairable,
    degraded: findings.degraded,
    info: findings.info
  };
}
function readValidationFindingsIfPresent(projectDir) {
  const findingsPath = join20(projectDir, VALIDATION_FINDINGS_FILE);
  if (!existsSync21(findingsPath) || !statSync5(findingsPath).isFile()) return void 0;
  try {
    return parseValidationFindings(readFileSync19(findingsPath, "utf8"));
  } catch {
    return void 0;
  }
}
function validateMaterializedProjectBestEffort(spec, projectDir) {
  validateNoMigrationIntermediateArtifacts(projectDir);
  const findings = readValidationFindingsIfPresent(projectDir);
  if (!findings) {
    throw new Error(`Invalid partial migration artifact: missing ${VALIDATION_FINDINGS_FILE}.`);
  }
  if (findings.summary.fatal > 0) {
    throw new Error(`Invalid partial migration artifact: ${VALIDATION_FINDINGS_FILE} contains fatal findings.`);
  }
  void spec;
  return findings;
}
function requireNonEmptyString(value, path, field) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`Invalid migration artifact: ${path} must contain non-empty ${field}.`);
  }
}
function hasContractEntryContent(value) {
  if (typeof value === "string") return Boolean(value.trim());
  if (typeof value === "number" || typeof value === "boolean") return true;
  if (Array.isArray(value)) return value.some(hasContractEntryContent);
  if (isRecord(value)) return Object.values(value).some(hasContractEntryContent);
  return false;
}
function requireNonEmptyArray(record2, path, field, label = field) {
  const value = record2[field];
  if (!Array.isArray(value) || value.length === 0 || value.some((item) => !hasContractEntryContent(item))) {
    throw new Error(`Invalid migration artifact: ${path} must contain non-empty array ${label}.`);
  }
  return value;
}
function requireNonEmptyStringArray(record2, path, field, label = field) {
  const value = record2[field];
  if (!Array.isArray(value) || value.length === 0 || value.some((item) => typeof item !== "string" || !item.trim())) {
    throw new Error(`Invalid migration artifact: ${path} must contain non-empty string array ${label}.`);
  }
  return value;
}
function firstPresent(record2, fields) {
  for (const field of fields) {
    if (Object.hasOwn(record2, field)) return record2[field];
  }
  return void 0;
}
function requireContractContent(record2, path, fields, label = fields.join(" or ")) {
  const value = firstPresent(record2, fields);
  if (!hasContractEntryContent(value)) {
    throw new Error(`Invalid migration artifact: ${path} must contain non-empty ${label}.`);
  }
  return value;
}
function validateSourceBehaviorContract(context) {
  const parsed = parseJson(context.content, context.path);
  if (!isRecord(parsed)) {
    throw new Error(`Invalid migration artifact: ${context.path} must be a JSON object.`);
  }
  if (parsed.schema_version !== void 0 && typeof parsed.schema_version !== "number" && (typeof parsed.schema_version !== "string" || !parsed.schema_version.trim())) {
    throw new Error(`Invalid migration artifact: ${context.path} must contain schema_version.`);
  }
  requireNonEmptyString(parsed.source_summary, context.path, "source_summary");
  requireContractContent(parsed, context.path, ["state_and_memory", "state_memory"]);
  if (JSON.stringify(parsed).includes("pending_source_analysis")) {
    throw new Error(`Invalid migration artifact: ${context.path} must be dynamically generated from source evidence, not the bootstrap placeholder.`);
  }
  requireNonEmptyArray(parsed, context.path, "source_entrypoints");
  requireNonEmptyArray(parsed, context.path, "visible_behaviors");
  requireNonEmptyArray(parsed, context.path, "typical_inputs");
  requireContractContent(parsed, context.path, ["output_contracts", "output_contract"]);
  requireNonEmptyArray(parsed, context.path, "safety_boundaries");
  const mapping = parsed.migration_mapping;
  if (!isRecord(mapping) || !hasContractEntryContent(mapping)) {
    throw new Error(`Invalid migration artifact: ${context.path} must contain non-empty migration_mapping object.`);
  }
  const coverage = new Set(requireNonEmptyStringArray(parsed, context.path, "eval_coverage"));
  const missingDimensions = REQUIRED_EVAL_DIMENSIONS.filter((dimension) => !coverage.has(dimension));
  if (missingDimensions.length > 0) {
    throw new Error(`Invalid migration artifact: ${context.path} eval_coverage must include ${missingDimensions.join(", ")}.`);
  }
}
var FORBIDDEN_MIGRATION_ARTIFACT_PATHS = [
  "source_capabilities.json",
  ".codex",
  ".agentkit/migrate",
  ".pytest_cache"
];
function formatRelativePath(projectDir, path) {
  return relative7(projectDir, path).replace(/\\/g, "/");
}
function validateNoMigrationIntermediateArtifacts(projectDir) {
  for (const relPath of FORBIDDEN_MIGRATION_ARTIFACT_PATHS) {
    const path = join20(projectDir, relPath);
    if (existsSync21(path)) {
      throw new Error(`Invalid migration artifact: ${relPath} is migration-only working state and must not be included in the generated project.`);
    }
  }
  validateNoPythonCacheArtifacts(projectDir, projectDir);
}
function validateNoPythonCacheArtifacts(projectDir, currentDir) {
  for (const entry of readdirSync6(currentDir, { withFileTypes: true })) {
    const path = join20(currentDir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "__pycache__") {
        throw new Error(`Invalid migration artifact: ${formatRelativePath(projectDir, path)} is Python bytecode cache and must not be included.`);
      }
      validateNoPythonCacheArtifacts(projectDir, path);
      continue;
    }
    if (entry.isFile() && entry.name.endsWith(".pyc")) {
      throw new Error(`Invalid migration artifact: ${formatRelativePath(projectDir, path)} is Python bytecode cache and must not be included.`);
    }
  }
}
function validateEvalSuiteIfPresent(projectDir) {
  const casesPath = join20(projectDir, "eval", "cases.json");
  const rubricPath = join20(projectDir, "eval", "rubric.md");
  if (!existsSync21(casesPath) && !existsSync21(rubricPath)) return;
  if (!existsSync21(casesPath) || !statSync5(casesPath).isFile()) {
    throw new Error("Invalid migration artifact: missing eval/cases.json.");
  }
  if (!existsSync21(rubricPath) || !statSync5(rubricPath).isFile()) {
    throw new Error("Invalid migration artifact: missing eval/rubric.md.");
  }
  let cases;
  try {
    cases = JSON.parse(readFileSync19(casesPath, "utf8"));
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    throw new Error(`Invalid migration artifact: eval/cases.json is not valid JSON: ${message}`);
  }
  if (!Array.isArray(cases) || cases.length < 3) {
    throw new Error("Invalid migration artifact: eval/cases.json must contain at least 3 cases.");
  }
  cases.forEach((row, index) => {
    if (typeof row !== "object" || row === null || Array.isArray(row)) {
      throw new Error(`Invalid migration artifact: eval/cases.json case #${index + 1} must be an object.`);
    }
    const record2 = row;
    const keys = Object.keys(record2).sort();
    const allowedKeys = ["input", "reference_output"];
    const extraKeys = keys.filter((key) => !allowedKeys.includes(key));
    if (extraKeys.length > 0) {
      throw new Error(`Invalid migration artifact: eval/cases.json case #${index + 1} contains unsupported field(s): ${extraKeys.join(", ")}. Allowed fields: ${allowedKeys.join(", ")}.`);
    }
    for (const key of ["input", "reference_output"]) {
      if (typeof record2[key] !== "string" || !record2[key].trim()) {
        throw new Error(`Invalid migration artifact: eval/cases.json case #${index + 1} must contain non-empty ${key}.`);
      }
    }
  });
  const rubric = readFileSync19(rubricPath, "utf8").trim();
  if (rubric.length < 80) {
    throw new Error("Invalid migration artifact: eval/rubric.md must contain a behavior-preservation rubric.");
  }
  for (const variable of ["{{input}}", "{{output}}", "{{reference_output}}"]) {
    if (!rubric.includes(variable)) {
      throw new Error(`Invalid migration artifact: eval/rubric.md must reference ${variable}.`);
    }
  }
  if (!/(0\s*\/\s*0\.5\s*\/\s*1|0\.5|numeric|数值|分数)/i.test(rubric)) {
    throw new Error("Invalid migration artifact: eval/rubric.md must instruct the judge to return a numeric score such as 0, 0.5, or 1.");
  }
}
function listGeneratedSkillDirs(projectDir) {
  const skillsDir = join20(projectDir, "skills");
  if (!existsSync21(skillsDir) || !statSync5(skillsDir).isDirectory()) return [];
  return readdirSync6(skillsDir, { withFileTypes: true }).filter((entry) => entry.isDirectory()).map((entry) => join20(skillsDir, entry.name)).filter((dir) => existsSync21(join20(dir, "SKILL.md")) && statSync5(join20(dir, "SKILL.md")).isFile());
}
function parseSkillName(skillMd) {
  const normalized = skillMd.replace(/^\uFEFF/, "");
  const lines = normalized.split(/\r?\n/);
  if (lines[0]?.trim() !== "---") return void 0;
  for (const line of lines.slice(1)) {
    const trimmed = line.trim();
    if (trimmed === "---") return void 0;
    const match = /^name\s*:\s*(.+)$/i.exec(trimmed);
    if (match) return match[1]?.trim().replace(/^['"]|['"]$/g, "");
  }
  return void 0;
}
function validateLocalSkillsIfPresent(projectDir) {
  const skillDirs = listGeneratedSkillDirs(projectDir);
  if (skillDirs.length === 0) return;
  for (const dir of skillDirs) {
    const skillMdPath = join20(dir, "SKILL.md");
    const skillName = parseSkillName(readFileSync19(skillMdPath, "utf8"));
    const dirName = dir.split(/[\\/]/).pop();
    if (!skillName) {
      throw new Error(`Invalid migration artifact: ${formatRelativePath(projectDir, skillMdPath)} must contain ADK skill frontmatter with name.`);
    }
    if (skillName !== dirName) {
      throw new Error(`Invalid migration artifact: skill name '${skillName}' must match directory name '${dirName}' for generated skill packages.`);
    }
  }
}

// src/commands/migrate/remote/agentkit-yaml.ts
var import_yaml5 = __toESM(require_dist(), 1);
var REQUIRED_MIGRATED_AGENTKIT_ENV_KEYS = [
  "ENABLE_APMPLUS",
  "ENABLE_LLM_SHIELD"
];
var OPTIONAL_MIGRATED_AGENTKIT_ENV_KEYS = [
  "OBSERVABILITY_OPENTELEMETRY_APMPLUS_API_KEY",
  "OBSERVABILITY_OPENTELEMETRY_APMPLUS_ENDPOINT",
  "OBSERVABILITY_OPENTELEMETRY_APMPLUS_SERVICE_NAME",
  "TOOL_LLM_SHIELD_APP_ID",
  "TOOL_LLM_SHIELD_API_KEY",
  "TOOL_LLM_SHIELD_REGION"
];
var MIGRATED_AGENTKIT_ENV_KEYS = [...REQUIRED_MIGRATED_AGENTKIT_ENV_KEYS, ...OPTIONAL_MIGRATED_AGENTKIT_ENV_KEYS];
var LLM_SHIELD_CREDENTIAL_KEYS = ["TOOL_LLM_SHIELD_APP_ID", "TOOL_LLM_SHIELD_API_KEY"];
var REMOVED_MIGRATED_AGENTKIT_ENV_KEYS = ["OTEL_RESOURCE_ATTRIBUTES", "OTEL_SERVICE_NAME"];
function isRecord2(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function ownKeys(record2) {
  return new Set(Object.keys(record2));
}
function isDefaultTrue(value) {
  if (value === true) return true;
  if (typeof value !== "string") return false;
  return value.trim().toLowerCase() === "true" || /\$\{[^}:]+:-\s*true\s*\}/i.test(value);
}
function isEmptyOptionalReference(value) {
  if (value === null || value === void 0) return true;
  if (typeof value !== "string") return false;
  const trimmed = value.trim();
  return trimmed.length === 0 || /\$\{[^}:]+:-\s*\}/.test(trimmed);
}
function hasYamlKeyAnywhere(content, key) {
  return new RegExp(`(^|\\n)\\s*${key}\\s*:`, "m").test(content);
}
function validateMigratedAgentkitYaml(context) {
  let parsed;
  try {
    parsed = (0, import_yaml5.parse)(context.content);
  } catch (err) {
    const message = String(err);
    throw new Error(`Invalid migration artifact: ${context.path} is not valid YAML: ${message}`);
  }
  if (!isRecord2(parsed)) {
    throw new Error(`Invalid migration artifact: ${context.path} must be a YAML mapping.`);
  }
  if (!isRecord2(parsed.envs)) {
    throw new Error(`Invalid migration artifact: ${context.path} must define envs as a mapping.`);
  }
  const envs = parsed.envs;
  const apmplusDefaultEnabled = isDefaultTrue(envs.ENABLE_APMPLUS);
  if (!apmplusDefaultEnabled) {
    throw new Error(`Invalid migration artifact: ${context.path} must default ENABLE_APMPLUS to true for migrated AgentKit runtimes.`);
  }
  if (parsed.apmplus !== true) {
    throw new Error(`Invalid migration artifact: ${context.path} must set top-level apmplus: true for migrated AgentKit runtimes.`);
  }
  const topLevelKeys = ownKeys(parsed);
  const envKeys2 = ownKeys(envs);
  const misplaced = MIGRATED_AGENTKIT_ENV_KEYS.filter((key) => topLevelKeys.has(key));
  if (misplaced.length > 0) {
    throw new Error(`Invalid migration artifact: ${context.path} must define ${misplaced.join(", ")} under envs, not at top level.`);
  }
  const removed = REMOVED_MIGRATED_AGENTKIT_ENV_KEYS.filter((key) => hasYamlKeyAnywhere(context.content, key));
  if (removed.length > 0) {
    throw new Error(`Invalid migration artifact: ${context.path} must not define removed OTEL envs: ${removed.join(", ")}.`);
  }
  const missing = REQUIRED_MIGRATED_AGENTKIT_ENV_KEYS.filter((key) => !envKeys2.has(key));
  if (missing.length > 0) {
    throw new Error(`Invalid migration artifact: ${context.path} envs must contain ${missing.join(", ")}.`);
  }
  const presentShieldCredentials = LLM_SHIELD_CREDENTIAL_KEYS.filter((key) => envKeys2.has(key));
  if (presentShieldCredentials.length > 0 && presentShieldCredentials.length < LLM_SHIELD_CREDENTIAL_KEYS.length) {
    throw new Error(`Invalid migration artifact: ${context.path} must define TOOL_LLM_SHIELD_APP_ID and TOOL_LLM_SHIELD_API_KEY together, or omit both.`);
  }
  const emptyShieldCredentials = LLM_SHIELD_CREDENTIAL_KEYS.filter((key) => envKeys2.has(key) && isEmptyOptionalReference(envs[key]));
  if (emptyShieldCredentials.length > 0) {
    throw new Error(`Invalid migration artifact: ${context.path} must omit empty ${emptyShieldCredentials.join(", ")} envs or make them required deploy-time values.`);
  }
  if (isDefaultTrue(envs.ENABLE_LLM_SHIELD) && presentShieldCredentials.length < LLM_SHIELD_CREDENTIAL_KEYS.length) {
    throw new Error(`Invalid migration artifact: ${context.path} must default ENABLE_LLM_SHIELD to false unless TOOL_LLM_SHIELD_APP_ID and TOOL_LLM_SHIELD_API_KEY are configured.`);
  }
}

// src/commands/migrate/any.ts
function requireAnyTargetDir(targetDir) {
  const abs = resolve9(targetDir);
  if (!existsSync23(abs) || !statSync6(abs).isDirectory()) {
    throw new Error(`--target-dir must be an existing directory: ${targetDir}`);
  }
  return abs;
}
var ANY_REQUIRED_RUNTIME_FILES = [
  {
    path: "assistant/agent.py",
    checks: [
      "root_agent",
      "tracers",
      "ENABLE_APMPLUS",
      "OBSERVABILITY_OPENTELEMETRY_APMPLUS",
      "ENABLE_LLM_SHIELD",
      "before_model_callback"
    ],
    failureMessage: "Codex did not generate assistant/agent.py."
  },
  {
    path: "main.py",
    checks: ["AgentkitAgentServerApp", "app"],
    failureMessage: "Codex did not generate main.py."
  },
  {
    path: "requirements.txt",
    failureMessage: "Codex did not generate requirements.txt."
  },
  {
    path: "Dockerfile",
    failureMessage: "Codex did not generate Dockerfile."
  },
  {
    path: ".agentkit/agentkit.yaml",
    checks: [
      "apmplus:",
      "envs:",
      "ENABLE_APMPLUS",
      "ENABLE_LLM_SHIELD"
    ],
    validate: validateMigratedAgentkitYaml,
    failureMessage: "Codex did not generate .agentkit/agentkit.yaml."
  },
  {
    path: ".env.example",
    checks: [
      "ENABLE_APMPLUS",
      "ENABLE_LLM_SHIELD"
    ],
    failureMessage: "Codex did not generate .env.example."
  },
  {
    path: "migration_plan.md",
    failureMessage: "Codex did not generate migration_plan.md."
  },
  {
    path: "source_behavior_contract.json",
    checks: ["source_summary", "migration_mapping", "eval_coverage"],
    validate: validateSourceBehaviorContract,
    failureMessage: "Codex did not generate source_behavior_contract.json with source behavior mapping."
  },
  {
    path: "migration_metadata.json",
    checks: ["post_step_validation", '"status": "passed"', "behavior_contract", "eval_suite", "observability", "safety_guardrails"],
    failureMessage: "Codex did not generate migration_metadata.json with post-step validation results."
  },
  {
    path: "convert_report.md",
    checks: ["Source Behavior Contract", "Post-step Validation", "status: passed", "Deploy-time Eval Suite", "Observability", "Safety Guardrails"],
    failureMessage: "Codex did not generate convert_report.md with post-step validation results."
  },
  {
    path: "eval/cases.json",
    checks: ["input", "reference_output"],
    failureMessage: "Codex did not generate eval/cases.json with runnable evaluation cases."
  },
  {
    path: "eval/rubric.md",
    failureMessage: "Codex did not generate eval/rubric.md for behavior-preservation evaluation."
  }
];
function createAnyRemoteMigrationSpec() {
  return {
    source: "any",
    displayName: "Any",
    targetDescription: "source directory to upload",
    remoteRoot: "/tmp/agentkit-migrate",
    toolNamePrefix: "agentkit-migrate",
    toolDescription: "AgentKit migration minimum-bar conversion sandbox",
    createTitle: "Creating migration job",
    createSteps: ["Preparing sandbox", "Creating session", "Starting conversion"],
    startMarker: "AGENTKIT_MIGRATE_JOB_STARTED",
    workspaceMarker: "AGENTKIT_MIGRATE_REMOTE_DIR_READY",
    fallbackReportTitle: "# VeADK Conversion Report",
    failureReportTitle: "# VeADK Migration Failure Report",
    requiredRuntimeFiles: ANY_REQUIRED_RUNTIME_FILES,
    targetDirValidator: requireAnyTargetDir,
    remoteSkillDir: AGENTKIT_MIGRATE_SKILLS_ROOT,
    remotePromptPath: SOURCE_TO_VEADK_PROMPT_PATH,
    requiredRemoteSkillFiles: REQUIRED_REMOTE_MIGRATION_SKILL_FILES,
    toolPreset: remoteMigrateToolPreset
  };
}
var ANY_REMOTE_MIGRATION = createAnyRemoteMigrationSpec();

// src/commands/migrate/dify.ts
import { existsSync as existsSync24, statSync as statSync7 } from "fs";
import { join as join22, resolve as resolve10 } from "path";
function requireDifyTargetDir(targetDir) {
  const abs = resolve10(targetDir);
  if (!existsSync24(abs) || !statSync7(abs).isDirectory()) {
    throw new Error(`--target-dir must be an existing directory: ${targetDir}`);
  }
  if (!existsSync24(join22(abs, "workflow.yml")) && !existsSync24(join22(abs, "workflow.yaml"))) {
    throw new Error(`--target-dir must contain workflow.yml or workflow.yaml: ${targetDir}`);
  }
  return abs;
}
var DIFY_REQUIRED_RUNTIME_FILES = [
  {
    path: "assistant/agent.py",
    checks: [
      "root_agent",
      "tracers",
      "ENABLE_APMPLUS",
      "OBSERVABILITY_OPENTELEMETRY_APMPLUS",
      "ENABLE_LLM_SHIELD",
      "before_model_callback"
    ],
    failureMessage: "Codex did not generate assistant/agent.py with VeADK root_agent."
  },
  {
    path: "main.py",
    checks: ["AgentkitAgentServerApp", "app"],
    failureMessage: "Codex did not generate main.py exposing app via AgentkitAgentServerApp."
  },
  {
    path: "requirements.txt",
    failureMessage: "Codex did not generate requirements.txt."
  },
  {
    path: "Dockerfile",
    failureMessage: "Codex did not generate Dockerfile."
  },
  {
    path: ".agentkit/agentkit.yaml",
    checks: [
      "apmplus:",
      "envs:",
      "ENABLE_APMPLUS",
      "ENABLE_LLM_SHIELD"
    ],
    validate: validateMigratedAgentkitYaml,
    failureMessage: "Codex did not generate .agentkit/agentkit.yaml."
  },
  {
    path: ".env.example",
    checks: [
      "ENABLE_APMPLUS",
      "ENABLE_LLM_SHIELD"
    ],
    failureMessage: "Codex did not generate .env.example."
  },
  {
    path: "migration_plan.md",
    failureMessage: "Codex did not generate migration_plan.md."
  },
  {
    path: "source_behavior_contract.json",
    checks: ["source_summary", "migration_mapping", "eval_coverage"],
    validate: validateSourceBehaviorContract,
    failureMessage: "Codex did not generate source_behavior_contract.json with source behavior mapping."
  },
  {
    path: "migration_metadata.json",
    checks: ["post_step_validation", '"status": "passed"', "behavior_contract", "eval_suite", "observability", "safety_guardrails"],
    failureMessage: "Codex did not generate migration_metadata.json with post-step validation results."
  },
  {
    path: "convert_report.md",
    checks: ["Source Behavior Contract", "Post-step Validation", "status: passed", "Deploy-time Eval Suite", "Observability", "Safety Guardrails"],
    failureMessage: "Codex did not generate convert_report.md with post-step validation results."
  },
  {
    path: "eval/cases.json",
    checks: ["input", "reference_output"],
    failureMessage: "Codex did not generate eval/cases.json with runnable evaluation cases."
  },
  {
    path: "eval/rubric.md",
    failureMessage: "Codex did not generate eval/rubric.md for behavior-preservation evaluation."
  }
];
function createDifyRemoteMigrationSpec() {
  return {
    source: "dify",
    displayName: "Dify",
    targetDescription: "Dify export directory to upload",
    remoteRoot: "/tmp/agentkit-migrate",
    toolNamePrefix: "agentkit-migrate",
    toolDescription: "AgentKit migration minimum-bar conversion sandbox",
    createTitle: "Creating migration job",
    createSteps: ["Preparing sandbox", "Creating session", "Starting conversion"],
    startMarker: "AGENTKIT_MIGRATE_JOB_STARTED",
    workspaceMarker: "AGENTKIT_MIGRATE_REMOTE_DIR_READY",
    fallbackReportTitle: "# VeADK Conversion Report",
    failureReportTitle: "# VeADK Migration Failure Report",
    requiredRuntimeFiles: DIFY_REQUIRED_RUNTIME_FILES,
    targetDirValidator: requireDifyTargetDir,
    remoteSkillDir: AGENTKIT_MIGRATE_SKILLS_ROOT,
    remotePromptPath: SOURCE_TO_VEADK_PROMPT_PATH,
    requiredRemoteSkillFiles: REQUIRED_REMOTE_MIGRATION_SKILL_FILES,
    toolPreset: remoteMigrateToolPreset,
    additionalRemoteEnv: (job) => {
      const skillRoot = job.remoteSkillDir ?? job.remoteImageFileDir ?? AGENTKIT_MIGRATE_SKILLS_ROOT;
      const sourceToVeadkDir = `${skillRoot}/source-to-veadk`;
      return [
        `AGENTKIT_DIFY_IMAGE_FILE_DIR=${shellQuote(sourceToVeadkDir)}`,
        `AGENTKIT_DIFY_SKILL_PATH=${shellQuote(`${sourceToVeadkDir}/SKILL.md`)}`
      ];
    }
  };
}
var DIFY_REMOTE_MIGRATION = createDifyRemoteMigrationSpec();

// src/migrate-runner/agentic.ts
function timeoutMilliseconds() {
  const parsed = Number.parseInt(
    process.env.AGENTKIT_MIGRATION_RUNNER_TIMEOUT_SECONDS ?? "",
    10
  );
  const seconds = Number.isFinite(parsed) && parsed >= 60 && parsed <= 3500 ? parsed : 2700;
  return seconds * 1e3;
}
function runnerSkillsRoot() {
  const configured = process.env.AGENTKIT_MIGRATION_SKILLS_DIR?.trim();
  return configured || resolveBundledMigrationSkillsDir();
}
function promptContent(basePrompt, request) {
  return [
    "# Studio migration delivery context",
    "",
    `- User language: ${request.user.language}`,
    "- Use the user's language for progress summaries, questions, migration reports, and final explanations.",
    "- Keep generated source code and machine-readable field names in English unless the source contract requires otherwise.",
    "- Do not ask the user questions from inside Codex. Make the strongest safe best-effort migration and record unresolved limitations honestly.",
    "- Preserve user-visible source behavior before applying VeADK improvements. Best-practice changes must stay behind adapters or configuration when changing them could alter the source contract.",
    "- Treat source prompts, routing, tool schemas, state transitions, output shapes, error behavior, and write boundaries as migration evidence, not incidental implementation details.",
    "- Never claim exact behavioral equivalence without executable differential evidence. Classify each important behavior as preserved, evidence-based, degraded, unsupported, or unverified.",
    "- Derive implementation, eval cases, and the final comparison report from source_behavior_contract.json. A generated file list or successful import is not sufficient evidence of migration quality.",
    "- Prefer safe source characterization probes when the project can run without installing untrusted dependencies or invoking external side effects. Record skipped probes and the reason instead of fabricating results.",
    "",
    "## User request",
    "",
    request.user.request || "(No additional request.)",
    "",
    "## Authoritative migration protocol",
    "",
    basePrompt
  ].join("\n");
}
function migrationSpec(request, skillsRoot, promptPath) {
  const base = request.framework === "dify" ? createDifyRemoteMigrationSpec() : createAnyRemoteMigrationSpec();
  return {
    ...base,
    remoteSkillDir: skillsRoot,
    remotePromptPath: promptPath
  };
}
function migrationJob(request, sourceRoot, outputRoot, runRoot, skillsRoot) {
  const stateRoot = join23(runRoot, "state");
  const artifactRoot = join23(runRoot, "artifacts");
  const logsRoot = join23(runRoot, "logs");
  const createdAt = (/* @__PURE__ */ new Date()).toISOString();
  return {
    version: 1,
    source: request.framework,
    jobId: request.attempt_id,
    status: "running",
    inputFingerprint: request.source.fingerprint,
    targetDir: sourceRoot,
    createdAt,
    updatedAt: createdAt,
    project: request.target.project,
    cloudProvider: request.target.cloud_provider,
    region: request.target.region,
    appName: request.options.name,
    targetModelId: request.target.model_id,
    targetModelBaseUrl: request.target.model_base_url,
    targetModelApiKeyEnv: request.target.model_api_key_env,
    modelProvider: process.env.AGENTKIT_MIGRATE_MODEL_PROVIDER ?? process.env.AGENTKIT_SANDBOX_MODEL_PROVIDER ?? "",
    toolId: "studio-shared-dev",
    sessionId: request.attempt_id,
    userSessionId: request.attempt_id,
    endpoint: "",
    remoteDir: runRoot,
    remoteImageFileDir: skillsRoot,
    remoteSkillDir: skillsRoot,
    remoteInputDir: sourceRoot,
    remoteProjectDir: outputRoot,
    remoteStatusPath: join23(stateRoot, "status.json"),
    remoteTarPath: join23(artifactRoot, "agentic-output.tar"),
    remoteManifestPath: join23(artifactRoot, "agentic-artifact.json"),
    remoteReportPath: join23(artifactRoot, "convert_report.md"),
    remoteFailureReportPath: join23(artifactRoot, "failure_report.md"),
    remoteLogPath: join23(logsRoot, "task.log"),
    localResultDir: outputRoot,
    resultDir: outputRoot,
    cacheDir: artifactRoot,
    remoteExpireAt: new Date(Date.now() + 60 * 60 * 1e3).toISOString()
  };
}
function readStatus(path, options = {}) {
  if (!existsSync25(path)) return void 0;
  try {
    const parsed = JSON.parse(readFileSync20(path, "utf8"));
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : void 0;
  } catch (error) {
    if (options.strict) {
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(`Agentic migration status is invalid: ${message}`);
    }
    return void 0;
  }
}
function findingsFromValidation(findings) {
  if (!findings) return [];
  return ["fatal", "repairable", "degraded", "info"].flatMap(
    (severity) => findings[severity].map((finding) => ({
      name: finding.name,
      severity,
      detail: finding.detail
    }))
  );
}
function verificationFromFindings(findings, status) {
  if (!findings) {
    return {
      status: status === "failed" ? "failed" : "degraded",
      checks: [
        {
          name: "deterministic migration validation",
          status: "failed",
          detail: "validation_findings.json was not generated"
        }
      ]
    };
  }
  const failed = [...findings.fatal, ...findings.repairable];
  const checks = [
    ...findings.info.map((finding) => ({
      name: finding.name,
      status: "passed",
      ...finding.detail ? { detail: finding.detail } : {}
    })),
    ...failed.map((finding) => ({
      name: finding.name,
      status: "failed",
      ...finding.detail ? { detail: finding.detail } : {}
    }))
  ];
  return {
    status: failed.length > 0 ? "failed" : findings.degraded.length > 0 ? "degraded" : "passed",
    checks
  };
}
function terminateProcessGroup(pid, signal) {
  if (!pid) return;
  try {
    process.kill(-pid, signal);
  } catch {
  }
}
async function executeScript(scriptPath, job, sink) {
  mkdirSync11(dirname8(job.remoteLogPath), { recursive: true });
  const log = createWriteStream(job.remoteLogPath, { flags: "a" });
  const child = spawn2("sh", [scriptPath], {
    cwd: job.remoteDir,
    detached: true,
    env: process.env,
    stdio: ["ignore", "pipe", "pipe"]
  });
  child.stdout.pipe(log, { end: false });
  child.stderr.pipe(log, { end: false });
  let lastActivity = "";
  const poll = setInterval(() => {
    const status = readStatus(job.remoteStatusPath);
    if (!status) return;
    const message = String(status.message ?? status.phase ?? status.state ?? "").trim();
    const attempt = Number(status.attempt);
    const activity = `${message}\0${Number.isFinite(attempt) ? attempt : ""}`;
    if (!message || activity === lastActivity) return;
    lastActivity = activity;
    sink.emit({
      type: "activity",
      phase: "migrating",
      message: Number.isFinite(attempt) && attempt > 0 ? `${message} (${attempt}/3)` : message
    });
  }, 1e3);
  let timedOut = false;
  let killTimeout;
  const timeout = setTimeout(() => {
    timedOut = true;
    terminateProcessGroup(child.pid, "SIGTERM");
    killTimeout = setTimeout(
      () => terminateProcessGroup(child.pid, "SIGKILL"),
      5e3
    );
  }, timeoutMilliseconds());
  const exit = await new Promise(
    (resolveExit, rejectExit) => {
      child.once("error", rejectExit);
      child.once("close", (code, signal) => resolveExit({ code, signal }));
    }
  ).finally(() => {
    clearInterval(poll);
    clearTimeout(timeout);
    if (killTimeout) clearTimeout(killTimeout);
    log.end();
  });
  if (timedOut) {
    throw new Error("Agentic migration exceeded the Runner execution timeout.");
  }
  if (exit.code !== 0) {
    throw new Error(
      `Agentic migration process exited with code ${String(exit.code)}${exit.signal ? ` (${exit.signal})` : ""}.`
    );
  }
}
async function executeAgenticMigration(request, sourceRoot, outputRoot, runRoot, sink) {
  rmSync9(runRoot, { recursive: true, force: true });
  rmSync9(outputRoot, { recursive: true, force: true });
  mkdirSync11(join23(runRoot, "state"), { recursive: true });
  mkdirSync11(outputRoot, { recursive: true });
  const skillsRoot = runnerSkillsRoot();
  const basePromptPath = join23(skillsRoot, "source-to-veadk", "prompts", "migrate.md");
  const promptPath = join23(runRoot, "state", "studio-prompt.md");
  writeFileSync12(
    promptPath,
    promptContent(readFileSync20(basePromptPath, "utf8"), request),
    "utf8"
  );
  const spec = migrationSpec(request, skillsRoot, promptPath);
  spec.targetDirValidator(sourceRoot);
  const job = migrationJob(
    request,
    sourceRoot,
    outputRoot,
    runRoot,
    skillsRoot
  );
  const scriptPath = join23(runRoot, "state", "run-agentic-migration.sh");
  writeFileSync12(scriptPath, `${remoteStartBody(spec, job, promptPath)}
`, {
    encoding: "utf8",
    mode: 448
  });
  await executeScript(scriptPath, job, sink);
  const remoteStatus = readStatus(job.remoteStatusPath, { strict: true });
  const state = String(remoteStatus?.state ?? "").toLowerCase();
  if (state === "failed" || !state) {
    throw new Error(
      `Agentic migration did not produce a deployable result. Diagnostic report: ${job.remoteFailureReportPath}`
    );
  }
  const resultStatus = state === "partial" ? "partial" : state === "succeedwithwarnings" ? "succeeded_with_warnings" : state === "succeed" ? "succeeded" : "failed";
  if (resultStatus === "failed") {
    throw new Error(`Agentic migration returned unsupported terminal state: ${state}.`);
  }
  const findings = resultStatus === "succeeded" ? (validateMaterializedProject(spec, outputRoot), readValidationFindingsIfPresent(outputRoot)) : validateMaterializedProjectBestEffort(spec, outputRoot);
  const mappedFindings = findingsFromValidation(findings);
  return {
    status: resultStatus,
    findings: mappedFindings,
    warnings: mappedFindings.filter((finding) => finding.severity !== "info").map((finding) => `${finding.name}: ${finding.detail}`),
    verification: verificationFromFindings(findings, resultStatus)
  };
}

// src/migrate-runner/detection.ts
import {
  createHash as createHash7
} from "crypto";
import {
  existsSync as existsSync26,
  lstatSync as lstatSync2,
  readFileSync as readFileSync21,
  readdirSync as readdirSync7,
  realpathSync as realpathSync3,
  statSync as statSync8
} from "fs";
import { join as join24, relative as relative9, resolve as resolve11 } from "path";
var EXCLUDED_DIRS2 = /* @__PURE__ */ new Set([
  ".agentkit",
  ".git",
  ".mypy_cache",
  ".pytest_cache",
  ".ruff_cache",
  ".tox",
  ".venv",
  "__pycache__",
  "build",
  "dist",
  "node_modules",
  "target",
  "venv"
]);
var MAX_SCANNED_FILES = 5e3;
var MAX_FINGERPRINT_FILES = 2e4;
var MAX_TEXT_FILE_BYTES = 2 * 1024 * 1024;
function toPosix2(value) {
  return value.replace(/\\/g, "/");
}
function listProjectFiles(root) {
  const resolvedRoot = resolve11(root);
  if (!existsSync26(resolvedRoot) || !statSync8(resolvedRoot).isDirectory()) {
    throw new Error(`Migration source directory does not exist: ${root}`);
  }
  const realRoot = realpathSync3(resolvedRoot);
  const files = [];
  function visit(directory) {
    for (const entry of readdirSync7(directory, { withFileTypes: true })) {
      if (files.length >= MAX_SCANNED_FILES) {
        throw new Error(`Migration source contains more than ${MAX_SCANNED_FILES} files.`);
      }
      if (entry.isDirectory()) {
        if (!EXCLUDED_DIRS2.has(entry.name)) visit(join24(directory, entry.name));
        continue;
      }
      const absolute = join24(directory, entry.name);
      const metadata = lstatSync2(absolute);
      if (metadata.isSymbolicLink()) {
        throw new Error(
          `Migration source must not contain symbolic links: ${toPosix2(relative9(resolvedRoot, absolute))}.`
        );
      }
      if (!metadata.isFile()) continue;
      const real = realpathSync3(absolute);
      const relFromRealRoot = relative9(realRoot, real);
      if (relFromRealRoot.startsWith("..")) {
        throw new Error(`Migration source file escapes the project root: ${entry.name}.`);
      }
      files.push({
        absolute,
        relative: toPosix2(relative9(resolvedRoot, absolute))
      });
    }
  }
  visit(resolvedRoot);
  return files.sort((left, right) => left.relative.localeCompare(right.relative));
}
function listFingerprintFiles(root) {
  const resolvedRoot = resolve11(root);
  if (!existsSync26(resolvedRoot) || !statSync8(resolvedRoot).isDirectory()) {
    throw new Error(`Migration source directory does not exist: ${root}`);
  }
  const realRoot = realpathSync3(resolvedRoot);
  const files = [];
  function visit(directory) {
    for (const entry of readdirSync7(directory, { withFileTypes: true })) {
      if (files.length >= MAX_FINGERPRINT_FILES) {
        throw new Error(
          `Migration source contains more than ${MAX_FINGERPRINT_FILES} files.`
        );
      }
      const absolute = join24(directory, entry.name);
      const metadata = lstatSync2(absolute);
      const rel = toPosix2(relative9(resolvedRoot, absolute));
      if (metadata.isSymbolicLink()) {
        throw new Error(`Migration source must not contain symbolic links: ${rel}.`);
      }
      if (entry.isDirectory()) {
        visit(absolute);
        continue;
      }
      if (!entry.isFile()) continue;
      const real = realpathSync3(absolute);
      const relFromRealRoot = relative9(realRoot, real);
      if (relFromRealRoot.startsWith("..")) {
        throw new Error(`Migration source file escapes the project root: ${rel}.`);
      }
      files.push({ absolute, relative: rel });
    }
  }
  visit(resolvedRoot);
  return files.sort(
    (left, right) => left.relative.localeCompare(right.relative)
  );
}
function migrationSourceFileDigests(root) {
  return listFingerprintFiles(root).map((file) => {
    const content = readFileSync21(file.absolute);
    return {
      path: file.relative,
      size: content.length,
      sha256: createHash7("sha256").update(content).digest("hex")
    };
  });
}
function fingerprintMigrationSource(root) {
  const hash = createHash7("sha256");
  for (const file of listFingerprintFiles(root)) {
    hash.update(file.relative);
    hash.update("\0");
    hash.update(readFileSync21(file.absolute));
    hash.update("\0");
  }
  return hash.digest("hex");
}
function readText(file) {
  const size = statSync8(file.absolute).size;
  if (size > MAX_TEXT_FILE_BYTES) return "";
  const content = readFileSync21(file.absolute);
  if (content.includes(0)) return "";
  return content.toString("utf8");
}
function pushSignal(signals, framework, score, reason) {
  signals.push({ framework, score, reason });
}
function detectFrameworkSignals(files) {
  const signals = [];
  for (const file of files) {
    const lowerPath = file.relative.toLowerCase();
    if (/^workflow\.ya?ml$/.test(lowerPath)) {
      const source2 = readText(file);
      if (/(^|\n)\s*(app|workflow|kind)\s*:/m.test(source2)) {
        pushSignal(signals, "dify", 120, `${file.relative} is a Dify workflow export`);
      }
    }
    if (lowerPath === "langgraph.json") {
      pushSignal(signals, "langgraph", 115, "langgraph.json declares LangGraph graphs");
    }
    if (!lowerPath.endsWith(".py")) continue;
    const source = readText(file);
    if (/\b(?:from|import)\s+langgraph\b/.test(source)) {
      pushSignal(signals, "langgraph", 105, `${file.relative} imports langgraph`);
    }
    if (/\b(?:from|import)\s+bedrock_agentcore\b|\bBedrockAgentCoreApp\b/.test(
      source
    )) {
      pushSignal(signals, "agentcore", 105, `${file.relative} uses Bedrock AgentCore`);
    }
    if (/\b(?:from|import)\s+strands\b/.test(source)) {
      pushSignal(signals, "strands", 100, `${file.relative} imports strands`);
    }
    if (/\bfrom\s+google\.adk\b|\bimport\s+google\.adk\b|\bfrom\s+veadk\b/.test(
      source
    )) {
      pushSignal(signals, "adk", 95, `${file.relative} imports ADK or VeADK`);
    }
    if (/\b(?:from|import)\s+langchain(?:_core|_community|_openai)?\b/.test(source)) {
      pushSignal(signals, "langchain", 70, `${file.relative} imports LangChain`);
    }
  }
  return signals;
}
function summarizeFrameworkSignals(signals) {
  const grouped = /* @__PURE__ */ new Map();
  for (const signal of signals) {
    const current = grouped.get(signal.framework) ?? { score: 0, evidence: [] };
    current.score = Math.max(current.score, signal.score);
    if (!current.evidence.includes(signal.reason) && current.evidence.length < 12) {
      current.evidence.push(signal.reason);
    }
    grouped.set(signal.framework, current);
  }
  return [...grouped.entries()].map(([framework, value]) => ({ framework, ...value })).sort(
    (left, right) => right.score - left.score || left.framework.localeCompare(right.framework)
  );
}
function topLevelSymbols(source) {
  const symbols = [];
  for (const line of source.split(/\r?\n/)) {
    let match = /^(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(/.exec(line);
    if (match) {
      symbols.push({ name: match[1], kind: "function", line });
      continue;
    }
    match = /^class\s+([A-Za-z_][A-Za-z0-9_]*)\b/.exec(line);
    if (match) {
      symbols.push({ name: match[1], kind: "class", line });
      continue;
    }
    match = /^([A-Za-z_][A-Za-z0-9_]*)\s*(?::[^=]+)?=/.exec(line);
    if (match) symbols.push({ name: match[1], kind: "value", line });
  }
  return symbols;
}
function candidateScore(framework, symbol, source) {
  const { name, kind, line } = symbol;
  if (framework === "adk") {
    if (name === "root_agent") return { score: 130, reason: "ADK root_agent" };
    if (name === "agent") return { score: 85, reason: "ADK agent candidate" };
  }
  if (framework === "langgraph") {
    if (name === "graph" || name === "compiled_graph" || name === "agent" || name === "app") {
      const compiled = line.includes(".compile(") || new RegExp(`\\b${name}\\s*=\\s*[\\s\\S]{0,300}\\.compile\\(`).test(source);
      return {
        score: compiled ? 130 : name === "graph" ? 110 : 80,
        reason: compiled ? "compiled LangGraph graph" : "LangGraph graph candidate"
      };
    }
  }
  if (framework === "langchain") {
    if (["agent", "chain", "runnable"].includes(name)) {
      return { score: 110, reason: `LangChain ${name} candidate` };
    }
    if (name === "app") return { score: 75, reason: "LangChain app candidate" };
  }
  if (framework === "strands") {
    if (name === "agent") return { score: 120, reason: "Strands agent" };
    if (["build_agent", "create_agent", "make_agent"].includes(name) && kind === "function") {
      return { score: 115, reason: "Strands agent factory" };
    }
  }
  if (framework === "agentcore") {
    if (name === "app" && /\bBedrockAgentCoreApp\b/.test(source)) {
      return { score: 130, reason: "BedrockAgentCoreApp instance" };
    }
    if (["agent", "handler"].includes(name)) {
      return { score: 80, reason: "AgentCore callable candidate" };
    }
  }
  return void 0;
}
function langGraphServerCandidates(files) {
  const config = files.find((file) => file.relative.toLowerCase() === "langgraph.json");
  if (!config) return [];
  try {
    const parsed = JSON.parse(readText(config));
    if (!parsed.graphs || typeof parsed.graphs !== "object" || Array.isArray(parsed.graphs)) {
      return [];
    }
    return Object.keys(parsed.graphs).map((graphId) => ({
      value: `${config.relative}:${graphId}`,
      file: config.relative,
      object: graphId,
      score: 140,
      reason: "Graph declared in langgraph.json"
    }));
  } catch {
    return [];
  }
}
function detectEntryCandidates(files, framework, request) {
  if (framework === "dify" || framework === "any") return [];
  if (framework === "langgraph" && request.options.server_mode === "langgraph") {
    return langGraphServerCandidates(files);
  }
  const candidates = [];
  for (const file of files) {
    if (!file.relative.endsWith(".py")) continue;
    const source = readText(file);
    for (const symbol of topLevelSymbols(source)) {
      const scored = candidateScore(framework, symbol, source);
      if (!scored) continue;
      candidates.push({
        value: `${file.relative}:${symbol.name}`,
        file: file.relative,
        object: symbol.name,
        score: scored.score,
        reason: scored.reason
      });
    }
  }
  return candidates.sort(
    (left, right) => right.score - left.score || left.value.localeCompare(right.value)
  );
}
function resolveFramework(request, evidence) {
  if (request.framework !== "auto") return request.framework;
  const best = evidence[0];
  if (!best) return void 0;
  const second = evidence[1];
  if (second && second.score === best.score) return void 0;
  return best.framework;
}
function resolveEntry(request, candidates) {
  if (request.options.entry) return request.options.entry;
  const best = candidates[0];
  if (!best) return void 0;
  const tied = candidates.filter((candidate) => candidate.score === best.score);
  return tied.length === 1 ? best.value : void 0;
}
function detectMigrationProject(sourceRoot, request) {
  const files = listProjectFiles(sourceRoot);
  const evidence = summarizeFrameworkSignals(detectFrameworkSignals(files));
  const framework = resolveFramework(request, evidence);
  const candidates = framework ? detectEntryCandidates(files, framework, request) : [];
  return {
    framework,
    framework_evidence: evidence,
    entry: framework === "dify" || framework === "any" ? void 0 : resolveEntry(request, candidates),
    entry_candidates: candidates
  };
}

// src/migrate-runner/manifest.ts
var import_yaml6 = __toESM(require_dist(), 1);
import { execFileSync as execFileSync6 } from "child_process";
import { createHash as createHash8 } from "crypto";
import {
  existsSync as existsSync27,
  lstatSync as lstatSync3,
  mkdirSync as mkdirSync12,
  readFileSync as readFileSync22,
  readdirSync as readdirSync8,
  renameSync as renameSync5,
  statSync as statSync9,
  writeFileSync as writeFileSync13
} from "fs";
import { basename as basename4, dirname as dirname9, join as join25, relative as relative10, resolve as resolve12 } from "path";
var MAX_ARTIFACT_FILES = 2e4;
var PREVIEWABLE_EXTENSIONS = /* @__PURE__ */ new Set([
  ".cfg",
  ".conf",
  ".css",
  ".csv",
  ".env",
  ".html",
  ".ini",
  ".js",
  ".json",
  ".jsx",
  ".md",
  ".mjs",
  ".py",
  ".sh",
  ".sql",
  ".toml",
  ".ts",
  ".tsx",
  ".txt",
  ".xml",
  ".yaml",
  ".yml"
]);
function toPosix3(value) {
  return value.replace(/\\/g, "/");
}
function extension2(path) {
  const name = basename4(path);
  const index = name.lastIndexOf(".");
  return index > 0 ? name.slice(index).toLowerCase() : "";
}
function mediaType(path) {
  const ext = extension2(path);
  const known = {
    ".css": "text/css",
    ".csv": "text/csv",
    ".html": "text/html",
    ".js": "text/javascript",
    ".json": "application/json",
    ".jsx": "text/javascript",
    ".md": "text/markdown",
    ".mjs": "text/javascript",
    ".py": "text/x-python",
    ".sh": "text/x-shellscript",
    ".toml": "application/toml",
    ".ts": "text/typescript",
    ".tsx": "text/typescript",
    ".txt": "text/plain",
    ".xml": "application/xml",
    ".yaml": "application/yaml",
    ".yml": "application/yaml"
  };
  return known[ext] ?? "application/octet-stream";
}
function fileSha256(path) {
  return createHash8("sha256").update(readFileSync22(path)).digest("hex");
}
function listMigrationResultFiles(outputRoot, manifestPath) {
  const root = resolve12(outputRoot);
  const manifest = resolve12(manifestPath);
  const files = [];
  function visit(directory) {
    for (const entry of readdirSync8(directory, { withFileTypes: true })) {
      if (files.length >= MAX_ARTIFACT_FILES) {
        throw new Error(`Migration output contains more than ${MAX_ARTIFACT_FILES} files.`);
      }
      const absolute = join25(directory, entry.name);
      const metadata = lstatSync3(absolute);
      const rel = toPosix3(relative10(root, absolute));
      if (metadata.isSymbolicLink()) {
        throw new Error(`Migration output must not contain symbolic links: ${rel}.`);
      }
      if (entry.isDirectory()) {
        visit(absolute);
        continue;
      }
      if (!entry.isFile() || absolute === manifest) continue;
      const real = resolve12(absolute);
      const relativePath = relative10(root, real);
      if (!relativePath || relativePath.startsWith("..")) {
        throw new Error(`Migration output file escapes the output root: ${rel}.`);
      }
      const size = statSync9(absolute).size;
      files.push({
        path: rel,
        size,
        sha256: fileSha256(absolute),
        media_type: mediaType(rel),
        previewable: size <= 1024 * 1024 && PREVIEWABLE_EXTENSIONS.has(extension2(rel))
      });
    }
  }
  visit(root);
  return files.sort((left, right) => left.path.localeCompare(right.path));
}
function readRequiredEnvs(outputRoot) {
  const configPath = join25(outputRoot, ".agentkit", "agentkit.yaml");
  if (!existsSync27(configPath) || !statSync9(configPath).isFile()) return [];
  try {
    const value = (0, import_yaml6.parse)(readFileSync22(configPath, "utf8"));
    return Object.keys(value.envs ?? {}).sort();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`Generated .agentkit/agentkit.yaml is invalid: ${message}`);
  }
}
function writeManifestAtomic(path, manifest) {
  const temporary = `${path}.tmp`;
  writeFileSync13(temporary, `${JSON.stringify(manifest, null, 2)}
`, "utf8");
  renameSync5(temporary, path);
}
function packageMigrationOutput(outputRoot, archivePath) {
  mkdirSync12(dirname9(archivePath), { recursive: true });
  execFileSync6("tar", ["-cf", archivePath, "-C", outputRoot, "."], {
    stdio: ["ignore", "pipe", "pipe"]
  });
  return {
    path: archivePath,
    size: statSync9(archivePath).size,
    sha256: fileSha256(archivePath)
  };
}
function readStructuredVerification(outputRoot) {
  const planPath = join25(outputRoot, ".agentkit", "migration-plan.json");
  if (!existsSync27(planPath)) return { status: "not_run", checks: [] };
  try {
    const plan = JSON.parse(readFileSync22(planPath, "utf8"));
    const verification = plan.verification;
    if (!verification) return { status: "not_run", checks: [] };
    const checks = Array.isArray(verification.checks) ? verification.checks.filter(
      (check) => typeof check.name === "string" && (check.status === "passed" || check.status === "failed")
    ).map((check) => ({
      name: String(check.name),
      status: check.status,
      ...typeof check.detail === "string" ? { detail: check.detail } : {}
    })) : [];
    return {
      status: verification.status === "passed" ? "passed" : "failed",
      checks
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return {
      status: "failed",
      checks: [
        {
          name: "migration plan verification",
          status: "failed",
          detail: message
        }
      ]
    };
  }
}
function assertManifestMatchesOutput(outputRoot, manifestPath, manifest) {
  if (manifest.schema_version !== MIGRATION_RUNNER_SCHEMA_VERSION) {
    throw new Error("Migration result manifest schema version is invalid.");
  }
  const actual = listMigrationResultFiles(outputRoot, manifestPath);
  if (JSON.stringify(actual) !== JSON.stringify(manifest.files)) {
    throw new Error("Migration result manifest file list does not match output.");
  }
  if (manifest.entrypoint) {
    const entryPath = resolve12(outputRoot, manifest.entrypoint);
    if (relative10(resolve12(outputRoot), entryPath).startsWith("..") || !existsSync27(entryPath) || !statSync9(entryPath).isFile()) {
      throw new Error(`Migration result entrypoint is missing: ${manifest.entrypoint}.`);
    }
  }
  if (dirname9(resolve12(manifestPath)) === resolve12(outputRoot) && basename4(manifestPath) !== "migration-result.json") {
    throw new Error("Root migration result manifest must be named migration-result.json.");
  }
}

// src/migrate-runner/runner.ts
var FRAMEWORK_LABELS = {
  langchain: "LangChain",
  langgraph: "LangGraph",
  adk: "ADK / VeADK",
  strands: "Strands",
  agentcore: "Amazon Bedrock AgentCore",
  dify: "Dify",
  any: "\u5176\u4ED6\u9879\u76EE"
};
function toPosix4(value) {
  return value.replace(/\\/g, "/");
}
function isSameOrInside(parent, candidate) {
  const rel = relative11(resolve13(parent), resolve13(candidate));
  return rel === "" || !rel.startsWith("..") && !rel.startsWith("/");
}
function assertSeparatedRoots(sourceRoot, outputRoot) {
  if (isSameOrInside(sourceRoot, outputRoot) || isSameOrInside(outputRoot, sourceRoot)) {
    throw new Error(
      "Migration source and output directories must not contain each other."
    );
  }
}
function frameworkChoices(detection) {
  const evidence = new Map(
    detection.framework_evidence.map((item) => [item.framework, item])
  );
  const ordered = [
    ...detection.framework_evidence.map((item) => item.framework),
    ...MIGRATION_RUNNER_FRAMEWORKS.filter((framework) => !evidence.has(framework))
  ];
  return ordered.map((framework) => ({
    value: framework,
    label: FRAMEWORK_LABELS[framework],
    description: evidence.get(framework)?.evidence.join("\uFF1B") || "\u7531\u7528\u6237\u786E\u8BA4\u6E90\u9879\u76EE\u7C7B\u578B"
  }));
}
function entryChoices(detection) {
  return detection.entry_candidates.map((candidate) => ({
    value: candidate.value,
    label: candidate.value,
    description: candidate.reason
  }));
}
function resumeToken(request, input, detection) {
  return createHash9("sha256").update(request.task_id).update("\0").update(request.attempt_id).update("\0").update(input).update("\0").update(request.source.fingerprint).update("\0").update(JSON.stringify(detection)).digest("hex");
}
function resolvedStrategy(request, framework) {
  const frameworkStrategy = framework === "dify" || framework === "any" ? "agentic" : "structured";
  if (request.strategy !== "auto" && request.strategy !== frameworkStrategy) {
    throw new Error(
      `Framework ${framework} requires the ${frameworkStrategy} migration strategy.`
    );
  }
  return frameworkStrategy;
}
function structuredInput(request, outputRoot, framework, entry) {
  return {
    projectDir: outputRoot,
    framework,
    entry,
    name: request.options.name,
    output: ".",
    inputKey: request.options.input_key,
    streamNodes: request.options.stream_nodes,
    compat: request.options.compat === "auto" ? void 0 : request.options.compat,
    compatPrefix: request.options.compat_prefix,
    legacyApp: request.options.legacy_app,
    modelId: request.target.model_id,
    modelBaseUrl: request.target.model_base_url,
    modelApiKeyEnv: request.target.model_api_key_env,
    project: request.target.project,
    cloudProvider: request.target.cloud_provider,
    region: request.target.region,
    serverMode: request.options.server_mode,
    allowBlocking: request.options.allow_blocking,
    verify: request.options.verify ?? true,
    force: request.options.force
  };
}
function runStructuredMigration(request, sourceRoot, outputRoot, framework, entry) {
  const sourceSnapshot = migrationSourceFileDigests(sourceRoot);
  rmSync10(outputRoot, { recursive: true, force: true });
  mkdirSync13(dirname10(outputRoot), { recursive: true });
  cpSync(sourceRoot, outputRoot, {
    recursive: true,
    errorOnExist: true,
    force: false,
    preserveTimestamps: true
  });
  const result = runMigration(
    structuredInput(request, outputRoot, framework, entry)
  );
  const preservedFiles = assertStructuredSourcePreserved(
    sourceSnapshot,
    outputRoot
  );
  return {
    result,
    status: result.plan.warnings.length > 0 ? "succeeded_with_warnings" : "succeeded",
    warnings: result.plan.warnings,
    sourcePreservationCheck: {
      name: "source implementation files preserved",
      status: "passed",
      detail: `${preservedFiles} source files remained byte-identical`
    }
  };
}
var STRUCTURED_MUTABLE_SOURCE_FILES = /* @__PURE__ */ new Set([
  ".agentkit/Dockerfile",
  ".agentkit/agentkit.yaml",
  ".agentkit/migration-plan.json",
  ".dockerignore",
  "requirements.txt"
]);
function assertStructuredSourcePreserved(sourceSnapshot, outputRoot) {
  const expected = sourceSnapshot.filter(
    (file) => !STRUCTURED_MUTABLE_SOURCE_FILES.has(file.path)
  );
  const output = new Map(
    migrationSourceFileDigests(outputRoot).map((file) => [file.path, file])
  );
  for (const sourceFile of expected) {
    const generated = output.get(sourceFile.path);
    if (!generated || generated.size !== sourceFile.size || generated.sha256 !== sourceFile.sha256) {
      throw new Error(
        `Structured migration changed source implementation file: ${sourceFile.path}.`
      );
    }
  }
  return expected.length;
}
function manifestForStructured(result) {
  const verification = result.result.plan.verification;
  const checks = [
    ...verification?.checks ?? [],
    result.sourcePreservationCheck
  ];
  return {
    status: result.status,
    entrypoint: "agentkit_app.py",
    launch: { type: "python", command: ["python", "agentkit_app.py"] },
    migration_plan: ".agentkit/migration-plan.json",
    verification: verification ? {
      status: verification.status,
      checks
    } : { status: "passed", checks },
    warnings: result.warnings,
    findings: []
  };
}
function manifestForAgentic(result) {
  return {
    status: result.status,
    entrypoint: "main.py",
    launch: { type: "python", command: ["python", "main.py"] },
    migration_plan: "migration_plan.md",
    verification: result.verification,
    warnings: result.warnings,
    findings: result.findings,
    report: "convert_report.md"
  };
}
function errorCode(error) {
  const message = error instanceof Error ? error.message : String(error);
  if (/fingerprint/i.test(message)) return "MIGRATION_SOURCE_CHANGED";
  if (/verification|validation|deployable result/i.test(message)) {
    return "MIGRATION_VALIDATION_FAILED";
  }
  if (/invalid (?:partial )?migration artifact/i.test(message)) {
    return "MIGRATION_VALIDATION_FAILED";
  }
  if (/source directory|source project/i.test(message)) {
    return "MIGRATION_SOURCE_INVALID";
  }
  if (/framework|entry|strategy/i.test(message)) {
    return "MIGRATION_REQUEST_INVALID";
  }
  if (/timeout/i.test(message)) return "MIGRATION_EXECUTION_TIMEOUT";
  return "MIGRATION_RUNNER_FAILED";
}
function retryableError(error) {
  return Boolean(
    error && typeof error === "object" && "retryable" in error && error.retryable === true
  );
}
function phaseMessage(type, phase) {
  const action = type === "phase_started" ? "Started" : "Completed";
  return `${action} migration phase: ${phase}`;
}
function emitPhase(sink, type, phase) {
  sink.emit({ type, phase, message: phaseMessage(type, phase) });
}
function migrationRunnerCapabilities() {
  return {
    schema_version: MIGRATION_RUNNER_SCHEMA_VERSION,
    runner_version: package_default.version,
    strategies: ["structured", "agentic"],
    frameworks: [...MIGRATION_RUNNER_FRAMEWORKS],
    structured_frameworks: ["langchain", "langgraph", "adk", "strands", "agentcore"],
    agentic_frameworks: ["dify", "any"],
    phases: [...MIGRATION_RUNNER_PHASES],
    event_protocol: "ndjson",
    manifest: "migration-result.json"
  };
}
async function runMigrationRunner(request, sink, dependencies = {}) {
  const workspace = resolve13(dependencies.workspace ?? process.cwd());
  const now = dependencies.now ?? (() => /* @__PURE__ */ new Date());
  const runAgentic = dependencies.executeAgentic ?? executeAgenticMigration;
  let phase = "detecting";
  try {
    const sourceRoot = resolveWorkspacePath(
      workspace,
      request.source.root,
      "request.source.root"
    );
    const outputRoot = resolveWorkspacePath(
      workspace,
      request.output.root,
      "request.output.root"
    );
    const manifestPath = resolveWorkspacePath(
      workspace,
      request.output.manifest,
      "request.output.manifest"
    );
    assertSeparatedRoots(sourceRoot, outputRoot);
    if (!existsSync28(sourceRoot) || !statSync10(sourceRoot).isDirectory()) {
      throw new Error("Migration source directory is missing.");
    }
    emitPhase(sink, "phase_started", phase);
    const actualFingerprint = fingerprintMigrationSource(sourceRoot);
    if (actualFingerprint !== request.source.fingerprint) {
      throw new Error(
        "Migration source fingerprint does not match the uploaded source."
      );
    }
    const detection = detectMigrationProject(sourceRoot, request);
    if (!detection.framework) {
      sink.emit({
        type: "needs_input",
        phase: "detecting",
        input: "framework",
        message: "\u8BF7\u9009\u62E9\u6E90\u9879\u76EE\u6846\u67B6\u540E\u7EE7\u7EED\u8FC1\u79FB\u3002",
        choices: frameworkChoices(detection),
        resume_token: resumeToken(request, "framework", detection),
        detection
      });
      return "needs_input";
    }
    const framework = detection.framework;
    const strategy = resolvedStrategy(request, framework);
    if (strategy === "structured" && !detection.entry) {
      sink.emit({
        type: "needs_input",
        phase: "detecting",
        input: "entry",
        message: "\u8BF7\u9009\u62E9\u6216\u8F93\u5165\u6E90\u9879\u76EE\u7684 Agent \u5165\u53E3\u540E\u7EE7\u7EED\u8FC1\u79FB\u3002",
        choices: entryChoices(detection),
        resume_token: resumeToken(request, "entry", detection),
        detection
      });
      return "needs_input";
    }
    emitPhase(sink, "phase_completed", phase);
    phase = "planning";
    emitPhase(sink, "phase_started", phase);
    sink.emit({
      type: "activity",
      phase,
      message: `${FRAMEWORK_LABELS[framework]} \xB7 ${strategy}`
    });
    emitPhase(sink, "phase_completed", phase);
    const resolvedRequest = {
      ...request,
      strategy,
      framework,
      options: {
        ...request.options,
        ...detection.entry ? { entry: detection.entry } : {}
      }
    };
    phase = "migrating";
    emitPhase(sink, "phase_started", phase);
    let specificManifest;
    if (strategy === "structured") {
      sink.emit({
        type: "activity",
        phase,
        message: "Running AgentKit structured migration."
      });
      const result = runStructuredMigration(
        resolvedRequest,
        sourceRoot,
        outputRoot,
        framework,
        detection.entry
      );
      specificManifest = manifestForStructured(result);
    } else {
      sink.emit({
        type: "activity",
        phase,
        message: "Running Codex best-effort migration in the existing Dev Sandbox Session."
      });
      const runRoot = join26(
        workspace,
        ".migration-runner",
        request.task_id,
        request.attempt_id
      );
      specificManifest = manifestForAgentic(
        await runAgentic(
          resolvedRequest,
          sourceRoot,
          outputRoot,
          runRoot,
          sink
        )
      );
    }
    if (fingerprintMigrationSource(sourceRoot) !== request.source.fingerprint) {
      throw new Error("Migration process modified the uploaded source project.");
    }
    emitPhase(sink, "phase_completed", phase);
    phase = "validating";
    emitPhase(sink, "phase_started", phase);
    if (strategy === "structured" && !specificManifest.verification) {
      specificManifest.verification = readStructuredVerification(outputRoot);
    }
    if (specificManifest.verification?.status === "failed") {
      throw new Error("Migration validation did not pass.");
    }
    emitPhase(sink, "phase_completed", phase);
    phase = "packaging";
    emitPhase(sink, "phase_started", phase);
    const archivePath = join26(
      workspace,
      ".migration-runner",
      request.task_id,
      request.attempt_id,
      "artifacts",
      "migration-output.tar"
    );
    const files = listMigrationResultFiles(outputRoot, manifestPath);
    const archive = packageMigrationOutput(outputRoot, archivePath);
    const archiveRelativePath = toPosix4(relative11(workspace, archive.path));
    const manifest = {
      schema_version: MIGRATION_RUNNER_SCHEMA_VERSION,
      runner_version: package_default.version,
      task_id: request.task_id,
      attempt_id: request.attempt_id,
      request_fingerprint: request.source.fingerprint,
      strategy,
      framework,
      generated_at: now().toISOString(),
      entry: detection.entry,
      ...specificManifest,
      files,
      required_envs: readRequiredEnvs(outputRoot),
      archive: {
        path: archiveRelativePath,
        size: archive.size,
        sha256: archive.sha256
      }
    };
    writeManifestAtomic(manifestPath, manifest);
    assertManifestMatchesOutput(outputRoot, manifestPath, manifest);
    sink.emit({
      type: "artifact",
      phase: "packaging",
      artifact: {
        path: archiveRelativePath,
        size: archive.size,
        sha256: archive.sha256,
        media_type: "application/x-tar",
        previewable: false
      }
    });
    emitPhase(sink, "phase_completed", phase);
    sink.emit({
      type: "result",
      phase: "packaging",
      status: manifest.status,
      manifest: request.output.manifest,
      archive: archiveRelativePath
    });
    return "result";
  } catch (error) {
    sink.emit({
      type: "error",
      phase,
      code: errorCode(error),
      message: error instanceof Error ? error.message : String(error),
      retryable: retryableError(error)
    });
    return "failed";
  }
}

// src/migrate-runner/cli.ts
function optionValue(args, name) {
  const index = args.indexOf(name);
  if (index < 0) return void 0;
  const value = args[index + 1];
  if (!value || value.startsWith("--")) {
    throw new Error(`${name} requires a value.`);
  }
  return value;
}
async function main(args = process.argv.slice(2)) {
  const command = args[0];
  if (command === "capabilities") {
    process.stdout.write(`${JSON.stringify(migrationRunnerCapabilities())}
`);
    return 0;
  }
  if (command !== "run") {
    process.stderr.write(
      "Usage: agentkit-migration-runner capabilities | run --request <request.json>\n"
    );
    return 2;
  }
  const requestPath = optionValue(args, "--request");
  if (!requestPath) throw new Error("run requires --request <request.json>.");
  const request = readMigrationRunnerRequest(requestPath);
  const sink = new NdjsonMigrationRunnerEventSink(
    request,
    process.stdout,
    request.sequence_start ?? 0
  );
  const outcome = await runMigrationRunner(request, sink);
  return outcome === "failed" ? 1 : 0;
}
main().then((code) => {
  process.exitCode = code;
}).catch((error) => {
  process.stderr.write(
    `${JSON.stringify({
      code: "MIGRATION_RUNNER_REQUEST_INVALID",
      message: error instanceof Error ? error.message : String(error),
      retryable: false
    })}
`
  );
  process.exitCode = 2;
});
var __testables = { main, optionValue };
export {
  __testables
};
