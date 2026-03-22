"""
Pandas Agent - Intelligent data processing using PandasAI v3
Intermediary agent to process large datasets before detailed analysis
"""
import pandas as pd
import os
from typing import Dict, Any, Union, List
from agents.base_agent import BaseAgent

import pandasai as pai
from pandasai_litellm.litellm import LiteLLM
from pandasai import Agent

import warnings
warnings.filterwarnings('ignore', category=UserWarning, module='pydantic')


class PandasAgent(BaseAgent):
    """
    Agent that utilizes PandasAI v3 to manipulate, aggregate, or filter 
    dataframes based on natural language queries.
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__("PandasAgent", config)
        
        openai_config = config.get('openai', {})
        api_key = openai_config.get('api_key')
        
        if not api_key:
            raise ValueError("OpenAI API Key is required for PandasAgent")
        
        self.llm = LiteLLM(model="gpt-4.1", api_key=api_key)
        
        pai.config.set({"llm": self.llm})
        
        self.verbose = config.get('verbose', True)
        self.enable_cache = config.get('enable_cache', True)

    async def execute(self, sql_result: Dict[str, Any], instruction: str) -> Dict[str, Any]:
        """
        Execute PandasAI processing on the SQL results using the Agent class
        """
        self.log_info(f"Processing data with PandasAI v3 for query: {instruction}")
        
        raw_data = sql_result.get('results', [])
        if not raw_data:
            self.log_error("No data received from SQL Executor. Skipping Pandas processing.")
            return {
                'success': False, 
                'error': 'No data to process',
                'processed_data': [],
                'summary': 'No data available.'
            }

        try:
            df = pd.DataFrame(raw_data)

            for col in df.select_dtypes(include=['object']).columns:
                try:
                    df[col] = pd.to_numeric(df[col], errors='ignore')
                except:
                    pass

            row_count = len(df)
            
            if df.empty:
                return {
                    'success': True,
                    'processed_data': [],
                    'summary': "Empty result set."
                }

            self.log_info(f"DataFrame created with {row_count} rows. Initializing PandasAI Agent.")

            agent = Agent(df, config={
                "llm": self.llm,
                "save_charts": False,     
                "save_artifacts": False, 
                "open_charts": False
                })

            response = agent.chat(f"""Perform the following task on the dataframe: {instruction}
                                  The final result should always be a dataframe even if it is a single string or int value. 
                                  Make sure to compress the data if there are a large amount (>1000) of rows if not keep the row count the same, do not remove any columns or features, you can add new columns.
                                  **Important: Keep the transformation to the minimum as that leads to errors.**
                                  Even if the question asking for the top or best give 10 rows instead of just one.""")
            
            result = response.value if hasattr(response, 'value') else response

            processed_data = []
            summary_text = ""
            is_dataframe_result = False

            if isinstance(result, dict):
                if 'type' in result and 'value' in result:
                    result_type = result['type']
                    result_value = result['value']
                    
                    if result_type == 'dataframe':
                        result = result_value
                    elif result_type in ['number', 'string', 'plot']:
                        result = result_value
            
            if isinstance(result, pd.DataFrame):
                processed_data = result.to_dict(orient='records')
                summary_text = f"Data aggregated/filtered to {len(processed_data)} rows."
                is_dataframe_result = True
                self.log_info("PandasAI returned a DataFrame")
                
            elif isinstance(result, pd.Series):
                df_result = result.to_frame().reset_index()
                processed_data = df_result.to_dict(orient='records')
                summary_text = "Data reduced to a Series."
                is_dataframe_result = True
                self.log_info("PandasAI returned a Series")
                
            elif isinstance(result, (int, float, str, bool)):
                summary_text = str(result)
                #processed_data = [{"answer": result, "context": "calculated_value"}]
                processed_data = raw_data[:100]
                self.log_info(f"PandasAI returned a scalar: {result}")
                
            elif result is None:
                summary_text = "Analysis completed but no direct data returned."
                processed_data = raw_data[:100]
                self.log_error("PandasAI returned None.")
            
            else:
                summary_text = str(result)
                processed_data = [{"result": str(result)}]
                self.log_error(f"PandasAI returned unexpected type: {type(result)}")

            return {
                'success': True,
                'original_row_count': row_count,
                'processed_row_count': len(processed_data) if is_dataframe_result else 1,
                'processed_data': processed_data,
                'summary': summary_text,
                'is_aggregation': is_dataframe_result
            }

        except Exception as e:
            self.log_error(f"Error in PandasAgent: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'processed_data': raw_data,
                'summary': "Pandas processing failed, reverting to raw data."
            }