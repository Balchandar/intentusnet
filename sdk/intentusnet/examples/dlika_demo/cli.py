# intentusnet/examples/dlika_demo/cli.py

from __future__ import annotations
import sys
import traceback

from intentusnet import IntentusRuntime

# Agent imports
from intentusnet.examples.dlika_demo.agents.nlu_agent import (
    build_dlika_nlu_definition,
    DlikaNLUAgent,
)
from intentusnet.examples.dlika_demo.agents.planner_agent import (
    build_planner_definition,
    DlikaPlannerAgent,
)
from intentusnet.examples.dlika_demo.agents.calendar_agent import (
    build_calendar_definition,
    CalendarAgent,
)
from intentusnet.examples.dlika_demo.agents.contacts_agent import (
    build_contacts_definition,
    ContactsAgent,
)
from intentusnet.examples.dlika_demo.agents.maps_agent import (
    build_maps_definition,
    MapsAgent,
)
from intentusnet.examples.dlika_demo.agents.weather_agent import (
    build_weather_definition,
    WeatherAgent,
)


def build_runtime():
    runtime = IntentusRuntime()

    runtime.register_agent(
        lambda router, emcl: DlikaNLUAgent(build_dlika_nlu_definition(), router, emcl)
    )
    runtime.register_agent(
        lambda router, emcl: DlikaPlannerAgent(build_planner_definition(), router, emcl)
    )
    runtime.register_agent(
        lambda router, emcl: CalendarAgent(build_calendar_definition(), router, emcl)
    )
    runtime.register_agent(
        lambda router, emcl: ContactsAgent(build_contacts_definition(), router, emcl)
    )
    runtime.register_agent(
        lambda router, emcl: MapsAgent(build_maps_definition(), router, emcl)
    )
    runtime.register_agent(
        lambda router, emcl: WeatherAgent(build_weather_definition(), router, emcl)
    )

    return runtime


def run_dlika_cli():
    print("=== DLika Assistant (IntentusNet Demo) ===")
    print("Type 'exit' to quit.\n")

    runtime = build_runtime()
    client = runtime.client()

    while True:
        try:
            text = input("You: ").strip()
            if not text:
                continue
            if text.lower() in ("exit", "quit", "bye"):
                print("\nDLika: Bye Boss 💜")
                break

            # Send message normally
            resp = client.send("dlika.handle_command", {"text": text})

            msg = resp.payload.get("message")
            if msg:
                print(f"\nDLika: {msg}\n")
            else:
                print("\nDLika: (no message returned)\n")

        except KeyboardInterrupt:
            print("\nDLika: Bye Boss 💜")
            break

        except Exception as ex:
            print("\n[ERROR]", ex)
            traceback.print_exc()
            continue


if __name__ == "__main__":
    run_dlika_cli()
