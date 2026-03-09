# Main.py
import threading
import time

import dash
from dash import html, dcc
from dash.dependencies import Input, Output

from core.Loader import load_iac_yaml
from Task_Tester import run_task_tester  # your existing runner
from core.Allocator import Allocator  # adjust path if needed
from AllocatorTester import tester

# -----------------------------
# Load resources + allocator
# -----------------------------
resources = load_iac_yaml("config/temp.yaml")
allocator = Allocator(resources)

resource_states = {name: {"info": "Loading..."} for name in resources}
experiment_running = False


# -----------------------------
# Background hardware polling
# -----------------------------
def poll_resources():
    while True:
        for name, res in resources.items():
            try:
                if hasattr(res, "read"):
                    data = res.read()
                    if isinstance(data, dict) and "state" in data:
                        resource_states[name] = data["state"]
                    else:
                        resource_states[name] = {"info": str(data)}
                else:
                    resource_states[name] = getattr(res, "actual_state", {"info": "No state"})
            except Exception as e:
                resource_states[name] = {"status": "error", "error_message": str(e)}
        time.sleep(1)


threading.Thread(target=poll_resources, daemon=True).start()


# -----------------------------
# Helpers: render resource tree
# -----------------------------
def get_child_lists(resource):
    children = []
    for attr_name, value in vars(resource).items():
        if attr_name.startswith("_"):
            continue
        if isinstance(value, list) and value and hasattr(value[0], "name"):
            children.append(value)
    return children


def render_state_kv(state):
    items = []
    for k, v in state.items():
        style = {"color": "black"}
        if k.lower() == "status":
            val = str(v).lower()
            if "available" in val:
                style["color"] = "green"
            elif "error" in val:
                style["color"] = "red"
            elif "in_use" in val:
                style["color"] = "orange"
        items.append(html.Div([html.Strong(f"{k}: "), html.Span(str(v), style=style)]))
    return html.Div(items, style={"marginLeft": "15px", "marginBottom": "5px"})


def render_node(resource):
    state = resource_states.get(resource.name, {"info": "No state"})
    children_lists = get_child_lists(resource)
    if not children_lists:
        return html.Li(
            [html.Span(resource.name, style={"fontWeight": "bold"}), render_state_kv(state)]
        )
    return html.Li(
        [
            html.Span(resource.name, style={"fontWeight": "bold"}),
            render_state_kv(state),
            html.Ul(
                [render_node(child) for child_list in children_lists for child in child_list],
                style={"listStyleType": "circle", "marginLeft": "20px"},
            ),
        ]
    )


def find_roots():
    all_children = set()
    for res in resources.values():
        for child_list in get_child_lists(res):
            all_children.update(child_list)
    return [res for res in resources.values() if res not in all_children]


# -----------------------------
# Helpers: render allocator queues
# -----------------------------
def render_queues_view():
    snap = allocator.snapshot_queues()
    queues = snap.get("queues", {})

    if not queues:
        return html.Div("No queues yet.", style={"fontFamily": "monospace"})

    blocks = []
    for module_type in sorted(queues.keys()):
        items = queues[module_type]
        blocks.append(
            html.Div(
                [
                    html.Div(
                        f"module_type: {module_type}  (len={len(items)})",
                        style={"fontWeight": "bold", "marginTop": "10px"},
                    ),
                    html.Div(
                        [
                            html.Div(
                                f"{i+1:02d}. exp_id={it.get('experiment_id')}  "
                                f"tasks={it.get('n_tasks')}  requested={it.get('module_request')}"
                            )
                            for i, it in enumerate(items)
                        ],
                        style={"marginLeft": "15px"},
                    ),
                ],
                style={"fontFamily": "monospace"},
            )
        )
    return blocks


# -----------------------------
# Dash app (single-file multi-page)
# -----------------------------
app = dash.Dash(__name__)
app.title = "EaC Lab Monitor"

app.layout = html.Div(
    [
        dcc.Location(id="url", refresh=False),

        html.H2("🧪 EaC Lab Monitor"),
        html.Div(
            [
                dcc.Link("Resource Tree", href="/", style={"marginRight": "15px"}),
                dcc.Link("Allocator Queues", href="/queues"),
            ],
            style={"marginBottom": "12px"},
        ),

        dcc.Interval(id="refresh", interval=500, n_intervals=0),

        html.Div(id="page-content"),
    ]
)


# -----------------------------
# Page router
# -----------------------------
@app.callback(
    Output("page-content", "children"),
    Input("url", "pathname"),
    Input("refresh", "n_intervals"),
)
def route(pathname, _):
    # Resource tree page
    if pathname == "/" or pathname is None:
        roots = find_roots()
        return html.Div(
            [
                html.H3("Lab Resource Tree"),
                html.Button("Run Experiment (direct)", id="run-exp-btn", n_clicks=0),
                html.Div(id="exp-status", style={"marginTop": "10px"}),
                html.Div(
                    html.Ul([render_node(r) for r in roots], style={"listStyleType": "none", "paddingLeft": "0px"}),
                    style={"fontFamily": "monospace", "color": "black"},
                ),
            ]
        )

    # Allocator queues page
    if pathname == "/queues":
        return html.Div(
            [
                html.H3("Allocator Queues"),
                html.Div("One experiment per line (auto-refresh).", style={"marginBottom": "10px"}),
                html.Div(render_queues_view()),
            ]
        )

    return html.Div("404: page not found")


# -----------------------------
# Run experiment button callback (only exists on tree page)
# -----------------------------
@app.callback(
    Input("run-exp-btn", "n_clicks"),
    prevent_initial_call=True,
)
def start_experiment(n_clicks):
    if n_clicks:
        tester(allocator)


# -----------------------------
# Run
# -----------------------------
if __name__ == "__main__":
    app.run(port=8050)