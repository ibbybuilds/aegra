# Plan: Auto Version Increment with Semantic Release

## Overview

Implement automatic version bumping and PyPI publishing using `python-semantic-release` based on Conventional Commits.

## Why Semantic Release?

- Aegra already uses Conventional Commits (`fix:`, `feat:`, etc.)
- Automatic version bumping based on commit messages
- Supports monorepos (aegra-api, aegra-cli, aegra)
- Integrates with GitHub Actions and PyPI trusted publishing

## Version Bump Rules

| Commit Prefix | Version Bump | Example |
|--------------|--------------|---------|
| `fix:` | PATCH (0.0.X) | Bug fixes |
| `perf:` | PATCH (0.0.X) | Performance improvements |
| `feat:` | MINOR (0.X.0) | New features |
| `BREAKING CHANGE:` in body | MAJOR (X.0.0) | Breaking API changes |

## Implementation Tasks

### 1. Install Dependencies

```bash
# Add to dev dependencies
uv add --dev python-semantic-release
```

### 2. Configure Each Package

#### libs/aegra-api/pyproject.toml

```toml
[tool.semantic_release]
version_toml = ["pyproject.toml:project.version"]
branch = "main"
build_command = "uv build"
commit_parser = "conventional"
tag_format = "aegra-api-v{version}"

[tool.semantic_release.commit_parser_options]
minor_tags = ["feat"]
patch_tags = ["fix", "perf"]

[tool.semantic_release.remote]
type = "github"
token = { env = "GH_TOKEN" }

[tool.semantic_release.publish]
upload_to_vcs_release = true
```

#### libs/aegra-cli/pyproject.toml

```toml
[tool.semantic_release]
version_toml = ["pyproject.toml:project.version"]
branch = "main"
build_command = "uv build"
commit_parser = "conventional"
tag_format = "aegra-cli-v{version}"

[tool.semantic_release.commit_parser_options]
minor_tags = ["feat"]
patch_tags = ["fix", "perf"]
```

### 3. Update GitHub Actions Release Workflow

Replace manual release workflow with automated semantic-release:

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    branches:
      - main

permissions:
  contents: write
  id-token: write

jobs:
  release-api:
    runs-on: ubuntu-latest
    environment: release-api
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ secrets.GITHUB_TOKEN }}

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Install dependencies
        run: |
          cd libs/aegra-api
          uv sync --dev

      - name: Python Semantic Release
        uses: python-semantic-release/python-semantic-release@v9
        with:
          directory: libs/aegra-api
          github_token: ${{ secrets.GITHUB_TOKEN }}

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          packages-dir: libs/aegra-api/dist/

  release-cli:
    runs-on: ubuntu-latest
    environment: release-cli
    needs: release-api  # CLI depends on API
    steps:
      # Similar to above...
```

### 4. Enforce Conventional Commits

Install GitHub App: https://github.com/apps/semantic-pull-requests

This ensures all PRs use proper commit format before merging.

### 5. Add Commit Linting (Optional)

Add commitlint to pre-commit hooks:

```yaml
# .pre-commit-config.yaml
- repo: https://github.com/commitizen-tools/commitizen
  rev: v3.13.0
  hooks:
    - id: commitizen
      stages: [commit-msg]
```

## Monorepo Considerations

Since Aegra has 3 packages (aegra-api, aegra-cli, aegra), we need:

1. **Separate tags** for each package: `aegra-api-v0.1.0`, `aegra-cli-v0.1.0`
2. **Scoped commits** to identify which package changed:
   - `fix(api): fix thread state endpoint`
   - `feat(cli): add serve command`
3. **Release order**: api -> cli -> aegra (due to dependencies)

## Alternative: Manual Trigger with Auto-Bump

If full automation is too aggressive, use workflow_dispatch with auto version detection:

```yaml
on:
  workflow_dispatch:
    inputs:
      package:
        type: choice
        options: [aegra-api, aegra-cli, both]
      bump:
        type: choice
        options: [auto, patch, minor, major]
        default: auto
```

## Testing Strategy

1. Test on a branch first with `--noop` flag
2. Review generated changelog before enabling auto-publish
3. Start with manual trigger, graduate to full automation

## Timeline

1. **Phase 1**: Add semantic-release config to pyproject.toml files
2. **Phase 2**: Create GitHub Action with manual trigger + auto version detection
3. **Phase 3**: Enable full automation on merge to main
4. **Phase 4**: Add commit linting enforcement

## References

- [python-semantic-release docs](https://python-semantic-release.readthedocs.io/)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [Semantic Versioning](https://semver.org/)
