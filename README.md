# NQL: Multi-Agent SQL Business Intelligence System

NQL is a thread-safe, multi-agent system designed to process complex business intelligence queries against Microsoft SQL Server databases. 

Rather than relying on zero-shot LLM prompts, this system utilizes an agentic pipeline. It autonomously constructs execution plans, generates T-SQL, executes queries under strict read-only constraints, processes resulting datasets via Pandas, fetches external context via web search, and compiles the output into a structured summary.

## Core Architecture

* **Multi-Agent Distribution:** Workloads are isolated across specialized agents (Planner, Database, SQL Executor, Pandas, Analysis, Web, and Summarizer) to optimize accuracy and mitigate hallucination risks.
* **Database Integration:** Connects natively to Microsoft SQL Server via `pyodbc`.
* **Schema-Aware Generation:** Ingests a customizable `database_schema.json` file to map table relationships, column definitions, and business logic constraints prior to SQL generation.
* **Programmatic Data Processing:** Utilizes PandasAI to handle intermediate dataset transformations, aggregations, and filtering that exceed standard LLM context windows.
* **External Context Enrichment:** Integrates OpenAI's web search to supplement internal database metrics with real-time market data.
* **Thread-Safe Interface:** Provides a concurrent Gradio web UI that streams execution telemetry, raw data, SQL generation, and final outputs.

## Execution Pipeline

When a natural language query is submitted, the system routes the request through the following pipeline:

1. **Planner Agent:** Deconstructs the query into a sequential execution plan.
2. **Database Agent:** Evaluates the schema definition and translates the execution plan into Microsoft SQL Server T-SQL.
3. **SQL Executor Agent:** Parses the SQL for safety violations, executes the query, and retrieves the raw dataset.
4. **Pandas Agent (Optional):** Applies Python DataFrame transformations if the result set requires statistical manipulation or complex aggregation.
5. **Data Analysis Agent:** Evaluates the processed data to extract specific findings.
6. **Web Research Agent (Optional):** Queries external sources for supplementary market conditions or contextual data.
7. **Summarizer Agent:** Compiles the database outputs, analytical findings, and web research into a final Markdown report.

## System Requirements

* Python 3.11 (Since PandasAI doesnt support later versions)
* Microsoft SQL Server
* ODBC Driver 17 for SQL Server (installed on the host machine)
* OpenAI API Key (requires access to models supporting structured outputs and web search)

## Installation and Configuration

**1. Clone the repository**
```bash
git clone https://github.com/azazel1z/nql.git
cd nql
```

**2. Install dependencies**
```bash
pip install -r requirements.txt
```

**3. Configure Environment**
Create a `config.yaml` file in the root directory:
```yaml
database:
  driver: "ODBC Driver 17 for SQL Server"
  server: "your_server_address"
  database: "your_database_name"
  username: "your_db_username"
  password: "your_db_password"
  port: 1433
  trust_server_certificate: true

openai:
  api_key: "sk-your-openai-api-key"
  model: "gpt-5.1"

logging:
  level: "INFO"
  file: "logs/nql.log"
```

**4. Define Database Schema**
Modify the `database_schema.json` file in the root directory. This file dictates how the Database Agent interprets your tables, columns, categorical variables, and foreign key relationships.

## Usage

Initialize the application:
```bash
python app.py
```

1. Access the interface via `http://localhost:7860`.
2. Input a query into the prompt field.
3. Monitor the System Logs to observe agent execution.
4. Use the interface tabs (Final Answer, Execution Plan, Generated SQL, Raw Data) to review the intermediate outputs of the pipeline.

## Security and Concurrency

* **Query Safety:** The SQL Executor Agent actively parses all generated code and blocks execution of DDL and DML operations (e.g., DROP, DELETE, TRUNCATE, INSERT, UPDATE, ALTER, EXEC).
* **Process Isolation:** The Gradio interface spawns isolated agent instances and database cursors per user session. This ensures concurrent requests do not share execution states or expose data across threads.