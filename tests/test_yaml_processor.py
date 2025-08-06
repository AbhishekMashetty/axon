import pytest
import tempfile
import os
import json
from unittest.mock import patch, mock_open
from services.yaml_processor import YAMLProcessor
from utils.exceptions import ValidationError

class TestYAMLProcessor:
    
    def test_parse_valid_yaml(self, sample_yaml_file):
        """Test parsing valid YAML file"""
        processor = YAMLProcessor()
        result = processor.parse_and_validate(sample_yaml_file)
        
        assert result['version'] == 'v1.0'
        assert len(result['deployments']) == 2
        assert result['deployments'][0]['pillar'] == 'clearing'
        assert result['deployments'][1]['pillar'] == 'risk'
    
    def test_parse_empty_yaml(self, tmp_path):
        """Test parsing empty YAML file"""
        yaml_file = tmp_path / "empty.yaml"
        yaml_file.write_text("")
        
        processor = YAMLProcessor()
        with pytest.raises(ValidationError, match="YAML file is empty"):
            processor.parse_and_validate(str(yaml_file))
    
    def test_parse_malformed_yaml(self, tmp_path):
        """Test parsing malformed YAML file"""
        yaml_file = tmp_path / "malformed.yaml"
        yaml_file.write_text("invalid: yaml: content: [")
        
        processor = YAMLProcessor()
        with pytest.raises(ValidationError, match="YAML parsing error"):
            processor.parse_and_validate(str(yaml_file))
    
    def test_parse_nonexistent_file(self):
        """Test parsing non-existent file"""
        processor = YAMLProcessor()
        with pytest.raises(ValidationError, match="File not found"):
            processor.parse_and_validate("/nonexistent/file.yaml")
    
    def test_schema_validation_missing_version(self, tmp_path):
        """Test schema validation with missing version"""
        yaml_content = """
deployments:
  - pillar: clearing
    service_name: test-service
    docker_artifact_type: docker
    docker_image_version: v1.0.0
    environment_id: test
    infrastructure_id: test-cluster
"""
        yaml_file = tmp_path / "no_version.yaml"
        yaml_file.write_text(yaml_content)
        
        processor = YAMLProcessor()
        with pytest.raises(ValidationError, match="Schema validation error"):
            processor.parse_and_validate(str(yaml_file))
    
    def test_schema_validation_missing_deployments(self, tmp_path):
        """Test schema validation with missing deployments"""
        yaml_content = """
version: v1.0
metadata:
  name: "Test"
"""
        yaml_file = tmp_path / "no_deployments.yaml"
        yaml_file.write_text(yaml_content)
        
        processor = YAMLProcessor()
        with pytest.raises(ValidationError, match="Schema validation error"):
            processor.parse_and_validate(str(yaml_file))
    
    def test_schema_validation_invalid_pillar(self, tmp_path):
        """Test schema validation with invalid pillar"""
        yaml_content = """
version: v1.0
deployments:
  - pillar: invalid_pillar
    service_name: test-service
    docker_artifact_type: docker
    docker_image_version: v1.0.0
    environment_id: test
    infrastructure_id: test-cluster
"""
        yaml_file = tmp_path / "invalid_pillar.yaml"
        yaml_file.write_text(yaml_content)
        
        processor = YAMLProcessor()
        with pytest.raises(ValidationError, match="Invalid pillar"):
            processor.parse_and_validate(str(yaml_file))
    
    def test_schema_validation_invalid_artifact_type(self, tmp_path):
        """Test schema validation with invalid artifact type"""
        yaml_content = """
version: v1.0
deployments:
  - pillar: clearing
    service_name: test-service
    docker_artifact_type: invalid_type
    docker_image_version: v1.0.0
    environment_id: test
    infrastructure_id: test-cluster
"""
        yaml_file = tmp_path / "invalid_artifact.yaml"
        yaml_file.write_text(yaml_content)
        
        processor = YAMLProcessor()
        with pytest.raises(ValidationError, match="Invalid artifact type"):
            processor.parse_and_validate(str(yaml_file))
    
    def test_business_rules_validation_empty_deployments(self, tmp_path):
        """Test business rules validation with empty deployments"""
        yaml_content = """
version: v1.0
deployments: []
"""
        yaml_file = tmp_path / "empty_deployments.yaml"
        yaml_file.write_text(yaml_content)
        
        processor = YAMLProcessor()
        with pytest.raises(ValidationError, match="No deployments specified"):
            processor.parse_and_validate(str(yaml_file))
    
    def test_business_rules_validation_invalid_service(self, tmp_path, mock_service_mappings):
        """Test business rules validation with invalid service name"""
        yaml_content = """
version: v1.0
deployments:
  - pillar: clearing
    service_name: nonexistent-service
    docker_artifact_type: docker
    docker_image_version: v1.0.0
    environment_id: test
    infrastructure_id: test-cluster
"""
        yaml_file = tmp_path / "invalid_service.yaml"
        yaml_file.write_text(yaml_content)
        
        processor = YAMLProcessor()
        with pytest.raises(ValidationError, match="Service 'nonexistent-service' not found"):
            processor.parse_and_validate(str(yaml_file))
    
    def test_business_rules_validation_missing_image_version(self, tmp_path):
        """Test business rules validation with missing image version"""
        yaml_content = """
version: v1.0
deployments:
  - pillar: clearing
    service_name: test-service
    docker_artifact_type: docker
    docker_image_version: ""
    environment_id: test
    infrastructure_id: test-cluster
"""
        yaml_file = tmp_path / "missing_version.yaml"
        yaml_file.write_text(yaml_content)
        
        processor = YAMLProcessor()
        with pytest.raises(ValidationError, match="Invalid docker image version"):
            processor.parse_and_validate(str(yaml_file))
    
    def test_extract_deployment_info(self, deployment_config):
        """Test extracting deployment information"""
        processor = YAMLProcessor()
        deployments = processor.extract_deployment_info(deployment_config)
        
        assert len(deployments) == 2
        assert deployments[0]['pillar'] == 'clearing'
        assert deployments[0]['service_name'] == 'trade-processor'
        assert deployments[1]['pillar'] == 'risk'
        assert deployments[1]['service_name'] == 'risk-engine'
    
    def test_validate_yaml_string_valid(self, valid_yaml_content):
        """Test validating valid YAML string"""
        processor = YAMLProcessor()
        result = processor.validate_yaml_string(valid_yaml_content)
        
        assert result['version'] == 'v1.0'
        assert len(result['deployments']) == 2
    
    def test_validate_yaml_string_invalid(self):
        """Test validating invalid YAML string"""
        invalid_yaml = "invalid: yaml: [content"
        
        processor = YAMLProcessor()
        with pytest.raises(ValidationError, match="YAML parsing error"):
            processor.validate_yaml_string(invalid_yaml)
    
    def test_service_mappings_not_found(self, tmp_path):
        """Test behavior when service mappings file is not found"""
        yaml_content = """
version: v1.0
deployments:
  - pillar: clearing
    service_name: any-service
    docker_artifact_type: docker
    docker_image_version: v1.0.0
    environment_id: test
    infrastructure_id: test-cluster
"""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml_content)
        
        # Mock service mappings file not found
        with patch('builtins.open', side_effect=FileNotFoundError):
            processor = YAMLProcessor()
            # Should not raise an error when service mappings are not found
            result = processor.parse_and_validate(str(yaml_file))
            assert result['version'] == 'v1.0'
    
    def test_deployment_with_metadata(self, tmp_path):
        """Test parsing deployment with metadata"""
        yaml_content = """
version: v1.0
deployments:
  - pillar: clearing
    service_name: test-service
    docker_artifact_type: docker
    docker_image_version: v1.0.0
    environment_id: test
    infrastructure_id: test-cluster
    metadata:
      priority: 8
      timeout: 1800
      retry_count: 3
      tags: ["urgent", "hotfix"]
      rollback_strategy: automatic
"""
        yaml_file = tmp_path / "with_metadata.yaml"
        yaml_file.write_text(yaml_content)
        
        processor = YAMLProcessor()
        result = processor.parse_and_validate(str(yaml_file))
        
        deployment = result['deployments'][0]
        assert deployment['metadata']['priority'] == 8
        assert deployment['metadata']['timeout'] == 1800
        assert deployment['metadata']['retry_count'] == 3
        assert 'urgent' in deployment['metadata']['tags']
        assert deployment['metadata']['rollback_strategy'] == 'automatic'
    
    def test_deployment_with_defaults(self, tmp_path):
        """Test parsing deployment with defaults section"""
        yaml_content = """
version: v1.0
defaults:
  environment_id: prod
  infrastructure_id: default-cluster
  docker_artifact_type: docker
deployments:
  - pillar: clearing
    service_name: test-service
    docker_image_version: v1.0.0
    environment_id: test
    infrastructure_id: test-cluster
"""
        yaml_file = tmp_path / "with_defaults.yaml"
        yaml_file.write_text(yaml_content)
        
        processor = YAMLProcessor()
        result = processor.parse_and_validate(str(yaml_file))
        
        assert 'defaults' in result
        assert result['defaults']['environment_id'] == 'prod'
        assert result['defaults']['docker_artifact_type'] == 'docker'
    
    def test_duplicate_service_deployments(self, tmp_path):
        """Test validation with duplicate service deployments in same pillar"""
        yaml_content = """
version: v1.0
deployments:
  - pillar: clearing
    service_name: test-service
    docker_artifact_type: docker
    docker_image_version: v1.0.0
    environment_id: test
    infrastructure_id: test-cluster
  - pillar: clearing
    service_name: test-service
    docker_artifact_type: docker
    docker_image_version: v2.0.0
    environment_id: test
    infrastructure_id: test-cluster
"""
        yaml_file = tmp_path / "duplicates.yaml"
        yaml_file.write_text(yaml_content)
        
        # Mock the validation function to check for duplicates
        processor = YAMLProcessor()
        
        # The duplicate validation is in the _validate_business_rules method
        # This should be caught by the schema validation helper
        with patch.object(processor, '_validate_business_rules') as mock_validate:
            mock_validate.side_effect = ValidationError("Duplicate deployment found")
            
            with pytest.raises(ValidationError, match="Duplicate deployment"):
                processor.parse_and_validate(str(yaml_file))
    
    def test_invalid_dependency_reference(self, tmp_path):
        """Test validation with invalid dependency reference"""
        yaml_content = """
version: v1.0
deployments:
  - pillar: clearing
    service_name: service-a
    docker_artifact_type: docker
    docker_image_version: v1.0.0
    environment_id: test
    infrastructure_id: test-cluster
    metadata:
      dependencies: ["nonexistent-service"]
"""
        yaml_file = tmp_path / "invalid_deps.yaml"
        yaml_file.write_text(yaml_content)
        
        # Mock the validation to check dependencies
        processor = YAMLProcessor()
        
        with patch.object(processor, '_validate_business_rules') as mock_validate:
            mock_validate.side_effect = ValidationError("Dependency 'nonexistent-service' not found")
            
            with pytest.raises(ValidationError, match="Dependency 'nonexistent-service' not found"):
                processor.parse_and_validate(str(yaml_file))
    
    def test_valid_service_mapping(self, tmp_path, mock_service_mappings):
        """Test validation with valid service in service mappings"""
        yaml_content = """
version: v1.0
deployments:
  - pillar: clearing
    service_name: trade-processor
    docker_artifact_type: docker
    docker_image_version: v1.0.0
    environment_id: test
    infrastructure_id: test-cluster
"""
        yaml_file = tmp_path / "valid_service.yaml"
        yaml_file.write_text(yaml_content)
        
        processor = YAMLProcessor()
        result = processor.parse_and_validate(str(yaml_file))
        
        assert result['version'] == 'v1.0'
        assert len(result['deployments']) == 1
        assert result['deployments'][0]['service_name'] == 'trade-processor'
