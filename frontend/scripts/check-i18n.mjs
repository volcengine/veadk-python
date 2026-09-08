#!/usr/bin/env node

import { existsSync, readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = resolve(fileURLToPath(new URL("..", import.meta.url)));
const resourcesRoot = resolve(frontendRoot, "src/i18n/resources");
const sourceRoot = resolve(frontendRoot, "src");
const referenceLocale = "en-US";
const requiredLocales = ["en-US", "zh-CN"];

function fail(message) {
  console.error(`[i18n] ${message}`);
  process.exitCode = 1;
}

function jsonFiles(directory) {
  return readdirSync(directory, { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith(".json"))
    .map((entry) => entry.name)
    .sort();
}

function sourceFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = resolve(directory, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    return entry.isFile() && /\.[cm]?[jt]sx?$/.test(entry.name) ? [path] : [];
  });
}

function flatten(value, prefix = "", output = new Map()) {
  if (typeof value === "string") {
    output.set(prefix, value);
    return output;
  }
  if (!value || Array.isArray(value) || typeof value !== "object") {
    throw new TypeError(
      `translation value at "${prefix}" must be a string or object`,
    );
  }
  for (const [key, child] of Object.entries(value)) {
    flatten(child, prefix ? `${prefix}.${key}` : key, output);
  }
  return output;
}

function interpolationVariables(message) {
  return [...message.matchAll(/{{\s*-?\s*([^},\s]+)(?:\s*,[^}]*)?\s*}}/g)]
    .map((match) => match[1])
    .sort();
}

function defaultNamespace(source) {
  const match = source.match(/useTranslation\(\s*(?:\[\s*)?["']([^"']+)["']/);
  return match?.[1];
}

function namespaceOverride(source, offset) {
  const options = source.slice(offset, offset + 240);
  return options.match(/^\s*,\s*\{[^}]*\bns\s*:\s*["']([^"']+)["']/)?.[1];
}

function validateSourceReferences(referenceCatalogs) {
  const hookCallPattern = /(?<![\w.])t\(\s*(["'`])([^"'`\r\n]*)\1/g;
  const i18nCallPattern = /\bi18n\.t\(\s*(["'`])([^"'`\r\n]*)\1/g;
  const hasKey = (catalog, key) =>
    catalog.has(key) ||
    [...catalog.keys()].some((catalogKey) => catalogKey.startsWith(`${key}_`));

  for (const path of sourceFiles(sourceRoot)) {
    const source = readFileSync(path, "utf8");
    const defaultNs = defaultNamespace(source);
    const calls = [
      ...[...source.matchAll(hookCallPattern)].map((match) => ({
        match,
        fallbackNamespace: defaultNs,
      })),
      ...[...source.matchAll(i18nCallPattern)].map((match) => ({
        match,
        fallbackNamespace: undefined,
      })),
    ];

    for (const { match, fallbackNamespace } of calls) {
      const rawKey = match[2];
      let namespace =
        namespaceOverride(source, match.index + match[0].length) ??
        fallbackNamespace;
      let key = rawKey;
      const namespaceSeparator = rawKey.indexOf(":");
      if (
        namespaceSeparator !== -1 &&
        !rawKey.slice(0, namespaceSeparator).includes("${")
      ) {
        namespace = rawKey.slice(0, namespaceSeparator);
        key = rawKey.slice(namespaceSeparator + 1);
      }
      if (!namespace) continue;

      const catalog = referenceCatalogs.get(namespace);
      if (!catalog) {
        fail(`${path} uses unknown namespace ${namespace}`);
        continue;
      }

      const interpolationStart = key.indexOf("${");
      if (interpolationStart === -1) {
        if (!hasKey(catalog, key)) {
          fail(`${path} references missing key ${namespace}:${key}`);
        }
        continue;
      }

      const staticPrefix = key.slice(0, interpolationStart);
      if (
        staticPrefix &&
        ![...catalog.keys()].some((catalogKey) =>
          catalogKey.startsWith(staticPrefix),
        )
      ) {
        fail(
          `${path} references missing dynamic key prefix ${namespace}:${staticPrefix}`,
        );
      }
    }
  }
}

if (!existsSync(resourcesRoot)) {
  fail(`resources directory does not exist: ${resourcesRoot}`);
} else {
  const locales = readdirSync(resourcesRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();

  for (const locale of requiredLocales) {
    if (!locales.includes(locale)) fail(`required locale ${locale} is missing`);
  }

  if (!locales.includes(referenceLocale)) {
    fail(`reference locale ${referenceLocale} is missing`);
  } else {
    const referenceDirectory = resolve(resourcesRoot, referenceLocale);
    const referenceNamespaces = jsonFiles(referenceDirectory);
    const referenceCatalogs = new Map(
      referenceNamespaces.map((namespace) => [
        namespace.replace(/\.json$/, ""),
        flatten(
          JSON.parse(
            readFileSync(resolve(referenceDirectory, namespace), "utf8"),
          ),
        ),
      ]),
    );

    for (const locale of locales) {
      const localeDirectory = resolve(resourcesRoot, locale);
      const localeNamespaces = jsonFiles(localeDirectory);
      const missingNamespaces = referenceNamespaces.filter(
        (namespace) => !localeNamespaces.includes(namespace),
      );
      const extraNamespaces = localeNamespaces.filter(
        (namespace) => !referenceNamespaces.includes(namespace),
      );

      for (const namespace of missingNamespaces) {
        fail(`${locale} is missing namespace ${namespace}`);
      }
      for (const namespace of extraNamespaces) {
        fail(`${locale} has extra namespace ${namespace}`);
      }

      for (const namespace of referenceNamespaces) {
        if (!localeNamespaces.includes(namespace)) continue;
        let reference;
        let candidate;
        try {
          reference = flatten(
            JSON.parse(
              readFileSync(resolve(referenceDirectory, namespace), "utf8"),
            ),
          );
          candidate = flatten(
            JSON.parse(
              readFileSync(resolve(localeDirectory, namespace), "utf8"),
            ),
          );
        } catch (error) {
          fail(`${locale}/${namespace}: ${error.message}`);
          continue;
        }

        for (const key of reference.keys()) {
          if (!candidate.has(key)) {
            fail(`${locale}/${namespace} is missing key ${key}`);
            continue;
          }
          const expectedVariables = interpolationVariables(reference.get(key));
          const actualVariables = interpolationVariables(candidate.get(key));
          if (expectedVariables.join("\0") !== actualVariables.join("\0")) {
            fail(
              `${locale}/${namespace}:${key} interpolation variables differ ` +
                `(${actualVariables.join(", ")} != ${expectedVariables.join(", ")})`,
            );
          }
        }
        for (const key of candidate.keys()) {
          if (!reference.has(key)) {
            fail(`${locale}/${namespace} has extra key ${key}`);
          }
        }
      }
    }

    validateSourceReferences(referenceCatalogs);

    if (!process.exitCode) {
      console.log(
        `[i18n] ${locales.length} locales and ${referenceNamespaces.length} namespaces are consistent`,
      );
    }
  }
}
