import { create } from 'zustand';
import type { HistoryRange } from '../types';

interface UIState {
  activeBrand: string;
  setActiveBrand: (brand: string) => void;
  daysFilter: HistoryRange;
  setDaysFilter: (days: HistoryRange) => void;
}

export const useUIStore = create<UIState>((set) => ({
  activeBrand: '',
  setActiveBrand: (brand) => set({ activeBrand: brand }),
  daysFilter: 30,
  setDaysFilter: (days) => set({ daysFilter: days }),
}));
