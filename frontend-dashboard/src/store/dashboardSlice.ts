import { createSlice, type PayloadAction } from '@reduxjs/toolkit';

export type CardId = 'lights' | 'water' | 'carbon' | 'energy' | 'footfall';

export interface DashboardState {
  cardVisibility: Record<CardId, boolean>;
}

const initialState: DashboardState = {
  cardVisibility: {
    lights: true,
    water: true,
    carbon: true,
    energy: true,
    footfall: true,
  },
};

const dashboardSlice = createSlice({
  name: 'dashboard',
  initialState,
  reducers: {
    toggleCardVisibility: (state, action: PayloadAction<CardId>) => {
      const cardId = action.payload;
      state.cardVisibility[cardId] = !state.cardVisibility[cardId];
    },
    setCardVisibility: (
      state,
      action: PayloadAction<{ cardId: CardId; visible: boolean }>,
    ) => {
      const { cardId, visible } = action.payload;
      state.cardVisibility[cardId] = visible;
    },
  },
});

export const { toggleCardVisibility, setCardVisibility } = dashboardSlice.actions;
export default dashboardSlice.reducer;
