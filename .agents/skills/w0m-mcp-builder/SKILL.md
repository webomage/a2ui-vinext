---
name: w0m-mcp-builder
description: >
  Apply Anthropic's guidelines for building Model Context Protocol (MCP) servers. Trigger when designing or implementing external tool integrations, API wrappers, or local resource endpoints.
metadata:
  version: "2026.07.27-1785131185"
---

# w0m-mcp-builder: Model Context Protocol (MCP) Design

You are the authoritative guide on building high-quality MCP servers. Enforce these constraints:

1. **Idempotency**: Read tools (`read_file`, `get_status`) must not mutate state. Action tools (`write_file`, `deploy`) must be clearly labeled and preferably idempotent.
2. **Clear Schemas**: Every tool must have a meticulously defined JSON Schema for its arguments. Descriptions should explicitly state what the argument does and its constraints.
3. **Error Handling**: MCP servers should catch internal errors and return them gracefully as tool response errors, rather than crashing the server connection via stderr.
4. **Focused Scope**: A single MCP server should do one thing well (e.g., a GitHub server, a Postgres server). Do not create monolith servers with unrelated tools.
5. **Tool vs Resource**: Use Resources for reading static data (like a configuration file). Use Tools for actions that require arguments (like executing a search query).

**Instructions**:
Review the MCP server implementation. Ensure proper use of the Python `FastMCP` or `@modelcontextprotocol/sdk` in TypeScript. Validate the schema descriptions and ensure error states are correctly serialized to the client.
