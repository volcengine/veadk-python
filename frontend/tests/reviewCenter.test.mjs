import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { transformSync } from "esbuild";

const source = readFileSync(new URL("../src/reviews/reviewModel.ts", import.meta.url), "utf8");
const {code} = transformSync(source, {loader: "ts", format: "esm"});
const {filterReviewApplications,latestSourceReviews} = await import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`);
const applications = [
  {id: "copy-1", kind: "skill", name: "same-name", description: "Writing", author: "Alice", version: "v3", status: "pending"},
  {id: "copy-2", kind: "skill", name: "same-name", description: "Writing", author: "Bob", version: "v3", status: "pending"},
];

test("same names remain separate applications with their own authors", () => {
  assert.deepEqual(filterReviewApplications(applications, "skill", "all", "same-name").map(item => item.id), ["copy-1", "copy-2"]);
  assert.deepEqual(filterReviewApplications(applications, "skill", "all", " alice ").map(item => item.id), ["copy-1"]);
});
test("kind and status filters do not invent decisions or Agent requests", () => {
  assert.deepEqual(filterReviewApplications(applications, "agent", "all", ""), []);
  assert.deepEqual(filterReviewApplications(applications, "skill", "approved", ""), []);
  assert.equal(applications[0].status, "pending");
});

test("latest source status is isolated by skill ID and version while history stays intact", () => {
  const history=[
    {id:"returned",sourceSkillId:"skill-a",version:"v1",submittedAt:"2026-09-10T08:00:00Z",status:"returned"},
    {id:"resubmitted",sourceSkillId:"skill-a",version:"v1",submittedAt:"2026-09-11T08:00:00Z",status:"pending"},
    {id:"version-2",sourceSkillId:"skill-a",version:"v2",submittedAt:"2026-09-11T09:00:00Z",status:"approved"},
    {id:"other-skill",sourceSkillId:"skill-b",version:"v1",submittedAt:"2026-09-11T10:00:00Z",status:"returned"},
  ];
  const latest=latestSourceReviews(history);
  assert.equal(latest.get("skill-a:v1").id,"resubmitted");
  assert.equal(latest.get("skill-a:v2").status,"approved");
  assert.equal(latest.get("skill-b:v1").status,"returned");
  assert.equal(history.length,4);
});
