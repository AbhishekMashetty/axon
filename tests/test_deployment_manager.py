import pytest
import time
import os
from unittest.mock import patch, MagicMock, call
from concurrent.futures import Future
from services.deployment_manager import DeploymentManager
from models import Deployment, DeploymentBatch, DeploymentStatus, Pillar
from utils.exceptions import DeploymentError

class TestDeploymentManager:
    
    def test_init_with_default_values(self):
        """Test DeploymentManager initialization with default values"""
        manager = DeploymentManager()
        
        assert manager.max_workers == 5  # Default from environment
        assert manager.deployment_timeout == 1800  # Default 30 minutes
        assert manager.validation_retry_count == 3  # Default
        assert manager.validation_retry_delay == 30  # Default
        assert manager.harness_client is not None
        assert manager.k8s_client is not None
        assert manager.yaml_processor is not None
    
    def test_init_with_environment_variables(self):
        """Test DeploymentManager initialization with custom environment variables"""
        env_vars = {
            'MAX_DEPLOYMENT_WORKERS': '10',
            'DEPLOYMENT_TIMEOUT': '3600',
            'VALIDATION_RETRY_COUNT': '5',
            'VALIDATION_RETRY_DELAY': '60'
        }
        
        with patch.dict(os.environ, env_vars):
            manager = DeploymentManager()
            
            assert manager.max_workers == 10
            assert manager.deployment_timeout == 3600
            assert manager.validation_retry_count == 5
            assert manager.validation_retry_delay == 60
    
    @patch('services.deployment_manager.db')
    def test_process_batch_deployment_parallel(self, mock_db, sample_deployment_batch, 
                                             deployment_config, mock_harness_client, 
                                             mock_k8s_client, mock_yaml_processor):
        """Test parallel batch deployment processing"""
        manager = DeploymentManager()
        manager.harness_client = mock_harness_client.return_value
        manager.k8s_client = mock_k8s_client.return_value
        manager.yaml_processor = mock_yaml_processor.return_value
        
        # Mock database operations
        mock_db.session.commit.return_value = None
        mock_db.session.add.return_value = None
        
        # Mock DeploymentBatch.query
        mock_query = MagicMock()
        mock_query.filter_by.return_value.first.return_value = sample_deployment_batch
        
        with patch('services.deployment_manager.DeploymentBatch') as mock_batch_model:
            mock_batch_model.query = mock_query
            
            with patch('services.deployment_manager.Deployment') as mock_deployment_model:
                with patch.object(manager, '_process_parallel_deployments') as mock_parallel:
                    mock_parallel.return_value = [
                        {'success': True, 'deployment_id': 1},
                        {'success': True, 'deployment_id': 2}
                    ]
                    
                    manager.process_batch_deployment(
                        sample_deployment_batch.batch_id, 
                        deployment_config, 
                        'parallel'
                    )
                    
                    mock_parallel.assert_called_once()
                    assert sample_deployment_batch.status == DeploymentStatus.SUCCESS
                    assert sample_deployment_batch.successful_deployments == 2
                    assert sample_deployment_batch.failed_deployments == 0
    
    @patch('services.deployment_manager.db')
    def test_process_batch_deployment_sequential(self, mock_db, sample_deployment_batch, 
                                               deployment_config, mock_harness_client, 
                                               mock_k8s_client, mock_yaml_processor):
        """Test sequential batch deployment processing"""
        manager = DeploymentManager()
        manager.harness_client = mock_harness_client.return_value
        manager.k8s_client = mock_k8s_client.return_value
        manager.yaml_processor = mock_yaml_processor.return_value
        
        # Mock database operations
        mock_db.session.commit.return_value = None
        mock_db.session.add.return_value = None
        
        # Mock DeploymentBatch.query
        mock_query = MagicMock()
        mock_query.filter_by.return_value.first.return_value = sample_deployment_batch
        
        with patch('services.deployment_manager.DeploymentBatch') as mock_batch_model:
            mock_batch_model.query = mock_query
            
            with patch('services.deployment_manager.Deployment') as mock_deployment_model:
                with patch.object(manager, '_process_sequential_deployments') as mock_sequential:
                    mock_sequential.return_value = [
                        {'success': True, 'deployment_id': 1},
                        {'success': False, 'deployment_id': 2, 'error': 'Test error'}
                    ]
                    
                    manager.process_batch_deployment(
                        sample_deployment_batch.batch_id, 
                        deployment_config, 
                        'sequential'
                    )
                    
                    mock_sequential.assert_called_once()
                    assert sample_deployment_batch.status == DeploymentStatus.FAILED
                    assert sample_deployment_batch.successful_deployments == 1
                    assert sample_deployment_batch.failed_deployments == 1
    
    @patch('services.deployment_manager.db')
    def test_process_batch_deployment_batch_not_found(self, mock_db):
        """Test batch deployment processing when batch is not found"""
        manager = DeploymentManager()
        
        # Mock DeploymentBatch.query returning None
        mock_query = MagicMock()
        mock_query.filter_by.return_value.first.return_value = None
        
        with patch('services.deployment_manager.DeploymentBatch') as mock_batch_model:
            mock_batch_model.query = mock_query
            
            with pytest.raises(DeploymentError, match="Batch test-batch-123 not found"):
                manager.process_batch_deployment('test-batch-123', {}, 'parallel')
    
    @patch('services.deployment_manager.ThreadPoolExecutor')
    def test_process_parallel_deployments_success(self, mock_executor):
        """Test successful parallel deployment processing"""
        manager = DeploymentManager()
        
        # Create mock deployments
        deployments = [
            MagicMock(id=1, pillar=Pillar.CLEARING, service_name='service1'),
            MagicMock(id=2, pillar=Pillar.RISK, service_name='service2')
        ]
        
        # Mock ThreadPoolExecutor
        mock_executor_instance = MagicMock()
        mock_executor.return_value.__enter__.return_value = mock_executor_instance
        
        # Mock futures
        future1 = MagicMock()
        future1.result.return_value = {'success': True, 'deployment_id': 1}
        future2 = MagicMock()
        future2.result.return_value = {'success': True, 'deployment_id': 2}
        
        mock_executor_instance.submit.side_effect = [future1, future2]
        
        with patch('services.deployment_manager.as_completed') as mock_as_completed:
            mock_as_completed.return_value = [future1, future2]
            
            with patch.object(manager, '_process_single_deployment') as mock_single:
                results = manager._process_parallel_deployments(deployments)
                
                assert len(results) == 2
                assert all(result['success'] for result in results)
                assert mock_executor_instance.submit.call_count == 2
    
    @patch('services.deployment_manager.ThreadPoolExecutor')
    def test_process_parallel_deployments_with_exception(self, mock_executor):
        """Test parallel deployment processing with exception"""
        manager = DeploymentManager()
        
        # Create mock deployments
        deployments = [
            MagicMock(id=1, pillar=Pillar.CLEARING, service_name='service1'),
            MagicMock(id=2, pillar=Pillar.RISK, service_name='service2')
        ]
        
        # Mock ThreadPoolExecutor
        mock_executor_instance = MagicMock()
        mock_executor.return_value.__enter__.return_value = mock_executor_instance
        
        # Mock futures - one succeeds, one fails
        future1 = MagicMock()
        future1.result.return_value = {'success': True, 'deployment_id': 1}
        future2 = MagicMock()
        future2.result.side_effect = Exception("Processing error")
        
        mock_executor_instance.submit.side_effect = [future1, future2]
        
        with patch('services.deployment_manager.as_completed') as mock_as_completed:
            mock_as_completed.return_value = [future1, future2]
            
            with patch('services.deployment_manager.db'):
                results = manager._process_parallel_deployments(deployments)
                
                assert len(results) == 2
                assert results[0]['success'] is True
                assert results[1]['success'] is False
                assert 'Processing error' in results[1]['error']
    
    def test_process_sequential_deployments_success(self):
        """Test successful sequential deployment processing"""
        manager = DeploymentManager()
        
        # Create mock deployments
        deployments = [
            MagicMock(id=1, pillar=Pillar.CLEARING, service_name='service1'),
            MagicMock(id=2, pillar=Pillar.RISK, service_name='service2')
        ]
        
        with patch.object(manager, '_process_single_deployment') as mock_single:
            mock_single.side_effect = [
                {'success': True, 'deployment_id': 1},
                {'success': True, 'deployment_id': 2}
            ]
            
            results = manager._process_sequential_deployments(deployments)
            
            assert len(results) == 2
            assert all(result['success'] for result in results)
            assert mock_single.call_count == 2
    
    def test_process_sequential_deployments_with_failure(self):
        """Test sequential deployment processing with one failure"""
        manager = DeploymentManager()
        
        # Create mock deployments
        deployments = [
            MagicMock(id=1, pillar=Pillar.CLEARING, service_name='service1'),
            MagicMock(id=2, pillar=Pillar.RISK, service_name='service2')
        ]
        
        with patch.object(manager, '_process_single_deployment') as mock_single:
            mock_single.side_effect = [
                {'success': True, 'deployment_id': 1},
                {'success': False, 'deployment_id': 2, 'error': 'Deployment failed'}
            ]
            
            results = manager._process_sequential_deployments(deployments)
            
            assert len(results) == 2
            assert results[0]['success'] is True
            assert results[1]['success'] is False
            assert mock_single.call_count == 2
    
    def test_process_sequential_deployments_with_exception(self):
        """Test sequential deployment processing with exception"""
        manager = DeploymentManager()
        
        # Create mock deployments
        deployments = [
            MagicMock(id=1, pillar=Pillar.CLEARING, service_name='service1'),
            MagicMock(id=2, pillar=Pillar.RISK, service_name='service2')
        ]
        
        with patch.object(manager, '_process_single_deployment') as mock_single:
            mock_single.side_effect = [
                {'success': True, 'deployment_id': 1},
                Exception("Processing error")
            ]
            
            with patch('services.deployment_manager.db'):
                results = manager._process_sequential_deployments(deployments)
                
                assert len(results) == 2
                assert results[0]['success'] is True
                assert results[1]['success'] is False
                assert 'Processing error' in results[1]['error']
    
    @patch('services.deployment_manager.db')
    def test_process_single_deployment_success(self, mock_db, mock_harness_client, mock_k8s_client):
        """Test successful single deployment processing"""
        manager = DeploymentManager()
        manager.harness_client = mock_harness_client.return_value
        manager.k8s_client = mock_k8s_client.return_value
        
        # Create mock deployment
        deployment = MagicMock()
        deployment.id = 1
        deployment.pillar = Pillar.CLEARING
        deployment.service_name = 'test-service'
        deployment.docker_artifact_type = 'docker'
        deployment.docker_image_version = 'v1.0.0'
        deployment.environment_id = 'test'
        deployment.infrastructure_id = 'test-cluster'
        
        # Mock Harness client response
        manager.harness_client.trigger_deployment.return_value = {
            'success': True,
            'execution_id': 'test-execution-123'
        }
        
        with patch.object(manager, '_wait_and_validate_deployment') as mock_validate:
            mock_validate.return_value = {'success': True}
            
            result = manager._process_single_deployment(deployment)
            
            assert result['success'] is True
            assert result['deployment_id'] == 1
            assert result['execution_id'] == 'test-execution-123'
            assert deployment.status == DeploymentStatus.SUCCESS
    
    @patch('services.deployment_manager.db')
    def test_process_single_deployment_harness_failure(self, mock_db, mock_harness_client):
        """Test single deployment processing with Harness failure"""
        manager = DeploymentManager()
        manager.harness_client = mock_harness_client.return_value
        
        # Create mock deployment
        deployment = MagicMock()
        deployment.id = 1
        deployment.pillar = Pillar.CLEARING
        deployment.service_name = 'test-service'
        
        # Mock Harness client failure
        manager.harness_client.trigger_deployment.return_value = {
            'success': False,
            'error': 'Harness API error'
        }
        
        result = manager._process_single_deployment(deployment)
        
        assert result['success'] is False
        assert 'Harness deployment failed' in result['error']
        assert deployment.status == DeploymentStatus.FAILED
    
    @patch('services.deployment_manager.db')
    def test_process_single_deployment_validation_failure(self, mock_db, mock_harness_client):
        """Test single deployment processing with validation failure"""
        manager = DeploymentManager()
        manager.harness_client = mock_harness_client.return_value
        
        # Create mock deployment
        deployment = MagicMock()
        deployment.id = 1
        deployment.pillar = Pillar.CLEARING
        deployment.service_name = 'test-service'
        deployment.harness_execution_id = None
        
        # Mock Harness client success
        manager.harness_client.trigger_deployment.return_value = {
            'success': True,
            'execution_id': 'test-execution-123'
        }
        
        with patch.object(manager, '_wait_and_validate_deployment') as mock_validate:
            mock_validate.return_value = {
                'success': False,
                'error': 'Validation failed'
            }
            
            result = manager._process_single_deployment(deployment)
            
            assert result['success'] is False
            assert deployment.status == DeploymentStatus.FAILED
            assert deployment.error_message == 'Validation failed'
    
    @patch('services.deployment_manager.db')
    def test_process_single_deployment_exception(self, mock_db):
        """Test single deployment processing with exception"""
        manager = DeploymentManager()
        manager.harness_client = MagicMock()
        manager.harness_client.trigger_deployment.side_effect = Exception("Connection error")
        
        # Create mock deployment
        deployment = MagicMock()
        deployment.id = 1
        deployment.pillar = Pillar.CLEARING
        deployment.service_name = 'test-service'
        
        result = manager._process_single_deployment(deployment)
        
        assert result['success'] is False
        assert 'Connection error' in result['error']
        assert deployment.status == DeploymentStatus.FAILED
    
    @patch('time.time')
    @patch('time.sleep')
    def test_wait_and_validate_deployment_success(self, mock_sleep, mock_time, mock_harness_client, mock_k8s_client):
        """Test successful deployment validation with wait"""
        manager = DeploymentManager()
        manager.harness_client = mock_harness_client.return_value
        manager.k8s_client = mock_k8s_client.return_value
        manager.deployment_timeout = 300
        manager.validation_retry_count = 2
        
        # Mock time progression
        mock_time.side_effect = [0, 30, 60]  # Simulate time progression
        
        # Create mock deployment
        deployment = MagicMock()
        deployment.pillar = Pillar.CLEARING
        deployment.service_name = 'test-service'
        deployment.infrastructure_id = 'test-ns'
        deployment.harness_execution_id = 'test-execution-123'
        
        # Mock Harness status check
        manager.harness_client.get_execution_status.return_value = {
            'success': True,
            'status': 'success'
        }
        
        # Mock Kubernetes validation
        manager.k8s_client.validate_deployment.return_value = {
            'success': True,
            'ready': True
        }
        
        result = manager._wait_and_validate_deployment(deployment)
        
        assert result['success'] is True
    
    @patch('time.time')
    @patch('time.sleep')
    def test_wait_and_validate_deployment_timeout(self, mock_sleep, mock_time):
        """Test deployment validation timeout"""
        manager = DeploymentManager()
        manager.deployment_timeout = 100  # Short timeout for test
        
        # Mock time progression to exceed timeout
        mock_time.side_effect = [0, 50, 150]  # Exceeds timeout
        
        # Create mock deployment
        deployment = MagicMock()
        deployment.harness_execution_id = 'test-execution-123'
        
        result = manager._wait_and_validate_deployment(deployment)
        
        assert result['success'] is False
        assert 'timeout' in result['error'].lower()
    
    @patch('time.time')
    @patch('time.sleep')
    def test_wait_and_validate_deployment_harness_failure(self, mock_sleep, mock_time, mock_harness_client):
        """Test deployment validation with Harness execution failure"""
        manager = DeploymentManager()
        manager.harness_client = mock_harness_client.return_value
        manager.deployment_timeout = 300
        
        # Mock time progression
        mock_time.side_effect = [0, 30]
        
        # Create mock deployment
        deployment = MagicMock()
        deployment.harness_execution_id = 'test-execution-123'
        
        # Mock Harness status check returning failure
        manager.harness_client.get_execution_status.return_value = {
            'success': True,
            'status': 'failed'
        }
        
        result = manager._wait_and_validate_deployment(deployment)
        
        assert result['success'] is False
        assert 'failed with status: failed' in result['error']
    
    @patch('time.time')
    @patch('time.sleep')
    def test_wait_and_validate_deployment_k8s_validation_failure(self, mock_sleep, mock_time, 
                                                               mock_harness_client, mock_k8s_client):
        """Test deployment validation with Kubernetes validation failure"""
        manager = DeploymentManager()
        manager.harness_client = mock_harness_client.return_value
        manager.k8s_client = mock_k8s_client.return_value
        manager.deployment_timeout = 300
        manager.validation_retry_count = 2
        manager.validation_retry_delay = 10
        
        # Mock time progression
        mock_time.side_effect = [0, 30]
        
        # Create mock deployment
        deployment = MagicMock()
        deployment.pillar = Pillar.CLEARING
        deployment.service_name = 'test-service'
        deployment.infrastructure_id = 'test-ns'
        deployment.harness_execution_id = 'test-execution-123'
        
        # Mock Harness status check
        manager.harness_client.get_execution_status.return_value = {
            'success': True,
            'status': 'success'
        }
        
        # Mock Kubernetes validation failure
        manager.k8s_client.validate_deployment.return_value = {
            'success': False,
            'error': 'Pod not ready'
        }
        
        result = manager._wait_and_validate_deployment(deployment)
        
        assert result['success'] is False
        assert 'Kubernetes validation failed after 2 attempts' in result['error']
    
    @patch('services.deployment_manager.db')
    def test_rollback_batch_success(self, mock_db, mock_harness_client):
        """Test successful batch rollback"""
        manager = DeploymentManager()
        manager.harness_client = mock_harness_client.return_value
        
        # Mock batch
        mock_batch = MagicMock()
        mock_batch.batch_id = 'test-batch-123'
        
        # Mock successful deployments
        mock_deployments = [
            MagicMock(id=1, harness_execution_id='exec-1', status=DeploymentStatus.SUCCESS),
            MagicMock(id=2, harness_execution_id='exec-2', status=DeploymentStatus.SUCCESS)
        ]
        
        # Mock queries
        mock_batch_query = MagicMock()
        mock_batch_query.filter_by.return_value.first.return_value = mock_batch
        
        mock_deployment_query = MagicMock()
        mock_deployment_query.filter_by.return_value.all.return_value = mock_deployments
        
        # Mock Harness client
        manager.harness_client.cancel_execution.return_value = {'success': True}
        
        with patch('services.deployment_manager.DeploymentBatch') as mock_batch_model:
            mock_batch_model.query = mock_batch_query
            
            with patch('services.deployment_manager.Deployment') as mock_deployment_model:
                mock_deployment_model.query = mock_deployment_query
                
                result = manager.rollback_batch('test-batch-123')
                
                assert result['success'] is True
                assert 'Rollback initiated for 2 deployments' in result['message']
                assert mock_batch.status == DeploymentStatus.ROLLBACK
                
                # Verify all deployments marked for rollback
                for deployment in mock_deployments:
                    assert deployment.status == DeploymentStatus.ROLLBACK
    
    @patch('services.deployment_manager.db')
    def test_rollback_batch_not_found(self, mock_db):
        """Test batch rollback when batch not found"""
        manager = DeploymentManager()
        
        # Mock query returning None
        mock_query = MagicMock()
        mock_query.filter_by.return_value.first.return_value = None
        
        with patch('services.deployment_manager.DeploymentBatch') as mock_batch_model:
            mock_batch_model.query = mock_query
            
            result = manager.rollback_batch('nonexistent-batch')
            
            assert result['success'] is False
            assert 'Batch not found' in result['error']
    
    @patch('services.deployment_manager.db')
    def test_rollback_batch_no_successful_deployments(self, mock_db):
        """Test batch rollback with no successful deployments"""
        manager = DeploymentManager()
        
        # Mock batch
        mock_batch = MagicMock()
        
        # Mock empty deployment list
        mock_batch_query = MagicMock()
        mock_batch_query.filter_by.return_value.first.return_value = mock_batch
        
        mock_deployment_query = MagicMock()
        mock_deployment_query.filter_by.return_value.all.return_value = []
        
        with patch('services.deployment_manager.DeploymentBatch') as mock_batch_model:
            mock_batch_model.query = mock_batch_query
            
            with patch('services.deployment_manager.Deployment') as mock_deployment_model:
                mock_deployment_model.query = mock_deployment_query
                
                result = manager.rollback_batch('test-batch-123')
                
                assert result['success'] is False
                assert 'No successful deployments to rollback' in result['error']
    
    @patch('services.deployment_manager.db')
    def test_rollback_batch_exception(self, mock_db):
        """Test batch rollback with exception"""
        manager = DeploymentManager()
        
        # Mock query that raises exception
        mock_query = MagicMock()
        mock_query.filter_by.side_effect = Exception("Database error")
        
        with patch('services.deployment_manager.DeploymentBatch') as mock_batch_model:
            mock_batch_model.query = mock_query
            
            result = manager.rollback_batch('test-batch-123')
            
            assert result['success'] is False
            assert 'Database error' in result['error']
    
    def test_get_deployment_status_success(self, sample_deployment_batch, sample_deployments):
        """Test successful deployment status retrieval"""
        manager = DeploymentManager()
        
        # Mock queries
        mock_batch_query = MagicMock()
        mock_batch_query.filter_by.return_value.first.return_value = sample_deployment_batch
        
        mock_deployment_query = MagicMock()
        mock_deployment_query.filter_by.return_value.all.return_value = sample_deployments
        
        with patch('services.deployment_manager.DeploymentBatch') as mock_batch_model:
            mock_batch_model.query = mock_batch_query
            
            with patch('services.deployment_manager.Deployment') as mock_deployment_model:
                mock_deployment_model.query = mock_deployment_query
                
                result = manager.get_deployment_status(sample_deployment_batch.batch_id)
                
                assert result['success'] is True
                assert result['batch_status'] == sample_deployment_batch.status.value
                assert result['total_deployments'] == sample_deployment_batch.total_deployments
                assert len(result['deployments']) == len(sample_deployments)
    
    def test_get_deployment_status_batch_not_found(self):
        """Test deployment status retrieval when batch not found"""
        manager = DeploymentManager()
        
        # Mock query returning None
        mock_query = MagicMock()
        mock_query.filter_by.return_value.first.return_value = None
        
        with patch('services.deployment_manager.DeploymentBatch') as mock_batch_model:
            mock_batch_model.query = mock_query
            
            result = manager.get_deployment_status('nonexistent-batch')
            
            assert result['success'] is False
            assert 'Batch not found' in result['error']
    
    def test_get_deployment_status_counts(self, sample_deployment_batch):
        """Test deployment status counts calculation"""
        manager = DeploymentManager()
        
        # Create deployments with different statuses
        deployments = [
            MagicMock(id=1, status=DeploymentStatus.SUCCESS),
            MagicMock(id=2, status=DeploymentStatus.FAILED),
            MagicMock(id=3, status=DeploymentStatus.PROCESSING),
            MagicMock(id=4, status=DeploymentStatus.PENDING)
        ]
        
        # Mock queries
        mock_batch_query = MagicMock()
        mock_batch_query.filter_by.return_value.first.return_value = sample_deployment_batch
        
        mock_deployment_query = MagicMock()
        mock_deployment_query.filter_by.return_value.all.return_value = deployments
        
        with patch('services.deployment_manager.DeploymentBatch') as mock_batch_model:
            mock_batch_model.query = mock_batch_query
            
            with patch('services.deployment_manager.Deployment') as mock_deployment_model:
                mock_deployment_model.query = mock_deployment_query
                
                result = manager.get_deployment_status(sample_deployment_batch.batch_id)
                
                assert result['success'] is True
                status_counts = result['status_counts']
                assert status_counts['success'] == 1
                assert status_counts['failed'] == 1
                assert status_counts['processing'] == 1
                assert status_counts['pending'] == 1
                assert status_counts['rollback'] == 0
    
    @patch('time.sleep')
    def test_wait_and_validate_deployment_kubernetes_retry(self, mock_sleep, mock_harness_client, mock_k8s_client):
        """Test deployment validation with Kubernetes retry logic"""
        manager = DeploymentManager()
        manager.harness_client = mock_harness_client.return_value
        manager.k8s_client = mock_k8s_client.return_value
        manager.deployment_timeout = 300
        manager.validation_retry_count = 3
        manager.validation_retry_delay = 5
        
        # Create mock deployment
        deployment = MagicMock()
        deployment.pillar = Pillar.CLEARING
        deployment.service_name = 'test-service'
        deployment.infrastructure_id = 'test-ns'
        deployment.harness_execution_id = 'test-execution-123'
        
        # Mock Harness status check
        manager.harness_client.get_execution_status.return_value = {
            'success': True,
            'status': 'success'
        }
        
        # Mock Kubernetes validation - first two fail, third succeeds
        manager.k8s_client.validate_deployment.side_effect = [
            {'success': True, 'ready': False},
            {'success': True, 'ready': False},
            {'success': True, 'ready': True}
        ]
        
        with patch('time.time', side_effect=[0, 30]):  # Don't timeout
            result = manager._wait_and_validate_deployment(deployment)
            
            assert result['success'] is True
            assert manager.k8s_client.validate_deployment.call_count == 3
            assert mock_sleep.call_count == 2  # Two retries
    
    def test_deployment_data_preparation(self):
        """Test deployment data preparation for Harness"""
        manager = DeploymentManager()
        
        # Create mock deployment
        deployment = MagicMock()
        deployment.service_name = 'test-service'
        deployment.docker_artifact_type = 'docker'
        deployment.docker_image_version = 'v2.1.0'
        deployment.environment_id = 'prod'
        deployment.infrastructure_id = 'k8s-cluster'
        
        # Mock Harness client
        mock_harness_client = MagicMock()
        mock_harness_client.trigger_deployment.return_value = {
            'success': True,
            'execution_id': 'test-123'
        }
        manager.harness_client = mock_harness_client
        
        with patch.object(manager, '_wait_and_validate_deployment') as mock_validate:
            mock_validate.return_value = {'success': True}
            
            with patch('services.deployment_manager.db'):
                result = manager._process_single_deployment(deployment)
                
                # Verify the deployment data passed to Harness
                call_args = mock_harness_client.trigger_deployment.call_args
                pillar = call_args[0][0]
                deployment_data = call_args[0][1]
                
                assert pillar == deployment.pillar.value
                assert deployment_data['service_name'] == 'test-service'
                assert deployment_data['docker_artifact_type'] == 'docker'
                assert deployment_data['docker_image_version'] == 'v2.1.0'
                assert deployment_data['environment_id'] == 'prod'
                assert deployment_data['infrastructure_id'] == 'k8s-cluster'
