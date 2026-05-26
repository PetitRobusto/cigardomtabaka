import { create } from 'zustand';

interface UIState {
  activeBrand: string;
  setActiveBrand: (brand: string) => void;
  daysFilter: number;
  setDaysFilter: (days: number) => void;
}

export const useUIStore = create<UIState>((set) => ({
  activeBrand: '',
  setActiveBrand: (brand) => set({ activeBrand: brand }),
  daysFilter: 30,
  setDaysFilter: (days) => set({ daysFilter: days }),
}));
