import "./Skeleton.css";

export interface SkeletonProps {
  width?: "full" | "medium" | "short";
  shape?: "line" | "block";
}

export function Skeleton({ width = "full", shape = "line" }: SkeletonProps) {
  return <span className="studio-skeleton" data-width={width} data-shape={shape} aria-hidden="true" />;
}
