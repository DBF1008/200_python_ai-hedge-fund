import { FlowItemGroup } from '@/components/panels/left/flow-item-group';
import { SearchBox } from '@/components/panels/search-box';
import { Accordion } from '@/components/ui/accordion';
import { useTabsContext } from '@/contexts/tabs-context';
import { Flow } from '@/types/flow';
import { FolderOpen } from 'lucide-react';

interface FlowListProps {
  searchQuery: string;
  isLoading: boolean;
  openGroups: string[];
  recentFlows: Flow[];
  templateFlows: Flow[];
  recentTotal: number;
  templateTotal: number;
  hasMoreRecent: boolean;
  hasMoreTemplates: boolean;
  loadingMoreRecent: boolean;
  loadingMoreTemplates: boolean;
  onSearchChange: (query: string) => void;
  onAccordionChange: (value: string[]) => void;
  onLoadFlow: (flow: Flow) => Promise<void>;
  onDeleteFlow: (flow: Flow) => Promise<void>;
  onRefresh: () => Promise<void>;
  onLoadMoreRecent: () => void;
  onLoadMoreTemplates: () => void;
}

export function FlowList({
  searchQuery,
  isLoading,
  openGroups,
  recentFlows,
  templateFlows,
  recentTotal,
  templateTotal,
  hasMoreRecent,
  hasMoreTemplates,
  loadingMoreRecent,
  loadingMoreTemplates,
  onSearchChange,
  onAccordionChange,
  onLoadFlow,
  onDeleteFlow,
  onRefresh,
  onLoadMoreRecent,
  onLoadMoreTemplates,
}: FlowListProps) {
  const { tabs, activeTabId } = useTabsContext();

  // Only consider a flow active if the current active tab is a flow tab with that flow's ID
  const getActiveFlowId = (): number | null => {
    const activeTab = tabs.find(tab => tab.id === activeTabId);

    // If no active tab or active tab is not a flow tab, no flow should be active
    if (!activeTab || activeTab.type !== 'flow') {
      return null;
    }

    // Return the flow ID from the active flow tab
    return activeTab.flow?.id || null;
  };

  const activeFlowId = getActiveFlowId();
  const hasAnyResults = recentFlows.length > 0 || templateFlows.length > 0;

  return (
    <div className="flex-grow overflow-auto text-primary scrollbar-thin scrollbar-thumb-ramp-grey-700">
      <SearchBox
        value={searchQuery}
        onChange={onSearchChange}
        placeholder="Search flows..."
      />

      {isLoading ? (
        <div className="flex items-center justify-center py-8">
          <div className="text-muted-foreground text-sm">Loading flows...</div>
        </div>
      ) : (
        <Accordion
          type="multiple"
          className="w-full"
          value={openGroups}
          onValueChange={onAccordionChange}
        >
          {recentFlows.length > 0 && (
            <FlowItemGroup
              key="recent-flows"
              title="Recent Flows"
              flows={recentFlows}
              total={recentTotal}
              hasMore={hasMoreRecent}
              onLoadMore={onLoadMoreRecent}
              isLoadingMore={loadingMoreRecent}
              onLoadFlow={onLoadFlow}
              onDeleteFlow={onDeleteFlow}
              onRefresh={onRefresh}
              currentFlowId={activeFlowId}
            />
          )}

          {templateFlows.length > 0 && (
            <FlowItemGroup
              key="templates"
              title="Templates"
              flows={templateFlows}
              total={templateTotal}
              hasMore={hasMoreTemplates}
              onLoadMore={onLoadMoreTemplates}
              isLoadingMore={loadingMoreTemplates}
              onLoadFlow={onLoadFlow}
              onDeleteFlow={onDeleteFlow}
              onRefresh={onRefresh}
              currentFlowId={activeFlowId}
            />
          )}
        </Accordion>
      )}

      {!isLoading && !hasAnyResults && (
        <div className="text-center py-8 text-muted-foreground text-sm">
          {searchQuery ? (
            'No flows match your search'
          ) : (
            <div className="space-y-2">
              <FolderOpen size={32} className="mx-auto text-muted-foreground" />
              <div>No flows saved yet</div>
              <div className="text-xs">Create your first flow to get started</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
