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

export interface FlowListParams {
  isTemplate?: boolean;
  keyword?: string;
  tags?: string[];
  sortOrder?: 'asc' | 'desc';
  limit?: number;
  offset?: number;
}

export interface FlowListResponse {
  items: Flow[];
  total: number;
  limit: number;
  offset: number;
}

export const flowService = {
  // List flows with server-side filtering, search, and pagination
  async queryFlows(params: FlowListParams = {}): Promise<FlowListResponse> {
    const query = new URLSearchParams();
    if (params.isTemplate !== undefined) query.set('is_template', String(params.isTemplate));
    if (params.keyword) query.set('keyword', params.keyword);
    (params.tags ?? []).forEach((tag) => query.append('tags', tag));
    if (params.sortOrder) query.set('sort_order', params.sortOrder);
    if (params.limit !== undefined) query.set('limit', String(params.limit));
    if (params.offset !== undefined) query.set('offset', String(params.offset));

    const response = await fetch(`${API_BASE_URL}/flows/?${query.toString()}`);
    if (!response.ok) {
      throw new Error('Failed to fetch flows');
    }
    return response.json();
  },

  // Get all flows (convenience wrapper around queryFlows)
  async getFlows(): Promise<Flow[]> {
    const { items } = await this.queryFlows({});
    return items;
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
}; 