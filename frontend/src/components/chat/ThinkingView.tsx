import { useState, useEffect, useRef } from 'react';
import { ChevronDown, ChevronRight, Cpu } from 'lucide-react';
import { cn } from '@/utils/cn';
import { renderValue } from '@/utils/jsonTree';
import type { ThinkingStep } from '@/types';

function StepRow({
  step,
  isActive,
  showBorder,
}: {
  step: ThinkingStep;
  isActive: boolean;
  showBorder: boolean;
}) {
  const [open, setOpen] = useState(true);
  const isRunning = step.status === 'running';

  let parsed: unknown;
  try {
    parsed = JSON.parse(step.content);
  } catch {
    parsed = step.content;
  }

  return (
    <div
      className={cn(
        'px-3 py-2',
        showBorder && 'border-b border-white/[0.04]',
      )}
    >
      <button
        onClick={() => !isRunning && setOpen((v) => !v)}
        className="flex w-full items-center gap-2 text-xs"
      >
        {isRunning ? (
          <span className="relative inline-flex h-1.5 w-4 items-center">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary-400 opacity-75" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-primary-400" />
          </span>
        ) : (
          <span
            className={cn(
              'inline-block h-1.5 w-1.5 rounded-full',
              isActive
                ? 'bg-primary-400 animate-pulse'
                : 'bg-green-400',
            )}
          />
        )}
        <span className="font-medium text-gray-300">
          {step.label || step.step}
        </span>
        {!isRunning && (
          <span className="ml-auto text-gray-500">
            {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </span>
        )}
      </button>
      {isRunning && (
        <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-white/5">
          <div className="h-full animate-progress rounded-full bg-gradient-to-r from-primary-500 to-primary-400 bg-[length:200%_100%]" />
        </div>
      )}
      {!isRunning && open && (
        <div className="mt-1.5 text-xs leading-relaxed text-gray-400">
          {renderValue(parsed)}
        </div>
      )}
    </div>
  );
}

interface ThinkingViewProps {
  steps: ThinkingStep[];
}

export function ThinkingView({ steps }: ThinkingViewProps) {
  const [expanded, setExpanded] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (expanded && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [steps.length, expanded]);

  if (steps.length === 0) return null;

  return (
    <div>
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-1.5 rounded-md px-1 py-1 text-xs text-gray-400 hover:text-gray-300 transition-colors"
      >
        <Cpu size={13} className="text-gray-500" />
        <span className="font-medium">思考过程</span>
        <span className="ml-auto">
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
      </button>

      {expanded && (
        <div
          ref={containerRef}
          className="mt-1 max-h-72 overflow-y-auto rounded-lg border border-white/[0.04] bg-black/20"
        >
          {steps.map((step, idx) => (
            <StepRow
              key={idx}
              step={step}
              isActive={idx === steps.length - 1}
              showBorder={idx < steps.length - 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}
