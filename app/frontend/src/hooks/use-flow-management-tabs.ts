import { useFlowContext } from '@/contexts/flow-context';
import { useNodeContext } from '@/contexts/node-context';
import { useTabsContext } from '@/contexts/tabs-context';
import {
  clearFlowNodeStates,
  getNodeInternalState,
  setNodeInternalState
} from '@/hooks/use-node-state';
import { useToastManager } from '@/hooks/use-toast-manager';
import { flowService, FlowListParams, FlowTag } from '@/services/flow-service';
import { TabService } from '@/services/tab-service';
import { Flow } from '@/types/flow';
import { useCallback, useEffect, useRef, useState } from 'react';

const PAGE_SIZE_RECENT = 10;
const PAGE_SIZE_TEMPLATES = 20;
const SEARCH_DEBOUNCE_MS = 300;

export interface UseFlowManagementTabsReturn {
  // State
  searchQuery: string;
  selectedTag: string | null;
  availableTags: FlowTag[];
  isLoading: boolean;
  isLoadingTags: boolean;
  openGroups: string[];
  createDialogOpen: boolean;

  // Recent flows (non-templates)
  recentFlows: Flow[];
  recentPage: number;
  recentTotal: number;
  recentTotalPages: number;
  isLoadingRecent: boolean;

  // Template flows
  templateFlows: Flow[];
  templatePage: number;
  templateTotal: number;
  templateTotalPages: number;
  isLoadingTemplates: boolean;

  // Legacy compatibility
  flows: Flow[];
  filteredFlows: Flow[];

  // Actions
  setSearchQuery: (query: string) => void;
  setSelectedTag: (tag: string | null) => void;
  setOpenGroups: (groups: string[]) => void;
  setCreateDialogOpen: (open: boolean) => void;
  handleAccordionChange: (value: string[]) => void;
  handleCreateNewFlow: () => void;
  handleFlowCreated: (newFlow: Flow) => Promise<void>;
  handleSaveCurrentFlow: () => Promise<void>;
  handleOpenFlowInTab: (flow: Flow) => Promise<void>;
  handleDeleteFlow: (flow: Flow) => Promise<void>;
  handleRefresh: () => Promise<void>;

  // Pagination
  goToRecentPage: (page: number) => void;
  goToTemplatePage: (page: number) => void;

  // Internal functions (for testing/advanced use)
  loadFlows: () => Promise<void>;
  loadTags: () => Promise<void>;
  createDefaultFlow: () => Promise<void>;
}

export function useFlowManagementTabs(): UseFlowManagementTabsReturn {
  // Get flow context, node context, tabs context, and toast manager
  const { saveCurrentFlow, reactFlowInstance, currentFlowId } = useFlowContext();
  const { exportNodeContextData } = useNodeContext();
  const { openTab, isTabOpen, closeTab } = useTabsContext();
  const { success, error } = useToastManager();

  // Shared filter state
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [availableTags, setAvailableTags] = useState<FlowTag[]>([]);
  const [isLoadingTags, setIsLoadingTags] = useState(false);

  // UI state
  const [openGroups, setOpenGroups] = useState<string[]>(['recent-flows']);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);

  // Recent flows (non-templates) state
  const [recentFlows, setRecentFlows] = useState<Flow[]>([]);
  const [recentPage, setRecentPage] = useState(1);
  const [recentTotal, setRecentTotal] = useState(0);
  const [recentTotalPages, setRecentTotalPages] = useState(0);
  const [isLoadingRecent, setIsLoadingRecent] = useState(false);

  // Template flows state
  const [templateFlows, setTemplateFlows] = useState<Flow[]>([]);
  const [templatePage, setTemplatePage] = useState(1);
  const [templateTotal, setTemplateTotal] = useState(0);
  const [templateTotalPages, setTemplateTotalPages] = useState(0);
  const [isLoadingTemplates, setIsLoadingTemplates] = useState(false);

  // Debounced search value
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Debounce search input
  useEffect(() => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    debounceTimerRef.current = setTimeout(() => {
      setDebouncedSearch(searchQuery);
    }, SEARCH_DEBOUNCE_MS);

    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, [searchQuery]);

  // Reset pages when filters change
  useEffect(() => {
    setRecentPage(1);
    setTemplatePage(1);
  }, [debouncedSearch, selectedTag]);

  // Fetch recent flows (non-templates)
  const fetchRecentFlows = useCallback(async (page: number) => {
    setIsLoadingRecent(true);
    try {
      const params: FlowListParams = {
        search: debouncedSearch || undefined,
        is_template: false,
        tag: selectedTag || undefined,
        sort_by: 'updated_at',
        sort_order: 'desc',
        page,
        page_size: PAGE_SIZE_RECENT,
      };
      const result = await flowService.getFlowsFiltered(params);
      setRecentFlows(result.items);
      setRecentTotal(result.total);
      setRecentTotalPages(result.total_pages);
      setRecentPage(result.page);
    } catch (err) {
      console.error('Error loading recent flows:', err);
    } finally {
      setIsLoadingRecent(false);
    }
  }, [debouncedSearch, selectedTag]);

  // Fetch template flows
  const fetchTemplateFlows = useCallback(async (page: number) => {
    setIsLoadingTemplates(true);
    try {
      const params: FlowListParams = {
        search: debouncedSearch || undefined,
        is_template: true,
        tag: selectedTag || undefined,
        sort_by: 'updated_at',
        sort_order: 'desc',
        page,
        page_size: PAGE_SIZE_TEMPLATES,
      };
      const result = await flowService.getFlowsFiltered(params);
      setTemplateFlows(result.items);
      setTemplateTotal(result.total);
      setTemplateTotalPages(result.total_pages);
      setTemplatePage(result.page);
    } catch (err) {
      console.error('Error loading template flows:', err);
    } finally {
      setIsLoadingTemplates(false);
    }
  }, [debouncedSearch, selectedTag]);

  // Load tags
  const loadTags = useCallback(async () => {
    setIsLoadingTags(true);
    try {
      const tags = await flowService.getTags();
      setAvailableTags(tags);
    } catch (err) {
      console.error('Error loading tags:', err);
    } finally {
      setIsLoadingTags(false);
    }
  }, []);

  // Load both groups
  const loadFlows = useCallback(async () => {
    await Promise.all([
      fetchRecentFlows(recentPage),
      fetchTemplateFlows(templatePage),
    ]);
  }, [fetchRecentFlows, fetchTemplateFlows, recentPage, templatePage]);

  // Re-fetch when debounced search or tag changes (pages already reset to 1)
  useEffect(() => {
    fetchRecentFlows(1);
    fetchTemplateFlows(1);
  }, [debouncedSearch, selectedTag, fetchRecentFlows, fetchTemplateFlows]);

  // Load tags on mount
  useEffect(() => {
    loadTags();
  }, [loadTags]);

  // Pagination handlers
  const goToRecentPage = useCallback((page: number) => {
    fetchRecentFlows(page);
  }, [fetchRecentFlows]);

  const goToTemplatePage = useCallback((page: number) => {
    fetchTemplateFlows(page);
  }, [fetchTemplateFlows]);

  // Legacy compatibility: combined flows and filteredFlows
  const flows = [...recentFlows, ...templateFlows];
  const filteredFlows = flows;

  // Combined loading state
  const isLoading = isLoadingRecent || isLoadingTemplates;

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
      setRecentTotalPages(1);

      // Open the default flow in a tab
      const tabData = TabService.createFlowTab(defaultFlow);
      openTab(tabData);
    } catch (error) {
      console.error('Failed to create default flow:', error);
    }
  }, [reactFlowInstance, openTab]);

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

    // Refresh the flows list and tags
    await Promise.all([
      fetchRecentFlows(1),
      fetchTemplateFlows(1),
      loadTags(),
    ]);
  }, [openTab, fetchRecentFlows, fetchTemplateFlows, loadTags]);

  const handleSaveCurrentFlow = useCallback(async () => {
    try {
      const savedFlow = await saveCurrentFlowWithStates();
      if (savedFlow) {
        // Remember the saved flow
        localStorage.setItem('lastSelectedFlowId', savedFlow.id.toString());
        // Refresh the flows list and tags
        await Promise.all([
          fetchRecentFlows(recentPage),
          fetchTemplateFlows(templatePage),
          loadTags(),
        ]);
        success(`"${savedFlow.name}" saved!`, 'flow-save');
      } else {
        error('Failed to save flow', 'flow-save-error');
      }
    } catch (err) {
      console.error('Failed to save flow:', err);
      error('Failed to save flow', 'flow-save-error');
    }
  }, [saveCurrentFlowWithStates, fetchRecentFlows, fetchTemplateFlows, loadTags, recentPage, templatePage, success, error]);

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
    await Promise.all([
      fetchRecentFlows(recentPage),
      fetchTemplateFlows(templatePage),
      loadTags(),
    ]);
  }, [fetchRecentFlows, fetchTemplateFlows, loadTags, recentPage, templatePage]);

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

      // Refresh the flows list and tags
      await Promise.all([
        fetchRecentFlows(recentPage),
        fetchTemplateFlows(templatePage),
        loadTags(),
      ]);
    } catch (error) {
      console.error('Failed to delete flow:', error);
    }
  }, [fetchRecentFlows, fetchTemplateFlows, loadTags, recentPage, templatePage, closeTab]);

  return {
    // State
    searchQuery,
    selectedTag,
    availableTags,
    isLoading,
    isLoadingTags,
    openGroups,
    createDialogOpen,

    // Recent flows
    recentFlows,
    recentPage,
    recentTotal,
    recentTotalPages,
    isLoadingRecent,

    // Template flows
    templateFlows,
    templatePage,
    templateTotal,
    templateTotalPages,
    isLoadingTemplates,

    // Legacy compatibility
    flows,
    filteredFlows,

    // Actions
    setSearchQuery,
    setSelectedTag,
    setOpenGroups,
    setCreateDialogOpen,
    handleAccordionChange,
    handleCreateNewFlow,
    handleFlowCreated,
    handleSaveCurrentFlow,
    handleOpenFlowInTab,
    handleDeleteFlow,
    handleRefresh,

    // Pagination
    goToRecentPage,
    goToTemplatePage,

    // Internal functions
    loadFlows,
    loadTags,
    createDefaultFlow,
  };
}
