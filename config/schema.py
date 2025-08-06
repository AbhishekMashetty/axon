import json

def get_deployment_schema():
    """Return JSON schema for YAML deployment configuration validation"""
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["version", "deployments"],
        "properties": {
            "version": {
                "type": "string",
                "pattern": "^v[0-9]+\\.[0-9]+$",
                "description": "Schema version (e.g., v1.0)"
            },
            "metadata": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "author": {"type": "string"},
                    "created": {"type": "string", "format": "date-time"}
                }
            },
            "defaults": {
                "type": "object",
                "properties": {
                    "environment_id": {"type": "string"},
                    "infrastructure_id": {"type": "string"},
                    "docker_artifact_type": {"type": "string", "enum": ["docker", "helm", "kustomize"]}
                }
            },
            "deployments": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "required": ["pillar", "service_name", "docker_artifact_type", "docker_image_version"],
                    "properties": {
                        "pillar": {
                            "type": "string",
                            "enum": ["clearing", "risk", "data", "shared"],
                            "description": "Deployment pillar"
                        },
                        "service_name": {
                            "type": "string",
                            "minLength": 1,
                            "pattern": "^[a-zA-Z0-9][a-zA-Z0-9-_]*$",
                            "description": "Service name to deploy"
                        },
                        "docker_artifact_type": {
                            "type": "string",
                            "enum": ["docker", "helm", "kustomize"],
                            "description": "Type of Docker artifact"
                        },
                        "docker_image_version": {
                            "type": "string",
                            "minLength": 1,
                            "description": "Docker image version or tag"
                        },
                        "environment_id": {
                            "type": "string",
                            "minLength": 1,
                            "description": "Target environment identifier"
                        },
                        "infrastructure_id": {
                            "type": "string",
                            "minLength": 1,
                            "description": "Target infrastructure identifier"
                        },
                        "metadata": {
                            "type": "object",
                            "properties": {
                                "priority": {"type": "integer", "minimum": 1, "maximum": 10},
                                "timeout": {"type": "integer", "minimum": 60},
                                "retry_count": {"type": "integer", "minimum": 0, "maximum": 5},
                                "tags": {"type": "array", "items": {"type": "string"}},
                                "dependencies": {"type": "array", "items": {"type": "string"}},
                                "rollback_strategy": {"type": "string", "enum": ["automatic", "manual", "none"]}
                            }
                        }
                    }
                }
            }
        }
    }

def validate_deployment_yaml_structure(data):
    """Additional validation for deployment YAML structure"""
    errors = []
    
    # Check for duplicate service deployments within same pillar
    pillar_services = {}
    for i, deployment in enumerate(data.get('deployments', [])):
        pillar = deployment.get('pillar')
        service = deployment.get('service_name')
        
        if pillar and service:
            key = f"{pillar}/{service}"
            if key in pillar_services:
                errors.append(f"Duplicate deployment for {key} at index {i} (previously at index {pillar_services[key]})")
            else:
                pillar_services[key] = i
    
    # Validate dependency references
    service_names = set()
    for deployment in data.get('deployments', []):
        service_name = deployment.get('service_name')
        if service_name:
            service_names.add(service_name)
    
    for i, deployment in enumerate(data.get('deployments', [])):
        dependencies = deployment.get('metadata', {}).get('dependencies', [])
        for dep in dependencies:
            if dep not in service_names:
                errors.append(f"Deployment {i}: Dependency '{dep}' not found in deployment list")
    
    return errors
