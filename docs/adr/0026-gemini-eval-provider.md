# ADR 0021: Use Gemini for the optional model eval

- Status: Accepted
- Contract: `ARCHITECTURE.md` §15

## Context

The v0.1 model eval needs a concrete transport for its optional `--model` path, while deterministic evaluation must remain API-key free and dependency-light.

## Decision

Use Gemini `generateContent` over the standard library HTTP client, accepting `GEMINI_API_KEY` or `GOOGLE_API_KEY`. Send only fixed synthetic scenarios and keep the model path opt-in.

## Consequences

No SDK dependency is added and the default command makes no network call. Other providers require a separately documented adapter decision.
