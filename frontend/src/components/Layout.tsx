import { NavLink, Outlet, useLocation, useNavigate, useParams } from "react-router-dom";
import { BarChart3, FolderOpen, MessageSquare, Moon, Search, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useBids } from "@/hooks/useBids";
import { useTheme } from "@/hooks/useTheme";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Bids", icon: FolderOpen, end: true },
  { to: "/search", label: "Search", icon: Search, end: false },
  { to: "/ask", label: "Ask", icon: MessageSquare, end: false },
  { to: "/eval", label: "Evaluation", icon: BarChart3, end: false },
];

/** Top-bar bid switcher: navigates to /bids/:bidId. */
function BidSwitcher() {
  const bids = useBids();
  const navigate = useNavigate();
  const { bidId } = useParams<{ bidId: string }>();
  const location = useLocation();
  const items = bids.data ?? [];
  const current = bidId && items.some((b) => b.bid_id === bidId) ? bidId : undefined;

  const onChange = (value: string) => {
    const target = `/bids/${encodeURIComponent(value)}`;
    const onSearch = location.pathname.startsWith("/search");
    navigate(onSearch ? `/search?bid_id=${encodeURIComponent(value)}` : target);
  };

  return (
    <Select value={current ?? ""} onValueChange={onChange} disabled={items.length === 0}>
      <SelectTrigger className="w-56" aria-label="Switch bid">
        <SelectValue placeholder={bids.isLoading ? "Loading bids..." : items.length ? "Switch bid" : "No bids"} />
      </SelectTrigger>
      <SelectContent>
        {items.map((b) => (
          <SelectItem key={b.bid_id} value={b.bid_id}>
            <span className="font-mono">{b.bid_id}</span>
            {b.title ? <span className="text-muted-foreground"> · {b.title}</span> : null}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const label = theme === "dark" ? "Switch to light mode" : "Switch to dark mode";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button variant="ghost" size="icon" onClick={toggle} aria-label={label}>
          {theme === "dark" ? <Sun /> : <Moon />}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

/** App frame: left sidebar + top bar + routed content. */
export function Layout() {
  return (
    <div className="flex min-h-screen min-w-[1024px]">
      <aside className="flex w-56 shrink-0 flex-col border-r bg-card">
        <div className="flex h-14 items-center gap-2 border-b px-4">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-xs font-bold text-primary-foreground">
            R
          </span>
          <span className="font-semibold">RFP Intelligence</span>
        </div>
        <nav className="flex flex-col gap-1 p-3" aria-label="Main">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  isActive ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center justify-between gap-4 border-b bg-card px-6">
          <BidSwitcher />
          <ThemeToggle />
        </header>
        <main className="flex-1 overflow-x-hidden p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
