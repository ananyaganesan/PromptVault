/** Example workspace data is limited to tests or an explicit local opt-in. */
export const useDemoData = import.meta.env.MODE === 'test' || import.meta.env.VITE_USE_DEMO_DATA === 'true'
