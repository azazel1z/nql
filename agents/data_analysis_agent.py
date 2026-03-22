"""
Data Analysis Agent - Analyzes SQL results and generates insights
"""
from typing import Dict, Any, List
import json
from openai import OpenAI
from agents.base_agent import BaseAgent


class DataAnalysisAgent(BaseAgent):
    """Agent responsible for analyzing data and generating insights"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Data Analysis Agent
        
        Args:
            config: Configuration dictionary
        """
        super().__init__("DataAnalysisAgent", config)
        
        openai_config = config.get('openai', {})
        self.client = OpenAI(api_key=openai_config.get('api_key'))
        self.model = openai_config.get('model', 'gpt-5.1')
        self.temperature = 0.3 
        self.max_tokens = openai_config.get('max_tokens', 2000)
    
    def _format_data_summary(self, data: List[Dict[str, Any]]) -> str:
        """
        Create a summary of the data for LLM analysis
        
        Args:
            data: List of result dictionaries
        
        Returns:
            Formatted data summary
        """
        if not data:
            return "No data available"
        
        row_count = len(data)
        columns = list(data[0].keys()) if data else []
        
        sample_data = data
        
        summary = f"""
Data Summary:
- Total Rows: {row_count}
- Columns: {', '.join(columns)}

Sample Data:
{json.dumps(sample_data, indent=2, default=str)}
"""
        return summary
    
    async def execute(self, query_result: Dict[str, Any], instruction: str) -> Dict[str, Any]:
        """
        Analyze query results and generate insights
        
        Args:
            query_result: Dictionary containing SQL query results
        
        Returns:
            Dictionary containing analysis and insights
        """
        if not query_result.get('success', False):
            return {
                'success': False,
                'error': 'No valid data to analyze',
                'insights': []
            }
        
        results = query_result.get('results', [])
        sql_query = query_result.get('sql_query', '')
        
        self.log_info(f"Analyzing {len(results)} rows of data")
        
        if not results:
            return {
                'success': True,
                'insights': ['No data returned from the query.'],
                'summary': 'The query executed successfully but returned no results.'
            }
        
        try:
            data_summary = self._format_data_summary(results)
            
            system_prompt = """You are an expert Data Analyst. 
Your goal is to analyze the provided data to satisfy the specific instruction given.
- Rely strictly on the provided data summary and the SQL query context.
- Do NOT follow a fixed template (like "Key Findings", "Recommendations") unless the instruction explicitly asks for it.
- Adapt your tone and output format to the specific question (e.g., if asked for a list, give a list; if asked for a summary, give a narrative).
- Always be data-driven and professional."""
            
            user_prompt = f"""Analyze the following data based on this specific instruction:

Analysis Instruction:
{instruction}

Context (SQL Used):
{sql_query}

{data_summary}

Provide 3-5 key insights based on this data"""
            
            # Call OpenAI API
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature,
                max_completion_tokens=self.max_tokens
            )
            
            analysis = response.choices[0].message.content.strip()
            
            self.log_info("Data analysis completed successfully")
            
            return {
                'success': True,
                'analysis': analysis,
                'data_summary': {
                    'row_count': len(results),
                    'columns': list(results[0].keys()) if results else [],
                    'sample_data': results[:3]  # First 3 rows as sample
                },
                'model_used': self.model
            }
            
        except Exception as e:
            self.log_error(f"Error analyzing data: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'insights': []
            }