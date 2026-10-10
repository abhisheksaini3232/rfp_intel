import { useState } from "react";
import { Plus } from "lucide-react";
import { AddBidDialog } from "@/components/AddBidDialog";
import { BidCard } from "@/components/BidCard";
import { CardsSkeleton, EmptyState, ErrorState } from "@/components/States";
import { Button } from "@/components/ui/button";
import { useBids } from "@/hooks/useBids";

/** Bids overview: one card per bid plus the "Add bid" dialog. */
export function BidsPage() {
  const bids = useBids();
  const [adding, setAdding] = useState(false);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Bids</h1>
          <p className="text-sm text-muted-foreground">Indexed bid folders and their latest extraction.</p>
        </div>
        <Button onClick={() => setAdding(true)}>
          <Plus /> Add bid
        </Button>
      </div>

      {bids.isLoading && <CardsSkeleton />}
      {bids.isError && (
        <ErrorState title="Could not load bids" message={bids.error.message} onRetry={() => void bids.refetch()} />
      )}
      {bids.data && bids.data.length === 0 && (
        <EmptyState
          title="No bids yet"
          message="Upload the RFP, addenda and forms of a bid to index it and extract its fields."
          action={
            <Button onClick={() => setAdding(true)}>
              <Plus /> Add your first bid
            </Button>
          }
        />
      )}
      {bids.data && bids.data.length > 0 && (
        <div className="grid grid-cols-2 gap-4 xl:grid-cols-3">
          {bids.data.map((bid) => (
            <BidCard key={bid.bid_id} bid={bid} />
          ))}
        </div>
      )}

      <AddBidDialog open={adding} onOpenChange={setAdding} />
    </div>
  );
}
