import { OutputNodeData, useNodeContext } from '@/contexts/node-context';
import { flowConnectionManager } from '@/hooks/use-flow-connection';
import { FlowRun, FlowRunStatus, flowRunsApi } from '@/services/flow-runs-api';
import { useCallback, useRef } from 'react';

/**
 * Restores a saved flow's most recent persisted run (output + connection status)
 * from the backend. Used on tab activation / page refresh so a completed run's
 * results survive a reload, and an interrupted run shows as errored.
 *
 * Restoration is deliberately conservative — it never clobbers a live run or
 * in-session results, and fetches at most once per flow per mount.
 */
export function useFlowRunRestore() {
  const nodeContext = useNodeContext();
  // Flows already attempted this mount, to avoid redundant fetches / flicker
  // when FlowTabContent's load effect re-fires.
  const restoredRef = useRef<Set<string>>(new Set());

  const restoreLatestRun = useCallback(async (flowId: string | null) => {
    // Guard 1: unsaved flows have no persisted history.
    if (!flowId) return;

    // Guard 2: fetch at most once per flow per mount.
    if (restoredRef.current.has(flowId)) return;
    restoredRef.current.add(flowId);

    // Guard 3: a live run this session owns the connection/output state.
    const connection = flowConnectionManager.getConnection(flowId);
    if (connection.state === 'connecting' || connection.state === 'connected') {
      return;
    }

    // Guard 4: don't overwrite results already produced this session.
    if (nodeContext.getOutputNodeDataForFlow(flowId)) {
      return;
    }

    let run: FlowRun | null = null;
    try {
      run = await flowRunsApi.getLatestRun(parseInt(flowId, 10));
    } catch (error) {
      console.error('Failed to restore latest run for flow', flowId, error);
      // Allow a retry on the next trigger.
      restoredRef.current.delete(flowId);
      return;
    }

    if (!run) return;

    if (run.status === FlowRunStatus.COMPLETE && run.results) {
      const results = run.results;
      // Backtest results carry performance_metrics/total_days; single runs carry
      // decisions/analyst_signals (+ current_prices). Normalize both shapes.
      const isBacktest =
        results.performance_metrics !== undefined || results.total_days !== undefined;

      const outputData: OutputNodeData = isBacktest
        ? {
            decisions: { backtest: { type: 'backtest_complete' } },
            analyst_signals: {},
            performance_metrics: results.performance_metrics,
            final_portfolio: results.final_portfolio,
            total_days: results.total_days,
          }
        : (results as OutputNodeData);

      nodeContext.setOutputNodeData(flowId, outputData);
      nodeContext.updateAgentNode(flowId, 'output', {
        status: 'COMPLETE',
        message: 'Restored previous run',
      });
      flowConnectionManager.setConnection(flowId, {
        state: 'completed',
        abortController: null,
      });
    } else if (run.status === FlowRunStatus.ERROR) {
      flowConnectionManager.setConnection(flowId, {
        state: 'error',
        error: run.error_message || 'Previous run failed',
        abortController: null,
      });
    }
    // A residual IN_PROGRESS run (only from a hard server kill, since client
    // disconnects are recorded as ERROR) is left untouched.
  }, [nodeContext]);

  return { restoreLatestRun };
}
