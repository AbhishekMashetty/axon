import pytest
from unittest.mock import patch, MagicMock
from kubernetes.client import ApiException
from services.k8s_client import KubernetesClient
from utils.exceptions import KubernetesError

class TestKubernetesClient:
    
    @patch('services.k8s_client.config.load_incluster_config')
    def test_init_incluster_config(self, mock_incluster):
        """Test initialization with in-cluster config"""
        mock_incluster.return_value = None
        
        with patch('services.k8s_client.client.AppsV1Api'), \
             patch('services.k8s_client.client.CoreV1Api'), \
             patch('services.k8s_client.client.BatchV1Api'):
            
            k8s_client = KubernetesClient()
            mock_incluster.assert_called_once()
            assert k8s_client.apps_v1 is not None
    
    @patch('services.k8s_client.config.load_incluster_config')
    @patch('services.k8s_client.config.load_kube_config')
    def test_init_kubeconfig_fallback(self, mock_kubeconfig, mock_incluster):
        """Test initialization with kubeconfig fallback"""
        mock_incluster.side_effect = Exception("Not in cluster")
        mock_kubeconfig.return_value = None
        
        with patch('services.k8s_client.client.AppsV1Api'), \
             patch('services.k8s_client.client.CoreV1Api'), \
             patch('services.k8s_client.client.BatchV1Api'):
            
            k8s_client = KubernetesClient()
            mock_incluster.assert_called_once()
            mock_kubeconfig.assert_called_once()
            assert k8s_client.apps_v1 is not None
    
    @patch('services.k8s_client.config.load_incluster_config')
    @patch('services.k8s_client.config.load_kube_config')
    def test_init_config_failure(self, mock_kubeconfig, mock_incluster):
        """Test initialization with config failure"""
        mock_incluster.side_effect = Exception("Not in cluster")
        mock_kubeconfig.side_effect = Exception("No kubeconfig")
        
        k8s_client = KubernetesClient()
        
        # Should create mock clients
        assert k8s_client.apps_v1 is None
        assert k8s_client.core_v1 is None
    
    def test_get_k8s_object_info_with_mappings(self, mock_service_mappings):
        """Test getting K8s object info with service mappings"""
        k8s_client = KubernetesClient()
        k8s_client.service_mappings = mock_service_mappings
        
        info = k8s_client.get_k8s_object_info('clearing', 'trade-processor')
        
        assert info['type'] == 'deployment'
        assert info['name'] == 'trade-processor'
        assert info['namespace'] == 'clearing'
    
    def test_get_k8s_object_info_without_mappings(self):
        """Test getting K8s object info without service mappings"""
        k8s_client = KubernetesClient()
        k8s_client.service_mappings = {}
        
        info = k8s_client.get_k8s_object_info('risk', 'unknown-service')
        
        assert info['type'] == 'deployment'  # Default
        assert info['name'] == 'unknown-service'  # Service name as default
    
    def test_validate_deployment_no_client(self):
        """Test deployment validation without K8s client"""
        k8s_client = KubernetesClient()
        k8s_client.apps_v1 = None
        
        result = k8s_client.validate_deployment('clearing', 'test-service')
        
        assert result['success'] is False
        assert 'not available' in result['error']
    
    def test_validate_deployment_success(self):
        """Test successful deployment validation"""
        k8s_client = KubernetesClient()
        
        # Mock deployment object
        mock_deployment = MagicMock()
        mock_deployment.spec.replicas = 3
        mock_deployment.status.ready_replicas = 3
        mock_deployment.status.available_replicas = 3
        mock_deployment.status.conditions = []
        
        # Mock apps_v1 API
        mock_apps_v1 = MagicMock()
        mock_apps_v1.read_namespaced_deployment.return_value = mock_deployment
        k8s_client.apps_v1 = mock_apps_v1
        
        result = k8s_client.validate_deployment('clearing', 'test-service')
        
        assert result['success'] is True
        assert result['ready'] is True
        assert result['desired_replicas'] == 3
        assert result['ready_replicas'] == 3
    
    def test_validate_deployment_not_ready(self):
        """Test deployment validation when not ready"""
        k8s_client = KubernetesClient()
        
        # Mock deployment object
        mock_deployment = MagicMock()
        mock_deployment.spec.replicas = 3
        mock_deployment.status.ready_replicas = 1
        mock_deployment.status.available_replicas = 1
        mock_deployment.status.conditions = []
        
        # Mock apps_v1 API
        mock_apps_v1 = MagicMock()
        mock_apps_v1.read_namespaced_deployment.return_value = mock_deployment
        k8s_client.apps_v1 = mock_apps_v1
        
        result = k8s_client.validate_deployment('clearing', 'test-service')
        
        assert result['success'] is True
        assert result['ready'] is False
        assert result['desired_replicas'] == 3
        assert result['ready_replicas'] == 1
    
    def test_validate_deployment_api_exception(self):
        """Test deployment validation with API exception"""
        k8s_client = KubernetesClient()
        
        # Mock apps_v1 API with exception
        mock_apps_v1 = MagicMock()
        mock_apps_v1.read_namespaced_deployment.side_effect = ApiException(
            status=404, reason="Not Found"
        )
        k8s_client.apps_v1 = mock_apps_v1
        
        result = k8s_client.validate_deployment('clearing', 'nonexistent-service')
        
        assert result['success'] is False
        assert 'Kubernetes API error' in result['error']
        assert result['status_code'] == 404
    
    def test_validate_statefulset_success(self):
        """Test successful StatefulSet validation"""
        k8s_client = KubernetesClient()
        k8s_client.service_mappings = {
            'data': {
                'database': {
                    'k8s_object_type': 'statefulset',
                    'k8s_object_name': 'database',
                    'namespace': 'data'
                }
            }
        }
        
        # Mock StatefulSet object
        mock_statefulset = MagicMock()
        mock_statefulset.spec.replicas = 2
        mock_statefulset.status.ready_replicas = 2
        mock_statefulset.status.current_replicas = 2
        
        # Mock apps_v1 API
        mock_apps_v1 = MagicMock()
        mock_apps_v1.read_namespaced_stateful_set.return_value = mock_statefulset
        k8s_client.apps_v1 = mock_apps_v1
        
        result = k8s_client.validate_deployment('data', 'database')
        
        assert result['success'] is True
        assert result['ready'] is True
        assert result['desired_replicas'] == 2
    
    def test_validate_daemonset_success(self):
        """Test successful DaemonSet validation"""
        k8s_client = KubernetesClient()
        k8s_client.service_mappings = {
            'shared': {
                'monitor': {
                    'k8s_object_type': 'daemonset',
                    'k8s_object_name': 'monitor',
                    'namespace': 'shared'
                }
            }
        }
        
        # Mock DaemonSet object
        mock_daemonset = MagicMock()
        mock_daemonset.status.desired_number_scheduled = 3
        mock_daemonset.status.number_ready = 3
        mock_daemonset.status.current_number_scheduled = 3
        
        # Mock apps_v1 API
        mock_apps_v1 = MagicMock()
        mock_apps_v1.read_namespaced_daemon_set.return_value = mock_daemonset
        k8s_client.apps_v1 = mock_apps_v1
        
        result = k8s_client.validate_deployment('shared', 'monitor')
        
        assert result['success'] is True
        assert result['ready'] is True
        assert result['desired_nodes'] == 3
        assert result['ready_nodes'] == 3
    
    def test_validate_job_success(self):
        """Test successful Job validation"""
        k8s_client = KubernetesClient()
        k8s_client.service_mappings = {
            'data': {
                'etl': {
                    'k8s_object_type': 'job',
                    'k8s_object_name': 'etl-job',
                    'namespace': 'data'
                }
            }
        }
        
        # Mock Job object
        mock_job = MagicMock()
        mock_job.status.succeeded = 1
        mock_job.status.failed = 0
        mock_job.status.active = 0
        
        # Mock batch_v1 API
        mock_batch_v1 = MagicMock()
        mock_batch_v1.read_namespaced_job.return_value = mock_job
        k8s_client.batch_v1 = mock_batch_v1
        
        result = k8s_client.validate_deployment('data', 'etl')
        
        assert result['success'] is True
        assert result['ready'] is True
        assert result['complete'] is True
        assert result['succeeded'] == 1
    
    def test_validate_job_failed(self):
        """Test Job validation when job failed"""
        k8s_client = KubernetesClient()
        k8s_client.service_mappings = {
            'data': {
                'etl': {
                    'k8s_object_type': 'job',
                    'k8s_object_name': 'etl-job',
                    'namespace': 'data'
                }
            }
        }
        
        # Mock failed Job object
        mock_job = MagicMock()
        mock_job.status.succeeded = 0
        mock_job.status.failed = 1
        mock_job.status.active = 0
        
        # Mock batch_v1 API
        mock_batch_v1 = MagicMock()
        mock_batch_v1.read_namespaced_job.return_value = mock_job
        k8s_client.batch_v1 = mock_batch_v1
        
        result = k8s_client.validate_deployment('data', 'etl')
        
        assert result['success'] is True
        assert result['ready'] is False
        assert result['failed'] is True
        assert result['failed_count'] == 1
    
    def test_validate_cronjob_success(self):
        """Test successful CronJob validation"""
        k8s_client = KubernetesClient()
        k8s_client.service_mappings = {
            'shared': {
                'backup': {
                    'k8s_object_type': 'cronjob',
                    'k8s_object_name': 'backup-job',
                    'namespace': 'shared'
                }
            }
        }
        
        # Mock CronJob object
        mock_cronjob = MagicMock()
        mock_cronjob.status.last_schedule_time = MagicMock()
        mock_cronjob.status.last_schedule_time.isoformat.return_value = '2024-01-01T12:00:00Z'
        mock_cronjob.status.active = []
        mock_cronjob.spec.suspend = False
        
        # Mock batch_v1 API
        mock_batch_v1 = MagicMock()
        mock_batch_v1.read_namespaced_cron_job.return_value = mock_cronjob
        k8s_client.batch_v1 = mock_batch_v1
        
        result = k8s_client.validate_deployment('shared', 'backup')
        
        assert result['success'] is True
        assert result['ready'] is True
        assert result['suspended'] is False
        assert result['active_jobs'] == 0
    
    def test_validate_pod_success(self):
        """Test successful Pod validation"""
        k8s_client = KubernetesClient()
        k8s_client.service_mappings = {
            'risk': {
                'calculator': {
                    'k8s_object_type': 'pod',
                    'k8s_object_name': 'calculator-pod',
                    'namespace': 'risk'
                }
            }
        }
        
        # Mock Pod object
        mock_pod = MagicMock()
        mock_pod.status.phase = 'Running'
        mock_pod.status.container_statuses = [
            MagicMock(
                name='calculator',
                ready=True,
                restart_count=0,
                state='Running'
            )
        ]
        mock_pod.status.conditions = []
        
        # Mock core_v1 API
        mock_core_v1 = MagicMock()
        mock_core_v1.read_namespaced_pod.return_value = mock_pod
        k8s_client.core_v1 = mock_core_v1
        
        result = k8s_client.validate_deployment('risk', 'calculator')
        
        assert result['success'] is True
        assert result['ready'] is True
        assert result['phase'] == 'Running'
        assert len(result['container_statuses']) == 1
    
    def test_validate_unsupported_object_type(self):
        """Test validation with unsupported object type"""
        k8s_client = KubernetesClient()
        k8s_client.service_mappings = {
            'test': {
                'service': {
                    'k8s_object_type': 'unsupported',
                    'k8s_object_name': 'test-service',
                    'namespace': 'test'
                }
            }
        }
        k8s_client.apps_v1 = MagicMock()  # Ensure client is available
        
        result = k8s_client.validate_deployment('test', 'service')
        
        assert result['success'] is False
        assert 'Unsupported object type' in result['error']
    
    def test_get_deployment_logs_success(self):
        """Test successful log retrieval"""
        k8s_client = KubernetesClient()
        
        # Mock pod list
        mock_pod = MagicMock()
        mock_pod.metadata.name = 'test-pod-123'
        mock_pods = MagicMock()
        mock_pods.items = [mock_pod]
        
        # Mock core_v1 API
        mock_core_v1 = MagicMock()
        mock_core_v1.list_namespaced_pod.return_value = mock_pods
        mock_core_v1.read_namespaced_pod_log.return_value = "Sample log content"
        k8s_client.core_v1 = mock_core_v1
        
        result = k8s_client.get_deployment_logs('clearing', 'test-service')
        
        assert result['success'] is True
        assert result['logs'] == "Sample log content"
        assert result['pod_name'] == 'test-pod-123'
    
    def test_get_deployment_logs_no_pods(self):
        """Test log retrieval when no pods found"""
        k8s_client = KubernetesClient()
        
        # Mock empty pod list
        mock_pods = MagicMock()
        mock_pods.items = []
        
        # Mock core_v1 API
        mock_core_v1 = MagicMock()
        mock_core_v1.list_namespaced_pod.return_value = mock_pods
        k8s_client.core_v1 = mock_core_v1
        
        result = k8s_client.get_deployment_logs('clearing', 'test-service')
        
        assert result['success'] is False
        assert 'No pods found' in result['error']
    
    def test_get_deployment_logs_no_client(self):
        """Test log retrieval without K8s client"""
        k8s_client = KubernetesClient()
        k8s_client.core_v1 = None
        
        result = k8s_client.get_deployment_logs('clearing', 'test-service')
        
        assert result['success'] is False
        assert 'not available' in result['error']
    
    def test_get_deployment_logs_api_exception(self):
        """Test log retrieval with API exception"""
        k8s_client = KubernetesClient()
        
        # Mock core_v1 API with exception
        mock_core_v1 = MagicMock()
        mock_core_v1.list_namespaced_pod.side_effect = ApiException(
            status=403, reason="Forbidden"
        )
        k8s_client.core_v1 = mock_core_v1
        
        result = k8s_client.get_deployment_logs('clearing', 'test-service')
        
        assert result['success'] is False
        assert 'Kubernetes API error' in result['error']
    
    @patch('builtins.open')
    def test_load_service_mappings_success(self, mock_open):
        """Test successful service mappings loading"""
        mock_mappings = {
            'clearing': {
                'trade-processor': {
                    'k8s_object_type': 'deployment',
                    'k8s_object_name': 'trade-processor'
                }
            }
        }
        
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(mock_mappings)
        
        with patch('services.k8s_client.json.load', return_value=mock_mappings):
            k8s_client = KubernetesClient()
            assert k8s_client.service_mappings == mock_mappings
    
    @patch('builtins.open', side_effect=FileNotFoundError)
    def test_load_service_mappings_not_found(self, mock_open):
        """Test service mappings loading when file not found"""
        k8s_client = KubernetesClient()
        assert k8s_client.service_mappings == {}
    
    @patch('builtins.open')
    def test_load_service_mappings_exception(self, mock_open):
        """Test service mappings loading with exception"""
        mock_open.side_effect = Exception("Read error")
        
        k8s_client = KubernetesClient()
        assert k8s_client.service_mappings == {}
