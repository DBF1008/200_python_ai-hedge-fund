import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { cn } from '@/lib/utils';
import { MoreHorizontal } from 'lucide-react';
import { getActionColor } from './output-tab-utils';

// Component for displaying backtest progress
function BacktestProgress({ agentData }: { agentData: Record<string, any> }) {
  const backtestAgent = agentData['backtest'];
  
  if (!backtestAgent) return null;
  
  // Get the latest backtest result from the backtest results array
  const backtestResults = backtestAgent.backtestResults || [];
  const latestBacktestResult = backtestResults.length > 0 ? backtestResults[backtestResults.length - 1] : null;
  
  return (
    <Card className="bg-transparent mb-4">
      <CardHeader>
        <CardTitle className="text-lg">Backtest Progress</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {/* Current Status */}
          <div className="flex items-center gap-2">
            <MoreHorizontal className="h-4 w-4 text-yellow-500" />
            <span className="font-medium">Backtest Runner</span>
            <span className="text-yellow-500 flex-1">{backtestAgent.message || backtestAgent.status}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// Component for displaying backtest trading table (similar to CLI)
function BacktestTradingTable({ agentData }: { agentData: Record<string, any> }) {
  const backtestAgent = agentData['backtest'];

  // console.log("backtestAgent", backtestAgent);
  
  if (!backtestAgent || !backtestAgent.backtestResults) {
    return null;
  }
    
  // Get the backtest results directly from the agent data
  const backtestResults = backtestAgent.backtestResults || [];
  
  if (backtestResults.length === 0) {
    return null;
  }
  
  // Build table rows similar to CLI format
  const tableRows: any[] = [];
  
  backtestResults.forEach((backtestResult: any) => {    
    // Add ticker rows for this period
    if (backtestResult.ticker_details) {
      backtestResult.ticker_details.forEach((ticker: any) => {
        tableRows.push({
          type: 'ticker',
          date: backtestResult.date,
          ticker: ticker.ticker,
          action: ticker.action,
          quantity: ticker.quantity,
          price: ticker.price,
          shares_owned: ticker.shares_owned,
          long_shares: ticker.long_shares,
          short_shares: ticker.short_shares,
          position_value: ticker.position_value,
          bullish_count: ticker.bullish_count,
          bearish_count: ticker.bearish_count,
          neutral_count: ticker.neutral_count,
        });
      });
    }
    
    // Add portfolio summary row for this period
    tableRows.push({
      type: 'summary',
      date: backtestResult.date,
      portfolio_value: backtestResult.portfolio_value,
      cash: backtestResult.cash,
      portfolio_return: backtestResult.portfolio_return,
      total_position_value: backtestResult.portfolio_value - backtestResult.cash,
      performance_metrics: backtestResult.performance_metrics,
    });
  });
    
  // Sort by date descending (newest first) and show only the last 50 rows to avoid performance issues
  const recentRows = tableRows
    .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
    .slice(0, 50);
  
  
  return (
    <Card className="bg-transparent mb-4">
      <CardHeader>
        <CardTitle className="text-lg">Activity</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="max-h-96 overflow-y-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Ticker</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Quantity</TableHead>
                <TableHead>Price</TableHead>
                <TableHead>Shares</TableHead>
                <TableHead>Position Value</TableHead>
                <TableHead>Bullish</TableHead>
                <TableHead>Bearish</TableHead>
                <TableHead>Neutral</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {recentRows.map((row: any, idx: number) => {
                if (row.type === 'ticker') {
                  return (
                    <TableRow key={idx}>
                      <TableCell className="font-medium">{row.date}</TableCell>
                      <TableCell className="font-medium text-cyan-500">{row.ticker}</TableCell>
                      <TableCell>
                        <span className={cn("font-medium", getActionColor(row.action || ''))}>
                          {row.action?.toUpperCase() || 'HOLD'}
                        </span>
                      </TableCell>
                      <TableCell className={cn("font-medium", getActionColor(row.action || ''))}>
                        {row.quantity?.toLocaleString() || 0}
                      </TableCell>
                      <TableCell>${row.price?.toFixed(2) || '0.00'}</TableCell>
                      <TableCell>{row.shares_owned?.toLocaleString() || 0}</TableCell>
                      <TableCell className="text-primary">
                        ${row.position_value?.toLocaleString() || '0'}
                      </TableCell>
                      <TableCell className="text-green-500">{row.bullish_count || 0}</TableCell>
                      <TableCell className="text-red-500">{row.bearish_count || 0}</TableCell>
                      <TableCell className="text-blue-500">{row.neutral_count || 0}</TableCell>
                    </TableRow>
                  );
                }
              })}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}

// ---- Inline-SVG charting (dependency-free) ----
const CHART_W = 720;
const CHART_H = 220;
const CHART_PAD = { top: 14, right: 12, bottom: 24, left: 12 };

function niceCurrency(n: number): string {
  return `$${Math.round(n).toLocaleString()}`;
}

// Build an SVG polyline "points" string from (x,y) pairs in pixel space.
function toPolyline(points: Array<[number, number]>): string {
  return points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
}

// Equity curve: portfolio value vs buy-and-hold SPY benchmark (shared y-scale).
function EquityCurveChart({ data }: { data: any[] }) {
  if (!data || data.length === 0) return null;

  const innerW = CHART_W - CHART_PAD.left - CHART_PAD.right;
  const innerH = CHART_H - CHART_PAD.top - CHART_PAD.bottom;
  const n = data.length;

  const portfolioVals = data.map((d) => Number(d.portfolio_value));
  const benchVals = data.map((d) => (d.benchmark_value == null ? null : Number(d.benchmark_value)));
  const allVals = [...portfolioVals, ...benchVals.filter((v): v is number => v != null)];
  const minV = Math.min(...allVals);
  const maxV = Math.max(...allVals);
  const span = maxV - minV || 1;

  const xAt = (i: number) => CHART_PAD.left + (n <= 1 ? innerW / 2 : (i / (n - 1)) * innerW);
  const yAt = (v: number) => CHART_PAD.top + innerH - ((v - minV) / span) * innerH;

  const portfolioPts = toPolyline(portfolioVals.map((v, i): [number, number] => [xAt(i), yAt(v)]));
  // Benchmark may have gaps (null before first quote); plot only available points.
  const benchPts = toPolyline(
    benchVals
      .map((v, i) => (v == null ? null : ([xAt(i), yAt(v)] as [number, number])))
      .filter((p): p is [number, number] => p != null)
  );

  const startDate = data[0]?.date ?? '';
  const endDate = data[n - 1]?.date ?? '';

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-4 text-xs">
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-0.5" style={{ backgroundColor: '#10b981' }} />Portfolio
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-0.5" style={{ backgroundColor: '#f59e0b' }} />{'SPY (Buy & Hold)'}
        </span>
      </div>
      <svg
        viewBox={`0 0 ${CHART_W} ${CHART_H}`}
        className="w-full h-auto"
        role="img"
        aria-label="Equity curve versus SPY benchmark"
      >
        <line
          x1={CHART_PAD.left}
          y1={CHART_PAD.top + innerH}
          x2={CHART_PAD.left + innerW}
          y2={CHART_PAD.top + innerH}
          stroke="currentColor"
          className="text-muted-foreground"
          strokeOpacity={0.3}
        />
        {benchPts && <polyline points={benchPts} fill="none" stroke="#f59e0b" strokeWidth={1.5} />}
        <polyline points={portfolioPts} fill="none" stroke="#10b981" strokeWidth={1.5} />
        <text x={CHART_PAD.left} y={CHART_PAD.top + 9} fontSize={10} fill="currentColor" className="text-muted-foreground">{niceCurrency(maxV)}</text>
        <text x={CHART_PAD.left} y={CHART_PAD.top + innerH - 2} fontSize={10} fill="currentColor" className="text-muted-foreground">{niceCurrency(minV)}</text>
        <text x={CHART_PAD.left} y={CHART_H - 6} fontSize={10} fill="currentColor" className="text-muted-foreground">{startDate}</text>
        <text x={CHART_PAD.left + innerW} y={CHART_H - 6} fontSize={10} textAnchor="end" fill="currentColor" className="text-muted-foreground">{endDate}</text>
      </svg>
    </div>
  );
}

// Daily exposures: gross / net / long / short (shared y-scale incl. zero).
function ExposureChart({ data }: { data: any[] }) {
  if (!data || data.length === 0) return null;

  const innerW = CHART_W - CHART_PAD.left - CHART_PAD.right;
  const innerH = CHART_H - CHART_PAD.top - CHART_PAD.bottom;
  const n = data.length;

  const series = [
    { key: 'gross_exposure', color: '#0ea5e9', label: 'Gross' },
    { key: 'net_exposure', color: '#8b5cf6', label: 'Net' },
    { key: 'long_exposure', color: '#22c55e', label: 'Long' },
    { key: 'short_exposure', color: '#ef4444', label: 'Short' },
  ];

  const allVals = series.flatMap((s) => data.map((d) => Number(d[s.key] ?? 0)));
  const minV = Math.min(0, ...allVals);
  const maxV = Math.max(...allVals);
  const span = maxV - minV || 1;

  const xAt = (i: number) => CHART_PAD.left + (n <= 1 ? innerW / 2 : (i / (n - 1)) * innerW);
  const yAt = (v: number) => CHART_PAD.top + innerH - ((v - minV) / span) * innerH;

  const zeroY = yAt(0);
  const startDate = data[0]?.date ?? '';
  const endDate = data[n - 1]?.date ?? '';

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-4 text-xs flex-wrap">
        {series.map((s) => (
          <span key={s.key} className="flex items-center gap-1">
            <span className="inline-block w-3 h-0.5" style={{ backgroundColor: s.color }} />{s.label}
          </span>
        ))}
      </div>
      <svg
        viewBox={`0 0 ${CHART_W} ${CHART_H}`}
        className="w-full h-auto"
        role="img"
        aria-label="Daily portfolio exposures"
      >
        <line x1={CHART_PAD.left} y1={zeroY} x2={CHART_PAD.left + innerW} y2={zeroY} stroke="currentColor" className="text-muted-foreground" strokeOpacity={0.3} />
        {series.map((s) => {
          const pts = toPolyline(data.map((d, i): [number, number] => [xAt(i), yAt(Number(d[s.key] ?? 0))]));
          return <polyline key={s.key} points={pts} fill="none" stroke={s.color} strokeWidth={1.5} />;
        })}
        <text x={CHART_PAD.left} y={CHART_PAD.top + 9} fontSize={10} fill="currentColor" className="text-muted-foreground">{niceCurrency(maxV)}</text>
        <text x={CHART_PAD.left} y={CHART_PAD.top + innerH - 2} fontSize={10} fill="currentColor" className="text-muted-foreground">{niceCurrency(minV)}</text>
        <text x={CHART_PAD.left} y={CHART_H - 6} fontSize={10} fill="currentColor" className="text-muted-foreground">{startDate}</text>
        <text x={CHART_PAD.left + innerW} y={CHART_H - 6} fontSize={10} textAnchor="end" fill="currentColor" className="text-muted-foreground">{endDate}</text>
      </svg>
    </div>
  );
}

// Component for displaying backtest results
function BacktestResults({ outputData }: { outputData: any }) {
  if (!outputData) {
    return null;
  }

  console.log("outputData", outputData);
  
  if (!outputData.performance_metrics) {
    return (
      <Card className="bg-transparent mb-4">
        <CardHeader>
          <CardTitle className="text-lg">Backtest Results</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-8 text-muted-foreground">
            Backtest completed. Performance metrics will appear here.
          </div>
        </CardContent>
      </Card>
    );
  }
  
  const { performance_metrics, final_portfolio, total_days } = outputData;
  
  return (
    <Card className="bg-transparent mb-4">
      <CardHeader>
        <CardTitle className="text-lg">Backtest Results</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
          {/* Performance Metrics */}
          <div className="space-y-2">
            <h4 className="font-medium">Performance Metrics</h4>
            <div className="space-y-1 text-sm">
              {performance_metrics.sharpe_ratio !== null && performance_metrics.sharpe_ratio !== undefined && (
                <div className="flex justify-between">
                  <span>Sharpe Ratio:</span>
                  <span className={cn("font-medium", performance_metrics.sharpe_ratio > 1 ? "text-green-500" : "text-red-500")}>
                    {performance_metrics.sharpe_ratio.toFixed(2)}
                  </span>
                </div>
              )}
              {performance_metrics.sortino_ratio !== null && performance_metrics.sortino_ratio !== undefined && (
                <div className="flex justify-between">
                  <span>Sortino Ratio:</span>
                  <span className={cn("font-medium", performance_metrics.sortino_ratio > 1 ? "text-green-500" : "text-red-500")}>
                    {performance_metrics.sortino_ratio.toFixed(2)}
                  </span>
                </div>
              )}
              {performance_metrics.max_drawdown !== null && performance_metrics.max_drawdown !== undefined && (
                <div className="flex justify-between">
                  <span>Max Drawdown:</span>
                  <span className="font-medium text-red-500">
                    {Math.abs(performance_metrics.max_drawdown).toFixed(2)}%
                  </span>
                </div>
              )}
            </div>
          </div>
          
          {/* Portfolio Summary */}
          <div className="space-y-2">
            <h4 className="font-medium">Portfolio Summary</h4>
            <div className="space-y-1 text-sm">
              <div className="flex justify-between">
                <span>Total Days:</span>
                <span className="font-medium">{total_days}</span>
              </div>
              <div className="flex justify-between">
                <span>Final Cash:</span>
                <span className="font-medium">${final_portfolio.cash.toLocaleString()}</span>
              </div>
              <div className="flex justify-between">
                <span>Margin Used:</span>
                <span className="font-medium">${final_portfolio.margin_used.toLocaleString()}</span>
              </div>
            </div>
          </div>
          
          {/* Exposure Metrics */}
          <div className="space-y-2">
            <h4 className="font-medium">Exposure Metrics</h4>
            <div className="space-y-1 text-sm">
              {performance_metrics.gross_exposure !== null && performance_metrics.gross_exposure !== undefined && (
                <div className="flex justify-between">
                  <span>Gross Exposure:</span>
                  <span className="font-medium">${performance_metrics.gross_exposure.toLocaleString()}</span>
                </div>
              )}
              {performance_metrics.net_exposure !== null && performance_metrics.net_exposure !== undefined && (
                <div className="flex justify-between">
                  <span>Net Exposure:</span>
                  <span className="font-medium">${performance_metrics.net_exposure.toLocaleString()}</span>
                </div>
              )}
              {performance_metrics.long_short_ratio !== null && performance_metrics.long_short_ratio !== undefined && (
                <div className="flex justify-between">
                  <span>Long/Short Ratio:</span>
                  <span className="font-medium">
                    {performance_metrics.long_short_ratio === Infinity || performance_metrics.long_short_ratio === null ? '∞' : performance_metrics.long_short_ratio.toFixed(2)}
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Plottable time-series: equity curve vs SPY benchmark and daily exposures */}
        {outputData.timeseries && outputData.timeseries.length > 0 && (
          <div className="space-y-6 mb-6">
            <div>
              <h4 className="font-medium mb-2">Equity Curve vs SPY</h4>
              <EquityCurveChart data={outputData.timeseries} />
            </div>
            <div>
              <h4 className="font-medium mb-2">Exposures</h4>
              <ExposureChart data={outputData.timeseries} />
            </div>
          </div>
        )}

        {/* Final Positions */}
        {final_portfolio.positions && (
          <div>
            <h4 className="font-medium mb-2">Final Positions</h4>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Ticker</TableHead>
                  <TableHead>Long Shares</TableHead>
                  <TableHead>Short Shares</TableHead>
                  <TableHead>Long Cost Basis</TableHead>
                  <TableHead>Short Cost Basis</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {Object.entries(final_portfolio.positions).map(([ticker, position]: [string, any]) => (
                  <TableRow key={ticker}>
                    <TableCell className="font-medium">{ticker}</TableCell>
                    <TableCell className={cn(position.long > 0 ? "text-green-500" : "text-muted-foreground")}>
                      {position.long}
                    </TableCell>
                    <TableCell className={cn(position.short > 0 ? "text-red-500" : "text-muted-foreground")}>
                      {position.short}
                    </TableCell>
                    <TableCell>${position.long_cost_basis.toFixed(2)}</TableCell>
                    <TableCell>${position.short_cost_basis.toFixed(2)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// Component for displaying real-time backtest performance
function BacktestPerformanceMetrics({ agentData }: { agentData: Record<string, any> }) {
  const backtestAgent = agentData['backtest'];
  
  if (!backtestAgent || !backtestAgent.backtestResults) return null;
  
  // Get the backtest results directly from the agent data
  const backtestResults = backtestAgent.backtestResults || [];
  
  if (backtestResults.length === 0) return null;
  
  const firstPeriod = backtestResults[0];
  const latestPeriod = backtestResults[backtestResults.length - 1];
  
  // Calculate performance metrics
  const initialValue = firstPeriod.portfolio_value;
  const currentValue = latestPeriod.portfolio_value;
  const totalReturn = ((currentValue - initialValue) / initialValue) * 100;
  
  // Calculate win rate (periods with positive returns)
  const periodReturns = backtestResults.slice(1).map((period: any, idx: number) => {
    const prevPeriod = backtestResults[idx];
    return ((period.portfolio_value - prevPeriod.portfolio_value) / prevPeriod.portfolio_value) * 100;
  });
  
  const winningPeriods = periodReturns.filter((ret: number) => ret > 0).length;
  const winRate = periodReturns.length > 0 ? (winningPeriods / periodReturns.length) * 100 : 0;
  
  // Calculate max drawdown
  let maxDrawdown = 0;
  let peak = initialValue;
  
  backtestResults.forEach((period: any) => {
    if (period.portfolio_value > peak) {
      peak = period.portfolio_value;
    }
    const drawdown = ((period.portfolio_value - peak) / peak) * 100;
    if (drawdown < maxDrawdown) {
      maxDrawdown = drawdown;
    }
  });
  
  return (
    <Card className="bg-transparent mb-4">
      <CardHeader>
        <CardTitle className="text-lg">Performance</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="text-center">
            <div className="text-xs text-muted-foreground">Total Return</div>
            <div className={cn("font-sm", totalReturn >= 0 ? "text-green-500" : "text-red-500")}>
              {totalReturn >= 0 ? '+' : ''}{totalReturn.toFixed(2)}%
            </div>
          </div>
          <div className="text-center">
            <div className="text-xs text-muted-foreground">Win Rate</div>
            <div className="font-sm">{winRate.toFixed(1)}%</div>
          </div>
          <div className="text-center">
            <div className="text-xs text-muted-foreground">Max Drawdown</div>
            <div className="font-sm text-red-500">{Math.abs(maxDrawdown).toFixed(2)}%</div>
          </div>
          <div className="text-center">
            <div className="text-xs text-muted-foreground">Periods Traded</div>
            <div className="font-sm">{backtestResults.length}</div>
          </div>
        </div>
        
        {/* Additional metrics */}
        <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="text-center">
            <div className="text-xs text-muted-foreground">Current Value</div>
            <div className="font-sm">${currentValue?.toLocaleString()}</div>
          </div>
          <div className="text-center">
            <div className="text-xs text-muted-foreground">Initial Value</div>
            <div className="font-sm">${initialValue?.toLocaleString()}</div>
          </div>
          <div className="text-center">
            <div className="text-xs text-muted-foreground">P&L</div>
            <div className={cn("font-sm", totalReturn >= 0 ? "text-green-500" : "text-red-500")}>
              ${(currentValue - initialValue).toLocaleString()}
            </div>
          </div>
          <div className="text-center">
            <div className="text-xs text-muted-foreground">Long/Short Ratio</div>
            <div className="font-sm">
              {latestPeriod.long_short_ratio === Infinity || latestPeriod.long_short_ratio === null ? '∞' : latestPeriod.long_short_ratio?.toFixed(2)}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// Main component for backtest output
export function BacktestOutput({ 
  agentData, 
  outputData 
}: { 
  agentData: Record<string, any>; 
  outputData: any; 
}) {
  return (
    <>
      <BacktestProgress agentData={agentData} />
      {outputData && <BacktestResults outputData={outputData} />}
      {agentData && agentData['backtest'] && (
        <BacktestPerformanceMetrics agentData={agentData} />
      )}
      <BacktestTradingTable agentData={agentData} />

    </>
  );
} 