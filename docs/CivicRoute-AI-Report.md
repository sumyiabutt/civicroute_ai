# CivicRoute AI

**Agentic traffic planning over MCP — describe the jam, get the detour and the reason.**

| | |
| --- | --- |
| Built for | Amazon Alexa+ hackathon track |
| What it is | FastAPI page + agent + MCP server over four simulated Pakistani city networks |
| Stack | Python 3.12, official `mcp` SDK (Streamable HTTP), FastAPI, Amazon Bedrock (Claude) with a deterministic fallback |
| Map | Leaflet 1.9.4 + OpenStreetMap raster tiles |
| Data | Simulated incidents and congestion on real place names and coordinates |
| Runs with | Zero AWS credentials — the fallback planner is the demo path |
| Licence | MIT |

---

## 1. The problem

Traffic assistants answer "how long will it take?" but rarely answer the two questions that
matter when something goes wrong: *what actually happened on my route*, and *why is this the
way I should go instead?* A single prompt over a routing API can produce a confident answer
with nothing behind it.

CivicRoute AI makes the reasoning the product. You type a disruption in plain English —
"Canal Road closed near Liberty Market, route me to Mayo Hospital" — and an agent runs a
visible multi-step tool conversation against a live road network, then explains the choice in
a sentence a driver would believe. Every tool call, its arguments, its latency and its result
stay on screen so the recommendation is auditable, not decorative.

## 2. What it does

1. You pick a city — **Lahore, Karachi, Islamabad or Peshawar** — and describe what happened.
2. The agent matches your sentence against places, road names, road types and incident reports.
3. It compares every way to your destination with Dijkstra on *live* travel minutes, not
   free-flow minutes: the adaptive route, up to two detours, and your original plan (usually
   flagged infeasible because it now crosses a closure).
4. It prices congestion leg by leg, so it can say "Jail Road is running at 1.38× free-flow
   because it is absorbing the diverted Canal Road traffic".
5. The answer lands on a map: OpenStreetMap tiles, every corridor coloured by congestion, the
   recommended route drawn thick in navy with A/B pins, and the reasoning timeline underneath.

Nothing reads a live traffic feed. The network is simulated on top of real geography, so the
demo is deterministic and repeatable on stage — the same input gives the same numbers every time.

## 3. Architecture

```
 you type a disruption, pick a city
            |
            v
  FastAPI page  civicroute/web_app.py
            |
            v
  Agent  civicroute/agent.py  --- Amazon Bedrock (Claude) tool calling
            |                             |
            |  MCP over Streamable HTTP   |  no AWS credentials?
            v                             v
  MCP server  civicroute/mcp_server.py  --- rule-based planner (same 3 tools)
            |
            v
  cities/*.json  civicroute/network.py  (Dijkstra + congestion model, one graph per city)
```

| Component | File | Role |
| --- | --- | --- |
| Road network | `civicroute/network.py` | Loads one `RoadNetwork` per city, Dijkstra + k-alternates, congestion model, the three tool implementations, `map_state()` |
| MCP server | `civicroute/mcp_server.py` | FastMCP over Streamable HTTP on `:8777/mcp`, all four cities in one process |
| Agent | `civicroute/agent.py` | MCP client, Bedrock tool loop, rule-based planner, recommendation text |
| Web layer | `civicroute/web_app.py` | FastAPI routes, city registry, map payload attached to every plan |
| Page | `civicroute/templates/index.html` | City dropdown, Leaflet traffic map, route cards, reasoning timeline |
| Scenarios | `cities/*.json` | Nodes with real lat/lng, named edges, incidents, example sentences, default endpoints |

Scope: 3,455 lines across 10 files — `network.py` 803, `agent.py` 583, the page 769,
`mcp_server.py` 156, `web_app.py` 187, and four city files of 7 places / 12 corridors / 4
incidents each (28 places, 48 road corridors, 16 incident reports in total).

## 4. The three MCP tools

Every tool takes a `city` argument, because edge ids repeat across cities — `E3` in Karachi must
never mean `E3` in Lahore. The agent stamps the selected city onto all three calls even when the
model omits it.

| Tool | Input | Output |
| --- | --- | --- |
| `lookup_incident` | `location`, `city` | Matched places and roads, active incidents, closed edge ids, and `scope: "specific"` or `"city-wide"` |
| `compare_routes` | `origin`, `destination`, `closed_roads`, `peak`, `city` | Up to 4 route options with legs, live vs free-flow minutes, `feasible` flags |
| `estimate_congestion` | `route`, `closed_roads`, `peak`, `city` | Per-leg congestion factors, total minutes, worst stretch, reliability |

Schemas as negotiated on `mcp` 1.30.0, protocol `2025-11-25`:

```
server: CivicRoute AI | protocol: 2025-11-25
lookup_incident ['location', 'city']
compare_routes ['origin', 'destination', 'closed_roads', 'peak', 'city']
estimate_congestion ['route', 'closed_roads', 'peak', 'city']
```

`lookup_incident` deliberately answers city-wide when your sentence names nothing it recognises,
so "any closures right now?" returns every active incident instead of an empty list.

## 5. Worked example (real output)

City **Lahore**, both endpoint selects on *Auto — read from my sentence*, request:

> Canal Road closed near Liberty Market, route me to Mayo Hospital

The timeline the page renders:

| Step | Tool | Result |
| --- | --- | --- |
| 1 | `lookup_incident` | 3 active incidents, 2 closed roads, 2 places matched |
| 2 | `parse_request` | destination `mayo`; no departure named, so the saved default `liberty` is used |
| 3 | `compare_routes` | 4 route options, fastest 36.8 min |
| 4-6 | `estimate_congestion` | one pricing pass per serious candidate |

Closures in effect: `E3` Canal Road (the live collision) and `E9` Multan Road (a long-running
closure that ships in the file). The winning route is `liberty -> datadarbar -> mayo`:

| Leg | Road | Base | Factor | Live |
| --- | --- | --- | --- | --- |
| E12 | Jail Road | 20.0 min | 1.38× | 27.6 min |
| E7 | Mall Road | 7.0 min | 1.32× | 9.2 min |
| | **Total** | **27.0 min** | **1.36× avg** | **36.8 min** |

And the sentence the agent writes from those numbers, verbatim:

> Take adaptive route (avoids every closure) to Mayo Hospital: about 37 minutes in current
> traffic. Roads: Jail Road, Mall Road. This avoids the closed Canal Road. Reason: Multi-vehicle
> collision on Canal Road near Liberty Market. The pre-disruption plan (20 min on paper) is out:
> it runs onto Canal Road. Alternatives: 46 min (detour avoiding Mall Road), 48 min (detour
> avoiding Jail Road). Slowest stretch is Jail Road, about 1.38x free-flow. That is 10 min more
> than an empty road. The detour costs 17 min more than Canal Road did before it was shut.

Every claim in that paragraph traces back to a tool result — the minutes, the factor, the
alternatives and the closure reason. The agent is not allowed to invent advice that nothing measured.

Switch the city to Karachi and the same three steps run against `cities/karachi.json`: the
flagship example there shuts `E2` (Shahrah-e-Faisal) and the recommendation drops to
Khayaban-e-Iqbal and Shahrah-e-Liaquat.

## 6. Two engines, one contract

**Bedrock path.** If credentials resolve, Claude receives the three MCP tool schemas and chooses
the calls itself (`toolMode: auto`, capped at 8 steps by `CIVICROUTE_MAX_STEPS`). MCP JSON-Schema
keywords Bedrock rejects — `$schema`, `additionalProperties`, `$defs`, `definitions`, `default`,
`examples`, `title` — are stripped by `_sanitize_schema` before the call.

**Fallback path.** If `boto3` is missing, no region is configured, credentials do not resolve,
the Bedrock call raises, or Claude returns nothing, the deterministic planner runs the same three
tools in the same order and composes the recommendation from templates. Both engines return the
identical output shape, so nothing downstream branches on which one answered.

The page always shows which engine ran and why it switched, in an amber note:

> Bedrock not usable (no AWS region set - export AWS_REGION=us-east-1), so the rule-based planner ran instead.

That note is the point, not a caveat. A judge with no AWS account sees a working multi-step agent
in ten seconds, and a judge with credentials sees the same flow driven by Claude.

## 7. The simulated network and congestion model

Each city is one JSON file. Add a file and it appears in the dropdown — the filename stem is the
`city` id.

- `nodes` — `id`, `name`, `area`, `kind`, `aliases`, `lat`, `lng`. Aliases are how "take me to the
  hospital" resolves; the coordinates are real, and they are what the map draws between.
- `edges` — `from`, `to`, `name`, `road_type`, `distance_km`, `base_travel_min`, `closed`.
  `distance_km` is the straight-line distance between two places inflated by 1.3 to look like a
  driving route. Road names are real: Canal Road, Mall Road, Jail Road, Ferozepur Road, the Lahore
  Ring Road, Ravi Road and Multan Road in Lahore; Shahrah-e-Faisal, MA Jinnah Road and the N-5 in
  Karachi; Jinnah Avenue, Faisal Avenue and the Islamabad Expressway; GT Road, Charsadda Road and
  Airport Road in Peshawar.
- `incidents` — `edges`, `closes_edge`, `extra_delay_min`, `status` (`active` counts, `resolved`
  does not), `severity`, `note`. All sixteen are invented for the demo.
- `examples`, `default_origin`, `default_destination` — the chips under the text box and where a
  trip starts when the sentence does not say (this is what "take me home" resolves to).

Congestion is deterministic, never random. Each road type carries a base load (bridges and
highways worst), hotspot destinations add load, and **every closure pushes diversion load onto the
roads touching the same junctions**, capped at 2× free-flow. Close a road and the alternatives
reprice themselves consistently — which is why editing a city file changes the whole comparison
rather than one number.

The map colours every road from that same model: under 1.3× green, 1.3–1.6× amber, 1.6× and above
red, closed dashed red with an X.

Two matching details matter more than they look. Because a dozen Pakistani street names end in
"Road", `ROAD_GENERIC_WORDS` drops `road`, `street`, `avenue` and friends when road names are
matched word by word, so "Jail Road" finds Jail Road and not the whole city. And place matching
ranks by position then needle length, so "I am leaving Hayatabad, get me to the airport" cannot
resolve the airport to itself just because the airport sits inside Hayatabad.

## 8. The interface

Light theme only — no dark surfaces anywhere, because this is a map product. The palette is warm
cream page, white cards, asphalt charcoal text, road-sign amber for buttons and highlights, and
navy reserved for exactly one thing: the route you should take. Traffic colours stay the
green/orange/red drivers already read on a congestion map.

- **Live map** — Leaflet + OpenStreetMap tiles with visible attribution, every corridor coloured
  by current congestion, incident triangles, closure crosses, the recommended route drawn thick
  with a white casing and an animated flow dash, navy A/B pins.
- **Recommendation** — the plain-language answer, the engine badge, and the fallback note.
- **Route options** — one card per candidate with minutes, distance, free-flow comparison, load
  factor, a congestion bar and the roads it uses. Click a card to redraw the map for that route.
- **Agent reasoning steps** — a collapsible timeline of every tool call with latency, a summary,
  the reasoning behind it, and the full arguments/result JSON one click deeper.
- **Live network status** — current closures and active incidents for the selected city.

The page is honest about what it is showing: a permanent "Simulated traffic data on OpenStreetMap"
chip on the map, plus a footer note that the road lines are our own straight segments between
places, not the basemap's street geometry.

## 9. Run it

Terminal 1 — the MCP server (Streamable HTTP on port 8777):

```bash
python -m civicroute.mcp_server
```

Terminal 2 — the web app:

```bash
python -m uvicorn civicroute.web_app:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>, choose a city, type a disruption, press **Plan my route**.
`http://127.0.0.1:8000/?city=karachi` opens a city directly.

Setup, requirements and Bedrock enablement are in [README.md](../README.md). Verified on Windows
with Python 3.12.10, `mcp` 1.30.0, FastAPI 0.156.8, Starlette 1.9.0, uvicorn 0.54.0, Jinja2 3.1.6,
pydantic 2.14.1.

## 10. Verification performed

| Check | Command or action | Result |
| --- | --- | --- |
| Registry | `curl http://127.0.0.1:8000/api/health` | 4 cities, each 7 places / 12 roads / 3 active incidents, `default_city: lahore` |
| City list | `curl http://127.0.0.1:8000/api/cities` | all four ids with their example sentences |
| Per-city map | `curl "http://127.0.0.1:8000/api/map?city=islamabad"` | network state for that city only |
| Plan | `POST /api/plan` with `"city":"karachi"` | recommendation + steps, `city` stamped on every tool step |
| Bad city | `POST /api/plan` with an unknown city | HTTP 400 with the list of valid ids |
| Tool schemas | MCP `initialize` + `list_tools` | protocol `2025-11-25`, `city` present on all three tools |
| Map re-centering | browser, switch city | tile origin moves per city (Karachi 11/1405/877, Lahore 11/1446/834, Islamabad 10/719/410, Peshawar 12/2861/1635) |
| Zero credentials | engine badge + amber note | falls back to the rule planner and still completes |
| Console | browser devtools after a plan | no errors |
| Single-city pin | `CIVICROUTE_ROADS=cities/karachi.json` | registry collapses to one city, app still runs |

## 11. Why this fits Alexa+

The three tools are already the voice surface: `lookup_incident` answers "what happened on my
commute", `compare_routes` answers "how do I get around it", `estimate_congestion` answers "will I
still make my flight". Because the agent returns a plain-language recommendation *plus* structured
steps, the same payload can drive an Alexa+ response — spoken summary for the ear, the timeline for
the screen — with no change to the planning code. The city argument is what turns it from a Lahore
demo into a service you can point at any city that has a JSON file.

## 12. Honest limitations

- The network is simulated. Real places, real coordinates, real road names — invented geometry
  (straight segments), invented incidents, and a congestion model that is a designed function, not
  a traffic feed.
- 7 places and 12 corridors per city is enough to show multi-step reasoning and detours, and not
  enough to be a router. Do not plan an actual trip with it.
- Endpoint resolution is word matching, not NLU. The Bedrock path can handle looser phrasing; the
  fallback planner handles the four example sentences per city well and unusual phrasing less well.
- The basemap needs internet (cdnjs and `tile.openstreetmap.org`). Offline, the route cards,
  reasoning timeline and recommendation still work; only the tiles are missing.
- Bedrock was not exercised with live credentials in this build — the fallback path is the one
  that was run end to end.

## 13. Next

- Bind the same three tools to an actual Alexa+ skill and answer by voice.
- Swap `cities/*.json` for an OSRM/Valhalla graph behind the identical tool contract.
- Add a fourth tool — `time_to_leave` — so the agent can answer "when should I go?" with the same
  evidence trail.
- Persist incident reports from drivers, so the network state is crowd-fed rather than scripted.

## 14. Licence

MIT. See [LICENSE](../LICENSE).
