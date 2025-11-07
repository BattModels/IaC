import dash
from dash import html, dcc
from dash.dependencies import Input, Output, State
import dash_bootstrap_components as dbc
from Loader import load_lab_config
from Resource import Status
from Agent import Agent
import threading
from multiprocessing import Queue
labs = None
history = []
history.append({'sender': 'Agent', 'text': 'Start your conversation.'})
agent = Agent()
# Status color map
status_info = {
    Status.AVAILABLE: {"label": "AVAILABLE", "color": "green"},
    Status.IN_USE: {"label": "IN USE", "color": "orange"},
    Status.ERROR: {"label": "ERROR", "color": "red"}
}


def agent_worker(request_q: Queue, response_q: Queue):
    #agent.start_thread(request_q)
    while True:
        user_message = request_q.get()
        print(user_message)
        if user_message == "STOP":
            break
        response = agent.conversation_with_agent(user_message)
        response_q.put(response)

def render_resource_tree(resource):
    """Recursively render a Resource as nested HTML lists with dynamic properties."""
    children_elements = [render_resource_tree(child) for child in resource.children]

    status = status_info.get(resource.status, {"label": "UNKNOWN", "color": "black"})
    status_text = f"{resource.name} (Status: {status['label']})"

    def render_value(value):
        """Recursively render dicts/lists as nested HTML elements."""
        if isinstance(value, dict):
            return html.Ul([
                html.Li([
                    html.Span(f"{k}: "),
                    render_value(v)
                ]) for k, v in value.items()
            ], style={"marginLeft": "20px"})
        elif isinstance(value, list):
            return html.Ul([
                html.Li(render_value(v)) for v in value
            ], style={"marginLeft": "20px"})
        else:
            return html.Span(str(value))

    # Dynamically get resource info
    extra_elements = []
    try:
        info = resource.get_status()
        if isinstance(info, dict) and info:
            detail_list = html.Ul([
                html.Li([
                    html.Span(f"{key}: "),
                    render_value(value)
                ])
                for key, value in info.items()
            ], style={"marginLeft": "20px"})
            extra_elements.append(detail_list)
    except Exception:
        pass

    return html.Li(
        [
            html.Span(status_text, style={"color": status["color"], "fontWeight": "bold"}),
            *extra_elements,
            html.Ul(children_elements) if children_elements else None
        ]
    )

agent_thread = threading.Thread(target=agent_worker, args=(agent.request_q, agent.response_q), daemon=True)

    # Start the thread
agent_thread.start()
# ----------------------------
# Dash App
# ----------------------------
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], suppress_callback_exceptions=True)

app.layout = html.Div([
            html.Div(children=[dcc.Location(id='url', refresh=False),
            dcc.Link('Resource Tree', href='/', className='link'),
            dcc.Link('Chat with Agent', href='/agent-page', className='link')], className='top-menu-bar'),
            dcc.Interval(id="back-interval", interval=500, n_intervals=0),
        html.Div(id='page-content')
    ])

resource_content = html.Div([
    html.H2("Lab Resource Tree"),

    html.Div(id="resource-tree-container"),

    html.Br(),

    html.H4("Select Measurements to Perform:"),
    dcc.Checklist(
        id="measurement-checklist",
        options=[
            {"label": "Density", "value": "density"},
            {"label": "Conductivity", "value": "conductivity"},
            {"label": "Viscosity", "value": "viscosity"},
        ],
        value=[],  # None selected initially
        inline=True,
        style={"marginBottom": "15px"}
    ),
    html.Div(id="selected-measurements"),

    html.Hr(),

    html.Button("Run Demo", id="run-demo", n_clicks=0),
    html.Div(id="run-demo-container"),

    dcc.Interval(id="interval-update", interval=200, n_intervals=0)  # refresh every 2s
])

# Switch page function
@app.callback(
    Output('page-content', 'children'), 
    Input('url', 'pathname')
)
def display_page(pathname):
    if pathname == '/agent-page':
        agent_content = html.Div([
            html.H1("Chat with Agent!"),
            html.Div(children=[html.Div(id='chat-box', style={
                'border': '1px solid #ccc',
                'padding': '10px',
                'minHeight': '400px',     # prevents collapsing
                'maxHeight': '80vh', 
                'width': '80%', 
                'overflowY': 'scroll',
                'whiteSpace': 'pre-line',
                'backgroundColor': '#f9f9f9'
            }),
            html.Div(children=[
            dcc.Input(id='user-input', type='text', className='custom-textfield', placeholder='Type your message...', style={'width': '80%'}),
            html.Button('Send', id='send-button', className="custom-button", n_clicks=0, disabled=history[-1]['sender'] == 'Human')],
            style={
                'display': 'flex',
                'justifyContent': 'center',
                'alignItems': 'center',
                'width': '80%',
                'maxWidth': '800px',
                'margin': '0 auto'
            })],
            className='selection-container', style={
                    "display": "flex",                # Use flexbox
                    "justifyContent": "center",       # Center table horizontally
                    "align-items": "center",
                    "flex-direction": "column"
            }),
            # Store the chat log in browser memory
            dcc.Store(id='chat-store', data=[]),
            dcc.Interval(
                            id="agent-interval",
                            interval=200,  # Update every 5 seconds
                            n_intervals=0
                        )
            ])
        return agent_content
    else:
        return resource_content


# ----------------------------
# Callbacks
# ----------------------------
@app.callback(
    Output('user-input', 'value'),
    Input('send-button', 'n_clicks'),
    Input('user-input', 'n_submit'),  # Trigger when Enter is pressed
    State('user-input', 'value'),
    prevent_initial_call=True
)
def update_chat(n_clicks, n_submit, user_message):
    if user_message:
        history.append({'sender': 'Human', 'text': user_message})

        agent.request_q.put(user_message)
    return ''

@app.callback(
    [Output('chat-box', 'children'), Output('send-button', 'disabled')],
    Input('agent-interval', 'n_intervals'),
    prevent_initial_call=True
)
def display_chat(n_intervals):
    chat_elements = []
    # Wait for response (with timeout handling if desired)
    try:
        ai_response = agent.response_q.get(timeout=0.1)
        history.append({'sender': 'Agent', 'text': ai_response})
    except Exception:
        pass
    for msg in history:
        style = {
            'margin': '10px 0',          # space between messages
            'padding': '8px 12px',       # padding inside the message bubble
            'borderRadius': '8px',
            'maxWidth': '75%',
            'wordWrap': 'break-word',
        }

        if msg['sender'] == 'Human':
            style['color'] = '#00274C'
            style['textAlign'] = 'right'
            style['marginLeft'] = 'auto'      # push to right
            style['paddingRight'] = '20px'    # indent from right edge
            style['paddingLeft'] = '40px'     # small gap on left side
        else:
            style['color'] = '#B8860B'
            style['textAlign'] = 'left'
            style['marginRight'] = 'auto'
            style['paddingLeft'] = '20px'     # indent from left edge
            style['paddingRight'] = '40px'    # small gap on right side

        chat_elements.append(html.Div(f"{msg['text']}", style=style))
    
    return chat_elements, history[-1]['sender'] == 'Human'

@app.callback(
    Output("resource-tree-container", "children"),
    Input("interval-update", "n_intervals")
)
def update_tree(n):
    """Update the resource tree every interval."""
    if not labs:
        return "No labs loaded."
    return html.Ul([render_resource_tree(lab) for lab in labs], style={"listStyleType": "none"})


@app.callback(
    Output("run-demo-container", "children"),
    Input("run-demo", "n_clicks"),
    State("measurement-checklist", "value")
)
def run_demo(n_clicks, selected_measurements):
    if n_clicks > 0:
        if not selected_measurements:
            return "No measurements selected. Please select at least one."

        # Map selected checkboxes to boolean flags for tester()
        measurements_kwargs = {
            "density": "density" in selected_measurements,
            "conductivity": "conductivity" in selected_measurements,
            "viscosity": "viscosity" in selected_measurements
        }


        selected_list = [m.capitalize() for m in selected_measurements]
        return f"Run Demo executed for: {', '.join(selected_list)}"

    return f"Run Demo clicked {n_clicks} time(s)"


# ----------------------------
# Main Entry
# ----------------------------
if __name__ == "__main__":
    labs = load_lab_config()
    app.run(debug=True)
