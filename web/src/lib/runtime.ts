/** Uses the bundled workspace data unless a live API is explicitly enabled. */
export const useDemoData = import.meta.env.VITE_USE_MOCK_AUTH !== 'false'
