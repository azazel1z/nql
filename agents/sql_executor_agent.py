"""
SQL Executor Agent - Executes SQL queries on Microsoft SQL Server
"""
from typing import Dict, Any, List
import pyodbc
from agents.base_agent import BaseAgent


class SQLExecutorAgent(BaseAgent):
    """Agent responsible for executing SQL queries safely"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize SQL Executor Agent
        
        Args:
            config: Configuration dictionary
        """
        super().__init__("SQLExecutorAgent", config)
        
        self.db_config = config.get('database', {})
        self.connection = None
        self.max_retries = config.get('agents', {}).get('max_retries', 3)
    
    def _get_connection_string(self) -> str:
        """
        Build SQL Server connection string
        
        Returns:
            Connection string
        """
        driver = self.db_config.get('driver', 'ODBC Driver 17 for SQL Server')
        server = self.db_config.get('server')
        database = self.db_config.get('database')
        username = self.db_config.get('username')
        password = self.db_config.get('password')
        port = self.db_config.get('port', 1433)
        trust_cert = self.db_config.get('trust_server_certificate', True)

        conn_str = (
            f"DRIVER={{{driver}}};"
            f"SERVER={server},{port};"
            f"DATABASE={database};"
            f"UID={username};"
            f"PWD={password};"
        )
        
        if trust_cert:
            conn_str += "TrustServerCertificate=yes;"
        
        return conn_str
    
    def _connect(self) -> None:
        """Establish database connection"""
        if self.connection is None:
            try:
                conn_str = self._get_connection_string()
                self.connection = pyodbc.connect(conn_str, timeout=30)
                self.log_info("Successfully connected to database")
            except Exception as e:
                self.log_error(f"Failed to connect to database: {str(e)}")
                raise
    
    def _disconnect(self) -> None:
        """Close database connection"""
        if self.connection:
            self.connection.close()
            self.connection = None
            self.log_info("Disconnected from database")
    
    def _is_safe_query(self, sql_query: str) -> bool:
        """
        Check if SQL query is safe to execute (read-only)
        
        Args:
            sql_query: SQL query to check
        
        Returns:
            True if query is safe, False otherwise
        """
        sql_upper = sql_query.upper().strip()
        
        # Dangerous operations
        dangerous_keywords = [
            ' DROP ', 'DELETE ', ' TRUNCATE ', ' INSERT ', ' UPDATE ',
            ' ALTER ', 'CREATE ', ' GRANT ', ' REVOKE ', ' EXEC ',
            ' EXECUTE ', ' SP_ ', ' XP_ '
        ]
        
        for keyword in dangerous_keywords:
            if keyword in sql_upper:
                self.log_error(f"Unsafe query detected: contains {keyword}")
                return False
        
        return True
    
    async def execute(self, sql_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute SQL query and return results
        
        Args:
            sql_data: Dictionary containing SQL query and metadata
        
        Returns:
            Dictionary containing query results
        """
        if not sql_data.get('success', False):
            return {
                'success': False,
                'error': 'Invalid SQL data provided',
                'results': []
            }
        
        sql_query = sql_data.get('sql_query', '')
        
        self.log_info(f"Executing SQL query: {sql_query[:100]}...")
        
        # Safety check
        if not self._is_safe_query(sql_query):
            return {
                'success': False,
                'error': 'Query contains unsafe operations. Only SELECT queries are allowed.',
                'results': []
            }
        
        try:
            self._connect()
            cursor = self.connection.cursor()
            
            cursor.execute(sql_query)
            
            columns = [column[0] for column in cursor.description]
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                results.append(dict(zip(columns, row)))
            
            cursor.close()
            
            self.log_info(f"Query executed successfully. Retrieved {len(results)} rows.")
            
            return {
                'success': True,
                'results': results,
                'columns': columns,
                'row_count': len(results),
                'sql_query': sql_query
            }
            
        except Exception as e:
            self.log_error(f"Error executing SQL query: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'results': [],
                'sql_query': sql_query
            }
        
        finally:
            self._disconnect()