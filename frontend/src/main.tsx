import { StrictMode } from 'react';
import { createRoot, hydrateRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider, hydrate } from '@tanstack/react-query';
import App from './App';
import './styles/globals.css';
import { useAuthStore } from './store/authStore';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      retry: 2,
      refetchOnWindowFocus: false,
    },
  },
});

const rootEl = document.getElementById('root');
if (!rootEl) throw new Error('Root element not found');

const initialState = document.getElementById('cdt-public-state');
if (initialState?.textContent) {
  hydrate(queryClient, JSON.parse(initialState.textContent));
  useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false });
}

const app = (
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>
);
if (initialState) hydrateRoot(rootEl, app);
else createRoot(rootEl).render(app);
