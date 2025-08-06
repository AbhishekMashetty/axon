import yaml
import jsonschema
import json
import logging
from typing import Dict, List, Any
from utils.exceptions import ValidationError
from config.schema import get_deployment_schema

logger = logging.getLogger(__name__)

class YAMLProcessor:
    """Handles YAML file parsing and validation for deployment configurations"""
    
    def __init__(self):
        self.schema = get_deployment_schema()
        
    def parse_and_validate(self, filepath: str) -> Dict[str, Any]:
        """Parse YAML file and validate against schema"""
        try:
            # Parse YAML file
            with open(filepath, 'r', encoding='utf-8') as file:
                data = yaml.safe_load(file)
            
            if not data:
                raise ValidationError("YAML file is empty or invalid")
            
            # Validate against schema
            self._validate_schema(data)
            
            # Additional business logic validation
            self._validate_business_rules(data)
            
            logger.info(f"Successfully validated YAML file: {filepath}")
            return data
            
        except yaml.YAMLError as e:
            raise ValidationError(f"YAML parsing error: {str(e)}")
        except FileNotFoundError:
            raise ValidationError(f"File not found: {filepath}")
        except Exception as e:
            logger.error(f"Error processing YAML file {filepath}: {str(e)}")
            raise ValidationError(f"Error processing YAML: {str(e)}")
    
    def _validate_schema(self, data: Dict[str, Any]) -> None:
        """Validate data against JSON schema"""
        try:
            jsonschema.validate(data, self.schema)
        except jsonschema.ValidationError as e:
            raise ValidationError(f"Schema validation error: {e.message}")
        except jsonschema.SchemaError as e:
            raise ValidationError(f"Schema error: {e.message}")
    
    def _validate_business_rules(self, data: Dict[str, Any]) -> None:
        """Apply additional business logic validation"""
        deployments = data.get('deployments', [])
        
        if not deployments:
            raise ValidationError("No deployments specified in YAML")
        
        # Load service mappings for validation
        try:
            with open('config/service_mappings.json', 'r') as f:
                service_mappings = json.load(f)
        except FileNotFoundError:
            logger.warning("Service mappings file not found, skipping service validation")
            service_mappings = {}
        
        valid_pillars = ['clearing', 'risk', 'data', 'shared']
        valid_artifact_types = ['docker', 'helm', 'kustomize']
        
        for i, deployment in enumerate(deployments):
            # Validate pillar
            pillar = deployment.get('pillar', '').lower()
            if pillar not in valid_pillars:
                raise ValidationError(f"Deployment {i+1}: Invalid pillar '{pillar}'. Must be one of: {valid_pillars}")
            
            # Validate service exists in pillar
            service_name = deployment.get('service_name')
            if service_mappings and pillar in service_mappings:
                pillar_services = service_mappings[pillar]
                if service_name not in pillar_services:
                    available_services = list(pillar_services.keys())
                    raise ValidationError(f"Deployment {i+1}: Service '{service_name}' not found in pillar '{pillar}'. Available services: {available_services}")
            
            # Validate artifact type
            artifact_type = deployment.get('docker_artifact_type', '').lower()
            if artifact_type not in valid_artifact_types:
                raise ValidationError(f"Deployment {i+1}: Invalid artifact type '{artifact_type}'. Must be one of: {valid_artifact_types}")
            
            # Validate docker image version format
            image_version = deployment.get('docker_image_version')
            if not image_version or not isinstance(image_version, str):
                raise ValidationError(f"Deployment {i+1}: Invalid docker image version")
            
            # Validate environment and infrastructure IDs
            env_id = deployment.get('environment_id')
            infra_id = deployment.get('infrastructure_id')
            
            if not env_id or not isinstance(env_id, str):
                raise ValidationError(f"Deployment {i+1}: Invalid environment_id")
            
            if not infra_id or not isinstance(infra_id, str):
                raise ValidationError(f"Deployment {i+1}: Invalid infrastructure_id")
        
        logger.info(f"Business rules validation passed for {len(deployments)} deployments")
    
    def extract_deployment_info(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract and normalize deployment information"""
        deployments = []
        
        for deployment in data.get('deployments', []):
            normalized_deployment = {
                'pillar': deployment['pillar'].lower(),
                'service_name': deployment['service_name'],
                'docker_artifact_type': deployment['docker_artifact_type'].lower(),
                'docker_image_version': deployment['docker_image_version'],
                'environment_id': deployment['environment_id'],
                'infrastructure_id': deployment['infrastructure_id'],
                'metadata': deployment.get('metadata', {})
            }
            deployments.append(normalized_deployment)
        
        return deployments
    
    def validate_yaml_string(self, yaml_content: str) -> Dict[str, Any]:
        """Validate YAML content from string"""
        try:
            data = yaml.safe_load(yaml_content)
            self._validate_schema(data)
            self._validate_business_rules(data)
            return data
        except yaml.YAMLError as e:
            raise ValidationError(f"YAML parsing error: {str(e)}")
