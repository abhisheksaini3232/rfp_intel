import type { Citation } from "@/api/types";
import { citationLabel, cn } from "@/lib/utils";

interface CitationChipProps {
  citation: Citation;
  index?: number;
  active?: boolean;
  onClick?: () => void;
}

/** Small "file p.N" chip; clickable when onClick is provided. */
export function CitationChip({ citation, index, active, onClick }: CitationChipProps) {
  const label = citationLabel(citation);
  const classes = cn(
    "inline-flex max-w-full items-center gap-1 truncate rounded-md border px-1.5 py-0.5 font-mono text-[11px]",
    active ? "border-primary bg-accent text-accent-foreground" : "bg-muted/60 text-muted-foreground",
    onClick && "hover:border-primary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
  );
  const content = (
    <>
      {index !== undefined && <span className="font-semibold">[{index}]</span>}
      <span className="truncate">{label}</span>
    </>
  );
  if (!onClick) return <span className={classes}>{content}</span>;
  return (
    <button type="button" className={classes} onClick={onClick} title={citation.quote}>
      {content}
    </button>
  );
}
