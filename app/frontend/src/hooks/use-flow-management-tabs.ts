import { useFlowContext } from '@/contexts/flow-context';
import { useNodeContext } from '@/contexts/node-context';
import { useTabsContext } from '@/contexts/tabs-context';
import {
  clearFlowNodeStates,
  getNodeInternalState,
  setNodeInternalState
} from '@/hooks/use-node-state';
import { useToastManager } from '@/hooks/use-toast-manager';
import { flowService } from '@/services/flow-service';
import { TabService } from '@/services/tab-service';
import { Flow } from '@/types/flow';
import { useCallback, useEffect, useState } from 'react';

// Page size for incremental ("Load more") loading of each flow group.
const PAGE_SIZE = 20;
// Delay before a search query is sent to the server (avoids a request per keystroke).
const SEARCH_DEBOUNCE_MS = 300;

export interface UseFlowManagementTabsReturn {
  // State
  searchQuery: string;
  isLoading: boolean;
  openGroups: string[];
  createDialogOpen: boolean;

  // Server-driven groups
  recentFlows: Flow[];
  templateFlows: Flow[];
  recentTotal: number;
  templateTotal: number;
  hasMoreRecent: boolean;
  hasMoreTemplates: boolean;
  loadingMoreRecent: boolean;
  loadingMoreTemplates: boolean;

  // Actions
  setSearchQuery: (query: string) => void;
  setOpenGroups: (groups: string[]) => void;
  setCreateDialogOpen: (open: boolean) => void;
  handleAccordionChange: (value: string[]) => void;
  handleCreateNewFlow: () => void;
  handleFlowCreated: (newFlow: Flow) => Promise<void>;
  handleSaveCurrentFlow: () => Promise<void>;
  handleOpenFlowInTab: (flow: Flow) => Promise<void>;
  handleDeleteFlow: (flow: Flow) => Promise<void>;
  handleRefresh: () => Promise<void>;
  loadMoreRecent: () => Promise<void>;
  loadMoreTemplates: () => Promise<void>;

  // Internal functions (for testing/advanced use)
  loadFlows: () => Promise<void>;
  createDefaultFlow: () => Promise<void>;
}

export function useFlowManagementTabs(): UseFlowManagementTabsReturn {
  // Get flow context, node context, tabs context, and toast manager
  const { saveCurrentFlow, reactFlowInstance, currentFlowId } = useFlowContext();
  const { exportNodeContextData } = useNodeContext();
  const { openTab, isTabOpen, closeTab } = useTabsContext();
  const { success, error } = useToastManager();

  // UI state
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [openGroups, setOpenGroups] = useState<string[]>(['recent-flows']);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);

  // Server-driven, paginated flow groups
  const [recentFlows, setRecentFlows] = useState<Flow[]>([]);
  const [templateFlows, setTemplateFlows] = useState<Flow[]>([]);
  const [recentTotal, setRecentTotal] = useState(0);
  const [templateTotal, setTemplateTotal] = useState(0);
  const [loadingMoreRecent, setLoadingMoreRecent] = useState(false);
  const [loadingMoreTemplates, setLoadingMoreTemplates] = useState(false);

  // Enhanced save function that includes internal node states AND node context data
  const saveCurrentFlowWithStates = useCallback(async (): Promise<Flow | null> => {
    try {
      // Get current nodes from React Flow
      const currentNodes = reactFlowInstance.getNodes();

      // Get node context data (runtime data: agent status, messages, output data)
      const flowId = currentFlowId?.toString() || null;
      const nodeContextData = exportNodeContextData(flowId);

      // Enhance nodes with internal states
      const nodesWithStates = currentNodes.map((node: any) => {
        const internalState = getNodeInternalState(node.id);
        return {
          ...node,
          data: {
            ...node.data,
            // Only add internal_state if there is actually state to save
            ...(internalState && Object.keys(internalState).length > 0 ? { internal_state: internalState } : {})
          }
        };
      });

      // Temporarily replace nodes in React Flow with enhanced nodes
      reactFlowInstance.setNodes(nodesWithStates);

      try {
        // Use the context's save function which handles currentFlowId properly
        const savedFlow = await saveCurrentFlow();

        if (savedFlow) {
          // After basic save, update with node context data
          const updatedFlow = await flowService.updateFlow(savedFlow.id, {
            ...savedFlow,
            data: {
              ...savedFlow.data,
              nodeContextData, // Add runtime data from node context
            }
          });

          return updatedFlow;
        }

        return savedFlow;
      } finally {
        // Restore original nodes (without internal_state in React Flow)
        reactFlowInstance.setNodes(currentNodes);
      }
    } catch (err) {
      console.error('Failed to save flow with states:', err);
      return null;
    }
  }, [reactFlowInstance, saveCurrentFlow, exportNodeContextData, currentFlowId]);

  // Create default flow for new users
  const createDefaultFlow = useCallback(async () => {
    try {
      // Get current React Flow state, fallback to empty arrays if nothing exists
      const nodes = reactFlowInstance?.getNodes() || [];
      const edges = reactFlowInstance?.getEdges() || [];
      const viewport = reactFlowInstance?.getViewport() || { x: 0, y: 0, zoom: 1 };

      const defaultFlow = await flowService.createDefaultFlow(nodes, edges, viewport);
      setRecentFlows([defaultFlow]);
      setRecentTotal(1);

      // Open the default flow in a tab
      const tabData = TabService.createFlowTab(defaultFlow);
      openTab(tabData);
    } catch (error) {
      console.error('Failed to create default flow:', error);
    }
  }, [reactFlowInstance, openTab]);

  // Load the first page of both groups from the API (applies the current search).
  const loadFlows = useCallback(async () => {
    setIsLoading(true);
    try {
      const keyword = debouncedQuery || undefined;
      const [recent, templates] = await Promise.all([
        flowService.queryFlows({ isTemplate: false, keyword, sortOrder: 'desc', limit: PAGE_SIZE, offset: 0 }),
        flowService.queryFlows({ isTemplate: true, keyword, sortOrder: 'desc', limit: PAGE_SIZE, offset: 0 }),
      ]);
      setRecentFlows(recent.items);
      setRecentTotal(recent.total);
      setTemplateFlows(templates.items);
      setTemplateTotal(templates.total);
    } catch (error) {
      console.error('Error loading flows:', error);
    } finally {
      setIsLoading(false);
    }
  }, [debouncedQuery]);

  // Debounce the search query before it drives server queries.
  useEffect(() => {
    const handle = setTimeout(() => setDebouncedQuery(searchQuery.trim()), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(handle);
  }, [searchQuery]);

  // Reload (reset to first page) whenever the debounced query changes; also runs on mount.
  useEffect(() => {
    loadFlows();
  }, [loadFlows]);

  // Append the next page of recent (non-template) flows.
  const loadMoreRecent = useCallback(async () => {
    setLoadingMoreRecent(true);
    try {
      const res = await flowService.queryFlows({
        isTemplate: false,
        keyword: debouncedQuery || undefined,
        sortOrder: 'desc',
        limit: PAGE_SIZE,
        offset: recentFlows.length,
      });
      setRecentFlows((prev) => [...prev, ...res.items]);
      setRecentTotal(res.total);
    } catch (error) {
      console.error('Error loading more recent flows:', error);
    } finally {
      setLoadingMoreRecent(false);
    }
  }, [debouncedQuery, recentFlows.length]);

  // Append the next page of template flows.
  const loadMoreTemplates = useCallback(async () => {
    setLoadingMoreTemplates(true);
    try {
      const res = await flowService.queryFlows({
        isTemplate: true,
        keyword: debouncedQuery || undefined,
        sortOrder: 'desc',
        limit: PAGE_SIZE,
        offset: templateFlows.length,
      });
      setTemplateFlows((prev) => [...prev, ...res.items]);
      setTemplateTotal(res.total);
    } catch (error) {
      console.error('Error loading more templates:', error);
    } finally {
      setLoadingMoreTemplates(false);
    }
  }, [debouncedQuery, templateFlows.length]);

  const hasMoreRecent = recentFlows.length < recentTotal;
  const hasMoreTemplates = templateFlows.length < templateTotal;

  // Event handlers
  const handleAccordionChange = useCallback((value: string[]) => {
    setOpenGroups(value);
  }, []);

  const handleCreateNewFlow = useCallback(() => {
    setCreateDialogOpen(true);
  }, []);

  const handleFlowCreated = useCallback(async (newFlow: Flow) => {
    // Open the new flow in a tab
    const tabData = TabService.createFlowTab(newFlow);
    openTab(tabData);

    // Remember it
    localStorage.setItem('lastSelectedFlowId', newFlow.id.toString());

    // Refresh the flows list to show the new flow
    await loadFlows();
  }, [openTab, loadFlows]);

  const handleSaveCurrentFlow = useCallback(async () => {
    try {
      const savedFlow = await saveCurrentFlowWithStates();
      if (savedFlow) {
        // Remember the saved flow
        localStorage.setItem('lastSelectedFlowId', savedFlow.id.toString());
        // Refresh the flows list
        await loadFlows();
        success(`"${savedFlow.name}" saved!`, 'flow-save');
      } else {
        error('Failed to save flow', 'flow-save-error');
      }
    } catch (err) {
      console.error('Failed to save flow:', err);
      error('Failed to save flow', 'flow-save-error');
    }
  }, [saveCurrentFlowWithStates, loadFlows, success, error]);

  const handleOpenFlowInTab = useCallback(async (flow: Flow) => {
    try {
      // Always fetch the full flow data including nodes, edges, and viewport
      // This ensures we have the latest data from the backend
      const fullFlow = await flowService.getFlow(flow.id);

      // Create tab data with configuration restoration only
      const createTabWithConfigRestore = (flowData: Flow) => {
        const tabData = TabService.createFlowTab(flowData);

        // Enhance the tab content to restore only configuration data when the tab is activated
        return {
          ...tabData,
          onActivate: () => {
            // NOTE: We intentionally do NOT restore nodeContextData here
            // Runtime execution data (messages, analysis, agent status) should start fresh

            // Restore internal states for each node (use-node-state data - configuration only)
            if (flowData.nodes) {
              flowData.nodes.forEach((node: any) => {
                if (node.data?.internal_state) {
                  setNodeInternalState(node.id, node.data.internal_state);
                }
              });
            }
          }
        };
      };

      // Check if tab is already open
      if (isTabOpen(flow.id.toString(), 'flow')) {
        // Tab exists - update it with fresh data and focus it
        const tabId = `flow-${flow.id}`;
        const enhancedTabData = createTabWithConfigRestore(fullFlow);

        // Update the existing tab with fresh data
        openTab({
          id: tabId,
          type: enhancedTabData.type,
          title: enhancedTabData.title,
          content: enhancedTabData.content,
          flow: enhancedTabData.flow,
          metadata: enhancedTabData.metadata,
        });

        // Trigger the enhanced restoration
        if (enhancedTabData.onActivate) {
          enhancedTabData.onActivate();
        }
      } else {
        // Create new tab with fresh data
        const enhancedTabData = createTabWithConfigRestore(fullFlow);
        openTab(enhancedTabData);

        // Trigger the enhanced restoration for new tab
        if (enhancedTabData.onActivate) {
          enhancedTabData.onActivate();
        }
      }

      // Remember the selected flow
      localStorage.setItem('lastSelectedFlowId', fullFlow.id.toString());
    } catch (err) {
      console.error('Failed to open flow in tab:', err);
      error('Failed to load flow data');
    }
  }, [isTabOpen, openTab, error]);

  const handleRefresh = useCallback(async () => {
    await loadFlows();
  }, [loadFlows]);

  const handleDeleteFlow = useCallback(async (flow: Flow) => {
    try {
      await flowService.deleteFlow(flow.id);

      // Close the tab if it's open
      const tabId = `flow-${flow.id}`;
      closeTab(tabId);

      // Clear node states for the deleted flow
      clearFlowNodeStates(flow.id.toString());

      // Remove from localStorage if it was the last selected
      const lastSelectedFlowId = localStorage.getItem('lastSelectedFlowId');
      if (lastSelectedFlowId === flow.id.toString()) {
        localStorage.removeItem('lastSelectedFlowId');
      }

      // Refresh the flows list
      await loadFlows();
    } catch (error) {
      console.error('Failed to delete flow:', error);
    }
  }, [loadFlows, closeTab]);

  return {
    // State
    searchQuery,
    isLoading,
    openGroups,
    createDialogOpen,

    // Server-driven groups
    recentFlows,
    templateFlows,
    recentTotal,
    templateTotal,
    hasMoreRecent,
    hasMoreTemplates,
    loadingMoreRecent,
    loadingMoreTemplates,

    // Actions
    setSearchQuery,
    setOpenGroups,
    setCreateDialogOpen,
    handleAccordionChange,
    handleCreateNewFlow,
    handleFlowCreated,
    handleSaveCurrentFlow,
    handleOpenFlowInTab,
    handleDeleteFlow,
    handleRefresh,
    loadMoreRecent,
    loadMoreTemplates,

    // Internal functions
    loadFlows,
    createDefaultFlow,
  };
}
