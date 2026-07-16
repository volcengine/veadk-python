// Skill Hub (public findskill.com / skills.volces.com marketplace) picker.
// Extracted from the original inline SkillHubPicker in CustomCreate.tsx so the
// new multi-source SkillsSourceTabs can swap between sources without growing
// that file further.

import { useEffect, useState } from "react";
import { Check, Info, Loader2, Plus, Search } from "lucide-react";
import { searchSkills } from "./skills/skillhub";
import type { SelectedSkill, SkillHit } from "./skills/types";

export function SkillHubPicker({
  selected,
  onChange,
}: {
  selected: SelectedSkill[];
  onChange: (next: SelectedSkill[]) => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SkillHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  const isSelected = (slug: string) =>
    selected.some((s) => s.source === "skillhub" && s.slug === slug);

  const toggle = (hit: SkillHit) => {
    if (!hit.slug) return;
    if (isSelected(hit.slug)) {
      onChange(selected.filter((s) => !(s.source === "skillhub" && s.slug === hit.slug)));
    } else {
      onChange([
        ...selected,
        {
          source: "skillhub",
          slug: hit.slug,
          name: hit.name,
          folder: hit.slug.split("/").pop() || hit.name,
          namespace: hit.namespace || "public",
          description: hit.description,
        },
      ]);
    }
  };

  const runSearch = async (q: string) => {
    setLoading(true);
    setError(null);
    setSearched(true);
    try {
      const hits = await searchSkills(q);
      setResults(hits);
    } catch (e) {
      setError(e instanceof Error ? e.message : "搜索失败，请稍后重试。");
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  // Debounce typing ~300ms; also searches on Enter / button via runSearch.
  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setResults([]);
      setSearched(false);
      setError(null);
      return;
    }
    const t = setTimeout(() => runSearch(q), 300);
    return () => clearTimeout(t);
  }, [query]);

  return (
    <div className="cw-skillhub">
      <div className="cw-skill-searchrow">
        <div className="cw-skill-searchbox">
          <Search className="cw-i cw-skill-searchicon" aria-hidden />
          <input
            className="cw-input cw-skill-input"
            value={query}
            placeholder="搜索 Skill Hub，例如 数据分析、PDF…"
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                if (query.trim()) runSearch(query);
              }
            }}
          />
        </div>
        <button
          type="button"
          className="cw-btn cw-btn-soft"
          onClick={() => query.trim() && runSearch(query)}
          disabled={!query.trim() || loading}
        >
          {loading ? (
            <Loader2 className="cw-i cw-spin" />
          ) : (
            <Search className="cw-i" />
          )}
          搜索
        </button>
      </div>

      {error && (
        <div className="cw-banner">
          <Info className="cw-i" />
          <span>{error}</span>
        </div>
      )}

      {loading && results.length === 0 ? (
        <p className="cw-empty-line">正在搜索…</p>
      ) : results.length > 0 ? (
        <div className="cw-skill-results">
          {results.map((hit) => {
            const on = isSelected(hit.slug || "");
            return (
              <button
                key={hit.id || hit.slug}
                type="button"
                className={`cw-skill-result ${on ? "is-on" : ""}`}
                onClick={() => toggle(hit)}
                aria-pressed={on}
              >
                <span className="cw-skill-result-icon" aria-hidden>
                  {on ? (
                    <Check className="cw-i cw-i-sm" />
                  ) : (
                    <Plus className="cw-i cw-i-sm" />
                  )}
                </span>
                <span className="cw-skill-result-meta">
                  <span className="cw-skill-result-name">{hit.name}</span>
                  {hit.description && (
                    <span className="cw-skill-result-desc">{hit.description}</span>
                  )}
                  {hit.sourceRepo && (
                    <span className="cw-skill-result-repo">{hit.sourceRepo}</span>
                  )}
                </span>
              </button>
            );
          })}
        </div>
      ) : searched && !error ? (
        <p className="cw-empty-line">没有找到匹配的技能，换个关键词试试。</p>
      ) : (
        !searched && (
          <p className="cw-empty-line">
            输入关键词以搜索 Skill Hub，所选技能会在生成项目时下载到 skills/ 目录。
          </p>
        )
      )}
    </div>
  );
}
