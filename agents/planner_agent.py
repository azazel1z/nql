"""
Planner Agent - Deconstructs a user query into a sequential execution plan
"""
from typing import Dict, Any, List, Literal
from openai import OpenAI
from agents.base_agent import BaseAgent
from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    """Represents a single step in the execution plan"""
    step_number: int
    agent_name: Literal[
        "DatabaseAgent", 
        "SQLExecutorAgent", 
        "PandasAgent", 
        "DataAnalysisAgent", 
        "WebResearchAgent", 
        "SummarizerAgent"
    ] = Field(..., description="The exact class name of the agent to call")
    instruction: str = Field(..., description="Comprehensive natural language prompt/instruction for this specific agent")
    expected_output: str = Field(..., description="Description of what this step will produce")


class ExecutionPlan(BaseModel):
    """Represents the full plan"""
    question_understanding: str = Field(..., description="A brief restatement of the user's business question")
    required_data_points: List[str] = Field(..., description="List of specific metrics or data points needed")
    steps: List[PlanStep]
    final_answer_goal: str


class PlannerAgent(BaseAgent):
    """
    Analyzes the user query and creates a step-by-step plan 
    selecting the specific agents required to solve the problem.
    """
    
    DATABASE_SCHEMA = """
    **BUSINESS DOMAIN MAP & CONSTRAINTS:**

    1. 
    2. 
    3. 
    4. 
    
"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__("PlannerAgent", config)
        
        openai_config = config.get('openai', {})
        self.client = OpenAI(api_key=openai_config.get('api_key'))
        self.model = openai_config.get('model', 'gpt-5.1')
        self.temperature = openai_config.get('temperature', 0)
    
    def _build_planning_prompt(self) -> str:
        return f"""
You are the PLANNER AGENT for an enterprise jewelry system.

YOUR GOAL: 
Create a minimal, efficient execution plan that fetches ONLY the data needed to answer the question.

AVAILABLE AGENTS:
1. **DatabaseAgent**: 
   - **Role**: Translate business requirements into SQL.
   - **Instruction Guidelines**:
     * Be MINIMAL and SPECIFIC - request only columns directly needed for the final answer
     * Focus on the WHAT (data needed), not the HOW (table structure)
     * Use business terms (e.g., "vendor performance metrics") not technical terms
     * Example GOOD: "Get total purchase value and count by vendor for last quarter"
     * Example BAD: "Get vendor_id, vendor_name, po_number, po_date, line_amount, currency, status, etc."
   - **CRITICAL**: 
     * Do NOT list out column names unless absolutely necessary
     * Do NOT list out User defined filter values as they may or may not be present in the data and hence cause faulty data. Let the DB agent get the data for all categories.
     * Trust DatabaseAgent to select appropriate tables and joins
     * Keep joins minimal (max 2 tables unless essential)

2. **SQLExecutorAgent**:
   - **Role**: Execute the generated SQL query.
   - **Instruction**: Always use exactly: "Execute the SQL query from the previous step"
   
3. **PandasAgent**:
   - **Role**: Transform and analyze data (calculate, filter, rank, pivot, aggregate).
   - **Instruction Guidelines**:
     * Describe the transformation logic concisely, make sure it doesnt try to make the data to consise hence loosing its usefulness.
     * Example: "Calculate percentage share, rank by value descending, keep top 10"
     * DO NOT ask to convert to JSON/dict/list - output MUST be a DataFrame
   - **CRITICAL**: 
     * Final output must remain as pandas DataFrame
     * Push simple aggregations to DatabaseAgent when possible
     
4. **DataAnalysisAgent**:
   - **Role**: Generate business insights and interpretations from processed data.
   - **Instruction Guidelines**:
     * Request specific analytical perspectives
     * Example: "Identify sourcing concentration risks and suggest diversification strategies"
     * Focus on business implications, not just data description
     
5. **WebResearchAgent**:
   - **Role**: Retrieve external information (market data, competitor info, trends).
   - **When to Use**: When answer requires external knowledge not in database, it can be called with other agents or standalone depending on the requirement.
   - **Instruction**: Be verbose about what external information is needed

6. **SummarizerAgent**:
    - **Role**: Synthesize all gathered data, analysis, and research into a final natural language answer.
    - **Instruction**: "Summarize all collected data and analysis to answer the user's original question."

BUSINESS CONTEXT:
{self.DATABASE_SCHEMA}

PLANNING PRINCIPLES:
1. **Minimize Data Requests**: 
   - Fetch only columns that directly contribute to the answer
   - Avoid "SELECT *" thinking - be surgical about data needs
   - Push calculations to the appropriate layer (SQL for simple aggregations, Pandas for complex transformations)

2. **(IMP) Standard Flow Pattern**:
   - DatabaseAgent → SQLExecutorAgent → PandasAgent → DataAnalysisAgent → (Optional: WebResearchAgent) → SummarizerAgent
   - For queries where the data from the SQL will be less than 100 skip PandasAgent
   - **SummarizerAgent MUST ALWAYS be the last step** in the plan to formulate the final answer.

3. **One Agent, One Purpose**:
   - Each agent should appear at most ONCE in the plan
   - Combine related operations in a single step

4. **Instruction Clarity**:
   - DatabaseAgent: Focus on WHAT data is needed (business metrics), not HOW to get it (columns/tables)
   - PandasAgent: Focus on WHAT transformation is needed, not implementation details
   - Keep instructions under 2 sentences when possible

5. **Web Research**:
   - Use standalone if question cannot be answered from internal data
   - Integrate into flow only if external context enriches internal analysis

TASK: Create a lean execution plan with precise, minimal instructions for each step. Ensure SummarizerAgent is the final step.
"""

    async def execute(self, natural_query: str) -> Dict[str, Any]:
        """
        Generates the execution plan.
        """
        self.log_info(f"Generating plan for: {natural_query}")
        
        prompt = self._build_planning_prompt()
        
        try:
            completion = self.client.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {"role": "system", "content": f"You are a master planner. Output a strict JSON execution plan.\n\n{prompt}"},
                    {"role": "user", "content": natural_query}
                ],
                response_format=ExecutionPlan,
                temperature=self.temperature
            )
            
            plan_data = completion.choices[0].message.parsed
            
            plan_dict = plan_data.model_dump()
            
            self.log_info(f"Plan generated with {len(plan_dict['steps'])} steps.")
            return {
                'success': True,
                'plan': plan_dict
            }
            
        except Exception as e:
            self.log_error(f"Planning failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'plan': None
            }