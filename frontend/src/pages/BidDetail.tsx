import { useEffect, useRef } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, Loader2, Play } from "lucide-react";
import type { AddendumChange, BidRecord, DocumentSummary, FieldValue } from "@/api/types";
import { CitationChip } from "@/components/CitationChip";
import { FieldsTable } from "@/components/FieldsTable";
import { RunSteps } from "@/components/RunSteps";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/States";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "sonner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useBidDetail } from "@/hooks/useBids";
import { useCitationDrawer } from "@/hooks/useCitationDrawer";
import { useExtractRun } from "@/hooks/useExtractRun";
import { useRecord } from "@/hooks/useRecord";
import { docTypeLabel, formatDate, formatValue } from "@/lib/utils";

/** Field names (config/fields.yaml) used by the header and key-facts grid. */
const F = {
  bidNumber: "Bid Number",
  title: "Title",
  dueDate: "Due Date",
  submissionType: "Bid Submission Type",
  term: "Term of Bid",
  preBid: "Pre Bid Meeting",
  contact: "contact_info",
  agency: "company_name",
  summary: "Bid Summary",
} as const;

const KEY_FACTS: { label: string; field: string }[] = [
  { label: "Bid Number", field: F.bidNumber },
  { label: "Due Date", field: F.dueDate },
  { label: "Submission type", field: F.submissionType },
  { label: "Term", field: F.term },
  { label: "Pre-bid", field: F.preBid },
  { label: "Contact", field: F.contact },
  { label: "Agency", field: F.agency },
];

function fieldText(record: BidRecord | null | undefined, name: string): string | null {
  const field = record?.fields[name];
  if (!field || field.value === null) return null;
  return formatValue(field.value);
}

/** Bid detail: header, Overview / Fields / Addendum changes / Documents tabs. */
export function BidDetailPage() {
  const { bidId = "" } = useParams<{ bidId: string }>();
  const [params, setParams] = useSearchParams();
  const detail = useBidDetail(bidId);
  const record = useRecord(bidId);
  const run = useExtractRun(bidId);
  const autoStarted = useRef(false);

  // "Run extraction" offered from the upload toast arrives as ?extract=1.
  useEffect(() => {
    if (params.get("extract") === "1" && !autoStarted.current) {
      autoStarted.current = true;
      run.start();
      params.delete("extract");
      setParams(params, { replace: true });
    }
  }, [params, setParams, run]);

  useEffect(() => {
    if (!run.startError) return;
    toast.error(run.conflict ? "An extraction is already running for this bid." : run.startError.message);
  }, [run.startError, run.conflict]);

  useEffect(() => {
    if (!run.finished || !run.status) return;
    if (run.status.status === "done") toast.success(`Extraction finished for ${bidId}`);
    else toast.error(`Extraction failed for ${bidId}`);
  }, [run.finished, run.status, bidId]);

  const rec = record.data ?? null;
  const title = fieldText(rec, F.title);
  const tab = params.get("tab") ?? "overview";

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 space-y-1">
          <Link to="/" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
            <ArrowLeft className="h-3 w-3" /> All bids
          </Link>
          <h1 className="truncate text-2xl font-semibold tracking-tight">
            {title ?? bidId}
          </h1>
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <span className="font-mono">{bidId}</span>
            {fieldText(rec, F.bidNumber) && <span>· {fieldText(rec, F.bidNumber)}</span>}
            {fieldText(rec, F.agency) && <span>· {fieldText(rec, F.agency)}</span>}
            {fieldText(rec, F.dueDate) && <span>· due {fieldText(rec, F.dueDate)}</span>}
            {detail.data && (
              <Badge variant={detail.data.indexed ? "accent" : "secondary"}>
                {detail.data.indexed ? `indexed · ${detail.data.chunks} chunks` : "not indexed"}
              </Badge>
            )}
          </div>
        </div>
        <Button onClick={() => run.start()} disabled={run.starting || run.running}>
          {run.starting || run.running ? <Loader2 className="animate-spin" /> : <Play />}
          {run.running ? "Extracting..." : "Run extraction"}
        </Button>
      </div>

      {run.status && (
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle>Extraction run</CardTitle>
            <div className="flex items-center gap-2">
              <Button asChild variant="link" size="sm">
                <Link to={`/runs/${encodeURIComponent(run.status.run_id)}`}>
                  Full trace <ArrowRight />
                </Link>
              </Button>
              {run.finished && (
                <Button variant="ghost" size="sm" onClick={run.reset}>
                  Dismiss
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent>
            <RunSteps steps={run.status.steps} status={run.status.status} compact />
          </CardContent>
        </Card>
      )}

      <Tabs value={tab} onValueChange={(v) => { params.set("tab", v); setParams(params, { replace: true }); }}>
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="fields">Fields</TabsTrigger>
          <TabsTrigger value="changes">
            Addendum changes
            {rec && rec.addendum_changes.length > 0 && (
              <Badge variant="secondary" className="ml-2">{rec.addendum_changes.length}</Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="documents">Documents</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <RecordGate record={record} onRun={() => run.start()} running={run.running}>
            {(r) => <Overview record={r} />}
          </RecordGate>
        </TabsContent>
        <TabsContent value="fields">
          <RecordGate record={record} onRun={() => run.start()} running={run.running}>
            {(r) => (
              <Card>
                <CardContent className="p-0">
                  <FieldsTable bidId={bidId} fields={r.fields} />
                </CardContent>
              </Card>
            )}
          </RecordGate>
        </TabsContent>
        <TabsContent value="changes">
          <RecordGate record={record} onRun={() => run.start()} running={run.running}>
            {(r) => <AddendumTimeline bidId={bidId} changes={r.addendum_changes} />}
          </RecordGate>
        </TabsContent>
        <TabsContent value="documents">
          {detail.isLoading && <ListSkeleton />}
          {detail.isError && (
            <ErrorState title="Could not load documents" message={detail.error.message} onRetry={() => void detail.refetch()} />
          )}
          {detail.data && <DocumentsTable documents={detail.data.documents} />}
        </TabsContent>
      </Tabs>
    </div>
  );
}

/** Loading / error / empty handling shared by the record-based tabs. */
function RecordGate({
  record,
  onRun,
  running,
  children,
}: {
  record: ReturnType<typeof useRecord>;
  onRun: () => void;
  running: boolean;
  children: (record: BidRecord) => React.ReactNode;
}) {
  if (record.isLoading) return <ListSkeleton rows={8} />;
  if (record.isError) {
    return <ErrorState title="Could not load the record" message={record.error.message} onRetry={() => void record.refetch()} />;
  }
  if (!record.data) {
    return (
      <EmptyState
        title="No extraction yet"
        message="Run the multi-agent extraction to fill the 20 fields with cited values."
        action={
          <Button onClick={onRun} disabled={running}>
            {running ? <Loader2 className="animate-spin" /> : <Play />} Run extraction
          </Button>
        }
      />
    );
  }
  return <>{children(record.data)}</>;
}

function Overview({ record }: { record: BidRecord }) {
  const summary = fieldText(record, F.summary);
  const { open } = useCitationDrawer();
  const openField = (name: string, field: FieldValue) =>
    open({ title: name, bidId: record.bid_id, citations: field.sources, notes: field.notes });

  return (
    <div className="grid grid-cols-3 gap-4">
      <Card className="col-span-2">
        <CardHeader>
          <CardTitle>Bid Summary</CardTitle>
        </CardHeader>
        <CardContent>
          {summary ? (
            <p className="whitespace-pre-wrap text-sm leading-relaxed">{summary}</p>
          ) : (
            <p className="text-sm italic text-muted-foreground">Not found in documents</p>
          )}
          {record.fields[F.summary]?.sources.length ? (
            <Button variant="link" size="sm" className="mt-2 px-0" onClick={() => openField(F.summary, record.fields[F.summary])}>
              View sources ({record.fields[F.summary].sources.length})
            </Button>
          ) : null}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Key facts</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="space-y-3 text-sm">
            {KEY_FACTS.map(({ label, field }) => {
              const value = fieldText(record, field);
              const fv = record.fields[field];
              return (
                <div key={field}>
                  <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</dt>
                  <dd className="mt-0.5 break-words">
                    {value ? (
                      fv?.sources.length ? (
                        <button
                          type="button"
                          className="text-left hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                          onClick={() => openField(field, fv)}
                        >
                          {value}
                        </button>
                      ) : (
                        value
                      )
                    ) : (
                      <span className="italic text-muted-foreground">Not found in documents</span>
                    )}
                  </dd>
                </div>
              );
            })}
          </dl>
        </CardContent>
      </Card>
      <Card className="col-span-3">
        <CardContent className="flex flex-wrap items-center gap-4 p-4 text-sm text-muted-foreground">
          <span>
            Validation: <strong className="text-green-700 dark:text-green-400">{record.validation.passed} passed</strong>,{" "}
            <strong className="text-red-700 dark:text-red-400">{record.validation.failed} failed</strong>,{" "}
            <strong>{record.validation.not_found} not found</strong>
          </span>
          <span>Generated {formatDate(record.generated_at)}</span>
          <Link to={`/runs/${encodeURIComponent(record.run_id)}`} className="font-mono text-xs underline-offset-4 hover:underline">
            run {record.run_id}
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}

function AddendumTimeline({ bidId, changes }: { bidId: string; changes: AddendumChange[] }) {
  const { open } = useCitationDrawer();
  if (changes.length === 0) {
    return <EmptyState title="No addendum changes" message="No addendum overrode, clarified or added a field value." />;
  }
  const sorted = [...changes].sort((a, b) => a.addendum_number - b.addendum_number);
  return (
    <ol className="relative space-y-4 border-l pl-6">
      {sorted.map((c, i) => (
        <li key={`${c.field}-${c.addendum_number}-${i}`} className="relative">
          <span className="absolute -left-[31px] top-1 flex h-5 w-5 items-center justify-center rounded-full bg-primary text-[10px] font-bold text-primary-foreground">
            {c.addendum_number}
          </span>
          <Card>
            <CardContent className="space-y-2 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{c.field}</span>
                <Badge variant="secondary">{c.kind}</Badge>
                <span className="text-xs text-muted-foreground">Addendum {c.addendum_number}</span>
              </div>
              <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 text-sm">
                <div className="rounded-md bg-muted p-2 line-through decoration-muted-foreground/60">
                  {c.old_value ?? <span className="italic text-muted-foreground">(none)</span>}
                </div>
                <ArrowRight className="h-4 w-4 text-muted-foreground" />
                <div className="rounded-md border border-primary/40 bg-accent/40 p-2">{c.new_value}</div>
              </div>
              <CitationChip
                citation={c.source}
                onClick={() => open({ title: `${c.field} (Addendum ${c.addendum_number})`, bidId, citations: [c.source] })}
              />
            </CardContent>
          </Card>
        </li>
      ))}
    </ol>
  );
}

function DocumentsTable({ documents }: { documents: DocumentSummary[] }) {
  if (documents.length === 0) {
    return <EmptyState title="No documents" message="This bid folder has no parsed files." />;
  }
  return (
    <Card>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>File</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Addendum</TableHead>
              <TableHead className="text-right">Pages</TableHead>
              <TableHead className="text-right">Tables</TableHead>
              <TableHead>Warnings</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {documents.map((d) => (
              <TableRow key={d.file_name}>
                <TableCell className="font-mono text-xs">{d.file_name}</TableCell>
                <TableCell><Badge variant="secondary">{docTypeLabel(d.doc_type)}</Badge></TableCell>
                <TableCell>{d.addendum_number ?? "-"}</TableCell>
                <TableCell className="text-right tabular-nums">{d.pages}</TableCell>
                <TableCell className="text-right tabular-nums">{d.tables}</TableCell>
                <TableCell>
                  {d.warnings.length === 0 ? (
                    <span className="text-xs text-muted-foreground">none</span>
                  ) : (
                    <ul className="space-y-0.5 text-xs text-amber-700 dark:text-amber-400">
                      {d.warnings.map((w, i) => <li key={i}>{w}</li>)}
                    </ul>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
