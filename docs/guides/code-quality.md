# Quick Reference: Code Quality Enforcement

> This is a quick-reference companion to the [Developer Guide](developer-guide.md).
> For detailed explanations of the development workflow, see the Developer Guide.

## For New Contributors

### One-Time Setup (2 minutes)

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/aegra.git
cd aegra

# 2. Install dependencies and hooks
make dev-install

# OR if not using Make:
uv sync
uv run pre-commit install
uv run pre-commit install --hook-type commit-msg
```

### Daily Workflow

```bash
# 1. Create branch
git checkout -b feat/my-feature

# 2. Make changes
# ... edit files ...

# 3. Before committing (optional but recommended)
make format    # Auto-fix formatting
make test      # Run tests

# 4. Commit (hooks run automatically!)
git add .
git commit -m "feat: add my feature"

# 5. Push and create PR
git push origin feat/my-feature
```

---

## Commit Message Format

**Required format:** `type(scope): description`

### Quick Examples

```bash
✅ GOOD:
git commit -m "feat: add user authentication"
git commit -m "fix(api): resolve rate limiting bug"
git commit -m "docs: update installation guide"
git commit -m "test: add e2e tests for threads"
git commit -m "chore: upgrade dependencies"

❌ BAD:
git commit -m "fixed stuff"
git commit -m "WIP"
git commit -m "Update"
git commit -m "changes"
```

### Types

| Type | When to Use | Example |
|------|-------------|---------|
| `feat` | New feature | `feat: add OAuth login` |
| `fix` | Bug fix | `fix: resolve memory leak` |
| `docs` | Documentation | `docs: update API guide` |
| `style` | Formatting | `style: fix indentation` |
| `refactor` | Code restructure | `refactor: simplify auth logic` |
| `perf` | Performance | `perf: optimize database queries` |
| `test` | Tests | `test: add unit tests for auth` |
| `chore` | Maintenance | `chore: update dependencies` |
| `ci` | CI/CD | `ci: add coverage reporting` |

### Scope (Optional)

Use to specify what part is affected:
- `api`, `auth`, `db`, `graph`, `tests`, `docs`, `ci`

---

## What Happens When You Commit?

```
git commit -m "feat: add feature"
         ↓
    Git Hooks Run Automatically
         ↓
┌────────────────────────────┐
│ 1. Ruff Format             │ ← Formats code
│ 2. Ruff Lint               │ ← Checks quality
│ 3. mypy Type Check         │ ← Validates types
│ 4. Bandit Security         │ ← Scans for issues
│ 5. File Checks             │ ← Validates files
│ 6. Commit Message Check    │ ← Validates format
└────────────────────────────┘
         ↓
    All Pass? ✅
         ↓
   Commit Success!
```

---

## Common Issues & Quick Fixes

### ❌ "Commit message format invalid"

**Error:**
```
❌ Commit message must follow format: type(scope): description
```

**Fix:**
```bash
# Use correct format
git commit -m "feat: add new feature"
```

### ❌ "Ruff formatting failed"

**Error:**
```
❌ Files would be reformatted
```

**Fix:**
```bash
# Auto-fix formatting
make format

# Stage changes
git add .

# Commit again
git commit -m "feat: add feature"
```

### ❌ "Linting errors found"

**Error:**
```
❌ Found 5 linting errors
```

**Fix:**
```bash
# See what's wrong
make lint

# Auto-fix what's possible
make format

# Fix remaining issues manually
# Then commit again
```

### ❌ "Type checking failed"

**Error:**
```
❌ mypy found type errors
```

**Fix:**
```bash
# See specific errors
make type-check

# Add type hints
def my_function(name: str) -> str:
    return f"Hello {name}"
```

---

## Emergency: Bypass Hooks

**⚠️ NOT RECOMMENDED** - CI will still fail!

```bash
git commit --no-verify -m "emergency fix"
```

Only use in true emergencies. Your PR will still need to pass CI.

---

## Before Pushing: Run All Checks

```bash
# Run everything CI will run
make ci-check
```

This runs:
- ✅ Formatting
- ✅ Linting
- ✅ Type checking
- ✅ Security scan
- ✅ Tests

---

## Pull Request Checklist

Before creating a PR:

- [ ] Git hooks installed (`make setup-hooks`)
- [ ] All commits follow format
- [ ] Tests pass (`make test`)
- [ ] Code formatted (`make format`)
- [ ] No linting errors (`make lint`)
- [ ] PR title follows format: `type: description`

---

## Available Commands

```bash
make help          # Show all commands
make dev-install   # Install dependencies
make setup-hooks   # Install git hooks
make format        # Format code
make lint          # Check code quality
make type-check    # Check types
make security      # Security scan
make test          # Run tests
make test-cov      # Tests with coverage
make ci-check      # Run all CI checks
make clean         # Clean cache files
```

---

## CI/CD Pipeline

Every push and PR triggers:

1. **Format Check** - Code must be formatted
2. **Lint Check** - No quality issues
3. **Type Check** - Types must be valid
4. **Security Check** - No vulnerabilities
5. **Tests** - All tests must pass
6. **Coverage** - Coverage report generated

**Matrix:** Tests run on Python 3.11 and 3.12

---

## Branch Protection (Maintainers)

On GitHub, enable these for `main` branch:

- ✅ Require status checks before merging
- ✅ Require PR reviews (1 approval)
- ✅ Require branches up-to-date
- ✅ Require conversation resolution

---

## Getting Help

1. **Read error messages** - They tell you what to fix
2. **Check ENFORCEMENT.md** - Detailed troubleshooting
3. **Run `make ci-check`** - Test everything locally
4. **Ask in PR comments** - Maintainers will help

---

## Why This Matters

### For You
- ✅ Catch bugs before review
- ✅ Learn best practices
- ✅ Faster PR approval

### For the Team
- ✅ Consistent code style
- ✅ Higher quality
- ✅ Less review time
- ✅ Better maintainability

---

## Quick Start Checklist

- [ ] Repository cloned
- [ ] `make dev-install` completed
- [ ] `make setup-hooks` completed ← **CRITICAL**
- [ ] Test commit successful
- [ ] Read CONTRIBUTING.md
- [ ] Ready to contribute! 🚀

---

**Remember:** The tools are here to help! They catch issues early so you can focus on writing great code.

---

Last Updated: 2026-01-30
