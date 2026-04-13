# Converts the raw JSON pulls into tabular format
# with proper keys

from dataclasses import dataclass

@dataclass
class Market:
    
    def create_from_json(data:dict):
        