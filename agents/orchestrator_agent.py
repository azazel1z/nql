"""
Orchestrator Agent - Coordinates the multi-agent workflow based on Planner instructions
"""
from typing import Dict, Any, Callable, Optional, List
from agents.base_agent import BaseAgent
from agents.planner_agent import PlannerAgent
from agents.database_agent import DatabaseAgent
from agents.sql_executor_agent import SQLExecutorAgent
from agents.pandas_agent import PandasAgent
from agents.data_analysis_agent import DataAnalysisAgent
from agents.web_research_agent import WebResearchAgent
from agents.summarizer_agent import SummarizerAgent


class OrchestratorAgent(BaseAgent):
    def __init__(self, config: Dict[str, Any]):
        super().__init__("OrchestratorAgent", config)
        
        self.planner_agent = PlannerAgent(config)
        
        self.database_agent = DatabaseAgent(config)
        self.sql_executor_agent = SQLExecutorAgent(config)
        self.pandas_agent = PandasAgent(config)
        self.data_analysis_agent = DataAnalysisAgent(config)
        self.web_research_agent = WebResearchAgent(config)
        self.summarizer_agent = SummarizerAgent(config)
        
        self.agents = {
            'DatabaseAgent': self.database_agent,
            'SQLExecutorAgent': self.sql_executor_agent,
            'PandasAgent': self.pandas_agent,
            'DataAnalysisAgent': self.data_analysis_agent,
            'WebResearchAgent': self.web_research_agent,
            'SummarizerAgent': self.summarizer_agent
        }
    
    async def execute(self, natural_query: str, callback: Optional[Callable] = None) -> Dict[str, Any]:
        """
        Executes the query by getting a plan and invoking agents sequentially.
        """
        self.log_info(f"Starting workflow for query: {natural_query}")
        
        if callback: 
            callback("log", "Workflow started. Generating Execution Plan...")

        workflow_result = {
            'original_query': natural_query, 
            'success': True, 
            'plan': None,
            'steps_output': {},
            'final_summary': ""
        }
        
        context = {
            'sql_result': {},       
            'data_payload': {},     
            'web_insights': "",     
            'analysis_summary': "",
            'final_text': ""
        }

        try:
            plan_result = await self.planner_agent.execute(natural_query)
            
            if not plan_result['success']:
                return self._fail(workflow_result, f"Planning failed: {plan_result.get('error')}")

            workflow_result['plan'] = plan_result['plan']
            steps = plan_result['plan']['steps']
            
            if callback: 
                callback("plan", plan_result['plan'])

            for step in steps:
                agent_name = step['agent_name']
                instruction = step['instruction']
                step_id = step['step_number']
                
                self.log_info(f"Executing Step {step_id}: {agent_name}")
                if callback:
                    callback("log", f"Step {step_id}: {agent_name} - {step.get('expected_output', 'Processing...')}")

                agent_instance = self.agents.get(agent_name)
                
                if not agent_instance:
                    self.log_error(f"Unknown agent: {agent_name}")
                    continue

                step_output = None
                
                if agent_name == 'DatabaseAgent':
                    step_output = await agent_instance.execute(instruction)
                    
                    if step_output.get('success'):
                        context['sql_result'] = step_output
                        if callback: callback("sql", step_output.get('sql_query'))
                    else:
                        return self._fail(workflow_result, "SQL Generation Failed")

                elif agent_name == 'SQLExecutorAgent':
                    sql_payload = context.get('sql_result')
                    if not sql_payload:
                        return self._fail(workflow_result, "Cannot execute SQL: No SQL generated in previous steps.")
                        
                    step_output = await agent_instance.execute(sql_payload)
                    
                    if step_output.get('success'):
                        context['data_payload'] = step_output 
                        if callback: callback("data_raw", step_output.get('results', []))
                    else:
                        return self._fail(workflow_result, f"SQL Execution Failed: {step_output.get('error')}")

                elif agent_name == 'PandasAgent':
                    current_data = context.get('data_payload')
                    if not current_data or not current_data.get('results'):
                        self.log_error("PandasAgent called but no data available. Skipping.")
                        step_output = {'success': False, 'error': 'No data to process'}
                    else:
                        step_output = await agent_instance.execute(current_data, instruction)
                        
                        if step_output.get('success'):
                            context['data_payload'] = {
                                'success': True,
                                'results': step_output.get('processed_data', []),
                                'summary': step_output.get('summary', '')
                            }
                            if callback: callback("data_processed_summary", step_output.get('summary'))

                elif agent_name == 'DataAnalysisAgent':
                    current_data = context.get('data_payload')
                    step_output = await agent_instance.execute(current_data, instruction)
                    
                    if step_output.get('success'):
                        context['analysis_summary'] = step_output.get('analysis', '')
                        if callback: callback("data_insights", step_output.get('analysis'))

                elif agent_name == 'WebResearchAgent':
                    research_payload = {
                        'instruction': instruction, 
                        'data_analysis': context.get('analysis_summary', '')
                    }
                    step_output = await agent_instance.execute(research_payload)
                    
                    if step_output.get('success'):
                        context['web_insights'] = step_output.get('insights', '')
                        if callback: callback("web_insights", step_output.get('insights'))
                
                elif agent_name == 'SummarizerAgent':
                    summary_payload = {
                        'query': natural_query,
                        'data': context.get('data_payload'),
                        'analysis': context.get('analysis_summary'),
                        'web_research': context.get('web_insights')
                    }
                    step_output = await agent_instance.execute(summary_payload)
                    
                    if step_output.get('success'):
                        context['final_text'] = step_output.get('final_text', '')
                        if callback: callback("final_text", step_output.get('final_text'))

                workflow_result['steps_output'][f"step_{step_id}_{agent_name}"] = step_output

            workflow_result['final_output'] = self._prepare_final_output(workflow_result, context)
            
            if callback: 
                callback("done", workflow_result)
            
            return workflow_result
            
        except Exception as e:
            self.log_error(f"Orchestration Error: {str(e)}")
            if callback: callback("error", str(e))
            return {'success': False, 'error': str(e)}

    def _fail(self, res, error):
        res['success'] = False
        res['error'] = error
        return res

    def _prepare_final_output(self, workflow_result: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Consolidate the final state of the context into a clean result"""
        
        final_data = context.get('data_payload', {}).get('results', [])
        
        return {
            'query': workflow_result.get('original_query'),
            'plan_goal': workflow_result.get('plan', {}).get('final_answer_goal', ''),
            'data': final_data,
            'analysis': context.get('analysis_summary', ''),
            'web_research': context.get('web_insights', ''),
            'final_text': context.get('final_text', ''),
            'success': workflow_result.get('success', False)
        }