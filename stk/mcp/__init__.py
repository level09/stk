"""Expose an app's own functions to AI agents over MCP at `/mcp`.

A tool is an async function taking the validated arguments dict. It runs as the
token's user: `current_user` and `g.db_session` work as in a request handler.
"""

import re
from dataclasses import dataclass

from jsonschema import Draft202012Validator

# Spec-recommended tool name alphabet and length.
NAME = re.compile(r"[A-Za-z0-9_.-]{1,128}")


class ToolError(Exception):
    """Raise from a tool to tell the agent what went wrong; its writes roll back."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    schema: dict
    role: str | None
    fn: object
    validator: Draft202012Validator


TOOLS: dict[str, Tool] = {}


def tool(name, description, schema, *, role=None):
    """Register an MCP tool. `schema` is the JSON Schema of its arguments object.

    `role` gates the tool: the caller's token must carry that role as a scope and
    the user must still hold it. Without a role, any valid token may call it.
    """
    if not NAME.fullmatch(name):
        raise ValueError(f"MCP tool name {name!r} must match {NAME.pattern}")
    if name in TOOLS:
        raise ValueError(f"MCP tool {name!r} is already registered")
    if schema.get("type") != "object":
        raise ValueError(f"MCP tool {name!r} schema must have type object")
    Draft202012Validator.check_schema(schema)

    def decorator(fn):
        TOOLS[name] = Tool(
            name, description, schema, role, fn, Draft202012Validator(schema)
        )
        return fn

    return decorator
