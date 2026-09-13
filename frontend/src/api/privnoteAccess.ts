export type AccessAction = 'qr_open' | 'copy_card' | 'copy_account';
export interface AccessNote {
  token: string; title: string; note_type: string; created_at: string;
  view_count: number; last_opened_at?: string | null;
}
export interface AccessPage {
  page: number; pages: number; count: number; retention_days: number;
}
export interface AccessEntry {
  id: number; created_at: string; visitor: string; ip: string | null;
  device: string; browser: string; actor: 'customer' | 'staff' | 'bot';
  event: string; is_revisit: boolean;
}
export interface AccessDetail extends AccessPage {
  note: AccessNote; results: AccessEntry[];
  summary: { opens: number; visitors: number; revisits: number; last_opened_at: string | null };
}
async function read<T>(path: string): Promise<T> {
  const response = await fetch(path, { credentials: 'same-origin' });
  if (!response.ok) throw new Error(response.status === 403 ? '仅限已登录工作人员' : '访问记录加载失败，请重试');
  return response.json();
}
export const fetchAccessNotes = (q: string, type: string, page: number) =>
  read<AccessPage & { results: AccessNote[] }>(`/privnote/api/access/?${new URLSearchParams({ q, type, page: String(page) })}`);
export const fetchAccessDetail = (token: string, audience: string, page: number) =>
  read<AccessDetail>(`/privnote/api/access/${encodeURIComponent(token)}/?${new URLSearchParams({ audience, page: String(page) })}`);

/** Best effort: failed observations must never interrupt a customer action. */
export function trackAccessAction(token: string, trackingToken: string | undefined, event: AccessAction): void {
  if (!token || !trackingToken || !['qr_open', 'copy_card', 'copy_account'].includes(event)) return;
  void privnoteDeviceHeaders().then(headers => fetch(`/api/privnote/${encodeURIComponent(token)}/events/`, {
    method: 'POST', credentials: 'same-origin', keepalive: true,
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify({ event, tracking_token: trackingToken }),
  })).catch(() => undefined);
}

type ModelNavigator = Navigator & { userAgentData?: { getHighEntropyValues: (hints: string[]) => Promise<{ model?: unknown }> } };
let deviceHeaders: Promise<Record<string, string>> | undefined;
export function privnoteDeviceHeaders(): Promise<Record<string, string>> {
  if (!deviceHeaders) {
    deviceHeaders = (async (): Promise<Record<string, string>> => {
      try {
        const hints = (navigator as ModelNavigator).userAgentData;
        if (!hints) return {};
        const data = await Promise.race([
          hints.getHighEntropyValues(['model']),
          new Promise<{ model?: unknown }>(resolve => setTimeout(() => resolve({}), 150)),
        ]);
        // HTTP headers must be ASCII. Unsupported browsers simply omit this.
        if (typeof data.model === 'string' && /^[\x20-\x7e]{1,100}$/.test(data.model)) {
          return { 'X-Privnote-Model': data.model };
        }
      } catch { /* Browser privacy settings may refuse model hints. */ }
      return {};
    })();
  }
  return deviceHeaders;
}
