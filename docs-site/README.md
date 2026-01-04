# IntentusNet Documentation Site

This is the official documentation website for IntentusNet, built with [Docusaurus 3](https://docusaurus.io/).

## Prerequisites

- Node.js 18.0 or higher
- npm or yarn

## Installation

```bash
cd docs-site
npm install
```

## Local Development

```bash
npm start
```

This command starts a local development server and opens up a browser window. Most changes are reflected live without having to restart the server.

## Build

```bash
npm run build
```

This command generates static content into the `build` directory and can be served using any static contents hosting service.

## Deployment

### GitHub Pages

1. Configure `docusaurus.config.ts`:
   ```typescript
   const config = {
     url: 'https://yourusername.github.io',
     baseUrl: '/intentusnet/',
     organizationName: 'yourusername',
     projectName: 'intentusnet',
   };
   ```

2. Deploy:
   ```bash
   npm run deploy
   ```

   Or use GitHub Actions:
   ```yaml
   name: Deploy to GitHub Pages

   on:
     push:
       branches: [main]

   jobs:
     deploy:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-node@v4
           with:
             node-version: 18

         - name: Install dependencies
           working-directory: docs-site
           run: npm ci

         - name: Build
           working-directory: docs-site
           run: npm run build

         - name: Deploy
           uses: peaceiris/actions-gh-pages@v3
           with:
             github_token: ${{ secrets.GITHUB_TOKEN }}
             publish_dir: docs-site/build
   ```

### Cloudflare Pages

1. Connect your GitHub repository to Cloudflare Pages

2. Configure build settings:
   - **Build command:** `cd docs-site && npm install && npm run build`
   - **Build output directory:** `docs-site/build`
   - **Root directory:** `/`

3. Environment variables (if needed):
   ```
   NODE_VERSION=18
   ```

4. For custom domains, update `docusaurus.config.ts`:
   ```typescript
   const config = {
     url: 'https://docs.intentusnet.dev',
     baseUrl: '/',
   };
   ```

## Project Structure

```
docs-site/
├── blog/                    # Blog posts
│   ├── authors.yml
│   └── *.mdx
├── docs/                    # Documentation pages
│   ├── introduction/
│   ├── guarantees/
│   ├── architecture/
│   ├── getting-started/
│   ├── cli/
│   ├── advanced/
│   ├── mcp/
│   ├── demos/
│   ├── rfcs/
│   └── production/
├── src/
│   ├── css/
│   │   └── custom.css      # Custom styles (Tailwind)
│   └── pages/
│       └── index.tsx       # Homepage
├── static/
│   └── img/                # Static images
├── docusaurus.config.ts    # Docusaurus configuration
├── sidebars.ts             # Sidebar configuration
├── tailwind.config.js      # Tailwind CSS configuration
└── package.json
```

## Features

- **Docusaurus 3** with TypeScript
- **Tailwind CSS** for custom styling
- **Dark mode** enabled by default
- **Full-text search** via @easyops-cn/docusaurus-search-local
- **Mermaid diagrams** for architecture documentation
- **MDX** for interactive documentation
- **Blog** for release notes and updates

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run `npm run build` to verify
5. Submit a pull request

## License

MIT - see the main IntentusNet repository for details.
