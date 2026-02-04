# Plan: Documentation Site with MkDocs Material

## Overview

Create a professional documentation site using MkDocs with Material theme, following the Diataxis framework for structure.

## Why MkDocs Material?

- **Python-native**: Install with pip, configure with YAML, write in Markdown
- **Industry standard**: Used by FastAPI, Pydantic, Typer (same ecosystem as Aegra)
- **Free**: All features now available (formerly paid "Insiders" features)
- **CLI auto-docs**: mkdocs-click plugin generates CLI docs from Click commands
- **API auto-docs**: mkdocstrings generates API docs from Python docstrings
- **No JavaScript build toolchain required**

## Documentation Structure (Diataxis Framework)

```
docs/
├── index.md                    # Home page with quick overview
├── getting-started/
│   ├── index.md               # Getting started overview
│   ├── quickstart.md          # < 10 min first success
│   ├── installation.md        # All installation methods
│   └── first-agent.md         # Build your first agent tutorial
├── tutorials/
│   ├── index.md               # Tutorials overview
│   ├── react-agent.md         # Build a ReAct agent
│   ├── human-in-the-loop.md   # Add approval gates
│   ├── multi-agent.md         # Hierarchical agents
│   └── streaming.md           # Real-time streaming
├── how-to/
│   ├── index.md               # How-to guides overview
│   ├── authentication.md      # Configure auth (JWT/OAuth)
│   ├── custom-routes.md       # Add FastAPI endpoints
│   ├── observability.md       # Set up tracing
│   ├── semantic-store.md      # Vector search
│   ├── production.md          # Deploy to production
│   └── migrations.md          # Database migrations
├── reference/
│   ├── index.md               # Reference overview
│   ├── cli.md                 # CLI commands (auto-generated)
│   ├── api.md                 # API endpoints (auto-generated)
│   ├── configuration.md       # aegra.json & env vars
│   └── sdk.md                 # LangGraph SDK usage
├── concepts/
│   ├── index.md               # Concepts overview
│   ├── architecture.md        # How Aegra works
│   ├── agent-protocol.md      # Agent Protocol explained
│   └── langgraph.md           # LangGraph integration
├── changelog.md               # Release history
└── contributing.md            # Contribution guide
```

## Implementation Tasks

### 1. Install MkDocs and Plugins

```bash
uv add --dev mkdocs-material mkdocs-click mkdocstrings[python] mkdocs-gen-files mkdocs-literate-nav
```

### 2. Create mkdocs.yml Configuration

```yaml
site_name: Aegra
site_url: https://aegra.dev
site_description: Self-hosted LangGraph Platform alternative
repo_url: https://github.com/ibbybuilds/aegra
repo_name: ibbybuilds/aegra

theme:
  name: material
  palette:
    - scheme: default
      primary: indigo
      accent: indigo
      toggle:
        icon: material/brightness-7
        name: Switch to dark mode
    - scheme: slate
      primary: indigo
      accent: indigo
      toggle:
        icon: material/brightness-4
        name: Switch to light mode
  features:
    - navigation.instant
    - navigation.tracking
    - navigation.tabs
    - navigation.sections
    - navigation.expand
    - navigation.top
    - search.suggest
    - search.highlight
    - content.code.copy
    - content.code.annotate

plugins:
  - search
  - mkdocstrings:
      handlers:
        python:
          options:
            show_source: true
            show_root_heading: true
  - mkdocs-click  # Auto-generate CLI docs

markdown_extensions:
  - pymdownx.highlight:
      anchor_linenums: true
  - pymdownx.superfences
  - pymdownx.tabbed:
      alternate_style: true
  - admonition
  - pymdownx.details
  - attr_list
  - md_in_html
  - tables

nav:
  - Home: index.md
  - Getting Started:
    - getting-started/index.md
    - Quickstart: getting-started/quickstart.md
    - Installation: getting-started/installation.md
    - First Agent: getting-started/first-agent.md
  - Tutorials:
    - tutorials/index.md
    - ReAct Agent: tutorials/react-agent.md
    - Human-in-the-Loop: tutorials/human-in-the-loop.md
    - Multi-Agent: tutorials/multi-agent.md
  - How-To Guides:
    - how-to/index.md
    - Authentication: how-to/authentication.md
    - Custom Routes: how-to/custom-routes.md
    - Observability: how-to/observability.md
    - Semantic Store: how-to/semantic-store.md
    - Production: how-to/production.md
  - Reference:
    - reference/index.md
    - CLI: reference/cli.md
    - API: reference/api.md
    - Configuration: reference/configuration.md
  - Concepts:
    - concepts/index.md
    - Architecture: concepts/architecture.md
  - Changelog: changelog.md
  - Contributing: contributing.md
```

### 3. Auto-Generate CLI Documentation

Create `docs/reference/cli.md`:

```markdown
# CLI Reference

::: mkdocs-click
    :module: aegra_cli.cli
    :command: cli
    :prog_name: aegra
    :depth: 2
```

### 4. Auto-Generate API Reference

Create `docs/reference/api.md`:

```markdown
# API Reference

::: aegra_api.api.assistants
::: aegra_api.api.threads
::: aegra_api.api.runs
::: aegra_api.api.store
```

### 5. Set Up GitHub Pages Deployment

```yaml
# .github/workflows/docs.yml
name: Deploy Docs

on:
  push:
    branches: [main]
    paths:
      - 'docs/**'
      - 'mkdocs.yml'
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install mkdocs-material mkdocs-click mkdocstrings[python]
      - run: mkdocs build --strict
      - uses: actions/upload-pages-artifact@v3
        with:
          path: site

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/deploy-pages@v4
        id: deployment
```

### 6. Migrate Existing Documentation

Move and reorganize existing docs:

| Current File | New Location |
|-------------|--------------|
| docs/developer-guide.md | Split into getting-started/ and how-to/ |
| docs/authentication.md | how-to/authentication.md |
| docs/custom-routes.md | how-to/custom-routes.md |
| docs/observability.md | how-to/observability.md |
| docs/semantic-store.md | how-to/semantic-store.md |
| docs/production-docker-setup.md | how-to/production.md |
| docs/configuration.md | reference/configuration.md |
| docs/dependencies.md | reference/configuration.md (merge) |

### 7. Create Missing Content

#### High Priority:
- [ ] Home page (index.md) with hero section
- [ ] Quickstart guide (< 10 min)
- [ ] Installation guide (pip, docker, source)
- [ ] First agent tutorial

#### Medium Priority:
- [ ] Architecture explanation
- [ ] Agent Protocol overview
- [ ] Streaming tutorial
- [ ] Multi-agent tutorial

#### Low Priority:
- [ ] SDK reference
- [ ] Changelog automation
- [ ] API playground integration

## Content Guidelines

### Writing Style
- Use simple, direct language
- Active voice ("Run the command" not "The command should be run")
- Include code examples for every concept
- Show expected output after commands

### Code Examples
- Must be copy-paste ready
- Include all imports
- Use realistic variable names (not foo/bar)
- Test all examples in CI

### Page Structure
```markdown
# Page Title

Brief description of what this page covers.

## Prerequisites
- What the reader needs to know/have

## Main Content
Step-by-step or organized sections

## Next Steps
Links to related pages
```

## Timeline

### Phase 1: Foundation (Week 1)
- [ ] Set up MkDocs with Material theme
- [ ] Create basic structure
- [ ] Migrate existing docs
- [ ] Deploy to GitHub Pages

### Phase 2: Core Content (Week 2-3)
- [ ] Write quickstart guide
- [ ] Write installation guide
- [ ] Create first agent tutorial
- [ ] Auto-generate CLI reference

### Phase 3: Expansion (Week 4+)
- [ ] Add remaining tutorials
- [ ] Create architecture diagrams
- [ ] Add search improvements
- [ ] Add versioning support

## Hosting Options

1. **GitHub Pages** (Free, recommended for start)
   - Custom domain: docs.aegra.dev
   - Auto-deploy on push

2. **Netlify** (Free tier)
   - Preview deployments for PRs
   - Better caching

3. **Vercel** (Free tier)
   - Edge caching
   - Analytics

## Success Metrics

- Time to first success: < 10 minutes
- All code examples pass CI tests
- Search covers all pages
- Mobile-responsive design

## References

- [MkDocs Material](https://squidfunk.github.io/mkdocs-material/)
- [mkdocs-click](https://github.com/mkdocs/mkdocs-click)
- [mkdocstrings](https://mkdocstrings.github.io/)
- [Diataxis Framework](https://diataxis.fr/)
- [FastAPI docs (example)](https://fastapi.tiangolo.com/)
- [Pydantic docs (example)](https://docs.pydantic.dev/)
