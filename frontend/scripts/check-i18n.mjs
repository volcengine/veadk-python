#!/usr/bin/env node

import { existsSync, readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = resolve(fileURLToPath(new URL("..", import.meta.url)));
const resourcesRoot = resolve(frontendRoot, "src/i18n/resources");
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

function flatten(value, prefix = "", output = new Map()) {
  if (typeof value === "string") {
    output.set(prefix, value);
    return output;
  }
  if (!value || Array.isArray(value) || typeof value !== "object") {
    throw new TypeError(`translation value at "${prefix}" must be a string or object`);
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
            JSON.parse(readFileSync(resolve(referenceDirectory, namespace), "utf8")),
          );
          candidate = flatten(
            JSON.parse(readFileSync(resolve(localeDirectory, namespace), "utf8")),
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

    if (!process.exitCode) {
      console.log(
        `[i18n] ${locales.length} locales and ${referenceNamespaces.length} namespaces are consistent`,
      );
    }
  }
}
