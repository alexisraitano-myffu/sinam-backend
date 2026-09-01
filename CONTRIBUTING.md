# Contributing to sinam

Thanks for looking. This is a small project with a clear shape, and the fastest
way to get a change merged is to know that shape before you write code.

## What this repo is, and what it is not

This repository is what **runs the brain on a computer and opens it to the rest
of the world**: the MCP server, the HTTP API, and the process that keeps a
memory alive on a machine. It is Apache-2.0, and it is enough on its own: clone
it, run it, point your assistant at it over MCP, and you have a working memory
with no application from us.

Two things are elsewhere.

The **engine** lives in [sinam-core](https://github.com/alexisraitano-myffu/sinam-core):
routing, confidence, vectors, decay, summaries, sync, pairing. It is Rust,
compiled once, and this repository consumes it as a wheel. If a change is about
what the engine *decides*, it belongs there, not here. A rule of thumb: if you
find yourself writing a heuristic in Python, stop and ask whether the core should
be doing it.

The **applications** are a separate, closed codebase. That is the open-core
boundary and it is deliberate: the engine is open so you can verify what happens
to your memory and use it without us; the apps are what we sell.

Bug reports, correctness fixes, endpoint and MCP tool improvements, packaging and
platform support are all welcome here.

## Before you write code

**Open an issue first** for anything beyond a typo or an obvious bug fix. Say
what you observed, what you expected, and on which platform. If you already know
the fix, say so and we will tell you quickly whether it is a direction we want. A
short exchange up front saves a rewritten branch.

## Setting up

```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

The brain ships as the **`sinam_core` wheel, which is not on PyPI yet**. Build it
once from the [sinam-core](https://github.com/alexisraitano-myffu/sinam-core)
repository and install it into this virtual environment. It must be the *only*
SQLite library in the process; installing another one produces failures that look
like data corruption and are not.

⚠️ **Install the requirements in full, never module by module.** The bundled
build only contains what is installed, so a partial install produces an import
that fails at runtime rather than at build time. That has bitten us three times,
each on a lazily imported package.

## Tests

```bash
pytest                               # the offline suites run without an API key
```

The suite does not run without the core: `db/__init__.py` imports `sinam_core` at
module level, so almost everything collapses if the wheel is missing.

Continuous integration **builds the wheel from the core's `main`** rather than
downloading a published artifact. That is deliberate. What we want to know is
that this backend works against today's engine; a released wheel one commit
behind once gave us two days of false green, validating a routing behaviour the
engine no longer applied.

A pull request that changes behaviour should come with a test that fails before
it and passes after. If the behaviour is hard to pin down in a test, say so in
the pull request and describe what you checked by hand instead.

## Things that are generated, not written

- **`openapi.json`** is produced from the code. Regenerate it with
  `python -m scripts.regen_openapi` rather than editing it; a hand-edited schema
  drifts from the server within a week and the clients believe the schema.
- The **prompts** deployed under `SYNAPSE_HOME/prompts` come from the core. Do
  not edit them here; a change made in this repository is overwritten on the next
  start and never reaches a phone.

## Style, and what a good pull request looks like

- Keep the change focused. One reason to merge per pull request.
- Match the surrounding code. This codebase has a voice; follow it rather than
  importing conventions from elsewhere.
- Comments explain **why**, not what. A comment that restates the line above is
  noise; a comment that records the trap someone already fell into is worth more
  than the code it sits on.
- No new dependency without saying in the issue why the standard library or an
  existing dependency will not do. This backend is bundled and shipped inside a
  desktop application; every dependency is weight on someone's machine.
- Reference issues by their GitHub number. Do not put internal tracker
  identifiers in commits or files here.

## Reporting a vulnerability

**Do not open a public issue for a security problem.** Use GitHub's private
vulnerability reporting on this repository, or write to
`alexis.raitano@myffu.fr`. Describe the class of problem and how to reproduce it;
you do not need to build a working exploit to be taken seriously.

This server holds people's personal memory and listens on a home network.
Anything touching authentication, the pairing endpoints, the sync transport or
the TLS certificate gets read carefully and fixed quickly.

## Licence

By contributing you agree that your contribution is licensed under the
Apache License 2.0, like the rest of this repository. See [LICENSE](LICENSE).

## Code of conduct

Participation is covered by our [Code of Conduct](CODE_OF_CONDUCT.md). It is
short, and it comes down to treating other people as though you had to sit
across from them.
