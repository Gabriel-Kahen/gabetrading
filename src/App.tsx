import { Component, lazy, Suspense, useEffect, useMemo, useState } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { format } from 'date-fns';
import type { PortfolioSnapshot, Position, Trade, EquityPoint, ClosedPosition } from './types';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
const MOBILE_EXECUTION_PAGE_SIZE = 25;
const CLOSED_POSITIONS_PAGE_SIZE = 10;
const RECENT_TRADES_LIMIT = 250;
const PERFORMANCE_POINT_LIMIT = 1500;
const PRIMARY_REFRESH_INTERVAL_MS = 10_000;
const HISTORY_REFRESH_INTERVAL_MS = 60_000;
const REQUEST_TIMEOUT_MS = 15_000;

const PerformanceChart = lazy(() => import('./PerformanceChart'));

type ClosedPositionSort = 'gainCash' | 'lossCash' | 'gainPercent' | 'lossPercent';
type ChartRange = '1D' | '1W' | '1M' | '3M' | 'ALL';
export type ChartPoint = EquityPoint & {
  timestampMs: number;
  tradingIndex: number;
  fullDate: string;
  spyNormalized: number | null;
};

type DataSection = 'portfolio' | 'holdings' | 'trades' | 'performance' | 'closedPositions';
type LoadStatus = 'loading' | 'ready' | 'stale' | 'error';
type ClosedPositionsPage = {
  items: ClosedPosition[];
  total: number;
  page: number;
  page_size: number;
};

const INITIAL_LOAD_STATUS: Record<DataSection, LoadStatus> = {
  portfolio: 'loading',
  holdings: 'loading',
  trades: 'loading',
  performance: 'loading',
  closedPositions: 'loading',
};

const CHART_RANGES: Array<{ label: ChartRange; durationMs: number | null }> = [
  { label: '1D', durationMs: 24 * 60 * 60 * 1000 },
  { label: '1W', durationMs: 7 * 24 * 60 * 60 * 1000 },
  { label: '1M', durationMs: 30 * 24 * 60 * 60 * 1000 },
  { label: '3M', durationMs: 90 * 24 * 60 * 60 * 1000 },
  { label: 'ALL', durationMs: null },
];

const EASTERN_TIME_FORMATTER = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York',
  weekday: 'short',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

function formatCurrency(val: number) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(val);
}

async function fetchJson<T>(path: string, signal: AbortSignal): Promise<T> {
  const requestController = new AbortController();
  const abortRequest = () => requestController.abort(signal.reason);
  if (signal.aborted) abortRequest();
  else signal.addEventListener('abort', abortRequest, { once: true });

  const timeout = window.setTimeout(
    () => requestController.abort(new DOMException(`${path} timed out`, 'TimeoutError')),
    REQUEST_TIMEOUT_MS,
  );

  try {
    const response = await fetch(`${API_BASE}${path}`, { signal: requestController.signal });
    if (!response.ok) {
      throw new Error(`${path} returned ${response.status}`);
    }
    return await response.json() as T;
  } finally {
    window.clearTimeout(timeout);
    signal.removeEventListener('abort', abortRequest);
  }
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === 'AbortError';
}

function isRegularTradingHours(timestamp: string) {
  const etParts = EASTERN_TIME_FORMATTER.formatToParts(new Date(timestamp));

  const weekday = etParts.find((part) => part.type === 'weekday')?.value;
  const hour = Number(etParts.find((part) => part.type === 'hour')?.value ?? '0');
  const minute = Number(etParts.find((part) => part.type === 'minute')?.value ?? '0');
  const minutesIntoDay = hour * 60 + minute;

  if (weekday === 'Sat' || weekday === 'Sun') {
    return false;
  }

  return minutesIntoDay >= 9 * 60 + 30 && minutesIntoDay <= 16 * 60;
}

function buildChartData(
  points: EquityPoint[],
  showBenchmark: boolean,
  initialSpy: number,
  initialEquity: number,
): ChartPoint[] {
  let latestSpy = initialSpy;
  return points.map((point, index) => {
    if (point.spy_price && point.spy_price > 0) latestSpy = point.spy_price;
    return {
      ...point,
      timestampMs: new Date(point.timestamp).getTime(),
      tradingIndex: index,
      fullDate: format(new Date(point.timestamp), 'MMM d, yyyy HH:mm'),
      spyNormalized: showBenchmark ? (latestSpy / initialSpy) * initialEquity : null,
    };
  });
}

function hasUsableData(status: LoadStatus) {
  return status === 'ready' || status === 'stale';
}

class ChartErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Failed to render performance chart:', error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex h-full items-center justify-center font-mono text-sm text-[#525252]">
          PERFORMANCE CHART UNAVAILABLE
        </div>
      );
    }
    return this.props.children;
  }
}

export default function App() {
  const [portfolio, setPortfolio] = useState<PortfolioSnapshot | null>(null);
  const [holdings, setHoldings] = useState<Position[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [closedPositions, setClosedPositions] = useState<ClosedPosition[]>([]);
  const [closedPositionsTotal, setClosedPositionsTotal] = useState(0);
  const [performance, setPerformance] = useState<EquityPoint[]>([]);
  const [loadedChartRange, setLoadedChartRange] = useState<ChartRange | null>(null);
  const [loadStatus, setLoadStatus] = useState(INITIAL_LOAD_STATUS);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);

  const [showBenchmark, setShowBenchmark] = useState(false);
  const [showExecutionLog, setShowExecutionLog] = useState(false);
  const [chartRange, setChartRange] = useState<ChartRange>('ALL');
  const [mobileExecutionPage, setMobileExecutionPage] = useState(1);
  const [closedPositionSort, setClosedPositionSort] = useState<ClosedPositionSort>('gainPercent');
  const [closedPositionsPage, setClosedPositionsPage] = useState(1);

  useEffect(() => {
    let stopped = false;
    let refreshTimer: number | undefined;
    let activeController: AbortController | null = null;
    const loadSection = async <T,>(
      section: DataSection,
      path: string,
      setter: (value: T) => void,
      signal: AbortSignal,
    ) => {
      try {
        const data = await fetchJson<T>(path, signal);
        if (stopped) return false;
        setter(data);
        setLoadStatus((current) => ({ ...current, [section]: 'ready' }));
        return true;
      } catch (error) {
        if (stopped || isAbortError(error)) return false;
        console.error(`Failed to load ${section}:`, error);
        setLoadStatus((current) => ({
          ...current,
          [section]: hasUsableData(current[section]) ? 'stale' : 'error',
        }));
        return false;
      }
    };

    const refresh = async () => {
      activeController?.abort();
      activeController = new AbortController();
      const { signal } = activeController;
      const results = await Promise.all([
        loadSection<PortfolioSnapshot>('portfolio', '/portfolio', setPortfolio, signal),
        loadSection<Position[]>('holdings', '/holdings', setHoldings, signal),
        loadSection<Trade[]>('trades', `/trades?limit=${RECENT_TRADES_LIMIT}`, setTrades, signal),
        loadSection<EquityPoint[]>(
          'performance',
          `/performance?range=${chartRange}&max_points=${PERFORMANCE_POINT_LIMIT}`,
          (points) => {
            setPerformance(points);
            setLoadedChartRange(chartRange);
          },
          signal,
        ),
      ]);

      if (stopped) return;
      if (results.some(Boolean)) setLastUpdatedAt(new Date());
      if (!document.hidden) {
        refreshTimer = window.setTimeout(refresh, PRIMARY_REFRESH_INTERVAL_MS);
      }
    };

    const handleVisibilityChange = () => {
      if (document.hidden) {
        if (refreshTimer !== undefined) window.clearTimeout(refreshTimer);
        activeController?.abort();
        return;
      }
      if (refreshTimer !== undefined) window.clearTimeout(refreshTimer);
      void refresh();
    };

    void refresh();
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      stopped = true;
      if (refreshTimer !== undefined) window.clearTimeout(refreshTimer);
      activeController?.abort();
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [chartRange]);

  useEffect(() => {
    const controller = new AbortController();
    let stopped = false;
    let refreshTimer: number | undefined;

    const loadClosedPositions = async () => {
      try {
        const params = new URLSearchParams({
          sort: closedPositionSort,
          page: String(closedPositionsPage),
          page_size: String(CLOSED_POSITIONS_PAGE_SIZE),
        });
        const data = await fetchJson<ClosedPositionsPage>(`/closed-positions/page?${params}`, controller.signal);
        if (stopped) return;
        setClosedPositions(data.items);
        setClosedPositionsTotal(data.total);
        setLoadStatus((current) => ({ ...current, closedPositions: 'ready' }));
        refreshTimer = window.setTimeout(loadClosedPositions, HISTORY_REFRESH_INTERVAL_MS);
      } catch (error) {
        if (stopped || isAbortError(error)) return;
        console.error('Failed to load closed positions:', error);
        setLoadStatus((current) => ({
          ...current,
          closedPositions: hasUsableData(current.closedPositions) ? 'stale' : 'error',
        }));
        refreshTimer = window.setTimeout(loadClosedPositions, HISTORY_REFRESH_INTERVAL_MS);
      }
    };

    void loadClosedPositions();
    return () => {
      stopped = true;
      if (refreshTimer !== undefined) window.clearTimeout(refreshTimer);
      controller.abort();
    };
  }, [closedPositionSort, closedPositionsPage]);

  const regularHoursPerformance = useMemo(
    () => performance.filter((pt) => isRegularTradingHours(pt.timestamp)),
    [performance],
  );
  const selectedRange = CHART_RANGES.find((range) => range.label === chartRange) ?? CHART_RANGES[CHART_RANGES.length - 1];
  const latestChartTimestamp = regularHoursPerformance.at(-1)
    ? new Date(regularHoursPerformance.at(-1)!.timestamp).getTime()
    : 0;
  const chartPerformance = selectedRange.durationMs && latestChartTimestamp
    ? regularHoursPerformance.filter((pt) => new Date(pt.timestamp).getTime() >= latestChartTimestamp - selectedRange.durationMs!)
    : regularHoursPerformance;
  const chartPerformanceWithBenchmark = chartPerformance.filter((pt) => pt.spy_price && pt.spy_price > 0);
  const initialEquity = chartPerformance[0]?.equity || performance[0]?.equity || 1000000;
  const initialSpy = chartPerformanceWithBenchmark[0]?.spy_price || 1;
  const chartData = buildChartData(chartPerformance, showBenchmark, initialSpy, initialEquity);

  const desiredTickCount = 6;
  const tickStep = Math.max(1, Math.ceil(chartData.length / desiredTickCount));
  const xAxisTicks = chartData
    .filter((_, index) => index % tickStep === 0)
    .map((pt) => pt.tradingIndex);
  const lastTick = chartData.at(-1)?.tradingIndex;
  if (lastTick !== undefined && !xAxisTicks.includes(lastTick)) {
    xAxisTicks.push(lastTick);
  }
  const chartPointsByIndex = new Map(chartData.map((pt) => [pt.tradingIndex, pt]));
  const spansMultipleYears = new Set(
    chartData.map((pt) => new Date(pt.timestamp).getFullYear())
  ).size > 1;
  const spansMultipleDays = chartData.length > 0 && (
    format(new Date(chartData[0].timestamp), 'yyyy-MM-dd') !== format(new Date(chartData.at(-1)!.timestamp), 'yyyy-MM-dd')
  );
  const mobileExecutionPageCount = Math.max(1, Math.ceil(trades.length / MOBILE_EXECUTION_PAGE_SIZE));
  const currentMobileExecutionPage = Math.min(mobileExecutionPage, mobileExecutionPageCount);
  const mobileExecutionTrades = trades.slice(
    (currentMobileExecutionPage - 1) * MOBILE_EXECUTION_PAGE_SIZE,
    currentMobileExecutionPage * MOBILE_EXECUTION_PAGE_SIZE,
  );
  const closedPositionsPageCount = Math.max(1, Math.ceil(closedPositionsTotal / CLOSED_POSITIONS_PAGE_SIZE));
  const currentClosedPositionsPage = Math.min(closedPositionsPage, closedPositionsPageCount);
  const paginatedClosedPositions = closedPositions;
  const criticalDataReady = hasUsableData(loadStatus.portfolio) && hasUsableData(loadStatus.holdings);
  const hasLoadError = Object.values(loadStatus).some((status) => status === 'error' || status === 'stale');

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-[#d4d4d4] font-sans p-4 sm:p-8 selection:bg-[#262626]">
      <div className="max-w-[1600px] mx-auto space-y-8">
        
        {/* Header Section */}
        <header className="flex flex-col lg:flex-row lg:items-end justify-between gap-6 pb-6 border-b border-[#262626]">
          <div>
            <h1 className="text-3xl font-medium text-[#ededed] tracking-tight">GABE<span className="text-[#3b82f6]">TRADING</span></h1>
            <p className="text-[11px] text-[#737373] mt-2 uppercase tracking-[0.2em] font-mono">Autonomous S&P 500 Simulation Engine</p>
            <div className="mt-3 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.18em] text-[#737373]" aria-live="polite">
              <span className={`h-1.5 w-1.5 rounded-full ${hasLoadError ? 'bg-[#f59e0b]' : criticalDataReady ? 'bg-[#10b981]' : 'animate-pulse bg-[#3b82f6]'}`} />
              <span>{hasLoadError ? 'Partial data' : criticalDataReady ? 'Live' : 'Connecting'}</span>
              {lastUpdatedAt && criticalDataReady && (
                <span className="text-[#404040]">· {format(lastUpdatedAt, 'HH:mm:ss')}</span>
              )}
            </div>
            <a
              href="/old/"
              className="mt-3 inline-block font-mono text-[10px] uppercase tracking-[0.2em] text-[#404040] transition-colors hover:text-[#737373]"
            >
              old
            </a>
          </div>
          
          {hasUsableData(loadStatus.portfolio) && portfolio ? (
            <div className="grid grid-cols-2 gap-4 font-mono sm:flex sm:flex-wrap sm:gap-8">
              <div className="flex flex-col">
                <span className="text-[#737373] text-[10px] uppercase tracking-wider mb-1">Total Equity</span>
                <span className="text-xl sm:text-2xl text-[#ededed]">{formatCurrency(portfolio.equity)}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[#737373] text-[10px] uppercase tracking-wider mb-1">Cash Balance</span>
                <span className="text-xl sm:text-2xl text-[#ededed]">{formatCurrency(portfolio.cash)}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[#737373] text-[10px] uppercase tracking-wider mb-1">Net Exposure</span>
                <span className="text-xl sm:text-2xl text-[#ededed]">{formatCurrency(portfolio.net_exposure)}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[#737373] text-[10px] uppercase tracking-wider mb-1">Open Pos</span>
                <span className="text-xl sm:text-2xl text-[#ededed]">{portfolio.holdings_count}</span>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-4 font-mono sm:flex sm:gap-8" aria-label="Loading portfolio summary">
              {['Total Equity', 'Cash Balance', 'Net Exposure', 'Open Pos'].map((label) => (
                <div key={label} className="flex min-w-28 flex-col">
                  <span className="mb-2 text-[10px] uppercase tracking-wider text-[#737373]">{label}</span>
                  <span className={`h-6 rounded-sm ${loadStatus.portfolio === 'error' ? 'bg-[#2a1717]' : 'animate-pulse bg-[#1f1f1f]'}`} />
                </div>
              ))}
            </div>
          )}
        </header>

        {/* Main Content Layout */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-8 xl:h-[calc(100vh-5rem)] xl:min-h-[940px]">
          
          {/* Left Column: Chart & Trades */}
          <div className="xl:col-span-2 flex flex-col gap-8 h-full min-h-0">
            
            {/* Chart Container */}
            <div className="bg-[#121212] border border-[#262626] p-5 rounded-sm shrink-0">
              <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <h2 className="text-sm font-mono text-[#a3a3a3] uppercase tracking-wider">Performance Curve</h2>
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-end">
                  <div className="grid grid-cols-5 overflow-hidden rounded-sm border border-[#262626] bg-[#0f0f0f] font-mono text-[10px] uppercase tracking-wider text-[#737373]">
                    {CHART_RANGES.map((range) => (
                      <button
                        key={range.label}
                        type="button"
                        onClick={() => setChartRange(range.label)}
                        className={`px-3 py-2 transition-colors hover:bg-[#171717] hover:text-[#d4d4d4] ${
                          chartRange === range.label ? 'bg-[#1f2937] text-[#ededed]' : ''
                        }`}
                      >
                        {range.label}
                      </button>
                    ))}
                  </div>
                  <label className="flex items-center cursor-pointer group">
                    <div className="relative">
                      <input 
                        type="checkbox" 
                        className="sr-only" 
                        checked={showBenchmark} 
                        onChange={() => setShowBenchmark(!showBenchmark)} 
                      />
                      <div className={`block w-8 h-4 rounded-full transition-colors ${showBenchmark ? 'bg-[#3b82f6]' : 'bg-[#262626]'}`}></div>
                      <div className={`dot absolute left-1 top-1 bg-[#a3a3a3] group-hover:bg-[#ededed] w-2 h-2 rounded-full transition-transform ${showBenchmark ? 'transform translate-x-4 bg-white' : ''}`}></div>
                    </div>
                    <div className="ml-3 text-[10px] uppercase tracking-wider font-mono text-[#737373] group-hover:text-[#a3a3a3] transition-colors">
                      S&P 500 OVERLAY
                    </div>
                  </label>
                </div>
              </div>
              <div className="h-[360px] min-w-0 w-full">
                {hasUsableData(loadStatus.performance) && loadedChartRange === chartRange && chartData.length > 0 ? (
                  <ChartErrorBoundary>
                    <Suspense fallback={<div className="flex h-full items-center justify-center font-mono text-sm text-[#525252]">PREPARING CHART...</div>}>
                      <PerformanceChart
                        chartData={chartData}
                        chartPointsByIndex={chartPointsByIndex}
                        showBenchmark={showBenchmark}
                        spansMultipleDays={spansMultipleDays}
                        spansMultipleYears={spansMultipleYears}
                        xAxisTicks={xAxisTicks}
                      />
                    </Suspense>
                  </ChartErrorBoundary>
                ) : (
                  <div className="flex h-full items-center justify-center text-[#525252] font-mono text-sm">
                    {loadStatus.performance === 'error' ? 'PERFORMANCE DATA UNAVAILABLE' : loadedChartRange !== chartRange || loadStatus.performance === 'loading' ? 'LOADING PERFORMANCE...' : 'AWAITING DATA...'}
                  </div>
                )}
              </div>
            </div>

            {/* Trades Table */}
            <div className="hidden rounded-sm border border-[#262626] bg-[#121212] md:flex md:flex-col flex-1 min-h-0">
              <div className="flex items-center justify-between gap-4 border-b border-[#262626] p-4">
                <div className="flex items-center gap-3">
                  <h2 className="text-sm font-mono text-[#a3a3a3] uppercase tracking-wider">Execution Log</h2>
                  <span className="text-[10px] font-mono uppercase tracking-wider text-[#737373]">{trades.length} recent</span>
                </div>
              </div>
              <div className="flex-1 overflow-auto hidden md:block min-h-0">
                <table className="w-full text-sm text-left">
                  <thead className="text-[10px] uppercase tracking-wider text-[#737373] bg-[#1a1a1a] sticky top-0 z-10 shadow-sm">
                    <tr>
                      <th className="px-5 py-3 font-medium">Time</th>
                      <th className="px-5 py-3 font-medium">Action</th>
                      <th className="px-5 py-3 font-medium">Symbol</th>
                      <th className="px-5 py-3 font-medium text-right">Qty</th>
                      <th className="px-5 py-3 font-medium text-right">Price</th>
                      <th className="px-5 py-3 font-medium">Driver</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#262626] font-mono">
                    {!hasUsableData(loadStatus.trades) ? (
                      <tr>
                        <td colSpan={6} className="px-5 py-8 text-center text-[#525252]">
                          {loadStatus.trades === 'error' ? 'Execution data unavailable.' : 'Loading recent executions...'}
                        </td>
                      </tr>
                    ) : trades.length === 0 && (
                      <tr>
                        <td colSpan={6} className="px-5 py-8 text-center text-[#525252]">No executions recorded.</td>
                      </tr>
                    )}
                    {trades.map((t, i) => {
                      const isBuy = t.side === 'buy' || t.side === 'cover';
                      const driverText = t.explanation || t.rationale;
                      return (
                        <tr key={i} className="hover:bg-[#1a1a1a] transition-colors">
                          <td className="px-5 py-4 whitespace-nowrap">
                            <div className="text-[#737373]">{format(new Date(t.timestamp), 'HH:mm:ss')}</div>
                            <div className="text-[10px] text-[#525252] mt-0.5">{format(new Date(t.timestamp), 'MM/dd/yy')}</div>
                          </td>
                          <td className="px-5 py-4">
                            <span className={`px-2 py-0.5 text-[10px] uppercase tracking-wider font-bold rounded-sm ${isBuy ? 'bg-[#052e16] text-[#10b981]' : 'bg-[#4c0519] text-[#f43f5e]'}`}>
                              {t.side}
                            </span>
                          </td>
                          <td className="px-5 py-4 text-[#ededed] font-medium">{t.symbol}</td>
                          <td className="px-5 py-4 text-right text-[#a3a3a3]">{t.quantity.toFixed(2)}</td>
                          <td className="px-5 py-4 text-right text-[#a3a3a3]">{formatCurrency(t.price)}</td>
                          <td className="px-5 py-4 text-xs text-[#a3a3a3] leading-relaxed">
                            <div className="group relative max-w-sm">
                              <span className="block truncate border-b border-dotted border-transparent transition-colors group-hover:border-[#525252]">
                                {driverText}
                              </span>
                              <div className="pointer-events-none absolute left-0 top-full z-20 mt-2 hidden w-[26rem] rounded-sm border border-[#262626] bg-[#090909] p-3 text-[11px] leading-5 text-[#d4d4d4] shadow-[0_12px_32px_rgba(0,0,0,0.45)] group-hover:block">
                                {driverText}
                              </div>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

          </div>

          {/* Right Column: Holdings */}
          <div className="bg-[#121212] border border-[#262626] rounded-sm flex flex-col h-full min-h-0">
            <div className="p-4 border-b border-[#262626] flex justify-between items-center shrink-0">
              <h2 className="text-sm font-mono text-[#a3a3a3] uppercase tracking-wider">Book</h2>
              <span className="text-xs font-mono text-[#737373]">{hasUsableData(loadStatus.holdings) ? holdings.length : '—'} POS</span>
            </div>
            <div className="overflow-auto flex-1">
              {/* Desktop Table */}
              <table className="w-full text-sm text-left hidden md:table">
                <thead className="text-[10px] uppercase tracking-wider text-[#737373] bg-[#1a1a1a] sticky top-0 z-10 shadow-sm">
                  <tr>
                    <th className="px-4 py-3 font-medium">Sym</th>
                    <th className="px-4 py-3 font-medium text-right">Size</th>
                    <th className="px-4 py-3 font-medium text-right">Price</th>
                    <th className="px-4 py-3 font-medium text-right">PnL</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#262626] font-mono">
                  {!hasUsableData(loadStatus.holdings) ? (
                    <tr>
                      <td colSpan={4} className="px-4 py-8 text-center text-[#525252]">
                        {loadStatus.holdings === 'error' ? 'Book unavailable.' : 'Loading book...'}
                      </td>
                    </tr>
                  ) : holdings.length === 0 && (
                    <tr>
                      <td colSpan={4} className="px-4 py-8 text-center text-[#525252]">Empty book.</td>
                    </tr>
                  )}
                  {holdings.map((h, i) => {
                    const costBasis = h.average_price * Math.abs(h.quantity);
                    const pnlPercent = costBasis > 0 ? (h.unrealized_pnl / costBasis) * 100 : 0;
                    
                    return (
                      <tr key={`${h.symbol}-${i}`} className="hover:bg-[#1a1a1a] transition-colors">
                        <td className="px-4 py-4">
                          <div className="text-[#ededed] font-medium">{h.symbol}</div>
                          <div className={`text-[10px] mt-0.5 ${h.direction === 'long' ? 'text-[#10b981]' : 'text-[#f43f5e]'}`}>
                            {h.direction.toUpperCase()}
                          </div>
                        </td>
                        <td className="px-4 py-4 text-right text-[#a3a3a3]">
                          <div>{formatCurrency(h.market_value)}</div>
                          <div className="text-[10px] text-[#737373] mt-0.5">{Math.abs(h.quantity).toFixed(2)} sh</div>
                        </td>
                        <td className="px-4 py-4 text-right text-[#a3a3a3]">
                          <div>{formatCurrency(h.last_price)}</div>
                          <div className="text-[10px] text-[#737373] mt-0.5">Avg {h.average_price.toFixed(2)}</div>
                        </td>
                        <td className={`px-4 py-4 text-right ${h.unrealized_pnl >= 0 ? 'text-[#10b981]' : 'text-[#f43f5e]'}`}>
                          <div>{h.unrealized_pnl > 0 ? '+' : ''}{formatCurrency(h.unrealized_pnl)}</div>
                          <div className="text-[10px] opacity-80 mt-0.5">
                            {pnlPercent > 0 ? '+' : ''}{pnlPercent.toFixed(2)}%
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              {/* Mobile Cards */}
              <div className="md:hidden divide-y divide-[#262626]">
                {!hasUsableData(loadStatus.holdings) ? (
                  <div className="p-8 text-center font-mono text-sm text-[#525252]">
                    {loadStatus.holdings === 'error' ? 'Book unavailable.' : 'Loading book...'}
                  </div>
                ) : holdings.length === 0 && (
                  <div className="p-8 text-center font-mono text-sm text-[#525252]">Empty book.</div>
                )}
                {holdings.map((h, i) => {
                  const costBasis = h.average_price * Math.abs(h.quantity);
                  const pnlPercent = costBasis > 0 ? (h.unrealized_pnl / costBasis) * 100 : 0;
                  
                  return (
                    <div key={`${h.symbol}-${i}-mobile`} className="p-4 font-mono">
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <span className="text-lg font-medium text-[#ededed]">{h.symbol}</span>
                          <span className={`px-2 py-0.5 text-[10px] uppercase tracking-wider font-bold rounded-sm ${h.direction === 'long' ? 'bg-[#052e16] text-[#10b981]' : 'bg-[#4c0519] text-[#f43f5e]'}`}>
                            {h.direction.toUpperCase()}
                          </span>
                        </div>
                        <div className={`text-right ${h.unrealized_pnl >= 0 ? 'text-[#10b981]' : 'text-[#f43f5e]'}`}>
                          <div className="text-sm font-medium">{h.unrealized_pnl > 0 ? '+' : ''}{formatCurrency(h.unrealized_pnl)}</div>
                          <div className="text-xs mt-0.5">{pnlPercent > 0 ? '+' : ''}{pnlPercent.toFixed(2)}%</div>
                        </div>
                      </div>
                      
                      <div className="flex justify-between text-xs text-[#a3a3a3] mt-4 pt-3 border-t border-[#262626] border-dashed">
                        <div className="flex flex-col">
                          <span className="text-[#737373] text-[10px] uppercase tracking-wider mb-0.5">Size</span> 
                          <span>{Math.abs(h.quantity).toFixed(2)}</span>
                        </div>
                        <div className="flex flex-col text-right">
                          <span className="text-[#737373] text-[10px] uppercase tracking-wider mb-0.5">Avg Price</span> 
                          <span>{formatCurrency(h.average_price)}</span>
                        </div>
                        <div className="flex flex-col text-right">
                          <span className="text-[#737373] text-[10px] uppercase tracking-wider mb-0.5">Last Price</span> 
                          <span>{formatCurrency(h.last_price)}</span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          <div className="rounded-sm border border-[#262626] bg-[#121212] flex flex-col md:hidden">
            <button
              type="button"
              onClick={() => {
                setMobileExecutionPage(1);
                setShowExecutionLog((value) => !value);
              }}
              className="flex items-center justify-between gap-4 border-b border-[#262626] p-4 text-left transition-colors hover:bg-[#171717]"
            >
              <div className="flex items-center gap-3">
                <h2 className="text-sm font-mono text-[#a3a3a3] uppercase tracking-wider">Execution Log</h2>
                <span className="text-[10px] font-mono uppercase tracking-wider text-[#737373]">{trades.length} recent</span>
              </div>
              <span className="font-mono text-[10px] uppercase tracking-wider text-[#737373]">
                {showExecutionLog ? 'Hide' : 'Show'}
              </span>
            </button>
            {showExecutionLog && (
              <div className="divide-y divide-[#262626]">
                {!hasUsableData(loadStatus.trades) ? (
                  <div className="px-5 py-8 text-center font-mono text-sm text-[#525252]">
                    {loadStatus.trades === 'error' ? 'Execution data unavailable.' : 'Loading recent executions...'}
                  </div>
                ) : trades.length === 0 && (
                  <div className="px-5 py-8 text-center font-mono text-sm text-[#525252]">No executions recorded.</div>
                )}
                {mobileExecutionTrades.map((t, i) => {
                  const isBuy = t.side === 'buy' || t.side === 'cover';
                  const driverText = t.explanation || t.rationale;
                  return (
                    <details key={`${currentMobileExecutionPage}-${i}`} className="group px-4 py-4">
                      <summary className="list-none cursor-pointer">
                        <div className="flex items-start justify-between gap-4">
                          <div className="min-w-0 space-y-2">
                            <div className="flex items-center gap-3">
                              <span className={`px-2 py-0.5 text-[10px] uppercase tracking-wider font-bold rounded-sm ${isBuy ? 'bg-[#052e16] text-[#10b981]' : 'bg-[#4c0519] text-[#f43f5e]'}`}>
                                {t.side}
                              </span>
                              <span className="font-mono text-lg font-medium text-[#ededed]">{t.symbol}</span>
                            </div>
                            <div className="font-mono text-[11px] text-[#737373]">
                              {format(new Date(t.timestamp), 'MM/dd/yy')} <span className="opacity-50 mx-1">•</span> {format(new Date(t.timestamp), 'HH:mm:ss')}
                            </div>
                          </div>
                          <div className="shrink-0 text-right font-mono">
                            <div className="text-sm text-[#ededed]">{formatCurrency(t.price)}</div>
                            <div className="text-xs text-[#737373]">{t.quantity.toFixed(2)} sh</div>
                          </div>
                        </div>
                        <div className="mt-3 flex items-center justify-between gap-3">
                          <p className="min-w-0 flex-1 truncate font-mono text-xs leading-relaxed text-[#a3a3a3]">
                            {driverText}
                          </p>
                          <span className="shrink-0 font-mono text-[10px] uppercase tracking-wider text-[#737373] transition-colors group-open:text-[#a3a3a3]">
                            Tap to expand
                          </span>
                        </div>
                      </summary>
                      <div className="mt-3 rounded-sm border border-[#262626] bg-[#090909] p-3 font-mono text-xs leading-6 text-[#d4d4d4]">
                        {driverText}
                      </div>
                    </details>
                  );
                })}
                {trades.length > MOBILE_EXECUTION_PAGE_SIZE && (
                  <div className="flex items-center justify-between gap-4 border-t border-[#262626] px-4 py-3 font-mono text-[10px] uppercase tracking-wider text-[#737373]">
                    <button
                      type="button"
                      onClick={() => setMobileExecutionPage((page) => Math.max(1, page - 1))}
                      disabled={currentMobileExecutionPage === 1}
                      className="rounded-sm border border-[#262626] px-3 py-2 transition-colors enabled:hover:bg-[#171717] disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      Newer
                    </button>
                    <span>
                      Page {currentMobileExecutionPage} / {mobileExecutionPageCount}
                    </span>
                    <button
                      type="button"
                      onClick={() => setMobileExecutionPage((page) => Math.min(mobileExecutionPageCount, page + 1))}
                      disabled={currentMobileExecutionPage === mobileExecutionPageCount}
                      className="rounded-sm border border-[#262626] px-3 py-2 transition-colors enabled:hover:bg-[#171717] disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      Older
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>

        </div>

        <div className="rounded-sm border border-[#262626] bg-[#121212]">
          <div className="flex flex-col gap-4 border-b border-[#262626] p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3">
              <h2 className="text-sm font-mono text-[#a3a3a3] uppercase tracking-wider">Closed Positions</h2>
              <span className="text-[10px] font-mono uppercase tracking-wider text-[#737373]">{closedPositionsTotal} closed</span>
            </div>
            <label className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-wider text-[#737373]">
              <span>Sort</span>
              <select
                value={closedPositionSort}
                onChange={(event) => {
                  setClosedPositions([]);
                  setLoadStatus((current) => ({ ...current, closedPositions: 'loading' }));
                  setClosedPositionsPage(1);
                  setClosedPositionSort(event.target.value as ClosedPositionSort);
                }}
                className="rounded-sm border border-[#262626] bg-[#0f0f0f] px-3 py-2 text-[#d4d4d4] outline-none transition-colors hover:border-[#404040]"
              >
                <option value="gainPercent">Biggest Gain (%)</option>
                <option value="lossPercent">Biggest Loss (%)</option>
                <option value="gainCash">Biggest Gain ($)</option>
                <option value="lossCash">Biggest Loss ($)</option>
              </select>
            </label>
          </div>
          <div className="overflow-auto">
            <table className="hidden min-w-full text-left text-sm md:table">
              <thead className="sticky top-0 z-10 bg-[#1a1a1a] text-[10px] uppercase tracking-wider text-[#737373] shadow-sm">
                <tr>
                  <th className="px-4 py-3 font-medium">Symbol</th>
                  <th className="px-4 py-3 font-medium">Opened</th>
                  <th className="px-4 py-3 font-medium">Closed</th>
                  <th className="px-4 py-3 font-medium text-right">Qty</th>
                  <th className="px-4 py-3 font-medium text-right">Entry</th>
                  <th className="px-4 py-3 font-medium text-right">Exit</th>
                  <th className="px-4 py-3 font-medium text-right">P&amp;L</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#262626] font-mono">
                {!hasUsableData(loadStatus.closedPositions) ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-[#525252]">
                      {loadStatus.closedPositions === 'error' ? 'Closed positions unavailable.' : 'Loading closed positions...'}
                    </td>
                  </tr>
                ) : closedPositionsTotal === 0 && (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-[#525252]">No closed positions yet.</td>
                  </tr>
                )}
                {paginatedClosedPositions.map((position, index) => (
                  <tr key={`${position.symbol}-${position.closed_at}-${index}`} className="transition-colors hover:bg-[#1a1a1a]">
                    <td className="px-4 py-4">
                      <div className="font-medium text-[#ededed]">{position.symbol}</div>
                      <div className={`mt-0.5 text-[10px] ${position.direction === 'long' ? 'text-[#10b981]' : 'text-[#f43f5e]'}`}>
                        {position.direction.toUpperCase()}
                      </div>
                    </td>
                    <td className="px-4 py-4 text-[#a3a3a3]">{format(new Date(position.opened_at), 'MM/dd/yy HH:mm')}</td>
                    <td className="px-4 py-4 text-[#a3a3a3]">{format(new Date(position.closed_at), 'MM/dd/yy HH:mm')}</td>
                    <td className="px-4 py-4 text-right text-[#a3a3a3]">{position.quantity.toFixed(2)}</td>
                    <td className="px-4 py-4 text-right text-[#a3a3a3]">{formatCurrency(position.average_entry_price)}</td>
                    <td className="px-4 py-4 text-right text-[#a3a3a3]">{formatCurrency(position.average_exit_price)}</td>
                    <td className={`px-4 py-4 text-right ${position.realized_pnl >= 0 ? 'text-[#10b981]' : 'text-[#f43f5e]'}`}>
                      <div>{position.realized_pnl > 0 ? '+' : ''}{formatCurrency(position.realized_pnl)}</div>
                      <div className="mt-0.5 text-[10px] opacity-80">{position.realized_return_pct > 0 ? '+' : ''}{position.realized_return_pct.toFixed(2)}%</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="divide-y divide-[#262626] md:hidden">
              {!hasUsableData(loadStatus.closedPositions) ? (
                <div className="px-4 py-8 text-center font-mono text-sm text-[#525252]">
                  {loadStatus.closedPositions === 'error' ? 'Closed positions unavailable.' : 'Loading closed positions...'}
                </div>
              ) : closedPositionsTotal === 0 && (
                <div className="px-4 py-8 text-center font-mono text-sm text-[#525252]">No closed positions yet.</div>
              )}
              {paginatedClosedPositions.map((position, index) => (
                <div key={`${position.symbol}-${position.closed_at}-${index}-mobile`} className="p-4 font-mono">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-lg font-medium text-[#ededed]">{position.symbol}</span>
                        <span className={`text-[10px] uppercase tracking-wider ${position.direction === 'long' ? 'text-[#10b981]' : 'text-[#f43f5e]'}`}>
                          {position.direction}
                        </span>
                      </div>
                      <div className="mt-2 text-[11px] text-[#737373]">{format(new Date(position.closed_at), 'MM/dd/yy HH:mm')}</div>
                    </div>
                    <div className={`text-right ${position.realized_pnl >= 0 ? 'text-[#10b981]' : 'text-[#f43f5e]'}`}>
                      <div className="text-sm">{position.realized_pnl > 0 ? '+' : ''}{formatCurrency(position.realized_pnl)}</div>
                      <div className="mt-0.5 text-xs">{position.realized_return_pct > 0 ? '+' : ''}{position.realized_return_pct.toFixed(2)}%</div>
                    </div>
                  </div>
                  <div className="mt-4 grid grid-cols-3 gap-3 border-t border-[#262626] pt-3 text-xs text-[#a3a3a3]">
                    <div>
                      <div className="mb-1 text-[10px] uppercase tracking-wider text-[#737373]">Qty</div>
                      <div>{position.quantity.toFixed(2)}</div>
                    </div>
                    <div className="text-right">
                      <div className="mb-1 text-[10px] uppercase tracking-wider text-[#737373]">Entry</div>
                      <div>{formatCurrency(position.average_entry_price)}</div>
                    </div>
                    <div className="text-right">
                      <div className="mb-1 text-[10px] uppercase tracking-wider text-[#737373]">Exit</div>
                      <div>{formatCurrency(position.average_exit_price)}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            {closedPositionsTotal > CLOSED_POSITIONS_PAGE_SIZE && (
              <div className="flex items-center justify-between gap-4 border-t border-[#262626] px-4 py-3 font-mono text-[10px] uppercase tracking-wider text-[#737373]">
                <button
                  type="button"
                  onClick={() => {
                    setClosedPositions([]);
                    setLoadStatus((current) => ({ ...current, closedPositions: 'loading' }));
                    setClosedPositionsPage((page) => Math.max(1, page - 1));
                  }}
                  disabled={currentClosedPositionsPage === 1}
                  className="rounded-sm border border-[#262626] px-3 py-2 transition-colors enabled:hover:bg-[#171717] disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Prev
                </button>
                <span>
                  Page {currentClosedPositionsPage} / {closedPositionsPageCount}
                </span>
                <button
                  type="button"
                  onClick={() => {
                    setClosedPositions([]);
                    setLoadStatus((current) => ({ ...current, closedPositions: 'loading' }));
                    setClosedPositionsPage((page) => Math.min(closedPositionsPageCount, page + 1));
                  }}
                  disabled={currentClosedPositionsPage === closedPositionsPageCount}
                  className="rounded-sm border border-[#262626] px-3 py-2 transition-colors enabled:hover:bg-[#171717] disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
