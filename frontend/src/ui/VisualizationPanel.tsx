import { memo, useState, type ReactNode } from "react";
import { SegmentedControl } from "@openai/apps-sdk-ui/components/SegmentedControl";

type VisualizationView = "preview" | "code";

interface VisualizationPanelProps {
  children: ReactNode;
  label: string;
  language: string;
  source: string;
  streaming?: boolean;
}

function VisualizationPanelImpl({
  children,
  label,
  language,
  source,
  streaming = false,
}: VisualizationPanelProps) {
  const [view, setView] = useState<VisualizationView>("preview");
  const activeView: VisualizationView = streaming ? "code" : view;

  return (
    <section className="visualization-card" aria-label={`${label} 图表`}>
      <div className="visualization-card__toolbar">
        <SegmentedControl
          className="visualization-card__tabs"
          value={activeView}
          size="sm"
          gutterSize="sm"
          pill={false}
          aria-label={`${label} 显示方式`}
          onChange={(nextView) => {
            if (!streaming) setView(nextView);
          }}
        >
          <SegmentedControl.Option value="preview" disabled={streaming}>
            预览
          </SegmentedControl.Option>
          <SegmentedControl.Option value="code">
            代码
          </SegmentedControl.Option>
        </SegmentedControl>
      </div>

      <div className="visualization-card__body">
        {activeView === "code" ? (
          <pre className="visualization-card__code">
            <code className={`language-${language}`}>{source}</code>
          </pre>
        ) : children}
      </div>
    </section>
  );
}

export const VisualizationPanel = memo(VisualizationPanelImpl);
