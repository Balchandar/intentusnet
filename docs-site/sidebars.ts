import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docsSidebar: [
    {
      type: 'category',
      label: 'Introduction',
      collapsed: false,
      items: [
        'introduction/what-is-intentusnet',
        'introduction/why-deterministic-execution',
        'introduction/mcp-compatibility',
      ],
    },
    {
      type: 'category',
      label: 'Runtime Guarantees',
      collapsed: false,
      link: {
        type: 'doc',
        id: 'guarantees/overview',
      },
      items: [
        'guarantees/deterministic-routing',
        'guarantees/crash-safe-execution',
        'guarantees/historical-retrieval',
        'guarantees/policy-filtering',
        'guarantees/observability-contract',
        'guarantees/limitations',
      ],
    },
    {
      type: 'category',
      label: 'Architecture',
      collapsed: false,
      link: {
        type: 'doc',
        id: 'architecture/overview',
      },
      items: [
        'architecture/data-flow',
        'architecture/determinism-model',
        'architecture/failure-model',
        'architecture/security-model',
      ],
    },
    {
      type: 'category',
      label: 'Getting Started',
      collapsed: false,
      items: [
        'getting-started/install',
        'getting-started/quickstart',
        'getting-started/walkthrough',
      ],
    },
    {
      type: 'category',
      label: 'CLI Reference',
      collapsed: true,
      link: {
        type: 'doc',
        id: 'cli/overview',
      },
      items: [
        'cli/run',
        'cli/inspect',
        'cli/retrieve',
        'cli/estimate',
        'cli/validate',
      ],
    },
    {
      type: 'category',
      label: 'Advanced Topics',
      collapsed: true,
      items: [
        'advanced/crash-safety-internals',
        'advanced/cost-estimation',
        'advanced/policy-design',
        'advanced/retrieval-semantics',
        'advanced/deterministic-routing-patterns',
      ],
    },
    {
      type: 'category',
      label: 'MCP Compatibility',
      collapsed: true,
      items: [
        'mcp/overview',
        'mcp/integration-patterns',
        'mcp/protocol-vs-runtime',
      ],
    },
    {
      type: 'category',
      label: 'Demos',
      collapsed: true,
      link: {
        type: 'doc',
        id: 'demos/overview',
      },
      items: [
        'demos/dangerous-target-filtering',
        'demos/crash-recovery',
        'demos/model-swap-prevention',
        'demos/project-blackbox',
      ],
    },
    {
      type: 'category',
      label: 'RFCs',
      collapsed: true,
      items: [
        'rfcs/index',
        'rfcs/rfc-0001-debuggable-llm-execution',
      ],
    },
    {
      type: 'category',
      label: 'Production Readiness',
      collapsed: true,
      items: [
        'production/observability',
        'production/security',
        'production/operations',
        'production/limitations',
      ],
    },
    {
      type: 'category',
      label: 'Release Notes',
      collapsed: true,
      items: [
        'release-notes/v4-5',
      ],
    },
  ],
};

export default sidebars;
