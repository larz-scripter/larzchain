# Releasing larzchain to PyPI

`larzchain` publishes to PyPI via **Trusted Publishing** (OIDC) — no API token.

## One-time setup (maintainer)
1. On https://pypi.org → your account → **Publishing** → add a **pending publisher**:
   - PyPI Project Name: `larzchain`
   - Owner: `larz-scripter`  ·  Repository: `larzchain`
   - Workflow: `publish.yml`  ·  Environment: `pypi`
2. In the GitHub repo, create an **Environment** named `pypi` (Settings → Environments).

## Cut a release
```bash
# bump the version in pyproject.toml + larzchain/__init__.py, commit, then:
git tag v0.2.1 && git push origin v0.2.1
```
The `publish.yml` workflow builds the sdist+wheel and uploads to PyPI.
Then anyone can `pip install larzchain`.
