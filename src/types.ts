export interface Position {
  symbol: string;
  quantity: number;
  average_price: number;
  last_price: number;
  market_value: number;
  unrealized_pnl: number;
  direction: 'long' | 'short';
  target_weight: number;
}

export interface Trade {
  timestamp: string;
  symbol: string;
  side: 'buy' | 'sell' | 'short' | 'cover';
  quantity: number;
  price: number;
  notional: number;
  rationale: string;
  explanation: string;
}

export interface ClosedPosition {
  symbol: string;
  direction: 'long' | 'short';
  opened_at: string;
  closed_at: string;
  quantity: number;
  average_entry_price: number;
  average_exit_price: number;
  realized_pnl: number;
  realized_return_pct: number;
}

export interface EquityPoint {
  timestamp: string;
  equity: number;
  cash: number;
  gross_exposure: number;
  net_exposure: number;
  spy_price?: number;
}

export interface PortfolioSnapshot {
  timestamp: string;
  cash: number;
  equity: number;
  gross_exposure: number;
  net_exposure: number;
  long_exposure: number;
  short_exposure: number;
  holdings_count: number;
}
