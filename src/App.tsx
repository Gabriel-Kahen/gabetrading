import { useEffect, useState } from 'react';
import { format } from 'date-fns';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import type { PortfolioSnapshot, Position, Trade, EquityPoint } from './types';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

function formatCurrency(val: number) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(val);
}

function isRegularTradingHours(timestamp: string) {
  const etParts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).formatToParts(new Date(timestamp));

  const weekday = etParts.find((part) => part.type === 'weekday')?.value;
  const hour = Number(etParts.find((part) => part.type === 'hour')?.value ?? '0');
  const minute = Number(etParts.find((part) => part.type === 'minute')?.value ?? '0');
  const minutesIntoDay = hour * 60 + minute;

  if (weekday === 'Sat' || weekday === 'Sun') {
    return false;
  }

  return minutesIntoDay >= 9 * 60 + 30 && minutesIntoDay <= 16 * 60;
}

export default function App() {
  const [portfolio, setPortfolio] = useState<PortfolioSnapshot | null>(null);
  const [holdings, setHoldings] = useState<Position[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [performance, setPerformance] = useState<EquityPoint[]>([]);
  const [loading, setLoading] = useState(true);

  const [showBenchmark, setShowBenchmark] = useState(false);
  const [showExecutionLog, setShowExecutionLog] = useState(() => typeof window !== 'undefined' && window.innerWidth >= 768);

  const fetchData = async () => {
    try {
      const [pf, h, t, p] = await Promise.all([
        fetch(`${API_BASE}/portfolio`).then((res) => res.json()),
        fetch(`${API_BASE}/holdings`).then((res) => res.json()),
        fetch(`${API_BASE}/trades`).then((res) => res.json()),
        fetch(`${API_BASE}/performance`).then((res) => res.json()),
      ]);
      setPortfolio(pf);
      setHoldings(h);
      setTrades(t);
      setPerformance(p);
    } catch (err) {
      console.error('Failed to fetch data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10_000); // 10s auto refresh
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#0a0a0a] text-[#a3a3a3] font-mono text-sm tracking-widest">
        INITIALIZING TERMINAL...
      </div>
    );
  }

  const chartPerformance = performance.filter((pt) => isRegularTradingHours(pt.timestamp));
  const initialEquity = chartPerformance[0]?.equity || performance[0]?.equity || 1000000;
  const initialSpy = chartPerformance.find(pt => pt.spy_price && pt.spy_price > 0)?.spy_price || 1;

  const chartData = chartPerformance.map((pt) => ({
    ...pt,
    timestampMs: new Date(pt.timestamp).getTime(),
    fullDate: format(new Date(pt.timestamp), 'MMM d, yyyy HH:mm'),
    spyNormalized: (pt.spy_price && pt.spy_price > 0 && showBenchmark) 
      ? (pt.spy_price / initialSpy) * initialEquity 
      : null,
  }));

  const dayTicks: number[] = [];
  const seenDays = new Set<string>();
  
  chartData.forEach((pt) => {
    const dayStr = format(new Date(pt.timestamp), 'yyyy-MM-dd');
    if (!seenDays.has(dayStr)) {
      seenDays.add(dayStr);
      dayTicks.push(pt.timestampMs); // Use actual data timestamp for categorical ticks
    }
  });

  const tickStep = Math.max(1, Math.ceil(dayTicks.length / 6));
  const xAxisTicks = dayTicks.filter((_, index) => index % tickStep === 0);
  const lastTick = dayTicks[dayTicks.length - 1];

  if (lastTick !== undefined && !xAxisTicks.includes(lastTick)) {
    xAxisTicks.push(lastTick);
  }

  const spansMultipleYears = new Set(
    chartData.map((pt) => new Date(pt.timestamp).getFullYear())
  ).size > 1;

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-[#d4d4d4] font-sans p-4 sm:p-8 selection:bg-[#262626]">
      <div className="max-w-[1600px] mx-auto space-y-8">
        
        {/* Header Section */}
        <header className="flex flex-col lg:flex-row lg:items-end justify-between gap-6 pb-6 border-b border-[#262626]">
          <div>
            <h1 className="text-3xl font-medium text-[#ededed] tracking-tight">GABE<span className="text-[#3b82f6]">TRADING</span></h1>
            <p className="text-[11px] text-[#737373] mt-2 uppercase tracking-[0.2em] font-mono">Autonomous S&P 500 Simulation Engine</p>
            <a
              href="/old/"
              className="mt-3 inline-block font-mono text-[10px] uppercase tracking-[0.2em] text-[#404040] transition-colors hover:text-[#737373]"
            >
              old
            </a>
          </div>
          
          {portfolio && (
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
          )}
        </header>

        {/* Main Content Layout */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-8 xl:h-[calc(100vh-10rem)] xl:min-h-[820px]">
          
          {/* Left Column: Chart & Trades */}
          <div className="xl:col-span-2 flex flex-col gap-8 h-full min-h-0">
            
            {/* Chart Container */}
            <div className="bg-[#121212] border border-[#262626] p-5 rounded-sm shrink-0">
              <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <h2 className="text-sm font-mono text-[#a3a3a3] uppercase tracking-wider">Performance Curve</h2>
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
              <div className="h-[360px] w-full">
                {chartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={chartData} margin={{ top: 5, right: 5, left: -20, bottom: 25 }}>
                      <defs>
                        <linearGradient id="colorEquity" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
                          <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="2 4" stroke="#262626" vertical={false} />
                      <XAxis 
                        dataKey="timestampMs"
                        ticks={xAxisTicks}
                        stroke="#525252" 
                        fontSize={11} 
                        fontFamily="monospace"
                        tickFormatter={(value) =>
                          format(new Date(value), spansMultipleYears ? 'MMM d, yy' : 'MMM d')
                        }
                        tickLine={false}
                        axisLine={false}
                        dy={15}
                      />
                      <YAxis 
                        domain={['auto', 'auto']} 
                        stroke="#525252" 
                        fontSize={11}
                        fontFamily="monospace"
                        tickFormatter={(val) => `$${(val / 1000).toFixed(0)}k`}
                        tickLine={false}
                        axisLine={false}
                        width={80}
                        dx={-10}
                      />
                      <Tooltip 
                        contentStyle={{ backgroundColor: '#0a0a0a', border: '1px solid #262626', borderRadius: '2px', fontFamily: 'monospace', fontSize: '12px' }}
                        itemStyle={{ color: '#ededed' }}
                        labelStyle={{ color: '#737373', marginBottom: '6px' }}
                        formatter={(val: any, name: any) => [
                          formatCurrency(Number(val)), 
                          name === 'equity' ? 'Equity' : 'SPY (Norm)'
                        ]}
                        labelFormatter={(label, payload) => payload?.[0]?.payload?.fullDate || label}
                      />
                      <Area 
                        type="monotone" 
                        dataKey="equity" 
                        stroke="#3b82f6" 
                        strokeWidth={2} 
                        fillOpacity={1} 
                        fill="url(#colorEquity)" 
                        isAnimationActive={false}
                      />
                      {showBenchmark && (
                        <Area
                          type="monotone"
                          dataKey="spyNormalized"
                          stroke="#10b981"
                          strokeWidth={1.5}
                          strokeDasharray="4 4"
                          fill="none"
                          isAnimationActive={false}
                        />
                      )}
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex h-full items-center justify-center text-[#525252] font-mono text-sm">
                    AWAITING DATA...
                  </div>
                )}
              </div>
            </div>

            {/* Trades Table */}
            <div className="hidden rounded-sm border border-[#262626] bg-[#121212] md:flex md:flex-col flex-1 min-h-0">
              <button
                type="button"
                onClick={() => setShowExecutionLog((value) => !value)}
                className="flex items-center justify-between gap-4 border-b border-[#262626] p-4 text-left transition-colors hover:bg-[#171717]"
              >
                <div className="flex items-center gap-3">
                  <h2 className="text-sm font-mono text-[#a3a3a3] uppercase tracking-wider">Execution Log</h2>
                  <span className="text-[10px] font-mono uppercase tracking-wider text-[#737373]">{trades.length} entries</span>
                </div>
                <span className="font-mono text-[10px] uppercase tracking-wider text-[#737373]">
                  {showExecutionLog ? 'Hide' : 'Show'}
                </span>
              </button>
              {showExecutionLog && (
                <>
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
                    {trades.length === 0 && (
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
              <div className="divide-y divide-[#262626] md:hidden">
                {trades.length === 0 && (
                  <div className="px-5 py-8 text-center font-mono text-sm text-[#525252]">No executions recorded.</div>
                )}
                {trades.map((t, i) => {
                  const isBuy = t.side === 'buy' || t.side === 'cover';
                  const driverText = t.explanation || t.rationale;
                  return (
                    <details key={i} className="group px-4 py-4">
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
              </div>
                </>
              )}
            </div>

          </div>

          {/* Right Column: Holdings */}
          <div className="bg-[#121212] border border-[#262626] rounded-sm flex flex-col h-full min-h-0">
            <div className="p-4 border-b border-[#262626] flex justify-between items-center shrink-0">
              <h2 className="text-sm font-mono text-[#a3a3a3] uppercase tracking-wider">Book</h2>
              <span className="text-xs font-mono text-[#737373]">{holdings.length} POS</span>
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
                  {holdings.length === 0 && (
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
                {holdings.length === 0 && (
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
              onClick={() => setShowExecutionLog((value) => !value)}
              className="flex items-center justify-between gap-4 border-b border-[#262626] p-4 text-left transition-colors hover:bg-[#171717]"
            >
              <div className="flex items-center gap-3">
                <h2 className="text-sm font-mono text-[#a3a3a3] uppercase tracking-wider">Execution Log</h2>
                <span className="text-[10px] font-mono uppercase tracking-wider text-[#737373]">{trades.length} entries</span>
              </div>
              <span className="font-mono text-[10px] uppercase tracking-wider text-[#737373]">
                {showExecutionLog ? 'Hide' : 'Show'}
              </span>
            </button>
            {showExecutionLog && (
              <div className="divide-y divide-[#262626]">
                {trades.length === 0 && (
                  <div className="px-5 py-8 text-center font-mono text-sm text-[#525252]">No executions recorded.</div>
                )}
                {trades.map((t, i) => {
                  const isBuy = t.side === 'buy' || t.side === 'cover';
                  const driverText = t.explanation || t.rationale;
                  return (
                    <details key={i} className="group px-4 py-4">
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
              </div>
            )}
          </div>

        </div>
      </div>
    </div>
  );
}
