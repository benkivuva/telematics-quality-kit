# Privacy

## v0.1 data handling

The default workflow uses generated synthetic vehicle IDs and synthetic protocol frames. It does not require a user account, API key, device connection, or telemetry upload. The simulator runs locally; the static report is written to a path chosen by the user. No analytics or telemetry collection is implemented.

The CLI may connect to an MCP server only when the user explicitly supplies an attach URL. That server may be remote and is outside this project's control. Review the endpoint and its privacy practices before sending requests.

The provided Docker Compose service publishes MCP over loopback on the host. It does not configure persistence or mount host files into the container.

## Real data

Do not place real IMEIs, precise locations, driver details, or captured device payloads in examples, fixtures, issue reports, or public logs. Synthetic identifiers and data are used in the repository.

If a future integration processes real telemetry, location traces can identify or describe people and should be treated as sensitive personal data. Before enabling such a workflow, document collection purpose, lawful basis, retention, access control, deletion, redaction, and any cross-border processing. That future workflow is outside v0.1 and is not implemented here.
