# Threat model

## Scope

This model covers telematics-quality-kit v0.1: a local-first developer testbed that generates synthetic device data, decodes it through the project parsers, evaluates quality, and exposes results through a CLI, MCP server, or static HTML report. The default simulator does not connect to devices or a fleet service.

## Assets and trust boundaries

- Synthetic vehicle state, generated frames, fault configuration, and quality results.
- The user's local terminal, files, and MCP client.
- The Python environment and its dependencies.
- The GHCR container image and the PyPI distribution.
- An optional MCP client connection to a separately operated server. The server has no built-in authentication; loopback is the safe default.

Generated input crosses protocol parsers before reaching quality checks. MCP input crosses SDK validation and application schemas. Static reports contain escaped dynamic text, inline CSS/SVG, no JavaScript, and no remote requests. Fault tools mutate only the simulator backend and are absent for other backends.

## Threats and controls

| Threat | v0.1 control |
| --- | --- |
| Malformed or hostile protocol bytes | Bounded parsers return `ParseError`; property tests cover parser invariants. |
| Local browser reaches an HTTP service through DNS rebinding | HTTP service binds loopback by default; SDK origin protection remains enabled; Compose publishes loopback only. |
| MCP client changes simulator state unexpectedly | Fault tools exist only on the simulator backend, are marked destructive, and can be hidden with read-only mode. |
| HTML injection in report data | Escape dynamic strings; no script or external resource; CSP meta policy. |
| Dependency compromise or known vulnerable dependency | Lockfile, SHA-pinned Actions, gitleaks, Semgrep, pip-audit, Trivy, Dependabot, SBOM, provenance, and image signing. |
| Container process escalation or filesystem writes | Non-root runtime, read-only root filesystem, bounded `/tmp` tmpfs, all Linux capabilities dropped, and `no-new-privileges`. |
| Secrets accidentally committed | No secrets are needed for default operation; gitleaks runs in CI. |
| Remote MCP endpoint misuse or interception | Attached endpoints are user-selected and may be remote; the server has no authentication. Use loopback or a separately secured private network. Do not send sensitive data to an untrusted endpoint. |

## Residual risks

The MCP HTTP server has no authentication. Loopback binding limits exposure on a developer workstation but does not authenticate local processes. Users who intentionally attach to a remote MCP server are responsible for transport security and access control. A compromised Python dependency or release credential may affect the supply chain despite the automated controls.

The container entrypoint selects its container interface so that Docker port forwarding works. Host publication remains restricted to `127.0.0.1` in the provided Compose file. Deployments that change that publication rule change the trust boundary.

## Out of scope

Real device listeners, Traccar credentials, raw device identity spoofing, database access, dashboards, capture-file handling, and device command channels are v0.2 or later concerns. The project does not send commands to devices in any version.
