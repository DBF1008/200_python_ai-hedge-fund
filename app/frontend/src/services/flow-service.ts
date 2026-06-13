import { Flow } from '@/types/flow';

const API_BASE_URL = 'http://localhost:8000';

export interface CreateFlowRequest {
  name: string;
  description?: string;
  nodes: any;
  edges: any;
  viewport?: any;
  data?: any;
  is_template?: boolean;
  tags?: string[];
}

export interface UpdateFlowRequest {
  name?: string;
  description?: string;
  nodes?: any;
  edges?: any;
  viewport?: any;
  data?: any;
  is_template?: boolean;
  tags?: string[];
}

export interface FlowRunResponse {
  id: number;
  flow_id: number;
  status: 'IDLE' | 'IN_PROGRESS' | 'COMPLETE' | 'ERROR';
  run_number: number;
  trading_mode?: string;
  created_at: string;
  updated_at?: string;
  started_at?: string;
  completed_at?: string;
  request_data?: Record<string, any>;
  initial_portfolio?: Record<string, any>;
  final_portfolio?: Record<string, any>;
  results?: Record<string, any>;
  error_message?: string;
}

export const flowService = {
  // Get all flows
  async getFlows(): Promise<Flow[]> {
    const response = await fetch(`${API_BASE_URL}/flows/`);
    if (!response.ok) {
      throw new Error('Failed to fetch flows');
    }
    return response.json();
  },

  // Get a specific flow
  async getFlow(id: number): Promise<Flow> {
    const response = await fetch(`${API_BASE_URL}/flows/${id}`);
    if (!response.ok) {
      throw new Error('Failed to fetch flow');
    }
    return response.json();
  },

  // Create a new flow
  async createFlow(data: CreateFlowRequest): Promise<Flow> {
    const response = await fetch(`${API_BASE_URL}/flows/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
    });
    if (!response.ok) {
      throw new Error('Failed to create flow');
    }
    return response.json();
  },

  // Update an existing flow
  async updateFlow(id: number, data: UpdateFlowRequest): Promise<Flow> {
    const response = await fetch(`${API_BASE_URL}/flows/${id}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
    });
    if (!response.ok) {
      throw new Error('Failed to update flow');
    }
    return response.json();
  },

  // Delete a flow
  async deleteFlow(id: number): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/flows/${id}`, {
      method: 'DELETE',
    });
    if (!response.ok) {
      throw new Error('Failed to delete flow');
    }
  },

  // Duplicate a flow
  async duplicateFlow(id: number, newName?: string): Promise<Flow> {
    const url = `${API_BASE_URL}/flows/${id}/duplicate${newName ? `?new_name=${encodeURIComponent(newName)}` : ''}`;
    const response = await fetch(url, {
      method: 'POST',
    });
    if (!response.ok) {
      throw new Error('Failed to duplicate flow');
    }
    return response.json();
  },

  // Create a default flow for new users
  async createDefaultFlow(nodes: any, edges: any, viewport?: any): Promise<Flow> {
    return this.createFlow({
      name: 'My First Flow',
      description: 'Welcome to AI Hedge Fund! Start building your flow here.',
      nodes,
      edges,
      viewport,
    });
  },

  // Get the latest flow run
  async getLatestFlowRun(flowId: number): Promise<FlowRunResponse | null> {
    const response = await fetch(`${API_BASE_URL}/flows/${flowId}/runs/latest`);
    if (!response.ok) {
      if (response.status === 404) return null;
      throw new Error('Failed to fetch latest flow run');
    }
    return response.json();
  },

  // Get the active (in-progress) flow run
  async getActiveFlowRun(flowId: number): Promise<FlowRunResponse | null> {
    const response = await fetch(`${API_BASE_URL}/flows/${flowId}/runs/active`);
    if (!response.ok) {
      if (response.status === 404) return null;
      throw new Error('Failed to fetch active flow run');
    }
    return response.json();
  },

  // Get all flow runs (for history display)
  async getFlowRuns(flowId: number, limit: number = 10): Promise<FlowRunResponse[]> {
    const response = await fetch(
      `${API_BASE_URL}/flows/${flowId}/runs/?limit=${limit}`
    );
    if (!response.ok) {
      throw new Error('Failed to fetch flow runs');
    }
    return response.json();
  },
}; 