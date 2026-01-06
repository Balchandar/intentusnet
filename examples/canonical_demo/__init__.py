"""
Canonical IntentusNet Demo: Power Off System for Maintenance

This demo demonstrates:
- Multi-target intent resolution
- Target filtering (dangerous targets excluded)
- WAL-based crash safety and recovery
- Execution recording and replay

Run with:
    python examples/canonical_demo/run.py
"""

from .agent import (
    ServerPowerAgent,
    LightsPowerAgent,
    CCTVPowerAgent,
    MaintenanceCoordinatorAgent,
    register_all_agents,
)
