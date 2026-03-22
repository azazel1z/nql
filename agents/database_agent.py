"""
Database Agent - Converts natural language to SQL queries
"""
import os
import json
from typing import Dict, Any
from openai import OpenAI
from datetime import datetime
from agents.base_agent import BaseAgent


class DatabaseAgent(BaseAgent):
    """Agent responsible for converting natural language to SQL queries"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Database Agent
        
        Args:
            config: Configuration dictionary
        """
        super().__init__("DatabaseAgent", config)
        
        openai_config = config.get('openai', {})
        self.client = OpenAI(api_key=openai_config.get('api_key'))
        self.model = openai_config.get('model', 'gpt-5.2')
        self.temperature = openai_config.get('temperature', 0)
        
        self.schema_context = self._build_schema_context()

    def _load_schema_from_file(self) -> Dict[str, Any]:
        """
        Loads the JSON schema definition from the external file.
        Assumes 'database_schema.json' is in the same directory as this script.
        """
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(current_dir)
            schema_path = os.path.join(parent_dir, 'database_schema.json')
            
            with open(schema_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.log_error(f"Failed to load schema definition: {str(e)}")
            return {"standard_tables": [], "jms_tables": []}
    
    def _build_schema_context(self) -> str:
        """
        Build database schema context for the LLM
        
        Returns:
            String containing schema information and business logic
        """
        schema_data = self._load_schema_from_file()
        
        standard_schema_str = json.dumps(schema_data.get('standard_tables', []), indent=2)
        #jms_schema_str = json.dumps(schema_data.get('jms_tables', []), indent=2)

        return f"""
You are an SQL Server 2016 DB Agent. Use the following schema to answer user queries.

**CRITICAL BUSINESS LOGIC:**
1.
2.
3.
4. 


**SCHEMA DEFINITION:**
{standard_schema_str}

**Important SQL Server specific syntax:**
- Do not hallucinate column/table names if not present in the schema.
- Use TOP N instead of LIMIT N
- For categorical columns the row values are provided in the schema use those to query if required.
- Use GETDATE() for current date
- Use DATEADD, DATEDIFF for date operations
- Use ISNULL() instead of COALESCE when appropriate
- Always use proper JOIN syntax
- Include appropriate WHERE clauses for filtering
- Microsoft SQL Server version is 2016 one so dont use functions/methods launched after that. 
- Do not assume data values and their meanings unless 100% sure. Example: don't do something like WHERE Status = 1; when its not defined what would that mean.
- **Important:** Careful of many-to-many relationships between the foreign keys use multi column joins, CTE and windows function to make the joins many-to-one.
"""

    async def execute(self, instruction: str) -> Dict[str, Any]:
        """
        Convert natural language query to SQL
        
        Args:
            natural_query: Natural language query from user
        
        Returns:
            Dictionary containing SQL query and metadata
        """
        self.log_info(f"Converting natural language query to SQL: {instruction}")
        
        try:
            now = datetime.now()
            current_date = now.strftime("%Y-%m-%d")
            current_day = now.strftime("%A")

            system_prompt = f"""You are an expert SQL query generator for Microsoft SQL Server.
- Today's Date: {current_date} ({current_day})
- If the user asks for relative dates (e.g., "last Friday", "yesterday"), calculate the specific date based on Today's Date.

{self.schema_context}

Generate a valid SQL Server query based on the user's natural language request.
Return ONLY the SQL query without any explanation, markdown formatting, or additional text.
The query should be safe, efficient, and follow SQL Server best practices.
"""
            
            user_prompt = f"Generate a SQL query for: {instruction}"
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature
            )
            
            sql_query = response.choices[0].message.content.strip()
            
            sql_query = sql_query.replace('```sql', '').replace('```', '').strip()
                        
            return {
                'success': True,
                'sql_query': sql_query,
                'original_query': instruction,
                'model_used': self.model
            }
            
        except Exception as e:
            self.log_error(f"Error generating SQL query: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'original_query': instruction
            }