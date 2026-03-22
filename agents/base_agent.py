"""
Base agent class for all agents in the system
"""
from abc import ABC, abstractmethod
from typing import Any, Dict
from utils.logger import setup_logger


class BaseAgent(ABC):
    """Abstract base class for all agents"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        """
        Initialize base agent
        
        Args:
            name: Agent name
            config: Configuration dictionary
        """
        self.name = name
        self.config = config
        self.logger = setup_logger(
            name=f"Agent.{name}",
            log_file=config.get('logging', {}).get('file', 'multi_agent_sql.log'),
            level=config.get('logging', {}).get('level', 'INFO')
        )
        self.logger.info(f"Initialized {name} agent")
    
    @abstractmethod
    async def execute(self, input_data: Any) -> Any:
        """
        Execute agent's main task
        
        Args:
            input_data: Input data for the agent
        
        Returns:
            Agent's output
        """
        pass
    
    def log_info(self, message: str) -> None:
        """Log info message"""
        self.logger.info(f"[{self.name}] {message}")
    
    def log_error(self, message: str) -> None:
        """Log error message"""
        self.logger.error(f"[{self.name}] {message}")
    
    def log_debug(self, message: str) -> None:
        """Log debug message"""
        self.logger.debug(f"[{self.name}] {message}")