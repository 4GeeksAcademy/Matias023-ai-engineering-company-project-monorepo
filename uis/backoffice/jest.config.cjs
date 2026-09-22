/**
 * Jest configuration for the backoffice frontend.
 *
 * Minimal suite for TypeScript auth utilities:
 * - environment: node (no jsdom / React Testing Library)
 * - ts-jest transform for TypeScript
 * - only picks up *.test.ts files under src/
 *
 * NOTE: package.json declares "type": "module", so the config file is
 * deliberately named jest.config.cjs (CommonJS) to keep Jest loading simple
 * without ESM runtime complications.
 *
 * ts-jest uses an inline tsconfig so we do NOT need to touch the project's
 * Vite-oriented tsconfig files (bundler resolution, verbatimModuleSyntax, etc.).
 */

/** @type {import('ts-jest').JestConfigWithTsJest} */
module.exports = {
  testEnvironment: 'node',

  roots: ['<rootDir>/src'],

  testMatch: ['**/*.test.ts'],

  transform: {
    '^.+\\.tsx?$': [
      'ts-jest',
      {
        tsconfig: {
          target: 'es2023',
          module: 'commonjs',
          moduleResolution: 'node',
          lib: ['ES2023'],
          esModuleInterop: true,
          skipLibCheck: true,
          forceConsistentCasingInFileNames: true,
          verbatimModuleSyntax: false,
        },
      },
    ],
  },

  collectCoverageFrom: ['src/auth/authApi.ts'],
};