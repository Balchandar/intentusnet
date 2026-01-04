import type * as Preset from '@docusaurus/preset-classic';
import type { Config } from '@docusaurus/types';
import { themes as prismThemes } from 'prism-react-renderer';

const config: Config = {
  title: 'IntentusNet',
  tagline: 'Deterministic execution runtime for multi-agent systems',
  favicon: 'img/favicon.ico',

  // Production URL
  url: 'https://intentusnet.com',
  // Set the /<baseUrl>/ pathname under which your site is served
  // For GitHub pages deployment, it is often '/<projectName>/'
  baseUrl: '/',

  // GitHub pages deployment config
  organizationName: 'Balchandar',
  projectName: 'intentusnet',

  onBrokenLinks: 'throw',

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  markdown: {
    mermaid: true,
    hooks: {
      onBrokenMarkdownLinks: 'warn',
    }
  },

  themes: ['@docusaurus/theme-mermaid'],

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          editUrl: 'https://github.com/Balchandar/intentusnet/tree/main/docs-site/',
          showLastUpdateTime: false,
          showLastUpdateAuthor: false,
          // Versioning
          lastVersion: 'current',
          versions: {
            current: {
              label: '0.3.x',
              path: '',
            },
          },
        },
        blog: {
          showReadingTime: true,
          feedOptions: {
            type: ['rss', 'atom'],
            xslt: true,
          },
          editUrl: 'https://github.com/Balchandar/intentusnet/tree/main/docs-site/',
          blogSidebarTitle: 'All posts',
          blogSidebarCount: 'ALL',
        },
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  plugins: [
    async function tailwindPlugin(context, options) {
      return {
        name: 'docusaurus-tailwindcss',
        configurePostCss(postcssOptions) {
          postcssOptions.plugins.push(require('tailwindcss'));
          postcssOptions.plugins.push(require('autoprefixer'));
          return postcssOptions;
        },
      };
    },
    [
      require.resolve('@easyops-cn/docusaurus-search-local'),
      {
        hashed: true,
        language: ['en'],
        highlightSearchTermsOnTargetPage: true,
        explicitSearchResultPath: true,
        indexDocs: true,
        indexBlog: true,
        indexPages: true,
        docsRouteBasePath: '/docs',
        blogRouteBasePath: '/blog',
      },
    ],
  ],

  themeConfig: {
    image: 'img/intentusnet-social-card.png',
    navbar: {
      title: 'IntentusNet',
      logo: {
        alt: 'IntentusNet Logo',
        src: 'img/logo.svg',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'docsSidebar',
          position: 'left',
          label: 'Docs',
        },
        {
          to: '/docs/guarantees/overview',
          label: 'Guarantees',
          position: 'left',
        },
        {
          to: '/docs/architecture/overview',
          label: 'Architecture',
          position: 'left',
        },
        {
          to: '/docs/demos/overview',
          label: 'Demos',
          position: 'left',
        },
        {
          to: '/docs/cli/overview',
          label: 'CLI',
          position: 'left',
        },
        {
          to: '/docs/rfcs/',
          label: 'RFCs',
          position: 'left',
        },
        {
          to: '/blog',
          label: 'Blog',
          position: 'left',
        },
        {
          href: 'https://github.com/Balchandar/intentusnet',
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Documentation',
          items: [
            {
              label: 'Getting Started',
              to: '/docs/getting-started/install',
            },
            {
              label: 'Runtime Guarantees',
              to: '/docs/guarantees/overview',
            },
            {
              label: 'CLI Reference',
              to: '/docs/cli/overview',
            },
          ],
        },
        {
          title: 'Architecture',
          items: [
            {
              label: 'System Overview',
              to: '/docs/architecture/overview',
            },
            {
              label: 'Determinism Model',
              to: '/docs/architecture/determinism-model',
            },
            {
              label: 'Security Model',
              to: '/docs/architecture/security-model',
            },
          ],
        },
        {
          title: 'Resources',
          items: [
            {
              label: 'Demos',
              to: '/docs/demos/overview',
            },
            {
              label: 'RFCs',
              to: '/docs/rfcs/',
            },
            {
              label: 'Blog',
              to: '/blog',
            },
          ],
        },
        {
          title: 'Community',
          items: [
            {
              label: 'GitHub',
              href: 'https://github.com/Balchandar/intentusnet',
            },
            {
              label: 'Issues',
              href: 'https://github.com/Balchandar/intentusnet/issues',
            },
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} IntentusNet Contributors. Built with Docusaurus.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['python', 'bash', 'json', 'yaml', 'toml'],
    },
    mermaid: {
      theme: { light: 'neutral', dark: 'dark' },
    },
    colorMode: {
      defaultMode: 'dark',
      disableSwitch: false,
      respectPrefersColorScheme: true,
    },
    docs: {
      sidebar: {
        hideable: true,
        autoCollapseCategories: true,
      },
    },
    tableOfContents: {
      minHeadingLevel: 2,
      maxHeadingLevel: 4,
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
