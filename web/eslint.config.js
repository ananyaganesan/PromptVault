import js from '@eslint/js'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist', 'coverage', 'node_modules'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['src/**/*.{ts,tsx}'],
    plugins: { 'react-hooks': reactHooks, 'react-refresh': reactRefresh },
    languageOptions: {
      globals: {
        AbortSignal: 'readonly',
        document: 'readonly',
        fetch: 'readonly',
        sessionStorage: 'readonly',
        window: 'readonly',
      },
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // Prototype stores intentionally update in event handlers until the API is connected.
      'react-hooks/immutability': 'off',
      'react-hooks/purity': 'off',
      'react-refresh/only-export-components': 'off',
    },
  },
)
