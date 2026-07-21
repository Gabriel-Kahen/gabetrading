import { format } from 'date-fns';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { ChartPoint } from './App';

type PerformanceChartProps = {
  chartData: ChartPoint[];
  chartPointsByIndex: Map<number, ChartPoint>;
  showBenchmark: boolean;
  spansMultipleDays: boolean;
  spansMultipleYears: boolean;
  xAxisTicks: number[];
};

function formatCurrency(value: number) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export default function PerformanceChart({
  chartData,
  chartPointsByIndex,
  showBenchmark,
  spansMultipleDays,
  spansMultipleYears,
  xAxisTicks,
}: PerformanceChartProps) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={chartData} margin={{ top: 5, right: 5, left: -20, bottom: 25 }}>
        <defs>
          <linearGradient id="colorEquity" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="2 4" stroke="#262626" vertical={false} />
        <XAxis
          dataKey="tradingIndex"
          type="number"
          domain={['dataMin', 'dataMax']}
          ticks={xAxisTicks}
          stroke="#525252"
          fontSize={11}
          fontFamily="monospace"
          tickFormatter={(value) => {
            const point = chartPointsByIndex.get(Number(value));
            if (!point) return '';
            return format(
              new Date(point.timestamp),
              spansMultipleYears ? 'MMM d, yy' : spansMultipleDays ? 'MMM d' : 'HH:mm',
            );
          }}
          tickLine={false}
          axisLine={false}
          dy={15}
        />
        <YAxis
          domain={['auto', 'auto']}
          stroke="#525252"
          fontSize={11}
          fontFamily="monospace"
          tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`}
          tickLine={false}
          axisLine={false}
          width={80}
          dx={-10}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: '#0a0a0a',
            border: '1px solid #262626',
            borderRadius: '2px',
            fontFamily: 'monospace',
            fontSize: '12px',
          }}
          itemStyle={{ color: '#ededed' }}
          labelStyle={{ color: '#737373', marginBottom: '6px' }}
          formatter={(value, name) => [
            formatCurrency(Number(value)),
            name === 'equity' ? 'Equity' : 'SPY (Norm)',
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
  );
}
