// U192: the main process is plain CommonJS that nothing type-checks. A single
// undeclared identifier (`token` instead of `updateToken()`) silently broke the
// auto-installer for every release: the ReferenceError landed in a catch that
// degraded to "open the release page", so the app looked like it was working.
//
// `no-undef` is the whole point of this config — the rest is just telling
// ESLint which globals a CommonJS Electron main process legitimately has.
export default [
  {
    files: ['*.cjs'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'commonjs',
      globals: {
        require: 'readonly', module: 'writable', exports: 'writable',
        process: 'readonly', console: 'readonly', Buffer: 'readonly',
        __dirname: 'readonly', __filename: 'readonly', fetch: 'readonly',
        URL: 'readonly', TextDecoder: 'readonly', TextEncoder: 'readonly',
        AbortController: 'readonly',
        setTimeout: 'readonly', clearTimeout: 'readonly',
        setInterval: 'readonly', clearInterval: 'readonly',
        setImmediate: 'readonly', queueMicrotask: 'readonly',
      },
    },
    linterOptions: { reportUnusedDisableDirectives: true },
    rules: {
      'no-undef': 'error',
      'no-unused-vars': ['warn', { args: 'none', varsIgnorePattern: '^_' }],
    },
  },
]
