import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';
import clsx from 'clsx';
import React from 'react';

function HeroSection() {
  return (
    <header className="bg-gradient-to-br from-slate-900 via-blue-900 to-blue-800 text-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20 lg:py-28">
        <div className="text-center">
          <div className="inline-flex items-center px-4 py-2 rounded-full bg-blue-500/20 border border-blue-400/30 mb-6">
            <span className="text-blue-300 text-sm font-medium">v1.3.0 Released</span>
          </div>
          <h1 className="text-4xl lg:text-6xl font-bold tracking-tight mb-6">
            <span className="block">The model may change.</span>
            <span className="block text-blue-400">The execution must not.</span>
          </h1>
          <p className="text-xl lg:text-2xl text-slate-300 max-w-3xl mx-auto mb-10 leading-relaxed">
            IntentusNet is a deterministic execution runtime for multi-agent AI systems.
            Make routing, fallback, and failure behavior{' '}
            <strong className="text-white">replayable, explainable, and production-operable</strong>.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link
              to="/docs/getting-started/install"
              className="inline-flex items-center justify-center px-8 py-4 rounded-lg bg-blue-600 text-white font-semibold hover:bg-blue-700 transition-colors shadow-lg hover:shadow-xl no-underline"
            >
              Get Started
              <svg className="ml-2 w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </Link>
            <Link
              to="/docs/guarantees/overview"
              className="inline-flex items-center justify-center px-8 py-4 rounded-lg border-2 border-white/30 text-white font-semibold hover:bg-white/10 transition-colors no-underline"
            >
              View Guarantees
            </Link>
            <a
              href="https://github.com/Balchandar/intentusnet"
              className="inline-flex items-center justify-center px-8 py-4 rounded-lg bg-slate-800 text-white font-semibold hover:bg-slate-700 transition-colors no-underline"
              target="_blank"
              rel="noopener noreferrer"
            >
              <svg className="w-5 h-5 mr-2" fill="currentColor" viewBox="0 0 24 24">
                <path fillRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" clipRule="evenodd" />
              </svg>
              GitHub
            </a>
          </div>
        </div>
      </div>
    </header>
  );
}

function ProblemSection() {
  const problems = [
    {
      title: 'Non-deterministic routing',
      description: 'Agent selection varies between runs due to model drift, parameter changes, or race conditions.',
      icon: '🎲',
    },
    {
      title: 'Silent failures',
      description: 'Agents fail mid-execution with no record of partial state or clear recovery path.',
      icon: '🔇',
    },
    {
      title: 'Unreplayable executions',
      description: 'Cannot reproduce failures or debug issues because outputs depend on live model calls.',
      icon: '🔄',
    },
    {
      title: 'Policy blindspots',
      description: 'Blocking one dangerous target blocks entire intents instead of allowing safe subset execution.',
      icon: '🚫',
    },
    {
      title: 'Observability gaps',
      description: 'No structured logs, no execution traces, no way to audit what happened post-hoc.',
      icon: '👁️',
    },
    {
      title: 'Recovery nightmares',
      description: 'Crash during multi-step execution leaves system in undefined state with no resume capability.',
      icon: '💥',
    },
  ];

  return (
    <section className="py-20 bg-slate-50 dark:bg-slate-900">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-16">
          <h2 className="text-3xl lg:text-4xl font-bold text-slate-900 dark:text-white mb-4">
            Why AI Systems Fail in Production
          </h2>
          <p className="text-lg text-slate-600 dark:text-slate-400 max-w-2xl mx-auto">
            Multi-agent systems introduce failure modes that traditional software patterns don't address.
          </p>
        </div>
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {problems.map((problem, idx) => (
            <div
              key={idx}
              className="bg-white dark:bg-slate-800 rounded-xl p-6 border border-slate-200 dark:border-slate-700 hover:shadow-lg transition-shadow"
            >
              <div className="text-3xl mb-4">{problem.icon}</div>
              <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-2">
                {problem.title}
              </h3>
              <p className="text-slate-600 dark:text-slate-400 text-sm">
                {problem.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function GuaranteesSection() {
  const guarantees = [
    {
      title: 'Deterministic Routing',
      description: 'Same input always produces same agent selection order. No implicit retries, no hidden state.',
      link: '/docs/guarantees/deterministic-routing',
      color: 'blue',
    },
    {
      title: 'Crash-Safe Execution',
      description: 'Execution state persisted before side effects. Recovery resumes from last safe checkpoint.',
      link: '/docs/guarantees/crash-safe-execution',
      color: 'green',
    },
    {
      title: 'Replayable by Default',
      description: 'Every execution recorded with stable hashes. Replay returns recorded outputs without re-running models.',
      link: '/docs/guarantees/replayability',
      color: 'purple',
    },
    {
      title: 'Partial Policy Filtering',
      description: 'Block dangerous targets while allowing safe execution to continue. Filter, don\'t block wholesale.',
      link: '/docs/guarantees/policy-filtering',
      color: 'amber',
    },
    {
      title: 'CLI-First Observability',
      description: 'Structured JSON output, grepable logs, SSH-friendly inspection. No dashboard required.',
      link: '/docs/guarantees/observability-contract',
      color: 'teal',
    },
    {
      title: 'Explicit Failure Modes',
      description: 'Every error categorized with typed error codes. No silent failures, no swallowed exceptions.',
      link: '/docs/guarantees/limitations',
      color: 'red',
    },
  ];

  const colorClasses: Record<string, string> = {
    blue: 'border-l-blue-500 bg-blue-50 dark:bg-blue-900/20',
    green: 'border-l-green-500 bg-green-50 dark:bg-green-900/20',
    purple: 'border-l-purple-500 bg-purple-50 dark:bg-purple-900/20',
    amber: 'border-l-amber-500 bg-amber-50 dark:bg-amber-900/20',
    teal: 'border-l-teal-500 bg-teal-50 dark:bg-teal-900/20',
    red: 'border-l-red-500 bg-red-50 dark:bg-red-900/20',
  };

  return (
    <section className="py-20 bg-white dark:bg-slate-800">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-16">
          <h2 className="text-3xl lg:text-4xl font-bold text-slate-900 dark:text-white mb-4">
            What IntentusNet Guarantees
          </h2>
          <p className="text-lg text-slate-600 dark:text-slate-400 max-w-2xl mx-auto">
            Explicit contracts for production multi-agent systems. No hand-waving, no "best effort".
          </p>
        </div>
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {guarantees.map((guarantee, idx) => (
            <Link
              key={idx}
              to={guarantee.link}
              className={clsx(
                'block rounded-lg p-6 border-l-4 hover:shadow-md transition-shadow no-underline',
                colorClasses[guarantee.color]
              )}
            >
              <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-2">
                {guarantee.title}
              </h3>
              <p className="text-slate-600 dark:text-slate-400 text-sm">
                {guarantee.description}
              </p>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}

function NotAgentFrameworkSection() {
  return (
    <section className="py-20 bg-gradient-to-br from-amber-50 to-orange-50 dark:from-amber-900/20 dark:to-orange-900/20">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="bg-white dark:bg-slate-800 rounded-2xl p-8 lg:p-12 shadow-lg border border-amber-200 dark:border-amber-800">
          <div className="flex items-start gap-6">
            <div className="flex-shrink-0">
              <div className="w-16 h-16 rounded-full bg-amber-100 dark:bg-amber-900/50 flex items-center justify-center">
                <svg className="w-8 h-8 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
            </div>
            <div>
              <h2 className="text-2xl lg:text-3xl font-bold text-slate-900 dark:text-white mb-4">
                IntentusNet is NOT an Agent Framework
              </h2>
              <div className="prose prose-slate dark:prose-invert max-w-none">
                <p className="text-slate-600 dark:text-slate-400 mb-4">
                  IntentusNet does not build agents, define prompts, call LLMs, or orchestrate workflows.
                  It is a <strong className="text-slate-900 dark:text-white">runtime layer</strong> that sits beneath
                  agent frameworks to make their execution deterministic and debuggable.
                </p>
                <ul className="space-y-2 text-slate-600 dark:text-slate-400">
                  <li><strong className="text-slate-900 dark:text-white">Agent frameworks</strong> define what agents do and how they think</li>
                  <li><strong className="text-slate-900 dark:text-white">IntentusNet</strong> ensures that execution is reproducible, inspectable, and recoverable</li>
                </ul>
                <p className="text-slate-600 dark:text-slate-400 mt-4">
                  Think of it as systemd for AI agents: it doesn't write your service, but it ensures
                  reliable execution, restart semantics, and observability.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function HowItWorksSection() {
  return (
    <section className="py-20 bg-slate-50 dark:bg-slate-900">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-16">
          <h2 className="text-3xl lg:text-4xl font-bold text-slate-900 dark:text-white mb-4">
            How IntentusNet Works
          </h2>
          <p className="text-lg text-slate-600 dark:text-slate-400 max-w-2xl mx-auto">
            A deterministic execution pipeline from intent to completion.
          </p>
        </div>
        <div className="bg-white dark:bg-slate-800 rounded-2xl p-8 shadow-lg border border-slate-200 dark:border-slate-700">
          <div className="grid lg:grid-cols-6 gap-4">
            {[
              { step: '1', title: 'Intent', desc: 'Declare what to do' },
              { step: '2', title: 'Route', desc: 'Deterministic agent selection' },
              { step: '3', title: 'Policy', desc: 'Filter dangerous targets' },
              { step: '4', title: 'Execute', desc: 'Record before effects' },
              { step: '5', title: 'Persist', desc: 'WAL-backed state' },
              { step: '6', title: 'Inspect', desc: 'Replay & debug' },
            ].map((item, idx) => (
              <div key={idx} className="text-center">
                <div className="w-12 h-12 rounded-full bg-blue-600 text-white font-bold flex items-center justify-center mx-auto mb-3">
                  {item.step}
                </div>
                <h4 className="font-semibold text-slate-900 dark:text-white mb-1">{item.title}</h4>
                <p className="text-sm text-slate-600 dark:text-slate-400">{item.desc}</p>
                {idx < 5 && (
                  <div className="hidden lg:block absolute -right-2 top-1/2 transform -translate-y-1/2">
                    <svg className="w-4 h-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
        <div className="mt-12 text-center">
          <pre className="inline-block text-left bg-slate-900 text-slate-100 p-6 rounded-lg text-sm overflow-x-auto">
            <code>{`$ intentusnet run --intent "power-off-for-maintenance"
{
  "execution_id": "exec-a7b3c9d2",
  "status": "completed",
  "route": {
    "strategy": "FALLBACK",
    "agents_tried": ["hvac-controller", "lighting-controller"],
    "selected": "hvac-controller"
  },
  "policy": {
    "filtered": ["cctv-controller"],
    "reason": "security_exclusion"
  },
  "replayable": true
}`}</code>
          </pre>
        </div>
      </div>
    </section>
  );
}

function TerminologySection() {
  const terms = [
    { term: 'Intent', desc: 'A declarative unit of work (name + version + payload)' },
    { term: 'Route', desc: 'The deterministic selection of which agent handles an intent' },
    { term: 'Policy', desc: 'Rules that allow/deny/filter intent execution targets' },
    { term: 'Execution ID', desc: 'Unique identifier for each execution instance' },
    { term: 'WAL', desc: 'Write-Ahead Log for crash-safe state persistence' },
    { term: 'Replay', desc: 'Return recorded output without re-executing models' },
  ];

  return (
    <section className="py-20 bg-white dark:bg-slate-800">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-12">
          <h2 className="text-2xl lg:text-3xl font-bold text-slate-900 dark:text-white mb-4">
            Core Terminology
          </h2>
        </div>
        <div className="grid md:grid-cols-2 gap-4">
          {terms.map((item, idx) => (
            <div
              key={idx}
              className="flex items-start gap-4 p-4 rounded-lg bg-slate-50 dark:bg-slate-900"
            >
              <code className="flex-shrink-0 px-2 py-1 bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300 rounded text-sm font-mono">
                {item.term}
              </code>
              <p className="text-slate-600 dark:text-slate-400 text-sm">{item.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function CTASection() {
  return (
    <section className="py-20 bg-gradient-to-br from-blue-900 to-slate-900 text-white">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
        <h2 className="text-3xl lg:text-4xl font-bold mb-6">
          Ready to make your agents deterministic?
        </h2>
        <p className="text-xl text-slate-300 mb-10 max-w-2xl mx-auto">
          Start with a simple pip install. No configuration required for basic usage.
        </p>
        <div className="bg-slate-800 rounded-lg p-4 inline-block mb-10">
          <code className="text-lg text-green-400">pip install intentusnet</code>
        </div>
        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <Link
            to="/docs/getting-started/quickstart"
            className="inline-flex items-center justify-center px-8 py-4 rounded-lg bg-blue-600 text-white font-semibold hover:bg-blue-700 transition-colors no-underline"
          >
            Read the Quickstart
          </Link>
          <Link
            to="/docs/demos/overview"
            className="inline-flex items-center justify-center px-8 py-4 rounded-lg border-2 border-white/30 text-white font-semibold hover:bg-white/10 transition-colors no-underline"
          >
            See Demos
          </Link>
        </div>
      </div>
    </section>
  );
}

export default function Home(): React.JSX.Element {
  const { siteConfig } = useDocusaurusContext();
  return (
    <Layout
      title="Deterministic AI Runtime"
      description="IntentusNet is a deterministic execution runtime for multi-agent AI systems. Make routing, fallback, and failure behavior replayable, explainable, and production-operable."
    >
      <HeroSection />
      <ProblemSection />
      <GuaranteesSection />
      <NotAgentFrameworkSection />
      <HowItWorksSection />
      <TerminologySection />
      <CTASection />
    </Layout>
  );
}
