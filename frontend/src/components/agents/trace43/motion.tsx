/**
 * 4.3 抽屉的动效：样式、逐项入场延迟、数字滚动、进度条生长。
 * 关键帧统一加 t43- 前缀，避免与全局样式冲突；系统开启“减少动态效果”时全部关闭。
 */
import { useEffect, useState, type CSSProperties } from 'react';
import { cn } from '@/utils/cn';

export function MotionStyles() {
  return (
    <style>{`
      @keyframes t43-rise { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
      @keyframes t43-pop { 0% { opacity: 0; transform: scale(.3); } 70% { transform: scale(1.18); } 100% { opacity: 1; transform: scale(1); } }
      @keyframes t43-bar { from { width: 0; } to { width: var(--t43-w, 100%); } }
      @keyframes t43-line { from { transform: scaleY(0); } to { transform: scaleY(1); } }
      @keyframes t43-ping { 0% { opacity: .5; transform: scale(1); } 100% { opacity: 0; transform: scale(2); } }
      @keyframes t43-flow { 0% { transform: translateY(-120%); opacity: 0; } 25% { opacity: 1; } 100% { transform: translateY(320%); opacity: 0; } }
      @keyframes t43-glow { 0%, 100% { box-shadow: 0 0 0 0 rgb(var(--color-accent-rgb) / 0); } 50% { box-shadow: 0 0 12px 0 rgb(var(--color-accent-rgb) / .3); } }
      @keyframes t43-sweep { from { background-position: -180% 0; } to { background-position: 180% 0; } }
      @keyframes t43-blur-in { from { opacity: 0; filter: blur(5px); } to { opacity: 1; filter: blur(0); } }
      @keyframes t43-float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-2px); } }
      @keyframes t43-seg { from { transform: scaleX(0); } to { transform: scaleX(1); } }
      .t43-rise { animation: t43-rise .5s var(--ease-out) both; }
      .t43-pop { animation: t43-pop .45s var(--ease-spring) both; }
      .t43-bar { animation: t43-bar .9s var(--ease-out) both; }
      .t43-line { transform-origin: top; animation: t43-line .5s var(--ease-out) both; }
      .t43-ping { animation: t43-ping 1.6s ease-out 2 both; }
      .t43-flow { animation: t43-flow 1.8s ease-in-out infinite; }
      .t43-glow { animation: t43-glow 2.8s ease-in-out infinite; }
      .t43-blur-in { animation: t43-blur-in .7s ease-out both; }
      .t43-float { animation: t43-float 2.4s ease-in-out infinite; }
      .t43-seg { transform-origin: left; animation: t43-seg .45s var(--ease-out) both; }
      .t43-sweep { background-size: 60% 100%; background-repeat: no-repeat; animation: t43-sweep 2.6s ease-in-out 1 both; }
      @media (prefers-reduced-motion: reduce) {
        .t43-rise, .t43-pop, .t43-bar, .t43-line, .t43-ping, .t43-flow, .t43-glow,
        .t43-blur-in, .t43-float, .t43-seg, .t43-sweep { animation: none !important; }
      }
    `}</style>
  );
}

/** 逐项入场延迟：第 i 项晚 step 毫秒 */
export function delay(i: number, step = 70, base = 0): CSSProperties {
  return { animationDelay: `${base + i * step}ms` };
}

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true;
}

/** 数字从 0 滚动到 target */
export function useCountUp(target: number, duration = 800, startDelay = 0): number {
  const [value, setValue] = useState(0);
  useEffect(() => {
    if (prefersReducedMotion()) {
      setValue(target);
      return;
    }
    let raf = 0;
    let begin = 0;
    const timer = window.setTimeout(() => {
      const tick = (t: number) => {
        if (!begin) begin = t;
        const p = Math.min(1, (t - begin) / duration);
        setValue(Math.round(target * (1 - Math.pow(1 - p, 3))));
        if (p < 1) raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    }, startDelay);
    return () => {
      window.clearTimeout(timer);
      cancelAnimationFrame(raf);
    };
  }, [target, duration, startDelay]);
  return value;
}

/** 进度条：入场时从 0 生长到 percent */
export function AnimatedBar({
  percent,
  barClassName,
  startDelay = 0,
  className,
}: {
  percent: number;
  barClassName: string;
  startDelay?: number;
  className?: string;
}) {
  const w = Math.max(0, Math.min(100, percent));
  return (
    <div className={cn('h-1.5 w-full overflow-hidden rounded-full bg-bg-elevated', className)}>
      <div
        className={cn('t43-bar h-full rounded-full', barClassName)}
        style={{ '--t43-w': `${w}%`, width: `${w}%`, animationDelay: `${startDelay}ms` } as CSSProperties}
      />
    </div>
  );
}
