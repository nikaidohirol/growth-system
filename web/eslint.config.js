// 最小实用规则集：只拦真问题（未用变量/危险模式/依赖数组），不做风格约束——与后端 ruff 同哲学
import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist', 'node_modules', 'vite.config.*'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // 数据获取后写入 state 是本项目的既有加载模式（未引入 react-query），
      // v6 该规则会把此类同步链全部报错；降为 warn 保留提示，待数据层重构后收紧
      'react-hooks/set-state-in-effect': 'warn',
      'no-irregular-whitespace': ['error', { skipStrings: true, skipTemplates: true, skipComments: true }],
      'react-refresh/only-export-components': 'off',   // 页面文件常伴随常量导出，不适用
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      '@typescript-eslint/no-explicit-any': 'off',     // antd 表格 render 场景 any 收益低
    },
  },
)
