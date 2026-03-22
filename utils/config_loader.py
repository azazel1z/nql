"""
Configuration loader utility
"""
import yaml
from pathlib import Path
from typing import Dict, Any


class ConfigLoader:
    """Load and validate configuration from YAML file"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize configuration loader
        
        Args:
            config_path: Path to configuration file
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """
        Load configuration from YAML file
        
        Returns:
            Dict containing configuration
        
        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config is invalid
        """
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {self.config_path}\n"
                f"Please copy config.yaml.template to config.yaml and fill in your credentials."
            )
        
        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Validate required fields
        self._validate_config(config)
        
        return config
    
    def _validate_config(self, config: Dict[str, Any]) -> None:
        """
        Validate configuration structure
        
        Args:
            config: Configuration dictionary
        
        Raises:
            ValueError: If required fields are missing
        """
        required_fields = {
            #'database': ['server', 'database', 'username', 'password'],
            'database': ['server', 'database'],
            'openai': ['api_key', 'model']
        }
        
        for section, fields in required_fields.items():
            if section not in config:
                raise ValueError(f"Missing required section: {section}")
            
            for field in fields:
                if field not in config[section]:
                    raise ValueError(f"Missing required field: {section}.{field}")
                
                # Check for placeholder values
                value = str(config[section][field])
                if 'your_' in value.lower() or value == '':
                    raise ValueError(
                        f"Please update {section}.{field} in config.yaml with your actual credentials"
                    )
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by dot-notation key
        
        Args:
            key: Configuration key (e.g., 'database.server')
            default: Default value if key not found
        
        Returns:
            Configuration value
        """
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def get_database_config(self) -> Dict[str, Any]:
        """Get database configuration"""
        return self.config.get('database', {})
    
    def get_openai_config(self) -> Dict[str, Any]:
        """Get OpenAI configuration"""
        return self.config.get('openai', {})
    
    def get_agent_config(self) -> Dict[str, Any]:
        """Get agent configuration"""
        return self.config.get('agents', {})