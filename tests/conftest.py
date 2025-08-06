import pytest
import tempfile
import os
import json
from unittest.mock import MagicMock, patch
from app import app, db
from models import Deployment, DeploymentBatch, DeploymentStatus, Pillar

@pytest.fixture
def client():
    """Create a test client for the Flask application"""
    # Create a temporary database file
    db_fd, app.config['DATABASE'] = tempfile.mkstemp()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
    
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.drop_all()
    
    os.close(db_fd)
    os.unlink(app.config['DATABASE'])

@pytest.fixture
def app_context():
    """Create an application context for testing"""
    with app.app_context():
        yield app

@pytest.fixture
def db_session():
    """Create a database session for testing"""
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['TESTING'] = True
    
    with app.app_context():
        db.create_all()
        yield db.session
        db.session.remove()
        db.drop_all()

@pytest.fixture
def sample_deployment_batch(db_session):
    """Create a sample deployment batch for testing"""
    batch = DeploymentBatch(
        batch_id='test-batch-123',
        yaml_filename='test-deployment.yaml',
        total_deployments=2,
        successful_deployments=0,
        failed_deployments=0,
        status=DeploymentStatus.PENDING,
        processing_mode='parallel'
    )
    db_session.add(batch)
    db_session.commit()
    return batch

@pytest.fixture
def sample_deployments(db_session, sample_deployment_batch):
    """Create sample deployments for testing"""
    deployments = [
        Deployment(
            batch_id=sample_deployment_batch.batch_id,
            pillar=Pillar.CLEARING,
            service_name='trade-processor',
            docker_artifact_type='docker',
            docker_image_version='v1.2.3',
            environment_id='test',
            infrastructure_id='test-cluster',
            k8s_object_type='deployment',
            k8s_object_name='trade-processor',
            status=DeploymentStatus.PENDING
        ),
        Deployment(
            batch_id=sample_deployment_batch.batch_id,
            pillar=Pillar.RISK,
            service_name='risk-engine',
            docker_artifact_type='helm',
            docker_image_version='v2.1.0',
            environment_id='test',
            infrastructure_id='test-cluster',
            k8s_object_type='deployment',
            k8s_object_name='risk-engine',
            status=DeploymentStatus.PENDING
        )
    ]
    
    for deployment in deployments:
        db_session.add(deployment)
    
    db_session.commit()
    return deployments

@pytest.fixture
def valid_yaml_content():
    """Sample valid YAML content for testing"""
    return """
version: v1.0
metadata:
  name: "Test Deployment"
  description: "Test deployment configuration"

deployments:
  - pillar: clearing
    service_name: trade-processor
    docker_artifact_type: docker
    docker_image_version: v1.2.3
    environment_id: test
    infrastructure_id: test-cluster
    
  - pillar: risk
    service_name: risk-engine
    docker_artifact_type: helm
    docker_image_version: v2.1.0
    environment_id: test
    infrastructure_id: test-cluster
"""

@pytest.fixture
def invalid_yaml_content():
    """Sample invalid YAML content for testing"""
    return """
version: v1.0
deployments:
  - pillar: invalid_pillar
    service_name: test-service
    # Missing required fields
"""

@pytest.fixture
def sample_yaml_file(tmp_path, valid_yaml_content):
    """Create a temporary YAML file for testing"""
    yaml_file = tmp_path / "test-deployment.yaml"
    yaml_file.write_text(valid_yaml_content)
    return str(yaml_file)

@pytest.fixture
def mock_harness_client():
    """Mock Harness client for testing"""
    with patch('services.harness_client.HarnessClient') as mock:
        client_instance = MagicMock()
        client_instance.trigger_deployment.return_value = {
            'success': True,
            'execution_id': 'test-execution-123',
            'response': {'status': 'queued'}
        }
        client_instance.get_execution_status.return_value = {
            'success': True,
            'status': 'success',
            'data': {'status': 'success'}
        }
        client_instance.cancel_execution.return_value = {
            'success': True,
            'message': 'Execution cancelled'
        }
        client_instance.validate_webhook_connectivity.return_value = {
            'clearing': True,
            'risk': True,
            'data': True,
            'shared': True
        }
        mock.return_value = client_instance
        yield mock

@pytest.fixture
def mock_k8s_client():
    """Mock Kubernetes client for testing"""
    with patch('services.k8s_client.KubernetesClient') as mock:
        client_instance = MagicMock()
        client_instance.validate_deployment.return_value = {
            'success': True,
            'ready': True,
            'desired_replicas': 1,
            'ready_replicas': 1,
            'available_replicas': 1
        }
        client_instance.get_k8s_object_info.return_value = {
            'type': 'deployment',
            'name': 'test-service',
            'namespace': 'default'
        }
        client_instance.get_deployment_logs.return_value = {
            'success': True,
            'logs': 'Sample log content',
            'pod_name': 'test-pod-123'
        }
        mock.return_value = client_instance
        yield mock

@pytest.fixture
def mock_service_mappings():
    """Mock service mappings for testing"""
    mappings = {
        "clearing": {
            "trade-processor": {
                "k8s_object_type": "deployment",
                "k8s_object_name": "trade-processor",
                "namespace": "clearing"
            }
        },
        "risk": {
            "risk-engine": {
                "k8s_object_type": "deployment",
                "k8s_object_name": "risk-engine",
                "namespace": "risk"
            }
        },
        "data": {
            "analytics-engine": {
                "k8s_object_type": "deployment",
                "k8s_object_name": "analytics-engine",
                "namespace": "data"
            }
        },
        "shared": {
            "auth-service": {
                "k8s_object_type": "deployment",
                "k8s_object_name": "auth-service",
                "namespace": "shared"
            }
        }
    }
    
    with patch('builtins.open', create=True) as mock_open:
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(mappings)
        yield mappings

@pytest.fixture
def deployment_config():
    """Sample deployment configuration for testing"""
    return {
        'version': 'v1.0',
        'metadata': {
            'name': 'Test Deployment',
            'description': 'Test deployment configuration'
        },
        'deployments': [
            {
                'pillar': 'clearing',
                'service_name': 'trade-processor',
                'docker_artifact_type': 'docker',
                'docker_image_version': 'v1.2.3',
                'environment_id': 'test',
                'infrastructure_id': 'test-cluster'
            },
            {
                'pillar': 'risk',
                'service_name': 'risk-engine',
                'docker_artifact_type': 'helm',
                'docker_image_version': 'v2.1.0',
                'environment_id': 'test',
                'infrastructure_id': 'test-cluster'
            }
        ]
    }

@pytest.fixture
def mock_yaml_processor():
    """Mock YAML processor for testing"""
    with patch('services.yaml_processor.YAMLProcessor') as mock:
        processor_instance = MagicMock()
        processor_instance.parse_and_validate.return_value = {
            'version': 'v1.0',
            'deployments': [
                {
                    'pillar': 'clearing',
                    'service_name': 'trade-processor',
                    'docker_artifact_type': 'docker',
                    'docker_image_version': 'v1.2.3',
                    'environment_id': 'test',
                    'infrastructure_id': 'test-cluster'
                }
            ]
        }
        processor_instance.extract_deployment_info.return_value = [
            {
                'pillar': 'clearing',
                'service_name': 'trade-processor',
                'docker_artifact_type': 'docker',
                'docker_image_version': 'v1.2.3',
                'environment_id': 'test',
                'infrastructure_id': 'test-cluster',
                'metadata': {}
            }
        ]
        mock.return_value = processor_instance
        yield mock

@pytest.fixture
def mock_deployment_manager():
    """Mock deployment manager for testing"""
    with patch('services.deployment_manager.DeploymentManager') as mock:
        manager_instance = MagicMock()
        manager_instance.process_batch_deployment.return_value = None
        manager_instance.rollback_batch.return_value = {
            'success': True,
            'message': 'Rollback initiated'
        }
        manager_instance.get_deployment_status.return_value = {
            'success': True,
            'batch_status': 'success',
            'total_deployments': 2,
            'status_counts': {
                'success': 2,
                'failed': 0,
                'processing': 0,
                'pending': 0,
                'rollback': 0
            },
            'deployments': []
        }
        mock.return_value = manager_instance
        yield mock

@pytest.fixture(autouse=True)
def setup_test_environment():
    """Setup test environment variables"""
    test_env_vars = {
        'HARNESS_BASE_URL': 'https://test.harness.io',
        'HARNESS_API_TOKEN': 'test-token',
        'HARNESS_CLEARING_WEBHOOK': 'https://test.webhook.site/clearing',
        'HARNESS_RISK_WEBHOOK': 'https://test.webhook.site/risk',
        'HARNESS_DATA_WEBHOOK': 'https://test.webhook.site/data',
        'HARNESS_SHARED_WEBHOOK': 'https://test.webhook.site/shared',
        'SESSION_SECRET': 'test-secret-key',
        'MAX_DEPLOYMENT_WORKERS': '3',
        'DEPLOYMENT_TIMEOUT': '300',
        'VALIDATION_RETRY_COUNT': '2',
        'VALIDATION_RETRY_DELAY': '5'
    }
    
    with patch.dict(os.environ, test_env_vars):
        yield

@pytest.fixture
def mock_requests():
    """Mock requests for HTTP calls"""
    with patch('requests.post') as mock_post, \
         patch('requests.get') as mock_get:
        
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'executionId': 'test-execution-123',
            'status': 'success'
        }
        mock_response.text = 'Success'
        
        mock_post.return_value = mock_response
        mock_get.return_value = mock_response
        
        yield {'post': mock_post, 'get': mock_get}
