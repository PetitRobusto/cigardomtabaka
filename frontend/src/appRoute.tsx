import App from './App';
import { PageError } from './components/shared/PageError';

export const appRoute = { path: '*', Component: App, ErrorBoundary: PageError };
