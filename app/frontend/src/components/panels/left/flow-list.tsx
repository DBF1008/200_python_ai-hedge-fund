import { FlowItemGroup } from '@/components/panels/left/flow-item-group';
import { SearchBox } from '@/components/panels/search-box';
import { Accordion } from '@/components/ui/accordion';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useTabsContext } from '@/contexts/tabs-context';
import { FlowTag } from '@/services/flow-service';
import { Flow } from '@/types/flow';
import { Filter, FolderOpen, X } from 'lucide-react';
import { useState } from 'react';

interface FlowListProps {
  searchQuery: string;
  isLoading: boolean;
  openGroups: string[];

  // Tag filter
  selectedTag: string | null;
  availableTags: FlowTag[];
  onTagSelect: (tag: string | null) => void;

  // Recent flows (non-templates)
  recentFlows: Flow[];
  recentPage: number;
  recentTotal: number;
  recentTotalPages: number;
  isLoadingRecent: boolean;
  onRecentPageChange: (page: number) => void;

  // Template flows
  templateFlows: Flow[];
  templatePage: number;
  templateTotal: number;
  templateTotalPages: number;
  isLoadingTemplates: boolean;
  onTemplatePageChange: (page: number) => void;

  onSearchChange: (query: string) => void;
  onAccordionChange: (value: string[]) => void;
  onLoadFlow: (flow: Flow) => Promise<void>;
  onDeleteFlow: (flow: Flow) => Promise<void>;
  onRefresh: () => Promise<void>;
}

export function FlowList({
  searchQuery,
  isLoading,
  openGroups,
  selectedTag,
  availableTags,
  onTagSelect,
  recentFlows,
  recentPage,
  recentTotal,
  recentTotalPages,
  isLoadingRecent,
  onRecentPageChange,
  templateFlows,
  templatePage,
  templateTotal,
  templateTotalPages,
  isLoadingTemplates,
  onTemplatePageChange,
  onSearchChange,
  onAccordionChange,
  onLoadFlow,
  onDeleteFlow,
  onRefresh,
}: FlowListProps) {
  const { tabs, activeTabId } = useTabsContext();
  const [showTagFilter, setShowTagFilter] = useState(false);

  // Only consider a flow active if the current active tab is a flow tab with that flow's ID
  const getActiveFlowId = (): number | null => {
    const activeTab = tabs.find(tab => tab.id === activeTabId);

    if (!activeTab || activeTab.type !== 'flow') {
      return null;
    }

    return activeTab.flow?.id || null;
  };

  const activeFlowId = getActiveFlowId();
  const hasFlows = recentTotal > 0 || templateTotal > 0;
  const hasSearchResults = recentFlows.length > 0 || templateFlows.length > 0;

  return (
    <div className="flex-grow overflow-auto text-primary scrollbar-thin scrollbar-thumb-ramp-grey-700">
      {/* Search bar with filter toggle */}
      <div className="relative">
        <SearchBox
          value={searchQuery}
          onChange={onSearchChange}
          placeholder="Search flows..."
        />
        {availableTags.length > 0 && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2 z-20">
            <Button
              variant="ghost"
              size="sm"
              className="h-6 w-6 p-0"
              onClick={() => setShowTagFilter(!showTagFilter)}
              title="Filter by tag"
            >
              <Filter className={`h-3 w-3 ${selectedTag ? 'text-blue-500' : 'text-muted-foreground'}`} />
            </Button>
          </div>
        )}
      </div>

      {/* Tag filter chips */}
      {(showTagFilter || selectedTag) && availableTags.length > 0 && (
        <div className="px-3 pb-2 flex flex-wrap gap-1">
          {selectedTag && (
            <Badge
              variant="success"
              className="text-[10px] cursor-pointer flex items-center gap-1"
              onClick={() => onTagSelect(null)}
            >
              {selectedTag}
              <X className="h-2.5 w-2.5" />
            </Badge>
          )}
          {availableTags
            .filter(t => t.name !== selectedTag)
            .slice(0, 12)
            .map(tag => (
              <Badge
                key={tag.name}
                variant="secondary"
                className="text-[10px] cursor-pointer hover:bg-accent"
                onClick={() => onTagSelect(tag.name)}
              >
                {tag.name}
                <span className="ml-1 text-muted-foreground">({tag.count})</span>
              </Badge>
            ))}
        </div>
      )}

      {/* Flow groups */}
      {(isLoading || isLoadingRecent || isLoadingTemplates) ? (
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
              onLoadFlow={onLoadFlow}
              onDeleteFlow={onDeleteFlow}
              onRefresh={onRefresh}
              currentFlowId={activeFlowId}
              page={recentPage}
              totalPages={recentTotalPages}
              total={recentTotal}
              onPageChange={onRecentPageChange}
            />
          )}

          {templateFlows.length > 0 && (
            <FlowItemGroup
              key="templates"
              title="Templates"
              flows={templateFlows}
              onLoadFlow={onLoadFlow}
              onDeleteFlow={onDeleteFlow}
              onRefresh={onRefresh}
              currentFlowId={activeFlowId}
              page={templatePage}
              totalPages={templateTotalPages}
              total={templateTotal}
              onPageChange={onTemplatePageChange}
            />
          )}
        </Accordion>
      )}

      {/* Empty states */}
      {!isLoading && !isLoadingRecent && !isLoadingTemplates && !hasSearchResults && (
        <div className="text-center py-8 text-muted-foreground text-sm">
          {!hasFlows && !searchQuery && !selectedTag ? (
            <div className="space-y-2">
              <FolderOpen size={32} className="mx-auto text-muted-foreground" />
              <div>No flows saved yet</div>
              <div className="text-xs">Create your first flow to get started</div>
            </div>
          ) : (
            'No flows match your filters'
          )}
        </div>
      )}
    </div>
  );
}
