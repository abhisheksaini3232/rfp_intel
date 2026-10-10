import { Link } from "react-router-dom";
import { Building2, CalendarDays, FileStack } from "lucide-react";
import type { BidSummary } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDate } from "@/lib/utils";

/** Summary card for one bid on the Bids page. */
export function BidCard({ bid }: { bid: BidSummary }) {
  const v = bid.validation;
  return (
    <Link
      to={`/bids/${encodeURIComponent(bid.bid_id)}`}
      className="block rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      aria-label={`Open bid ${bid.bid_id}`}
    >
      <Card className="h-full transition-colors hover:border-primary/60">
        <CardHeader>
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="font-mono text-xs text-muted-foreground">{bid.bid_id}</p>
              <CardTitle className="mt-1 line-clamp-2">{bid.title ?? "Untitled bid"}</CardTitle>
            </div>
            <Badge variant={bid.indexed ? "accent" : "secondary"} className="shrink-0">
              {bid.indexed ? "indexed" : "not indexed"}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p className="flex items-center gap-2 text-muted-foreground">
            <Building2 className="h-4 w-4 shrink-0" />
            <span className="truncate">{bid.agency ?? "Agency unknown"}</span>
          </p>
          <p className="flex flex-wrap items-center gap-2 text-muted-foreground">
            <CalendarDays className="h-4 w-4 shrink-0" />
            <span>{bid.due_date ?? "Due date unknown"}</span>
            {bid.due_date_changed_by !== null && (
              <Badge variant="outline" className="border-amber-500 text-amber-700 dark:text-amber-400">
                changed by Addendum {bid.due_date_changed_by}
              </Badge>
            )}
          </p>
          <p className="flex items-center gap-2 text-muted-foreground">
            <FileStack className="h-4 w-4 shrink-0" />
            <span>
              {bid.doc_count} document{bid.doc_count === 1 ? "" : "s"}
            </span>
          </p>
          <div className="flex flex-wrap items-center gap-1.5 pt-1">
            {v ? (
              <>
                <Badge variant="outline" className="border-green-500 text-green-700 dark:text-green-400">
                  {v.passed} passed
                </Badge>
                <Badge variant="outline" className="border-red-500 text-red-700 dark:text-red-400">
                  {v.failed} failed
                </Badge>
                <Badge variant="outline" className="text-muted-foreground">
                  {v.not_found} not found
                </Badge>
              </>
            ) : (
              <span className="text-xs text-muted-foreground">No extraction yet</span>
            )}
          </div>
          {bid.last_run && (
            <p className="text-xs text-muted-foreground">Last run: {formatDate(bid.last_run)}</p>
          )}
        </CardContent>
      </Card>
    </Link>
  );
}
