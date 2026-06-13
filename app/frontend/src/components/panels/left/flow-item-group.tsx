import { AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Flow } from '@/types/flow';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import FlowItem from './flow-item';

interface FlowItemGroupProps {
  title: string;
  flows: Flow[];
  onLoadFlow: (flow: Flow) => Promise<void>;
  onDeleteFlow: (flow: Flow) => Promise<void>;
  onRefresh: () => Promise<void>;
  currentFlowId?: number | null;
  // Pagination (optional)
  page?: number;
  totalPages?: number;
  total?: number;
  onPageChange?: (page: number) => void;
}

export function FlowItemGroup({
  title,
  flows,
  onLoadFlow,
  onDeleteFlow,
  onRefresh,
  currentFlowId,
  page,
  totalPages,
  total,
  onPageChange,
}: FlowItemGroupProps) {
  const groupId = title.toLowerCase().replace(/\s+/g, '-');
  const showPagination = totalPages !== undefined && totalPages > 1 && onPageChange;

  return (
    <AccordionItem value={groupId} className="border">
      <AccordionTrigger className="px-4 py-2 text-primary hover-bg hover:no-underline">
        <div className="flex items-center justify-between w-full">
          <span className="text-xs font-medium">{title}</span>
          <span className="text-xs text-muted-foreground">
            {total !== undefined ? total : flows.length}
          </span>
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

        {/* Pagination controls */}
        {showPagination && page !== undefined && (
          <div className="flex items-center justify-between px-4 py-2 border-t">
            <Button
              variant="ghost"
              size="sm"
              className="h-6 w-6 p-0"
              disabled={page <= 1}
              onClick={() => onPageChange(page - 1)}
            >
              <ChevronLeft className="h-3 w-3" />
            </Button>
            <span className="text-[10px] text-muted-foreground">
              {page} / {totalPages}
            </span>
            <Button
              variant="ghost"
              size="sm"
              className="h-6 w-6 p-0"
              disabled={page >= totalPages}
              onClick={() => onPageChange(page + 1)}
            >
              <ChevronRight className="h-3 w-3" />
            </Button>
          </div>
        )}
      </AccordionContent>
    </AccordionItem>
  );
}
