import { useFlowManagementTabs } from '@/hooks/use-flow-management-tabs';
import { useResizable } from '@/hooks/use-resizable';
import { cn } from '@/lib/utils';
import { ReactNode, useEffect } from 'react';
import { FlowActions } from './flow-actions';
import { FlowCreateDialog } from './flow-create-dialog';
import { FlowList } from './flow-list';

interface LeftSidebarProps {
  children?: ReactNode;
  isCollapsed: boolean;
  onCollapse: () => void;
  onExpand: () => void;
  onWidthChange?: (width: number) => void;
}

export function LeftSidebar({
  isCollapsed,
  onWidthChange,
}: LeftSidebarProps) {
  // Use our custom hooks
  const { width, isDragging, elementRef, startResize } = useResizable({
    defaultWidth: 280,
    minWidth: 200,
    maxWidth: window.innerWidth * .90,
    side: 'left',
  });

  // Notify parent component of width changes
  useEffect(() => {
    onWidthChange?.(width);
  }, [width, onWidthChange]);
  
  // Use flow management hook with tabs
  const {
    searchQuery,
    isLoading,
    openGroups,
    createDialogOpen,
    recentFlows,
    templateFlows,
    recentTotal,
    templateTotal,
    hasMoreRecent,
    hasMoreTemplates,
    loadingMoreRecent,
    loadingMoreTemplates,
    setSearchQuery,
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
  } = useFlowManagementTabs();

  return (
    <div 
      ref={elementRef}
      className={cn(
        "h-full bg-panel flex flex-col relative pt-5 border",
        isCollapsed ? "shadow-lg" : "",
      )}
      style={{ 
        width: `${width}px`
      }}
    >
      <FlowActions
        onSave={handleSaveCurrentFlow}
        onCreate={handleCreateNewFlow}
      />
      
      <FlowList
        searchQuery={searchQuery}
        isLoading={isLoading}
        openGroups={openGroups}
        recentFlows={recentFlows}
        templateFlows={templateFlows}
        recentTotal={recentTotal}
        templateTotal={templateTotal}
        hasMoreRecent={hasMoreRecent}
        hasMoreTemplates={hasMoreTemplates}
        loadingMoreRecent={loadingMoreRecent}
        loadingMoreTemplates={loadingMoreTemplates}
        onSearchChange={setSearchQuery}
        onAccordionChange={handleAccordionChange}
        onLoadFlow={handleOpenFlowInTab}
        onDeleteFlow={handleDeleteFlow}
        onRefresh={handleRefresh}
        onLoadMoreRecent={loadMoreRecent}
        onLoadMoreTemplates={loadMoreTemplates}
      />
      
      {/* Resize handle - on the right side for left sidebar */}
      {!isDragging && (
        <div 
          className="absolute top-0 right-0 h-full w-1 cursor-ew-resize transition-all duration-150 z-10"
          onMouseDown={startResize}
        />
      )}

      <FlowCreateDialog
        isOpen={createDialogOpen}
        onClose={() => setCreateDialogOpen(false)}
        onFlowCreated={handleFlowCreated}
      />
    </div>
  );
} 