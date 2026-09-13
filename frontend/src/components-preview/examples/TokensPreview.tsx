import { useState, type CSSProperties } from "react";
import { studioTokenGroups, studioTokens, type StudioToken } from "../../components/tokens";
import "./TokensPreview.css";

function TokenVisual({ token }: { token: StudioToken }) {
  const variable = `var(${token.name})`;
  if (token.category === "color") return <div className="tokens-preview-swatch" style={{ background: variable }} />;
  if (token.category === "radius") return <div className="tokens-preview-radius" style={{ borderRadius: variable }} />;
  if (token.category === "spacing") return <div className="tokens-preview-space" style={{ width: variable }} />;
  if (token.category === "size") return <div className="tokens-preview-size" style={{ width: variable }} />;
  if (token.category === "typography") {
    const style: CSSProperties = token.name.includes("font-family") ? { fontFamily: variable }
      : token.name.includes("font-size") ? { fontSize: variable }
      : token.name.includes("line-height") ? { lineHeight: variable }
      : { fontWeight: Number(token.value) };
    return <span className="tokens-preview-type" style={style}>Aa 0123</span>;
  }
  return null;
}

export function TokensPreview() {
  const [motionActive, setMotionActive] = useState(false);
  return (
    <section className="tokens-preview" aria-labelledby="tokens-preview-title">
      <h2 id="tokens-preview-title" className="component-preview-title">Tokens</h2>
      <p className="tokens-preview-intro">统一管理组件的视觉参数，切换主题查看深浅模式</p>
      {studioTokenGroups.map((group) => (
        <section key={group.category} className="tokens-preview-group" aria-labelledby={`tokens-${group.category}`}>
          <div className="tokens-preview-group-heading">
            <h3 id={`tokens-${group.category}`}>{group.label}</h3>
            <p>{group.description}</p>
          </div>
          {group.category === "motion" ? <button className="tokens-preview-replay" type="button" onClick={() => setMotionActive((active) => !active)}>预览动效</button> : null}
          <div className={`tokens-preview-grid tokens-preview-grid--${group.category}`}>
            {studioTokens.filter((token) => token.category === group.category).map((token) => (
              <article className="tokens-preview-token" key={token.name}>
                <div className="tokens-preview-visual">
                  <TokenVisual token={token} />
                  {token.category === "motion" ? <div className="tokens-preview-motion-track"><span
                    className="tokens-preview-motion-dot"
                    data-active={motionActive}
                    style={token.name.includes("duration") ? { transitionDuration: `var(${token.name})` } : { transitionTimingFunction: `var(${token.name})` }}
                  /></div> : null}
                </div>
                <h4>{token.label}</h4>
                <p className="tokens-preview-name">{token.name}</p>
                {token.category === "color" ? <dl className="tokens-preview-values"><div><dt>Dark</dt><dd>{token.dark}</dd></div><div><dt>Light</dt><dd>{token.light}</dd></div></dl> : <p className="tokens-preview-value">{token.value}</p>}
              </article>
            ))}
          </div>
        </section>
      ))}
    </section>
  );
}
