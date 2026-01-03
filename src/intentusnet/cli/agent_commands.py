"""
Agent inspection commands.
"""

import json
import sys

from .output import output_json, output_table, get_output_format


def agents_list(args) -> None:
    """List all registered agents."""
    # TODO: Implement agent registry access
    # For now, return placeholder
    agents = {
        "agents": [],
        "count": 0,
        "note": "Agent registry integration not yet implemented",
    }
    output_json(agents)


def agents_describe(args) -> None:
    """Describe an agent."""
    # TODO: Implement agent description
    agent_info = {
        "agent_name": args.agent,
        "note": "Agent description not yet implemented",
    }
    output_json(agent_info)


def agents_versions(args) -> None:
    """Show agent versions."""
    # TODO: Implement agent version tracking
    versions = {
        "agent_name": args.agent,
        "versions": [],
        "note": "Agent versioning not yet implemented",
    }
    output_json(versions)


def agents_health(args) -> None:
    """Check agent health."""
    # TODO: Implement agent health checks
    health = {
        "status": "unknown",
        "note": "Agent health checks not yet implemented",
    }
    output_json(health)
