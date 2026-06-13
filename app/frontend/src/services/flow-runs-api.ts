// API client for saved-flow run history (backend prefix `/flows/{flowId}/runs`).
// Mirrors flow-service.ts; primarily used to restore the latest persisted run
// (status + results) after a page refresh.

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export enum FlowRunStatus {
  IDLE = 'IDLE',
  IN_PROGRESS = 'IN_PROGRESS',
  COMPLETE = 'COMPLETE',
  ERROR = 'ERROR',
}

// Mirrors the backend FlowRunResponse. `results` / `request_data` are absent on
// the lightweight list endpoint, hence optional.
export interface FlowRun {
  id: number;
  flow_id: number;
  status: FlowRunStatus;
  run_number: number;
  created_at: string;
  updated_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  request_data?: Record<string, any> | null;
  results?: Record<string, any> | null;
  error_message?: string | null;
}

export const flowRunsApi = {
  // List runs for a flow (most recent first), lightweight summaries.
  async getRuns(flowId: number, limit = 50, offset = 0): Promise<FlowRun[]> {
    const response = await fetch(
      `${API_BASE_URL}/flows/${flowId}/runs/?limit=${limit}&offset=${offset}`
    );
    if (!response.ok) {
      throw new Error('Failed to fetch flow runs');
    }
    return response.json();
  },

  // The current IN_PROGRESS run, or null if none is active.
  async getActiveRun(flowId: number): Promise<FlowRun | null> {
    const response = await fetch(`${API_BASE_URL}/flows/${flowId}/runs/active`);
    if (!response.ok) {
      throw new Error('Failed to fetch active flow run');
    }
    return response.json();
  },

  // The most recent run (any status) including its full results, or null.
  async getLatestRun(flowId: number): Promise<FlowRun | null> {
    const response = await fetch(`${API_BASE_URL}/flows/${flowId}/runs/latest`);
    if (!response.ok) {
      throw new Error('Failed to fetch latest flow run');
    }
    return response.json();
  },

  // A specific run by id including its full results.
  async getRun(flowId: number, runId: number): Promise<FlowRun> {
    const response = await fetch(`${API_BASE_URL}/flows/${flowId}/runs/${runId}`);
    if (!response.ok) {
      throw new Error('Failed to fetch flow run');
    }
    return response.json();
  },
};
