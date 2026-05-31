import json
import asyncio
import sqlalchemy
import re
from sqlalchemy import text
from datetime import datetime
from dotenv import load_dotenv

from langchain_core.tools import tool
from deepagents import create_deep_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware
from anthropic.types.beta import BetaWebSearchTool20250305Param 
from database import engine

load_dotenv()

with open("database_schema.json", "r") as f:
    schema_data = json.load(f)
    db_schema_str = json.dumps(schema_data, indent=2)

_ANYWHERE_WRITE_PATTERN = re.compile(
    r'\b(INSERT|UPDATE|DELETE|MERGE|TRUNCATE|DROP|CREATE|ALTER|EXEC|EXECUTE|GRANT|REVOKE|DENY|SP_|XP_)\b',
    re.IGNORECASE
)

def _validate_read_only(query: str) -> str | None:
    if _ANYWHERE_WRITE_PATTERN.search(query):
        matched = _ANYWHERE_WRITE_PATTERN.search(query).group().strip().upper()
        return f"Blocked: Query contains disallowed keyword '{matched}'. Read Only queries are permitted."
    return None

def _sync_execute_sql(query: str) -> str:
    """Synchronous database call. Kept separate so we can run it in a threadpool."""
    if error := _validate_read_only(query):
        return error
    
    try:
        with engine.connect() as conn:
            result = conn.execute(text(query))
            if result.returns_rows:
                rows = result.fetchmany(500) 
                columns = list(result.keys())
                
                if not rows:
                    return "Query returned no rows."
                
                lines = ["\t".join(columns)]
                lines += ["\t".join(str(val) for val in row) for row in rows]
                
                if len(rows) == 500:
                    lines.append("\n... [WARNING: Output truncated. Use aggregation.] ...")
                    
                return "\n".join(lines)
    except Exception as e:
        return f"SQL Error: {str(e)}"

@tool
async def execute_sql_query(query: str) -> str:
    """Executes a SQL Server query and returns the results as a string."""
    return await asyncio.to_thread(_sync_execute_sql, query)

web_search_tool = BetaWebSearchTool20250305Param(
    name="web_search",
    type="web_search_20250305",
    max_uses=3,
)

def get_sql_subagent():
    now = datetime.now()
    current_date = now.strftime("%Y-%m-%d")
    current_day = now.strftime("%A")
    return {
        "name": "sql-agent",
        "description": "Delegated to fetch structured data from the database. Use when the question requires internal data, metrics, or records.",
        "system_prompt": f"""<database_schema>
{db_schema_str}
</database_schema>

<role>
You are an MS SQL Server 2016 data analyst. Your only job is to write one query, run it, and return the raw results.
</role>

<output_contract>
Respond directly without preamble. Your response must follow this format:

If the query succeeds:
- Output the data as a compact table or key numbers only.
- Include a brief, plain-text explanation only if a finding is genuinely non-obvious from the numbers alone.
- Keep the response concise and truncate large datasets naturally into a summary.

If the query fails after retries:
- Output exactly: "QUERY_FAILED: [exact error message]"
</output_contract>

<single_query_rule>
Answer the entire question in one or two execute_sql_query calls.
- Combine logic using CTEs, joins, aggregations, and window functions to ensure many-to-one joins.
- Write direct, comprehensive queries rather than exploratory checks.
- If a question is complex, make your best attempt to answer it within this constraint.
</single_query_rule>

<retry_rule>
If execute_sql_query returns a SQL Error, evaluate the error, fix the query, and retry exactly once. If the second attempt fails, stop and return the QUERY_FAILED message.
</retry_rule>

<query_strategy>
Choose based on question type:
- AGGREGATION (counts, trends, rankings): Group data logically (GROUP BY, COUNT, AVG, CASE WHEN) and return 10-20 grouped rows maximum.
- ROW FETCH (specific records, recent entries): Limit results using TOP 100. Select only relevant columns instead of SELECT *.
- Always use DataAreaID alongside the main join column.

Today: {current_date} ({current_day})
</query_strategy>

<business_logic>

</business_logic>""",
        "tools": [execute_sql_query],
        "model": "claude-sonnet-4-6",
    }

web_business_subagent = {
    "name": "web-business-agent",
    "description": "Delegated to answer questions requiring company business rules, external web search, or qualitative market insights. Also handles general-knowledge and non-database questions.",
    "system_prompt": """<role>
You are a business analyst for xyz company. Answer questions using company knowledge or web search.
</role>

<business_knowledge>

</business_knowledge>


<output_contract>
Respond directly without preamble or conversational filler phrases like "Based on my research".
- For facts and figures: Present as concise bullet points.
- For web search results: Cite the specific key finding in a single sentence.
- For general questions: Provide a single, direct answer.
- Format strictly in plain text. Avoid emojis or special characters.
</output_contract>""",
    "tools": [web_search_tool],
    "model": "claude-haiku-4-5",
}

main_system_prompt = """<role>
You are a business intelligence orchestrator for xyz company. Your task is to route questions to the correct specialized subagents, synthesize their findings, and deliver a clear, formatted answer to the user.
</role>

<subagents>
- sql-agent: internal data (products, vendors, POs, GRNs, sales, inventory, margins, stock levels).
- web-business-agent: business rules, market context, competitor info, general knowledge, web search.
</subagents>

<use_parallel_tool_calls>
If you intend to call multiple tools or subagents and there are no dependencies between them, make all of the independent tool calls in parallel. For example, if a question requires both internal database metrics and external market context, invoke both the sql-agent and web-business-agent simultaneously. Maximize the use of parallel tool calls to increase speed and efficiency.
</use_parallel_tool_calls>

<routing_instructions>
Before delegating to the sql-agent, carefully rephrase the question into concrete data requirements. 
Provide the subagent with a precise, answerable request so it can formulate the exact query immediately.
</routing_instructions>

<output_rules>
Adhere strictly to these formatting rules for your final response to the user:
1. Critical: Never output your thinking or intermediate steps use them to prompt the sub agents.
1. Synthesize the subagent results to directly answer the user's question. Avoid simply passing raw subagent output through.
2. **Present tabular data cleanly with proper formatting (using '\\n' before and after tables). Other wise the table in UI wouldnt be understandable.**
3. Let the data speak for itself. Incorporate data points naturally into your sentences and provide commentary only if an insight is non-obvious.
4. Aggregate large datasets (more than 20 rows) into concise summaries rather than dumping long lists.
5. Maintain a professional tone using standard text characters. Avoid markdown formatting like emojis or special characters.
6. limit: Final responses must not exceed 300 words or 15 table rows total.
   Never present multiple full tables — pick the top 1 or 2 most relevant breakdown.
   Omit any section where the dominant value is "Unknown" or "Unmapped" — these 
   are data quality issues, not business insights.
</output_rules>"""