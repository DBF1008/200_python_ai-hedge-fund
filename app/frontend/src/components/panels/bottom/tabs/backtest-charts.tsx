import { useMemo, useState } from 'react';
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

interface BacktestTimeSeries {
  dates: string[];
  portfolio_values: number[];
  benchmark_values: (number | null)[];
  long_exposures: number[];
  short_exposures: number[];
  gross_exposures: number[];
  net_exposures: number[];
}

interface BacktestPerformanceMetrics {
  sharpe_ratio?: number;
  sortino_ratio?: number;
  max_drawdown?: number;
  benchmark_return_pct?: number;
  alpha_pct?: number;
}

interface BacktestChartsProps {
  timeSeries: BacktestTimeSeries;
  performanceMetrics?: BacktestPerformanceMetrics;
}

type ChartTab = 'equity' | 'exposures';

function formatCurrency(value: number): string {
  if (Math.abs(value) >= 1_000_000) {
    return `$${(value / 1_000_000).toFixed(1)}M`;
  }
  if (Math.abs(value) >= 1_000) {
    return `$${(value / 1_000).toFixed(1)}K`;
  }
  return `$${value.toFixed(0)}`;
}

function formatDate(dateStr: string): string {
  // Show short date: "Jan 15"
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload || payload.length === 0) return null;

  return (
    <div className="bg-popover border border-border rounded-md shadow-md p-2 text-xs">
      <p className="font-medium mb-1">{label}</p>
      {payload.map((entry: any, idx: number) => (
        <div key={idx} className="flex items-center gap-2">
          <span
            className="inline-block w-2 h-2 rounded-full"
            style={{ backgroundColor: entry.color }}
          />
          <span className="text-muted-foreground">{entry.name}:</span>
          <span className="font-medium">
            {typeof entry.value === 'number' ? formatCurrency(entry.value) : entry.value ?? 'N/A'}
          </span>
        </div>
      ))}
    </div>
  );
}

export function BacktestCharts({ timeSeries, performanceMetrics }: BacktestChartsProps) {
  const [activeTab, setActiveTab] = useState<ChartTab>('equity');

  // Build chart data for equity curve
  const equityData = useMemo(() => {
    return timeSeries.dates.map((date, i) => ({
      date: formatDate(date),
      fullDate: date,
      Portfolio: timeSeries.portfolio_values[i],
      'SPY Benchmark': timeSeries.benchmark_values[i],
    }));
  }, [timeSeries]);

  // Build chart data for exposures
  const exposureData = useMemo(() => {
    return timeSeries.dates.map((date, i) => ({
      date: formatDate(date),
      fullDate: date,
      'Long Exposure': timeSeries.long_exposures[i],
      'Short Exposure': timeSeries.short_exposures[i],
      'Gross Exposure': timeSeries.gross_exposures[i],
      'Net Exposure': timeSeries.net_exposures[i],
    }));
  }, [timeSeries]);

  // Compute tick interval to avoid label overlap
  const tickInterval = useMemo(() => {
    const len = timeSeries.dates.length;
    if (len <= 30) return 4;
    if (len <= 60) return 9;
    if (len <= 120) return 19;
    if (len <= 252) return 29;
    return Math.floor(len / 8);
  }, [timeSeries.dates.length]);

  // Summary badges
  const portfolioReturn = useMemo(() => {
    const vals = timeSeries.portfolio_values;
    if (vals.length < 2 || vals[0] === 0) return 0;
    return ((vals[vals.length - 1] / vals[0]) - 1) * 100;
  }, [timeSeries.portfolio_values]);

  const benchmarkReturn = performanceMetrics?.benchmark_return_pct;
  const alpha = performanceMetrics?.alpha_pct;

  return (
    <Card className="bg-transparent mb-4">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">Charts</CardTitle>
          <div className="flex gap-1">
            <button
              onClick={() => setActiveTab('equity')}
              className={cn(
                'px-3 py-1 text-xs rounded-md transition-colors',
                activeTab === 'equity'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
              )}
            >
              Equity Curve
            </button>
            <button
              onClick={() => setActiveTab('exposures')}
              className={cn(
                'px-3 py-1 text-xs rounded-md transition-colors',
                activeTab === 'exposures'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
              )}
            >
              Exposures
            </button>
          </div>
        </div>

        {/* Summary badges */}
        {activeTab === 'equity' && (
          <div className="flex gap-3 mt-2 text-xs">
            <span className="flex items-center gap-1">
              <span className="text-muted-foreground">Return:</span>
              <span className={cn('font-medium', portfolioReturn >= 0 ? 'text-green-500' : 'text-red-500')}>
                {portfolioReturn >= 0 ? '+' : ''}{portfolioReturn.toFixed(2)}%
              </span>
            </span>
            {benchmarkReturn !== undefined && benchmarkReturn !== null && (
              <span className="flex items-center gap-1">
                <span className="text-muted-foreground">SPY:</span>
                <span className={cn('font-medium', benchmarkReturn >= 0 ? 'text-green-500' : 'text-red-500')}>
                  {benchmarkReturn >= 0 ? '+' : ''}{benchmarkReturn.toFixed(2)}%
                </span>
              </span>
            )}
            {alpha !== undefined && alpha !== null && (
              <span className="flex items-center gap-1">
                <span className="text-muted-foreground">Alpha:</span>
                <span className={cn('font-medium', alpha >= 0 ? 'text-green-500' : 'text-red-500')}>
                  {alpha >= 0 ? '+' : ''}{alpha.toFixed(2)}%
                </span>
              </span>
            )}
          </div>
        )}
      </CardHeader>
      <CardContent className="pt-0">
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            {activeTab === 'equity' ? (
              <LineChart data={equityData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 10 }}
                  interval={tickInterval}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 10 }}
                  tickFormatter={formatCurrency}
                  width={60}
                  tickLine={false}
                />
                <Tooltip content={<CustomTooltip />} />
                <Legend
                  wrapperStyle={{ fontSize: '11px' }}
                  iconType="circle"
                  iconSize={8}
                />
                <Line
                  type="monotone"
                  dataKey="Portfolio"
                  stroke="#3b82f6"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 3 }}
                />
                <Line
                  type="monotone"
                  dataKey="SPY Benchmark"
                  stroke="#9ca3af"
                  strokeWidth={1.5}
                  strokeDasharray="4 4"
                  dot={false}
                  activeDot={{ r: 3 }}
                  connectNulls
                />
              </LineChart>
            ) : (
              <AreaChart data={exposureData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 10 }}
                  interval={tickInterval}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 10 }}
                  tickFormatter={formatCurrency}
                  width={60}
                  tickLine={false}
                />
                <Tooltip content={<CustomTooltip />} />
                <Legend
                  wrapperStyle={{ fontSize: '11px' }}
                  iconType="circle"
                  iconSize={8}
                />
                <Area
                  type="monotone"
                  dataKey="Long Exposure"
                  stroke="#22c55e"
                  fill="#22c55e"
                  fillOpacity={0.15}
                  strokeWidth={1.5}
                />
                <Area
                  type="monotone"
                  dataKey="Short Exposure"
                  stroke="#ef4444"
                  fill="#ef4444"
                  fillOpacity={0.15}
                  strokeWidth={1.5}
                />
                <Area
                  type="monotone"
                  dataKey="Net Exposure"
                  stroke="#8b5cf6"
                  fill="none"
                  strokeWidth={1.5}
                  strokeDasharray="4 4"
                />
              </AreaChart>
            )}
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
