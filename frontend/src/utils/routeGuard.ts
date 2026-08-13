export type StaffRouteDecision = 'loading' | 'login' | 'home' | 'allow';

export interface StaffRouteAuthState {
  isLoading: boolean;
  isAuthenticated: boolean;
  isStaff: boolean;
}

export function decideStaffRoute(state: StaffRouteAuthState): StaffRouteDecision {
  if (state.isLoading) return 'loading';
  if (!state.isAuthenticated) return 'login';
  if (!state.isStaff) return 'home';
  return 'allow';
}
