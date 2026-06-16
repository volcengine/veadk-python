# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Demo agent showcasing A2UI (agent-driven UI).

Run it with the bundled web UI:

    veadk frontend --agents-dir examples

then open http://127.0.0.1:8000 and ask e.g. "show me a flight status card".
"""

import json

from veadk import Agent
from veadk.utils.pdf_to_images import pdf_to_images_before_model_callback

BASIC_CATALOG_ID = "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json"


def _flight_card_a2ui(flight: dict[str, str]) -> list[dict]:
    surface_id = f"flight-{flight['flight_no'].lower()}-{flight['date']}"
    components = [
        {"id": "root", "component": "Card", "child": "flight-content"},
        {
            "id": "flight-content",
            "component": "Column",
            "children": [
                "flight-top",
                "flight-hero",
                "flight-times",
                "flight-divider",
                "flight-details",
                "flight-footer",
            ],
        },
        {
            "id": "flight-top",
            "component": "Row",
            "children": ["flight-brand", "flight-status-chip"],
            "justify": "spaceBetween",
            "align": "center",
        },
        {
            "id": "flight-brand",
            "component": "Row",
            "children": ["flight-brand-icon", "flight-title"],
            "align": "center",
        },
        {"id": "flight-brand-icon", "component": "Icon", "name": "send"},
        {
            "id": "flight-title",
            "component": "Text",
            "text": f"{flight['airline']} · {flight['flight_no']}",
            "variant": "h3",
        },
        {
            "id": "flight-status-chip",
            "component": "Row",
            "children": ["flight-status-icon", "flight-status-text"],
            "align": "center",
        },
        {"id": "flight-status-icon", "component": "Icon", "name": "check"},
        {
            "id": "flight-status-text",
            "component": "Text",
            "text": flight["status"],
            "variant": "caption",
        },
        {
            "id": "flight-hero",
            "component": "Row",
            "children": ["flight-origin", "flight-route-mark", "flight-destination"],
            "justify": "spaceBetween",
            "align": "center",
        },
        {
            "id": "flight-origin",
            "component": "Column",
            "children": [
                "flight-origin-label",
                "flight-origin-code",
                "flight-origin-city",
            ],
        },
        {
            "id": "flight-origin-label",
            "component": "Text",
            "text": "FROM",
            "variant": "caption",
        },
        {
            "id": "flight-origin-code",
            "component": "Text",
            "text": flight["departure_code"],
            "variant": "h1",
        },
        {
            "id": "flight-origin-city",
            "component": "Text",
            "text": flight["departure_city"],
            "variant": "body",
        },
        {
            "id": "flight-route-mark",
            "component": "Column",
            "children": ["flight-route-icon", "flight-duration", "flight-aircraft"],
            "align": "center",
        },
        {"id": "flight-route-icon", "component": "Icon", "name": "arrowForward"},
        {
            "id": "flight-duration",
            "component": "Text",
            "text": flight["duration"],
            "variant": "caption",
        },
        {
            "id": "flight-aircraft",
            "component": "Text",
            "text": flight["aircraft"],
            "variant": "caption",
        },
        {
            "id": "flight-destination",
            "component": "Column",
            "children": [
                "flight-destination-label",
                "flight-destination-code",
                "flight-destination-city",
            ],
            "align": "end",
        },
        {
            "id": "flight-destination-label",
            "component": "Text",
            "text": "TO",
            "variant": "caption",
        },
        {
            "id": "flight-destination-code",
            "component": "Text",
            "text": flight["arrival_code"],
            "variant": "h1",
        },
        {
            "id": "flight-destination-city",
            "component": "Text",
            "text": flight["arrival_city"],
            "variant": "body",
        },
        {
            "id": "flight-times",
            "component": "Row",
            "children": ["flight-departure-time", "flight-arrival-time"],
            "justify": "spaceBetween",
            "align": "stretch",
        },
        {
            "id": "flight-departure-time",
            "component": "Column",
            "children": [
                "flight-departure-label",
                "flight-departure-value",
                "flight-departure-airport",
            ],
        },
        {
            "id": "flight-departure-label",
            "component": "Text",
            "text": "Departure",
            "variant": "caption",
        },
        {
            "id": "flight-departure-value",
            "component": "Text",
            "text": flight["scheduled_departure"],
            "variant": "h3",
        },
        {
            "id": "flight-departure-airport",
            "component": "Text",
            "text": flight["departure_airport"],
            "variant": "caption",
        },
        {
            "id": "flight-arrival-time",
            "component": "Column",
            "children": [
                "flight-arrival-label",
                "flight-arrival-value",
                "flight-arrival-airport",
            ],
            "align": "end",
        },
        {
            "id": "flight-arrival-label",
            "component": "Text",
            "text": "Arrival",
            "variant": "caption",
        },
        {
            "id": "flight-arrival-value",
            "component": "Text",
            "text": flight["scheduled_arrival"],
            "variant": "h3",
        },
        {
            "id": "flight-arrival-airport",
            "component": "Text",
            "text": flight["arrival_airport"],
            "variant": "caption",
        },
        {"id": "flight-divider", "component": "Divider", "axis": "horizontal"},
        {
            "id": "flight-details",
            "component": "Row",
            "children": ["flight-terminal", "flight-gate", "flight-boarding"],
            "justify": "spaceBetween",
            "align": "stretch",
        },
        {
            "id": "flight-terminal",
            "component": "Column",
            "children": ["flight-terminal-label", "flight-terminal-value"],
        },
        {
            "id": "flight-terminal-label",
            "component": "Text",
            "text": "Terminal",
            "variant": "caption",
        },
        {
            "id": "flight-terminal-value",
            "component": "Text",
            "text": flight["terminal"],
            "variant": "h2",
        },
        {
            "id": "flight-gate",
            "component": "Column",
            "children": ["flight-gate-label", "flight-gate-value"],
        },
        {
            "id": "flight-gate-label",
            "component": "Text",
            "text": "Gate",
            "variant": "caption",
        },
        {
            "id": "flight-gate-value",
            "component": "Text",
            "text": flight["gate"],
            "variant": "h2",
        },
        {
            "id": "flight-boarding",
            "component": "Column",
            "children": ["flight-boarding-label", "flight-boarding-value"],
            "align": "end",
        },
        {
            "id": "flight-boarding-label",
            "component": "Text",
            "text": "Boarding",
            "variant": "caption",
        },
        {
            "id": "flight-boarding-value",
            "component": "Text",
            "text": flight["boarding_time"],
            "variant": "h2",
        },
        {
            "id": "flight-footer",
            "component": "Row",
            "children": ["flight-source", "flight-updated"],
            "justify": "spaceBetween",
            "align": "center",
        },
        {
            "id": "flight-source",
            "component": "Text",
            "text": "Mock flight data",
            "variant": "caption",
        },
        {
            "id": "flight-updated",
            "component": "Text",
            "text": f"Updated {flight['updated_at']}",
            "variant": "caption",
        },
    ]
    return [
        {
            "version": "v0.9",
            "createSurface": {
                "surfaceId": surface_id,
                "catalogId": BASIC_CATALOG_ID,
            },
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": surface_id,
                "components": components,
            },
        },
    ]


def query_flight_info(
    flight_no: str = "MU5101",
    departure_city: str = "Shanghai",
    arrival_city: str = "Beijing",
    date: str = "2026-06-16",
) -> dict[str, str]:
    """Return one mock flight card for the A2UI demo.

    Call this immediately for any flight-query intent. For demo speed, omit any
    argument that is not explicitly provided by the user and let defaults apply.

    Args:
        flight_no: Flight number, e.g. "MU5101".
        departure_city: Departure city, e.g. "Shanghai".
        arrival_city: Arrival city, e.g. "Beijing".
        date: Flight date in YYYY-MM-DD format.

    Returns:
        A dict containing structured mock flight details and a prebuilt
        `a2ui_json` string. Pass `a2ui_json` verbatim to
        `send_a2ui_json_to_client`.
    """
    normalized_flight_no = (flight_no or "MU5101").strip().upper()
    normalized_departure = (departure_city or "Shanghai").strip()
    normalized_arrival = (arrival_city or "Beijing").strip()
    normalized_date = (date or "2026-06-16").strip()

    flight = {
        "flight_no": normalized_flight_no,
        "date": normalized_date,
        "airline": "China Eastern Airlines",
        "departure_code": "SHA",
        "arrival_code": "PEK",
        "departure_city": normalized_departure,
        "arrival_city": normalized_arrival,
        "departure_airport": "Shanghai Hongqiao International Airport",
        "arrival_airport": "Beijing Capital International Airport",
        "scheduled_departure": f"{normalized_date} 09:25",
        "scheduled_arrival": f"{normalized_date} 11:45",
        "departure_time": "09:25",
        "arrival_time": "11:45",
        "boarding_time": "08:55",
        "duration": "2h 20m",
        "aircraft": "Airbus A321",
        "terminal": "T2",
        "gate": "C18",
        "status": "On time",
        "updated_at": "2026-06-16 08:40",
        "data_source": "mock",
    }
    flight["a2ui_json"] = json.dumps(_flight_card_a2ui(flight), ensure_ascii=False)
    return flight


INSTRUCTION = """You are an A2UI demo agent. Be fast and concise.

Never reveal chain-of-thought, planning, JSON drafting, or tool reasoning.

Flight demo flow:
1. If the user asks about flights, immediately call `query_flight_info`.
2. Do not infer dates such as "today"; use tool defaults unless the user gives
   an explicit YYYY-MM-DD value.
3. After `query_flight_info` returns, immediately call `send_a2ui_json_to_client`
   with the returned `a2ui_json` string verbatim.
4. Do not construct, rewrite, wrap, summarize, or explain the A2UI JSON.
5. If the A2UI tool fails once, stop and answer with a one-sentence plain-text
   fallback.

For non-flight requests, answer briefly in plain text unless a small A2UI card
is clearly useful.
"""

agent = Agent(
    name="a2ui_agent",
    description="Demo agent that replies with A2UI rich UI.",
    instruction=INSTRUCTION,
    tools=[query_flight_info],
    enable_a2ui=True,
    # Uploaded PDFs are rendered to page images so the vision model can read
    # them. The default model (doubao-seed-1.6) is vision-capable.
    before_model_callback=pdf_to_images_before_model_callback,
)

# Required by the Google ADK agent loader.
root_agent = agent
