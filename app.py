"""
Gradio UI for Multi-Agent SQL Query System
Thread-safe version for concurrent users.
"""
import gradio as gr
import asyncio
import sys
import threading
import queue
import time
import json
from pathlib import Path
from datetime import datetime
import pandas as pd

# ------------------------------------------------------------------------------
# Import Setup
# ------------------------------------------------------------------------------
try:
    from utils.config_loader import ConfigLoader
    from utils.logger import setup_logger
    from agents.orchestrator_agent import OrchestratorAgent
except ImportError:
    print("⚠️ Warning: Utils/Agents not found. Ensure you are running from the project root.")

# ------------------------------------------------------------------------------
# Backend System Class
# ------------------------------------------------------------------------------
class MultiAgentSQLSystem:
    """Main system class for multi-agent SQL query processing"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """Initialize the multi-agent system"""
        try:
            self.config_loader = ConfigLoader(config_path)
            self.config = self.config_loader.config
            # Note: For high concurrency, ensure setup_logger handles 
            # multiple file handles gracefully or use a rotation handler.
            self.logger = setup_logger(
                name=f"MultiAgentSystem-{threading.get_ident()}", # Unique name per thread
                log_file=self.config.get('logging', {}).get('file', 'multi_agent_sql.log'),
                level=self.config.get('logging', {}).get('level', 'INFO')
            )
            self.orchestrator = OrchestratorAgent(self.config)
            if self.logger:
                self.logger.info("Multi-Agent SQL System instance initialized")
        except Exception as e:
            print(f"Error initializing system: {str(e)}")
            self.logger = None
            raise e
    
    async def process_query(self, natural_query: str, status_callback=None) -> dict:
        """Process a natural language query through the multi-agent system"""
        if self.logger:
            self.logger.info(f"Processing query: {natural_query}")
        
        try:
            # The orchestrator will now call the SummarizerAgent at the end
            result = await self.orchestrator.execute(natural_query, callback=status_callback)
            return result
            
        except Exception as e:
            if self.logger: self.logger.error(f"Error processing query: {str(e)}")
            return {'success': False, 'error': str(e)}

# ------------------------------------------------------------------------------
# UI Logic
# ------------------------------------------------------------------------------
def process_query_streaming(query: str, history: list = None):
    """
    Generator function that yields updates to the UI in real-time.
    """
    # Initialize UI state variables
    # Output order: (Final Text, SQL, Raw DF, Proc Summary, Proc DF, Insights, Web, Plan, Status)
    
    if not query or not query.strip():
        yield "", "", None, "", None, "", "", {}, "⚠️ Please enter a valid query"
        return

    # Reset states
    current_final_text = "Analysis in progress..."
    current_sql = ""
    current_raw_df = None
    current_proc_summary = "Waiting for processing..."
    current_proc_df = None
    current_data_insights = "Waiting for analysis..."
    current_web_insights = "Waiting for web context..."
    current_plan_json = {}
    current_status = "Starting query processing..."
    
    # Yield initial state
    yield current_final_text, current_sql, current_raw_df, current_proc_summary, current_proc_df, current_data_insights, current_web_insights, current_plan_json, current_status

    update_queue = queue.Queue()

    def callback_handler(event_type, data):
        update_queue.put((event_type, data))

    def run_in_thread():
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # ---------------------------------------------------------
            # CRITICAL FIX FOR CONCURRENCY:
            # Instantiate the system HERE, inside the thread.
            # This ensures every user gets their own Agent instances, 
            # memory, and database cursors.
            # ---------------------------------------------------------
            local_system = MultiAgentSQLSystem()
            
            result = loop.run_until_complete(local_system.process_query(query.strip(), status_callback=callback_handler))
            update_queue.put(("done", result))
            
        except Exception as e:
            update_queue.put(("error", str(e)))
        finally:
            loop.close()

    # Start the worker thread
    t = threading.Thread(target=run_in_thread)
    t.start()

    # Poll the queue for updates
    while t.is_alive() or not update_queue.empty():
        try:
            event_type, data = update_queue.get(timeout=0.1)
            
            if event_type == "plan":
                current_plan_json = data
                steps_text = "\n".join([f"{s['step_number']}. {s['agent_name']}" for s in data.get('steps', [])])
                current_status = f"📋 Plan Generated:\n{steps_text}\n\nExecuting Step 1..."

            elif event_type == "sql":
                current_sql = data
                current_status = "📝 SQL Generated. Executing..."
            
            elif event_type == "data_raw":
                if isinstance(data, list) and len(data) > 0:
                    df = pd.DataFrame(data)
                    current_raw_df = df.head(100)
                    current_status = f"📊 Raw Data Retrieved ({len(data)} rows)."
            
            elif event_type == "data_processed_summary":
                current_proc_summary = f"✅ **Pandas AI Operation:** {data}"
                current_status = "🐼 Data Processed. Analyzing..."

            elif event_type == "data_insights":
                current_data_insights = f"📊 **Data Analysis**\n\n{data}"
                current_status = "💡 Analysis Generated..."

            elif event_type == "web_insights":
                current_web_insights = f"🌐 **Additional Context**\n\n{data}"
                current_status = "🌐 Web Research Complete..."
            
            elif event_type == "final_text":
                current_final_text = data
                current_status = "🤖 Final Answer Generated."

            elif event_type == "log":
                if "Step" in data: 
                    current_status = f"🔄 {data}"
            
            elif event_type == "error":
                current_status = f"❌ Error: {data}"
            
            elif event_type == "done":
                # Ensure we capture everything from the final result payload
                final_output = data.get('final_output', {})
                
                # Fallback to catch text if event was missed
                if final_output.get('final_text'):
                    current_final_text = final_output.get('final_text')
                
                final_data = final_output.get('data', [])
                plan_steps = data.get('plan', {}).get('steps', [])
                
                # Logic to determine which dataframe to show
                has_pandas = any(s['agent_name'] == 'PandasAgent' for s in plan_steps)
                if has_pandas and final_data:
                    current_proc_df = pd.DataFrame(final_data)
                    if "Waiting" in current_proc_summary:
                        current_proc_summary = "Processed data available."
                elif final_data:
                    current_raw_df = pd.DataFrame(final_data).head(100)
                    current_proc_summary = "No processing step in plan."

                current_status = f"✅ Process Complete at {datetime.now().strftime('%H:%M:%S')}"
            
            yield current_final_text, current_sql, current_raw_df, current_proc_summary, current_proc_df, current_data_insights, current_web_insights, current_plan_json, current_status
            
        except queue.Empty:
            continue

# ------------------------------------------------------------------------------
# UI Layout
# ------------------------------------------------------------------------------
with gr.Blocks(title="Multi-Agent SQL Query System", theme=gr.themes.Soft()) as demo:
    
    gr.Markdown("# 🤖 ProductionGPT")
    gr.Markdown("Submit business questions to the multi-agent swarm.")
    
    with gr.Row():
        with gr.Column(scale=2):
            query_input = gr.Textbox(
                label="Natural Language Query",
                placeholder="e.g., Show me the top 10 suppliers by revenue and check for market risks...",
                lines=3
            )
            with gr.Row():
                submit_btn = gr.Button("🚀 Execute Agents", variant="primary")
                clear_btn = gr.ClearButton(components=[query_input], value="Clear")
        
        with gr.Column(scale=1):
            status_box = gr.Textbox(label="System Status / Logs", interactive=False, lines=6)
    
    gr.Markdown("---")
    
    with gr.Tabs():
        # 1. Final Answer (New Tab)
        with gr.Tab("🤖 Final Answer"):
            final_answer_output = gr.Markdown("### ⏳ Waiting for agents to complete...")

        # 2. Plan
        with gr.Tab("📋 Execution Plan"):
             plan_output = gr.JSON(label="Agent Workflow Plan")

        # 3. SQL
        with gr.Tab("🔍 Generated SQL"):
            sql_output = gr.Code(label="SQL Query", language="sql", lines=10)
        
        # 4. Raw Data
        with gr.Tab("📊 Raw Data (SQL)"):
            gr.Markdown("*First 100 rows of raw database result:*")
            data_raw_output = gr.Dataframe(label="Raw Results", wrap=True, max_height=400)
            
        # 5. Processed Data
        with gr.Tab("🐼 Processed Data (Pandas)"):
            gr.Markdown("*Refined data after PandasAI processing:*")
            proc_summary_output = gr.Markdown("Waiting for processing...")
            data_proc_output = gr.Dataframe(label="Processed Results", wrap=True, max_height=400)
        
        # 6. Analysis
        with gr.Tab("💡 Data Insights"):
            insights_output = gr.Markdown("Execute a query to see insights here...")
        
        # 7. Web Context
        with gr.Tab("🌐 Additional Context"):
            web_output = gr.Markdown("Execute a query to see additional context here...")
    
    # --------------------------------------------------------------------------
    # Event Wiring
    # --------------------------------------------------------------------------
    outputs_list = [
        final_answer_output,
        sql_output, 
        data_raw_output, 
        proc_summary_output, 
        data_proc_output, 
        insights_output, 
        web_output,
        plan_output,
        status_box
    ]

    submit_btn.click(
        fn=process_query_streaming,
        inputs=[query_input],
        outputs=outputs_list
    )
    
    query_input.submit(
        fn=process_query_streaming,
        inputs=[query_input],
        outputs=outputs_list
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, show_error=True)