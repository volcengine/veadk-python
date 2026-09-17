export function MpaIcon({
  kind,
}: {
  kind:
    "plus" | "play" | "edit" | "more" | "detail" | "copy" | "delete" | "filter";
}) {
  const paths = {
    filter: "M4 5h16l-6 7v7l-4-2v-5Z",
    plus: "M12 5v14M5 12h14",
    play: "M8 5l11 7-11 7Z",
    edit: "m15 4 5 5-11 11H4v-5ZM13 6l5 5",
    more: "M5 12h.01M12 12h.01M19 12h.01",
    detail: "M7 3h10l3 3v15H4V3ZM8 9h8M8 13h8M8 17h5",
    copy: "M9 8V3h12v13h-5M3 8h13v13H3Z",
    delete: "M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7",
  };
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="icon"
      aria-hidden="true"
    >
      <path d={paths[kind]} />
    </svg>
  );
}
