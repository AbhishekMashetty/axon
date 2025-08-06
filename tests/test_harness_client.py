import pytest
import time
from unittest.mock import patch, MagicMock
import requests
from services.harness_client import HarnessClient
from utils.exceptions import DeploymentError

class TestHarnessClient:
    
    def test_init_with_default_values(self):
        """Test HarnessClient initialization with default values"""
        client = HarnessClient()
        
        assert client.base_url == 'https://app.harness.io'
        assert client.api_token == 'default-token'
        assert client.timeout == 30
        assert client.max_retries == 3
        assert len(client.webhook_urls) == 4
        assert 'clearing' in client.webhook_urls
    
    def test_init_with_environment_variables(self):
        """Test HarnessClient initialization with environment variables"""
        env_vars = {
            'HARNESS_BASE_URL': 'https://custom.harness.io',
            'HARNESS_API_TOKEN': 'custom-token',
            'HARNESS_CLEARING_WEBHOOK': 'https://custom.webhook.site/clearing'
        }
        
        with patch.dict('os.environ', env_vars):
            client = HarnessClient()
            
            assert client.base_url == 'https://custom.harness.io'
            assert client.api_token == 'custom-token'
            assert client.webhook_urls['clearing'] == 'https://custom.webhook.site/clearing'
    
    @patch('requests.post')
    def test_trigger_deployment_success(self, mock_post):
        """Test successful deployment trigger"""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'executionId': 'test-execution-123',
            'status': 'queued'
        }
        mock_post.return_value = mock_response
        
        client = HarnessClient()
        deployment_data = {
            'service_name': 'test-service',
            'docker_artifact_type': 'docker',
            'docker_image_version': 'v1.0.0',
            'environment_id': 'test',
            'infrastructure_id': 'test-cluster'
        }
        
        result = client.trigger_deployment('clearing', deployment_data)
        
        assert result['success'] is True
        assert result['execution_id'] == 'test-execution-123'
        assert 'response' in result
        
        # Verify the request was made correctly
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == client.webhook_urls['clearing']
        assert kwargs['json']['service_name'] == 'test-service'
        assert 'Authorization' in kwargs['headers']
    
    @patch('requests.post')
    def test_trigger_deployment_accepted(self, mock_post):
        """Test deployment trigger with 202 Accepted response"""
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.json.return_value = {
            'execution_id': 'test-execution-456'
        }
        mock_post.return_value = mock_response
        
        client = HarnessClient()
        deployment_data = {
            'service_name': 'test-service',
            'docker_artifact_type': 'docker',
            'docker_image_version': 'v1.0.0',
            'environment_id': 'test',
            'infrastructure_id': 'test-cluster'
        }
        
        result = client.trigger_deployment('risk', deployment_data)
        
        assert result['success'] is True
        assert result['execution_id'] == 'test-execution-456'
    
    @patch('requests.post')
    def test_trigger_deployment_http_error(self, mock_post):
        """Test deployment trigger with HTTP error"""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = 'Bad Request'
        mock_post.return_value = mock_response
        
        client = HarnessClient()
        deployment_data = {
            'service_name': 'test-service',
            'docker_artifact_type': 'docker',
            'docker_image_version': 'v1.0.0',
            'environment_id': 'test',
            'infrastructure_id': 'test-cluster'
        }
        
        with pytest.raises(DeploymentError, match="Failed to trigger deployment after 3 attempts"):
            client.trigger_deployment('data', deployment_data)
    
    @patch('requests.post')
    def test_trigger_deployment_with_retries(self, mock_post):
        """Test deployment trigger with retries"""
        # First two calls fail, third succeeds
        mock_responses = [
            MagicMock(status_code=500, text='Server Error'),
            MagicMock(status_code=502, text='Bad Gateway'),
            MagicMock(status_code=200)
        ]
        mock_responses[2].json.return_value = {'executionId': 'success-123'}
        mock_post.side_effect = mock_responses
        
        client = HarnessClient()
        deployment_data = {
            'service_name': 'test-service',
            'docker_artifact_type': 'docker',
            'docker_image_version': 'v1.0.0',
            'environment_id': 'test',
            'infrastructure_id': 'test-cluster'
        }
        
        with patch('time.sleep'):  # Speed up test by mocking sleep
            result = client.trigger_deployment('shared', deployment_data)
        
        assert result['success'] is True
        assert result['execution_id'] == 'success-123'
        assert mock_post.call_count == 3
    
    @patch('requests.post')
    def test_trigger_deployment_timeout(self, mock_post):
        """Test deployment trigger with timeout"""
        mock_post.side_effect = requests.exceptions.Timeout()
        
        client = HarnessClient()
        deployment_data = {
            'service_name': 'test-service',
            'docker_artifact_type': 'docker',
            'docker_image_version': 'v1.0.0',
            'environment_id': 'test',
            'infrastructure_id': 'test-cluster'
        }
        
        with pytest.raises(DeploymentError, match="timed out after 3 attempts"):
            client.trigger_deployment('clearing', deployment_data)
    
    @patch('requests.post')
    def test_trigger_deployment_request_exception(self, mock_post):
        """Test deployment trigger with request exception"""
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection failed")
        
        client = HarnessClient()
        deployment_data = {
            'service_name': 'test-service',
            'docker_artifact_type': 'docker',
            'docker_image_version': 'v1.0.0',
            'environment_id': 'test',
            'infrastructure_id': 'test-cluster'
        }
        
        with pytest.raises(DeploymentError, match="Request failed after 3 attempts"):
            client.trigger_deployment('clearing', deployment_data)
    
    def test_trigger_deployment_unknown_pillar(self):
        """Test deployment trigger with unknown pillar"""
        client = HarnessClient()
        deployment_data = {}
        
        with pytest.raises(DeploymentError, match="Unknown pillar: unknown"):
            client.trigger_deployment('unknown', deployment_data)
    
    @patch('requests.get')
    def test_get_execution_status_success(self, mock_get):
        """Test successful execution status retrieval"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'status': 'success',
            'executionId': 'test-123',
            'details': {'stage': 'completed'}
        }
        mock_get.return_value = mock_response
        
        client = HarnessClient()
        result = client.get_execution_status('test-123')
        
        assert result['success'] is True
        assert result['status'] == 'success'
        assert 'data' in result
        
        # Verify request
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        assert 'test-123' in args[0]
        assert 'Authorization' in kwargs['headers']
    
    @patch('requests.get')
    def test_get_execution_status_not_found(self, mock_get):
        """Test execution status retrieval with 404"""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = 'Execution not found'
        mock_get.return_value = mock_response
        
        client = HarnessClient()
        result = client.get_execution_status('nonexistent-123')
        
        assert result['success'] is False
        assert 'HTTP 404' in result['error']
    
    @patch('requests.get')
    def test_get_execution_status_request_exception(self, mock_get):
        """Test execution status retrieval with request exception"""
        mock_get.side_effect = requests.exceptions.RequestException("Network error")
        
        client = HarnessClient()
        result = client.get_execution_status('test-123')
        
        assert result['success'] is False
        assert 'Network error' in result['error']
    
    @patch('requests.post')
    def test_cancel_execution_success(self, mock_post):
        """Test successful execution cancellation"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        client = HarnessClient()
        result = client.cancel_execution('test-123')
        
        assert result['success'] is True
        assert 'cancellation requested' in result['message']
        
        # Verify request
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert 'test-123' in args[0]
        assert kwargs['json']['interruptType'] == 'ABORT_ALL'
    
    @patch('requests.post')
    def test_cancel_execution_accepted(self, mock_post):
        """Test execution cancellation with 202 response"""
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_post.return_value = mock_response
        
        client = HarnessClient()
        result = client.cancel_execution('test-123')
        
        assert result['success'] is True
    
    @patch('requests.post')
    def test_cancel_execution_error(self, mock_post):
        """Test execution cancellation with error"""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = 'Cannot cancel execution'
        mock_post.return_value = mock_response
        
        client = HarnessClient()
        result = client.cancel_execution('test-123')
        
        assert result['success'] is False
        assert 'HTTP 400' in result['error']
    
    @patch('requests.post')
    def test_cancel_execution_request_exception(self, mock_post):
        """Test execution cancellation with request exception"""
        mock_post.side_effect = requests.exceptions.RequestException("Network error")
        
        client = HarnessClient()
        result = client.cancel_execution('test-123')
        
        assert result['success'] is False
        assert 'Network error' in result['error']
    
    @patch('requests.get')
    def test_validate_webhook_connectivity_all_pass(self, mock_get):
        """Test webhook connectivity validation - all pass"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        client = HarnessClient()
        results = client.validate_webhook_connectivity()
        
        assert len(results) == 4
        assert all(results.values())  # All should be True
        assert mock_get.call_count == 4
    
    @patch('requests.get')
    def test_validate_webhook_connectivity_some_fail(self, mock_get):
        """Test webhook connectivity validation - some fail"""
        responses = [
            MagicMock(status_code=200),  # clearing - pass
            MagicMock(status_code=500),  # risk - fail
            MagicMock(status_code=404),  # data - fail
            MagicMock(status_code=200),  # shared - pass
        ]
        mock_get.side_effect = responses
        
        client = HarnessClient()
        results = client.validate_webhook_connectivity()
        
        assert results['clearing'] is True
        assert results['risk'] is False
        assert results['data'] is False
        assert results['shared'] is True
    
    @patch('requests.get')
    def test_validate_webhook_connectivity_exception(self, mock_get):
        """Test webhook connectivity validation with exceptions"""
        mock_get.side_effect = [
            MagicMock(status_code=200),  # clearing - pass
            requests.exceptions.RequestException(),  # risk - exception
            requests.exceptions.Timeout(),  # data - timeout
            MagicMock(status_code=200),  # shared - pass
        ]
        
        client = HarnessClient()
        results = client.validate_webhook_connectivity()
        
        assert results['clearing'] is True
        assert results['risk'] is False
        assert results['data'] is False
        assert results['shared'] is True
    
    def test_payload_construction(self):
        """Test that the payload is constructed correctly"""
        client = HarnessClient()
        deployment_data = {
            'service_name': 'test-service',
            'docker_artifact_type': 'docker',
            'docker_image_version': 'v1.2.3',
            'environment_id': 'prod',
            'infrastructure_id': 'k8s-cluster',
            'metadata': {'priority': 8}
        }
        
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'executionId': 'test-123'}
            mock_post.return_value = mock_response
            
            client.trigger_deployment('clearing', deployment_data)
            
            # Verify payload structure
            args, kwargs = mock_post.call_args
            payload = kwargs['json']
            
            assert payload['service_name'] == 'test-service'
            assert payload['docker_artifact_type'] == 'docker'
            assert payload['docker_image_version'] == 'v1.2.3'
            assert payload['environment_id'] == 'prod'
            assert payload['infrastructure_id'] == 'k8s-cluster'
            assert payload['pillar'] == 'clearing'
            assert payload['metadata']['priority'] == 8
            assert 'timestamp' in payload
    
    def test_headers_construction(self):
        """Test that headers are constructed correctly"""
        client = HarnessClient()
        deployment_data = {
            'service_name': 'test-service',
            'docker_artifact_type': 'docker',
            'docker_image_version': 'v1.0.0',
            'environment_id': 'test',
            'infrastructure_id': 'test-cluster'
        }
        
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'executionId': 'test-123'}
            mock_post.return_value = mock_response
            
            client.trigger_deployment('clearing', deployment_data)
            
            # Verify headers
            args, kwargs = mock_post.call_args
            headers = kwargs['headers']
            
            assert headers['Content-Type'] == 'application/json'
            assert headers['Authorization'] == f'Bearer {client.api_token}'
            assert headers['User-Agent'] == 'BatchDeploymentSystem/1.0'
