import { ComponentApi } from "../api/ComponentApi";
import { PillTag } from "../../components/primitives/PillTag";
import lark from "../../components/primitives/PillTag/assets/lark.svg";
import dingtalk from "../../components/primitives/PillTag/assets/dingtalk.svg";
import wecom from "../../components/primitives/PillTag/assets/wecom.svg";
import slack from "../../components/primitives/PillTag/assets/slack.svg";

export function PillTagPreview() {
  return <section aria-labelledby="pill-tag-preview-title">
    <h2 id="pill-tag-preview-title" className="component-preview-title">Pill tag</h2>
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
      <PillTag defaultSelected style={{ width: 92.03899 }} icon={<img src={lark} alt="" style={{ width: 14.45, height: 14.22222 }} />}>Lark</PillTag>
      <PillTag style={{ width: 121.03899 }} icon={<img src={dingtalk} alt="" />}>DingTalk</PillTag>
      <PillTag style={{ width: 121.03899 }} icon={<img src={wecom} alt="" />}>WeCom</PillTag>
      <PillTag style={{ width: 100.03899 }} icon={<img src={slack} alt="" style={{ width: 13, height: 13 }} />}>Slack</PillTag>
    </div>
  <ComponentApi names={["PillTag"]} />
    </section>;
}
