# NQL: Multi-Agent SQL Business Intelligence System

NQL is an agentic business intelligence backend designed to process complex data queries against Microsoft SQL Server databases. 

Rather than relying on single-prompt text-to-SQL generation, this system leverages LangChain's `deepagents` framework to orchestrate specialized subagents. It dynamically builds execution plans, constructs and executes T-SQL queries under strict read-only constraints, utilizes stateful conversation checkpointers, and supplements database metrics with external market context via Claude's native web search tool.

---

## Core Architecture

* **Multi-Agent Orchestration:** Powered by LangChain's `deepagents` framework, a central orchestrator (`claude-haiku-4-5`) analyzes user prompts and delegates tasks to specialized subagents:
  * **SQL Agent (`claude-sonnet-4-6`):** References a schema map to generate, execute, and troubleshoot highly integrated SQL Server queries in a single round-trip.
  * **Web Business Agent (`claude-haiku-4-5`):** Uses Claude's native web search capability (`BetaWebSearchTool20250305Param`) to retrieve qualitative context, market insights, or answer general-knowledge queries.
* **FastAPI Streaming Backend:** Exposes standard endpoints alongside a Server-Sent Events (SSE) streaming endpoint (`/api/chats/{thread_id}/stream`) to deliver real-time token streams directly to the frontend.
* **Stateful Chat Memory:** Integrates LangGraph's `AsyncSqliteSaver` checkpointer to maintain conversational state and thread histories persistently in an SQLite database.
* **Schema-Aware Context:** Ingests a structured `database_schema.json` containing definitions, column properties, and relationship mappings for standard catalog, sales, and inventory tables.
* **Safe Database Access:** Implements a synchronous regex-based query validator to intercept and block mutative SQL execution (e.g., updates, inserts, deletions, schema modifications) before reaching the database connection pool.
* **Secure Session Management:** Employs JWT-based session tokens delivered through secure, HTTP-only cookies, guarded by Cloudflare Turnstile captcha validation during the login phase.

---

## Execution Pipeline

When a natural language query is submitted, the backend routes the request through the following pipeline:

```
                  ┌──────────────────────┐
                  │      User Input      │
                  └──────────┬───────────┘
                             │
                             ▼
               ┌──────────────────────────┐
               │    Main Orchestrator     │
               │   (claude-haiku-4-5)     │
               └──────┬────────────┬──────┘
                      │            │
            ┌─────────┘            └─────────┐
    (Internal Data)                 (Real-time Context)
            │                                │
            ▼                                ▼
┌───────────────────────┐        ┌───────────────────────┐
│       SQL Agent       │        │  Web Business Agent   │
│  (claude-sonnet-4-6)  │        │  (claude-haiku-4-5)   │
└───────────┬───────────┘        └───────────┬───────────┘
            │                                │
            ▼                                │
┌───────────────────────┐                    │
│ Regex Query Validator │                    │
└───────────┬───────────┘                    │
            │                                │
            ▼                                │
┌───────────────────────┐                    │
│   MS SQL Server DB    │                    │
└───────────┬───────────┘                    │
            │                                │
            ▼                                ▼
            └───────────────┬────────────────┘
                            │ (Synthesized Result)
                            ▼
               ┌──────────────────────────┐
               │    Main Orchestrator     │
               └────────────┬─────────────┘
                            │
                            ▼
               ┌──────────────────────────┐
               │   SSE Stream to Client   │
               └──────────────────────────┘
```

1. **Routing Strategy:** The main orchestrator parses the user's message. If a request is independent, the system invokes the `sql-agent` and `web-business-agent` in parallel to optimize delivery speed.
2. **Execution Strategy:**
   * **Database Pipeline:** The `sql-agent` designs SQL Server 2016 compatible T-SQL. A synchronous SQLAlchemy thread executes the query after validating that no unauthorized write commands are present.
   * **Web Search Pipeline:** The `web-business-agent` executes search queries and compiles concise, cited findings.
3. **Synthesis & Formatting:** The orchestrator digests the raw datasets, aggregates large tables to stay within length thresholds, structures tabular blocks cleanly, and pushes the compiled report over SSE.

---

## System Requirements

* Python >3.10
* Microsoft SQL Server 2016 or newer
* ODBC Driver 17 for SQL Server (installed on the host machine)
---

## Installation and Configuration

### 1. Clone the repository
```bash
git clone https://github.com/azazel1z/nql.git
cd nql
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure the Environment
Create a `.env` file in your project's root directory:
```env
# Database Credentials
DB_SERVER=your_database_server_address
DB_NAME=your_database_name
DB_USER=your_database_username
DB_PASSWORD=your_database_password

# Authentication & Security Keys
JWT_SECRET_KEY=your_super_secret_jwt_key
ADMIN_SECRET=your_admin_registration_passcode
TURNSTILE_SECRET=your_cloudflare_turnstile_secret_key

# Model Provider Keys
ANTHROPIC_API_KEY=your_anthropic_api_key
```

### 4. Database Schema Structure
The `sql-agent` references `database_schema.json` to generate valid queries. Ensure your database contains these matching structures or modify the schema file:
* **`core.products`**: Catalog of items, categories, and active statuses.
* **`core.customers`**: Customer profiles and locations.
* **`sales.orders`**: Order records, order totals, and delivery status.
* **`sales.order_items`**: Detailed line items matching products to orders.
* **`inventory.stock`**: Warehouse locations and quantities.

---

## Usage

### 1. Start the API Server
Ensure your database server is running, then launch the FastAPI server using command:
```bash
fastapi run dev
```

---

## Security Policies

* **Regex Mutation Guard:** The database execution path parses queries for write/alter operations using a pre-compiled regular expression, immediately blocking keywords such as `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, and stored procedure executions (`EXEC`).
* **HTTP-Only Session Management:** Access tokens are stored inside strict `SameSite=Strict` and `Secure` HTTP-Only cookies, preventing cross-site scripting (XSS) extraction.
* **CORS and CSP Middlewares:** Implements strict Security Headers Middleware, establishing robust Content Security Policies (CSP) and preventing unauthorized frame rendering (`X-Frame-Options: DENY`).
* **Bot Mitigation:** Registration is gated by an administrative secret key header, and user login triggers Cloudflare Turnstile site verification to minimize brute force risk.