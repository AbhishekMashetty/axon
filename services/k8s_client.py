import os
import logging
import json
from typing import Dict, Any, Optional, List
from kubernetes import client, config
from kubernetes.client import ApiException
from utils.exceptions import DeploymentError

logger = logging.getLogger(__name__)

class KubernetesClient:
    """Client for interacting with Kubernetes API for deployment validation"""
    
    def __init__(self):
        self._init_kubernetes_client()
        self.service_mappings = self._load_service_mappings()
    
    def _init_kubernetes_client(self):
        """Initialize Kubernetes client"""
        try:
            # Try to load in-cluster config first
            try:
                config.load_incluster_config()
                logger.info("Loaded in-cluster Kubernetes configuration")
            except config.ConfigException:
                # Fall back to kubeconfig
                kubeconfig_path = os.getenv('KUBECONFIG', '~/.kube/config')
                config.load_kube_config(config_file=kubeconfig_path)
                logger.info(f"Loaded Kubernetes configuration from {kubeconfig_path}")
            
            self.apps_v1 = client.AppsV1Api()
            self.core_v1 = client.CoreV1Api()
            self.batch_v1 = client.BatchV1Api()
            self.extensions_v1beta1 = client.ExtensionsV1beta1Api()
            
        except Exception as e:
            logger.error(f"Failed to initialize Kubernetes client: {str(e)}")
            # Create mock clients for development/testing
            self.apps_v1 = None
            self.core_v1 = None
            self.batch_v1 = None
            self.extensions_v1beta1 = None
    
    def _load_service_mappings(self) -> Dict[str, Any]:
        """Load service to K8s object mappings"""
        try:
            with open('config/service_mappings.json', 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning("Service mappings file not found")
            return {}
        except Exception as e:
            logger.error(f"Error loading service mappings: {str(e)}")
            return {}
    
    def get_k8s_object_info(self, pillar: str, service_name: str) -> Dict[str, str]:
        """Get Kubernetes object type and name for a service"""
        if not self.service_mappings:
            return {'type': 'deployment', 'name': service_name}  # Default assumption
        
        pillar_mappings = self.service_mappings.get(pillar, {})
        service_info = pillar_mappings.get(service_name, {})
        
        return {
            'type': service_info.get('k8s_object_type', 'deployment'),
            'name': service_info.get('k8s_object_name', service_name),
            'namespace': service_info.get('namespace', 'default')
        }
    
    def validate_deployment(self, pillar: str, service_name: str, namespace: str = 'default') -> Dict[str, Any]:
        """Validate deployment status in Kubernetes"""
        if not self.apps_v1:
            logger.warning("Kubernetes client not available, skipping validation")
            return {'success': False, 'error': 'Kubernetes client not available'}
        
        k8s_info = self.get_k8s_object_info(pillar, service_name)
        object_type = k8s_info['type']
        object_name = k8s_info['name']
        object_namespace = k8s_info.get('namespace', namespace)
        
        try:
            if object_type == 'deployment':
                return self._validate_deployment(object_name, object_namespace)
            elif object_type == 'statefulset':
                return self._validate_statefulset(object_name, object_namespace)
            elif object_type == 'daemonset':
                return self._validate_daemonset(object_name, object_namespace)
            elif object_type == 'job':
                return self._validate_job(object_name, object_namespace)
            elif object_type == 'cronjob':
                return self._validate_cronjob(object_name, object_namespace)
            elif object_type == 'pod':
                return self._validate_pod(object_name, object_namespace)
            else:
                return {
                    'success': False,
                    'error': f'Unsupported object type: {object_type}'
                }
                
        except ApiException as e:
            logger.error(f"Kubernetes API error validating {object_type}/{object_name}: {str(e)}")
            return {
                'success': False,
                'error': f'Kubernetes API error: {e.reason}',
                'status_code': e.status
            }
        except Exception as e:
            logger.error(f"Error validating {object_type}/{object_name}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _validate_deployment(self, name: str, namespace: str) -> Dict[str, Any]:
        """Validate Kubernetes Deployment"""
        deployment = self.apps_v1.read_namespaced_deployment(name=name, namespace=namespace)
        
        desired_replicas = deployment.spec.replicas or 1
        ready_replicas = deployment.status.ready_replicas or 0
        available_replicas = deployment.status.available_replicas or 0
        
        is_ready = ready_replicas == desired_replicas and available_replicas == desired_replicas
        
        return {
            'success': True,
            'ready': is_ready,
            'desired_replicas': desired_replicas,
            'ready_replicas': ready_replicas,
            'available_replicas': available_replicas,
            'conditions': [
                {
                    'type': condition.type,
                    'status': condition.status,
                    'reason': condition.reason,
                    'message': condition.message
                }
                for condition in (deployment.status.conditions or [])
            ]
        }
    
    def _validate_statefulset(self, name: str, namespace: str) -> Dict[str, Any]:
        """Validate Kubernetes StatefulSet"""
        statefulset = self.apps_v1.read_namespaced_stateful_set(name=name, namespace=namespace)
        
        desired_replicas = statefulset.spec.replicas or 1
        ready_replicas = statefulset.status.ready_replicas or 0
        
        is_ready = ready_replicas == desired_replicas
        
        return {
            'success': True,
            'ready': is_ready,
            'desired_replicas': desired_replicas,
            'ready_replicas': ready_replicas,
            'current_replicas': statefulset.status.current_replicas or 0
        }
    
    def _validate_daemonset(self, name: str, namespace: str) -> Dict[str, Any]:
        """Validate Kubernetes DaemonSet"""
        daemonset = self.apps_v1.read_namespaced_daemon_set(name=name, namespace=namespace)
        
        desired_nodes = daemonset.status.desired_number_scheduled or 0
        ready_nodes = daemonset.status.number_ready or 0
        
        is_ready = ready_nodes == desired_nodes
        
        return {
            'success': True,
            'ready': is_ready,
            'desired_nodes': desired_nodes,
            'ready_nodes': ready_nodes,
            'current_nodes': daemonset.status.current_number_scheduled or 0
        }
    
    def _validate_job(self, name: str, namespace: str) -> Dict[str, Any]:
        """Validate Kubernetes Job"""
        job = self.batch_v1.read_namespaced_job(name=name, namespace=namespace)
        
        succeeded = job.status.succeeded or 0
        failed = job.status.failed or 0
        active = job.status.active or 0
        
        is_complete = succeeded > 0
        is_failed = failed > 0
        
        return {
            'success': True,
            'ready': is_complete,
            'complete': is_complete,
            'failed': is_failed,
            'succeeded': succeeded,
            'failed_count': failed,
            'active': active
        }
    
    def _validate_cronjob(self, name: str, namespace: str) -> Dict[str, Any]:
        """Validate Kubernetes CronJob"""
        cronjob = self.batch_v1.read_namespaced_cron_job(name=name, namespace=namespace)
        
        last_schedule_time = cronjob.status.last_schedule_time
        active_jobs = len(cronjob.status.active or [])
        
        return {
            'success': True,
            'ready': True,  # CronJobs are considered ready if they exist
            'last_schedule_time': last_schedule_time.isoformat() if last_schedule_time else None,
            'active_jobs': active_jobs,
            'suspended': cronjob.spec.suspend or False
        }
    
    def _validate_pod(self, name: str, namespace: str) -> Dict[str, Any]:
        """Validate Kubernetes Pod"""
        pod = self.core_v1.read_namespaced_pod(name=name, namespace=namespace)
        
        phase = pod.status.phase
        is_ready = phase == 'Running'
        
        container_statuses = []
        if pod.status.container_statuses:
            for container in pod.status.container_statuses:
                container_statuses.append({
                    'name': container.name,
                    'ready': container.ready,
                    'restart_count': container.restart_count,
                    'state': str(container.state)
                })
        
        return {
            'success': True,
            'ready': is_ready,
            'phase': phase,
            'container_statuses': container_statuses,
            'conditions': [
                {
                    'type': condition.type,
                    'status': condition.status,
                    'reason': condition.reason,
                    'message': condition.message
                }
                for condition in (pod.status.conditions or [])
            ]
        }
    
    def get_deployment_logs(self, pillar: str, service_name: str, namespace: str = 'default', lines: int = 100) -> Dict[str, Any]:
        """Get logs for a deployment"""
        if not self.core_v1:
            return {'success': False, 'error': 'Kubernetes client not available'}
        
        k8s_info = self.get_k8s_object_info(pillar, service_name)
        object_name = k8s_info['name']
        object_namespace = k8s_info.get('namespace', namespace)
        
        try:
            # Get pods for the deployment
            if k8s_info['type'] == 'deployment':
                pods = self.core_v1.list_namespaced_pod(
                    namespace=object_namespace,
                    label_selector=f'app={object_name}'
                )
            else:
                # For other object types, try to find pods by name pattern
                pods = self.core_v1.list_namespaced_pod(
                    namespace=object_namespace,
                    field_selector=f'metadata.name={object_name}'
                )
            
            if not pods.items:
                return {'success': False, 'error': 'No pods found'}
            
            # Get logs from the first pod
            pod_name = pods.items[0].metadata.name
            logs = self.core_v1.read_namespaced_pod_log(
                name=pod_name,
                namespace=object_namespace,
                tail_lines=lines
            )
            
            return {
                'success': True,
                'logs': logs,
                'pod_name': pod_name
            }
            
        except ApiException as e:
            return {
                'success': False,
                'error': f'Kubernetes API error: {e.reason}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
