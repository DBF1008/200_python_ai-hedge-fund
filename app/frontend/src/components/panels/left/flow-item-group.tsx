import { AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Flow } from '@/types/flow';
import FlowItem from './flow-item';

interface FlowItemGroupProps {
  title: string;
  flows: Flow[];
  onLoadFlow: (flow: Flow) => Promise<void>;
  onDeleteFlow: (flow: Flow) => Promise<void>;
  onRefresh: () => Promise<void>;
  currentFlowId?: number | null;
  total?: number;
  hasMore?: boolean;
  onLoadMore?: () => void;
  isLoadingMore?: boolean;
}

export function FlowItemGroup({
  title,
  flows,
  onLoadFlow,
  onDeleteFlow,
  onRefresh,
  currentFlowId,
  total,
  hasMore,
  onLoadMore,
  isLoadingMore,
}: FlowItemGroupProps) {
  const groupId = title.toLowerCase().replace(/\s+/g, '-');
  const countLabel = total != null && total > flows.length ? `${flows.length} / ${total}` : `${flows.length}`;

  return (
    <AccordionItem value={groupId} className="border">
      <AccordionTrigger className="px-4 py-2 text-primary hover-bg hover:no-underline">
        <div className="flex items-center justify-between w-full">
          <span className="text-xs font-medium">{title}</span>
          <span className="text-xs text-muted-foreground">({countLabel})</span>
        </div>
      </AccordionTrigger>
      <AccordionContent className="px-0 pb-0">
        <div className="space-y-1">
          {flows.map((flow, index) => (
            <div key={flow.id}>
              <FlowItem
                flow={flow}
                onLoadFlow={onLoadFlow}
                onDeleteFlow={onDeleteFlow}
                onRefresh={onRefresh}
                isActive={currentFlowId === flow.id}
              />
              {index < flows.length - 1 && (
                <Separator className="mx-4" />
              )}
            </div>
          ))}
        </div>
        {hasMore && onLoadMore && (
          <div className="px-2 py-2">
            <Button
              variant="ghost"
              size="sm"
              className="w-full text-xs text-muted-foreground hover:text-primary"
              onClick={onLoadMore}
              disabled={isLoadingMore}
            >
              {isLoadingMore ? 'Loading...' : 'Load more'}
            </Button>
          </div>
        )}
      </AccordionContent>
    </AccordionItem>
  );
}
