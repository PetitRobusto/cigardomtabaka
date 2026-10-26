import type { ReactNode } from "react";

function sourceUrl(value: string): string | null {
  if (!/^https:\/\//i.test(value)) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.hostname && !url.username && !url.password ? url.href : null;
  } catch {
    return null;
  }
}

/** A deliberately small Markdown subset: inline HTTPS links, otherwise plain text. */
export function InlineSourceLinks({ text }: { text: string }) {
  const content: ReactNode[] = [];
  let cursor = 0;
  for (const match of text.matchAll(/\[([^[\]\n]+)\]\(([^\s()]+)\)/g)) {
    const start = match.index!;
    content.push(text.slice(cursor, start));
    const href = sourceUrl(match[2]);
    content.push(href
      ? <a key={start} href={href} target="_blank" rel="noopener noreferrer">{match[1]}</a>
      : match[0]);
    cursor = start + match[0].length;
  }
  content.push(text.slice(cursor));
  return <>{content}</>;
}
