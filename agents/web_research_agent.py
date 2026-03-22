"""
Web Research Agent - Fetches additional context from web searches using OpenAI's web search tool
"""
from typing import Dict, Any
from openai import OpenAI
from agents.base_agent import BaseAgent

class WebResearchAgent(BaseAgent):
    """Agent responsible for web research and context enrichment"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Web Research Agent
        
        Args:
            config: Configuration dictionary
        """
        super().__init__("WebResearchAgent", config)
        
        openai_config = config.get('openai', {})
        self.client = OpenAI(api_key=openai_config.get('api_key'))
        self.model = openai_config.get('model', 'gpt-5.1')
        self.temperature = 1.0
        self.max_tokens = 5000
        self.search_context_size = 'low'
        self.user_location = openai_config.get('user_location', None)
    
    def _perform_web_search(self, instruction: str, data_analysis: str) -> str:
        """
        Use OpenAI's Responses API with web search tool to find relevant information
        
        Args:
            original_query: Original user query
            data_analysis: Data analysis results
        
        Returns:
            Synthesized insights from web search
        """        
        input_prompt = f"""
CONTEXT: 

---

INTERNAL DATA INSIGHTS (From Database):
{data_analysis}

---

RESEARCH INSTRUCTION:
{instruction}

GUIDELINES:
1. Search the web to specifically address the "RESEARCH INSTRUCTION".
2. Use the "COMPANY PROFILE" to ensure relevance.
3. Synthesize the search results into a clear answer. 
4. Do not force a specific format (like SWOT or bullet points) unless the instruction asks for it.
"""
        
        web_search_tool = {
            "type": "web_search",
            "search_context_size": self.search_context_size
        }
        
        if self.user_location:
            web_search_tool["user_location"] = self.user_location
        
        response = self.client.responses.create(
            model=self.model,
            input=input_prompt,
            tools=[web_search_tool],
            temperature=self.temperature,
            max_output_tokens=self.max_tokens
        )
        
        insights_parts = []
        
        for output_item in response.output:
            if hasattr(output_item, 'type') and output_item.type == 'message':
                if hasattr(output_item, 'content'):
                    for content_block in output_item.content:
                        if hasattr(content_block, 'type') and content_block.type == 'output_text':
                            insights_parts.append(content_block.text)
        
        insights = "\n\n".join(insights_parts).strip()
        
        if not insights:
            insights = "Web search completed but no specific insights were generated."
        
        return insights
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform web research and generate additional insights
        
        Args:
            context: Dictionary containing original query and data analysis
        
        Returns:
            Dictionary containing web research insights
        """
        instruction = context.get('instruction', '')
        data_analysis = context.get('data_analysis', '')
        
        self.log_info(f"Executing web research for query: {instruction}")
        
        insights = self._perform_web_search(instruction, data_analysis)
        
        self.log_info("Web research insights generated successfully")
        
        return {
            'success': True,
            'insights': insights,
            'source': 'OpenAI Responses API with web search tool',
            'model_used': self.model,
            'search_context_size': self.search_context_size
        }