"""
Summarizer Agent - Synthesizes all gathered information into a final answer
"""
from typing import Dict, Any
from openai import OpenAI
from agents.base_agent import BaseAgent

class SummarizerAgent(BaseAgent):
    """
    Agent responsible for combining internal data, analysis, and web research 
    into a comprehensive final answer for the user.
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__("SummarizerAgent", config)
        
        openai_config = config.get('openai', {})
        self.client = OpenAI(api_key=openai_config.get('api_key'))
        self.model = openai_config.get('model', 'gpt-4o') 
        self.temperature = 0.5
    
    def _build_summary_prompt(self, query: str, data: Any, analysis: str, web_research: str) -> str:
        data_str = str(data)
        if len(data_str) > 10000:
            data_str = data_str[:10000] + "... [Data Truncated]"

        return f"""
You are the FINAL SUMMARIZER for an enterprise business intelligence system.

USER QUERY: "{query}"

---
SOURCE 1: INTERNAL DATA (SQL/Pandas Output)
{data_str}

---
SOURCE 2: DATA ANALYSIS (Statistical/Business Interpretation)
{analysis}

---
SOURCE 3: WEB RESEARCH (External Context)
{web_research}

---
INSTRUCTIONS:
1. Synthesize an answer to the User Query.
2. Combine the hard numbers from the Internal Data with the strategic insights from the Data Analysis.
3. If Web Research is present, use it to explain external factors (market trends, competitors) that explain the internal data.
4. If there are discrepancies between sources, mention them.
5. FORMATTING: Use Markdown (tables, bold text, lists) for readability.

YOUR GOAL: Provide a decision-ready executive summary. Keep the word count low we do not want to overwhelm the user with a wall of text.
"""

    async def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes the summarization.
        
        Args:
            payload: Dict containing 'query', 'data', 'analysis', and 'web_research'
        """
        query = payload.get('query', '')
        data = payload.get('data', {})
        analysis = payload.get('analysis', '')
        web_research = payload.get('web_research', '')
        
        self.log_info(f"Summarizing results for query: {query}")
        
        prompt = self._build_summary_prompt(query, data, analysis, web_research)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a senior business analyst synthesizing a final report."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.temperature
            )
            
            final_text = response.choices[0].message.content
            
            self.log_info("Summarization complete.")
            
            return {
                'success': True,
                'final_text': final_text
            }
            
        except Exception as e:
            self.log_error(f"Summarization failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'final_text': "Error generating summary."
            }