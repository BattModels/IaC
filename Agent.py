import os
import time
import openai
import json
from langgraph.prebuilt import create_react_agent
from langgraph.graph import END
from langchain_openai import AzureChatOpenAI
from langchain.agents import tool
from langgraph.graph import Graph
from langchain_core.runnables import Runnable
from langchain.schema.messages import SystemMessage, ToolMessage
from langgraph.prebuilt.chat_agent_executor import AgentState
from langchain_core.messages import AnyMessage
from functools import partial
from multiprocessing import Queue
from pprint import pformat
from datetime import datetime
import threading
from collections import deque
import asyncio

# ===============================
# Import custom lab modules
# ===============================
try:
    from Tools import *
    from ProcedureTool import *
    from Loader import load_lab_config
except Exception as e:
    # Handle relative import case
    from .Tools import *
    from .ProcedureTool import *
    from .Loader import load_lab_config

# ===============================
# Global constants
# ===============================
MAX_TRIAL = 5              # Maximum number of retries for communication attempts
NEW_EXPERIMENTS = 2         # Placeholder for number of new experiments (unused in code)

# Define root directories and paths
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
status_dir = os.path.join(project_root, 'Status.json')

# ===============================
# Custom state class for LangGraph agent
# ===============================
class CustomState(AgentState):
    user_name: str  # Extend base state schema with user_name field

# ===============================
# Helper functions
# ===============================

def safe_read_json(file_path):
    """Safely read JSON file; return empty dict if missing or invalid."""
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except Exception as e:
        return {}

def last_tool_call_content(msg):
    """Extract and parse the most recent ToolMessage content from LangGraph message list."""
    try:
        messages = msg["messages"]
        # Find the last ToolMessage in reverse order
        last_tool_msg = next(
            (m for m in reversed(messages) if isinstance(m, ToolMessage)),
            None
        )
        return json.loads(last_tool_msg.content)
    except Exception as e:
        return (str(e))

# ===============================
# MonitorAgent class
# ===============================
class MonitorAgent:
    """
    Central asynchronous router:
    - Maintains experiment queues
    - Handles background experiment execution
    - Reports progress and errors
    """

    def __init__(self, async_queue=None):
        self.id_queue = deque()            # Queue for experiment composition IDs
        self.file_name_queue = deque()     # Parallel queue for associated filenames
        self.async_queue = async_queue     # Async queue for inter-agent communication

    async def dispatch_loop(self, agent):
        """
        Background loop that dispatches experiments to the experiment agent
        when the system is ready and no errors exist.
        """
        while True:
            # Proceed only if system has no errors and queue is non-empty
            if get_error_status() == 'No errors' and self.id_queue:
                resolve()  # Reset error state
                # Initialize result if not set
                if 'compositionID' not in get_result():
                    set_result('compositionID', self.id_queue[0])
                # Prepare message for experiment agent
                msg = {
                    "compositionID": self.id_queue[0],
                    "messages": "Experiment Queued. Please start the experiment by calling generate_procedure"
                }
                # Trigger experiment execution
                agent.experiment_agent.invoke(msg)

                # Handle result or errors
                if get_error_status() == 'No errors':
                    result = get_result()
                    current_id = self.id_queue.popleft()
                    clear_result()
                else:
                    message = f'The experiment agent encounters an error: {error_status['error_status']}. Please notify the user.'
                    agent.response_q.put(agent.conversation_with_agent(message))

            await asyncio.sleep(0.5)  # Prevent busy loop

    def __call__(self, msg):
        """LangGraph node entrypoint for handling monitor messages synchronously."""
        print('Monitor called')
        try:
            info = last_tool_call_content(msg)
        except Exception as e:
            print(f"[MonitorAgent] Failed to parse message: {e}")
            return None

        # Handle message types:
        # 1. Add experiments to queue
        if "experiment_list" in info:
            if len(info["experiment_list"]) <= 0:
                return {'messages': 'Experiment list is empty. Did you call verify_id and passed in correct non-empty id-list and filenames?', 'Empty': True}
            
            # Extend internal queues
            self.id_queue.extend(info["experiment_list"])
            print(len(info["experiment_list"]))
            self.file_name_queue.extend([info["file_name"] for _ in info["experiment_list"]])

            update_msg = {
                "source": "monitor",
                "status": f"Queue extended → {list(self.id_queue)}"
            }
            print(f"[MonitorAgent] {update_msg['status']}")

            # Notify async listener if available
            if self.async_queue:
                asyncio.run_coroutine_threadsafe(
                    self.async_queue.put(update_msg), asyncio.get_event_loop()
                )
            time.sleep(0.5)

            dispatch_msg = {
                "messages": "Please notify the user that the experiments has been queued and will be executed later."
            }
            return dispatch_msg

        # 2. Continue paused experiments
        elif "continue" in info:
            resolve()
            return {'messages': 'Please notify the user that the experiments has resumed.'}

        # 3. Return current progress
        elif "progress" in info:
            result = get_result()
            if 'compositionID' not in result:
                return {'messages': 'No experiments is running. Please notify the user.' + get_error_status()}
            
            # Collect status info
            status = {
                'Current experiment': result['compositionID'],
                'Error_status': get_error_status(),
                'Date': result.get('Date', 'Experiments still preparing, not started.'),
                'Volume': result.get('Volume', 'Electrolyte yet to be made.'),
                'Density': result.get('Density', 'Density yet to be measured.'),
                'Conductivity': result.get('Conductivity', 'Conductivity yet to be measured.'),
                'Viscosity': result.get('Viscosity', 'Viscosity yet to be measured.'),
                'Temperature': result.get('Temperature', 'Temperature yet to be measured.')
            }
            return {'messages': f'Here is the experiment status:{status}, please notify the users.'}

        # 4. Handle missing experiment execution call
        elif "file_name" in info and "infeasible experiments" in info:
            return {'messages': f'You didn\'t call run_experiment. Please call it with filename {info["file_name"]}', 'Empty': True}

# ===============================
# Main Agent Class
# ===============================
class Agent:
    """
    Defines a multi-agent system using LangGraph and Azure OpenAI:
    - Front agent handles user requests
    - Monitor agent manages experiment queue and execution
    - Experiment agent performs lab operations
    """

    # ---------------------------
    # Static configuration
    # ---------------------------
    script_dir = os.path.dirname(os.path.abspath(__file__)) 
    tolerance = 1E-5 
    json_dir = os.path.join(script_dir, 'JSONHelper', 'System_prompt.json') 
    with open(json_dir, "r") as file: 
        system_prompt = json.load(file) 

    # Azure OpenAI configuration
    openai.api_type = "azure" 
    openai.api_version = "2024-02-15-preview"
    os.environ["AZURE_OPENAI_ENDPOINT"] = "https://fuelcell-management.openai.azure.com/" 
    os.environ["AZURE_OPENAI_API_KEY"] = "SI14urth4l29NXV1BIYWU9thScwaz1CGPB5AsfxhxuFZGFlfPUOlJQQJ99BHACYeBjFXJ3w3AAABACOG9nzD" 
    log_dir = os.path.join(script_dir, 'Conversation history')

    def __init__(self):
        """Initialize agents, queues, and async dispatch loop."""
        # Queues for async communication
        self.async_queue = asyncio.Queue()
        self.monitor_agent = MonitorAgent(async_queue=self.async_queue)
        self.request_q = Queue()
        self.response_q = Queue()

        # ---------------------------
        # Define prompt templates for agents
        # ---------------------------
        def prompt_front(state: CustomState) -> list[AnyMessage]: 
            system_msg = Agent.system_prompt["system_prompt_front"]
            system_msg += f'Solvents supported: {solvent_molar_mass}'
            system_msg += f'Salts supported: {salt_molar_mass}'
            return [{"role": "system", "content": system_msg}] + state["messages"] 
        
        def prompt_monitor(state: CustomState) -> list[AnyMessage]: 
            system_msg = Agent.system_prompt["system_prompt_monitor"] 
            return [{"role": "system", "content": system_msg}] + state["messages"] 
        
        def prompt_experiment(state: CustomState) -> list[AnyMessage]: 
            system_msg = Agent.system_prompt["system_prompt_experiment"] 
            return [{"role": "system", "content": system_msg}] + state["messages"] 
        
        # ---------------------------
        # Initialize agents and model
        # ---------------------------
        self.llm = AzureChatOpenAI(
            deployment_name="gpt-4o-mini",
            model_name="gpt-4o-mini",
            temperature=0,
            api_version="2023-03-15-preview"
        ) 

        # Create agent instances for different roles
        self.front_agent = create_react_agent(
            model=self.llm,
            tools=[get_experiment_progress, generate_space_sum, random_space_grid,
                   generate_ID_list_no_filename, hit_and_run, run_experiment, continue_experiment],
            state_schema=CustomState,
            prompt=prompt_front
        ) 

        self.experiment_agent = create_react_agent(
            model=self.llm,
            tools=[generate_procedure],
            state_schema=CustomState,
            prompt=prompt_experiment
        ) 

        self.monitor_agent = MonitorAgent()
        self.front_agent2 = create_react_agent(
            model=self.llm,
            tools=[generate_ID_list_filename, run_experiment],
            state_schema=CustomState,
            prompt=prompt_front
        ) 

        # ---------------------------
        # Async event loop setup
        # ---------------------------
        self.loop = asyncio.get_event_loop()
        self.loop.create_task(self.monitor_agent.dispatch_loop(self))
        threading.Thread(target=self.loop.run_forever, daemon=True).start()

        # ---------------------------
        # Build agent communication graph
        # ---------------------------
        self.graph = Graph()
        self.graph.set_entry_point("front_agent")
        self.graph.add_node("front_agent", self.front_agent)
        self.graph.add_node("monitor_agent", self.monitor_agent)
        self.graph.add_node("experiment_agent", self.experiment_agent)

        # Conditional routing logic between agents
        def to_monitor_edge(msg):
            info = last_tool_call_content(msg)
            if isinstance(info, dict) and ('experiment_list' in info or "continue" in info or "progress" in info):
                return "monitor_agent"
            return END
        
        def to_experiment_edge(msg):
            return "front_agent"

        # Register edges in the graph
        self.graph.add_conditional_edges("front_agent", to_monitor_edge)
        self.graph.add_conditional_edges("monitor_agent", to_experiment_edge)
        self.graph.add_edge("experiment_agent", "monitor_agent")

        # Compile LangGraph workflow
        self.app = self.graph.compile()

        # Initialize logging and history
        self.current_time_str = datetime.now().strftime("%Y-%m-%d %H-%M-%S") + '.log'
        self.log_file_dir = os.path.join(Agent.log_dir, self.current_time_str)
        self.history = [{"role": "system", "content": "You are a helpful assistant."}]

    # ===============================
    # Queue Management
    # ===============================
    def add_to_queue(self, compositionID):
        """Add a single experiment to the queue."""
        result = verifyCompositionID(compositionID)
        if isinstance(result, str):
            return result
        self.monitor_agent.id_queue.extend([compositionID])
        self.monitor_agent.file_name_queue.extend([''])
        return "No errors"

    def add_bulk_to_queue(self, compositionIDs):
        """Add multiple experiments to queue, validating each."""
        for i in range(len(compositionIDs)):
            result = verifyCompositionID(compositionIDs[i])
            if isinstance(result, str):
                return f'Invalid ID on line {i + 2}'
        self.monitor_agent.id_queue.extend(compositionIDs)
        self.monitor_agent.file_name_queue.extend(['' for _ in compositionIDs])
        return "No errors"

    def get_queue_length(self,):
        """Return the number of experiments in the queue."""
        return len(self.monitor_agent.id_queue)

    def delete_ith_element(self, i):
        """Remove an experiment at position i from the queue."""
        if i < 0 or i >= len(self.monitor_agent.id_queue):
            return
        del self.monitor_agent.id_queue[i]
        del self.monitor_agent.file_name_queue[i]

    # ===============================
    # Monitoring Thread (Legacy)
    # ===============================
    def _monitor_loop(self, request_q):
        """Background monitor for file-based error updates."""
        last_status = self.status.copy()
        while not self.stop_event.is_set():
            status = safe_read_json(status_dir)
            if status.get("Error") != last_status.get("Error"):
                last_status = status
                # Notify via request queue
                request_q.put(f"{status["Error"]}. Please notify the user.")
            time.sleep(1)

    def stop(self):
        """Stop background monitoring."""
        self.stop_event.set()
        self.monitor_thread.join()

    # ===============================
    # Conversation Handling
    # ===============================
    def conversation_with_agent(self, message, record_response=True):
        """
        Send a user message through the multi-agent system and log the conversation.
        Retries multiple times in case of transient errors.
        """
        conversation_result = ''
        for i in range(MAX_TRIAL):
            try:
                # Append user message
                self.history.append({"role": "user", "content": message})

                # Run graph pipeline
                conversation_result = self.app.invoke(
                    {"messages": self.history},
                    config={"recursion_limit": 100}
                )

                # Extract assistant response
                try:
                    assistant_reply = conversation_result['messages'][-1].content
                except Exception as e:
                    assistant_reply = ''

                # Record assistant response
                self.history.append({"role": "assistant", "content": assistant_reply})

                # Log conversation result
                with open(self.log_file_dir, "a") as log_file:
                    log_file.write(pformat(conversation_result))
                    log_file.write("\n\n")

                return assistant_reply
            except Exception as e:
                conversation_result = str(e)
        return conversation_result

# ===============================
# Script entry point
# ===============================
if __name__ == '__main__':
    agent = Agent()
    load_lab_config()
    while True:
        message = input("Enter your message: ")
        print(agent.conversation_with_agent(message, record_response=True))
