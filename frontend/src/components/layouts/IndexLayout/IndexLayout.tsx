import { useId, type HTMLAttributes, type ReactNode } from "react";
import logoAsset from "./assets/logo.svg";
import spotlightAsset from "./assets/spotlight.png";
import "./IndexLayout.css";

export interface IndexLayoutProps extends Omit<HTMLAttributes<HTMLDivElement>, "children"> {
  /** 顶部模式切换区域，推荐传入 GlassTabs */
  tabs: ReactNode;
  /** 主输入区域，推荐传入 PromptInput，桌面尺寸为 720 × 150px */
  prompt: ReactNode;
  /** 输入框下方的快捷入口，推荐传入三个 compact Item */
  shortcuts: ReactNode;
  /** 主标题 */
  heading?: ReactNode;
  /** 标题上方的标志，默认使用设计稿中的 60 × 60px AK 标志 */
  logo?: ReactNode;
}

/** Figma 602:43991 的右侧首页区域，不包含产品侧栏 */
export function IndexLayout({
  tabs,
  prompt,
  shortcuts,
  heading = "How can I help you today?",
  logo = <img src={logoAsset} width={60} height={60} alt="" />,
  className = "",
  ...props
}: IndexLayoutProps) {
  const headingId = useId();

  return (
    <div {...props} className={`studio-index-layout ${className}`.trim()}>
      <div className="studio-index-layout__spotlight" aria-hidden="true">
        <img src={spotlightAsset} width={1206} height={718} alt="" />
      </div>
      <div className="studio-index-layout__tabs">{tabs}</div>
      <section className="studio-index-layout__content" aria-labelledby={headingId}>
        <header className="studio-index-layout__welcome">
          <div className="studio-index-layout__logo">{logo}</div>
          <h1 className="studio-index-layout__heading" id={headingId}>{heading}</h1>
        </header>
        <div className="studio-index-layout__prompt">{prompt}</div>
        <div className="studio-index-layout__shortcuts">{shortcuts}</div>
      </section>
    </div>
  );
}
