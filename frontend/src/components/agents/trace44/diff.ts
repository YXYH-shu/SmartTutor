/**
 * 句子级 diff：用于共情回应"注入对比"视图。
 * 只做前缀 LCS 对齐，不引入外部依赖；文本规模为十几句，O(n·m) 足够。
 */

export type DiffKind = 'same' | 'added' | 'removed';

export interface DiffSegment {
  text: string;
  kind: DiffKind;
}

function splitSentences(text: string): string[] {
  return text
    .split(/(?<=[。！？!?；;\n])/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/** 对齐 before/after 句子序列：added = after 中新注入的内容 */
export function diffSegments(before: string, after: string): DiffSegment[] {
  const a = splitSentences(before);
  const b = splitSentences(after);
  const n = a.length;
  const m = b.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const segments: DiffSegment[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      segments.push({ text: b[j], kind: 'same' });
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      segments.push({ text: a[i], kind: 'removed' });
      i++;
    } else {
      segments.push({ text: b[j], kind: 'added' });
      j++;
    }
  }
  while (i < n) segments.push({ text: a[i++], kind: 'removed' });
  while (j < m) segments.push({ text: b[j++], kind: 'added' });
  return segments;
}
