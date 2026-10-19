import { StrictMode } from 'react';
import { prerenderToNodeStream } from 'react-dom/static';
import { StaticRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider, dehydrate } from '@tanstack/react-query';
import { AppRoutes } from './App';
import { useAuthStore } from './store/authStore';
import { structuredData, type PublicPage } from './seo/metadata';
import type { BrandListResponse, BrandDetailResponse, CigarDetailResponse } from './types';
export interface CatalogSnapshot {
  schemaVersion: number;
  contentDigest: string;
  catalog: BrandListResponse;
  brands: Record<string, BrandDetailResponse>;
  cigars: Record<string, { path: string; note: string; data: CigarDetailResponse }>;
}

export async function renderPage(page: PublicPage, snapshot: CatalogSnapshot) {
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: false } } });
  if (page.kind === 'home') client.setQueryData(['brands'], snapshot.catalog);
  if (page.brandSlug) client.setQueryData(['brand', page.brandSlug], snapshot.brands[page.brandSlug]);
  if (page.cigarId) client.setQueryData(['cigar', String(page.cigarId)], snapshot.cigars[String(page.cigarId)].data);
  // Every generated page is anonymous. Authentication is checked independently after hydration.
  useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false });
  const state = dehydrate(client);
  // React also chunks large *synchronous* Suspense boundaries by default. A
  // static document must inline them, otherwise no-JS visitors see hidden text.
  const rendered = await prerenderToNodeStream(
    <StrictMode><QueryClientProvider client={client}><StaticRouter location={page.path}><AppRoutes /></StaticRouter></QueryClientProvider></StrictMode>,
    { progressiveChunkSize: Infinity, signal: AbortSignal.timeout(15000), onError(error) { throw error; } },
  );
  return { prelude: rendered.prelude, state, structured: structuredData(page) };
}
