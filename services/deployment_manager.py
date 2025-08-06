import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List
from app import db
from models import Deployment, DeploymentBatch, DeploymentStatus, Pillar
from services.harness_client import HarnessClient
from services.k8s_client import KubernetesClient
from services.yaml_processor import YAMLProcessor
from utils.exceptions import DeploymentError

logger = logging.getLogger(__name__)

class DeploymentManager:
    """Manages batch deployments and coordinates between Harness and Kubernetes"""
    
    def __init__(self):
        self.harness_client = HarnessClient()
        self.k8s_client = KubernetesClient()
        self.yaml_processor = YAMLProcessor()
        self.max_workers = int(os.getenv('MAX_DEPLOYMENT_WORKERS', '5'))
        self.deployment_timeout = int(os.getenv('DEPLOYMENT_TIMEOUT', '1800'))  # 30 minutes
        self.validation_retry_count = int(os.getenv('VALIDATION_RETRY_COUNT', '3'))
        self.validation_retry_delay = int(os.getenv('VALIDATION_RETRY_DELAY', '30'))
    
    def process_batch_deployment(self, batch_id: str, deployment_config: Dict[str, Any], processing_mode: str = 'parallel'):
        """Process a batch of deployments"""
        try:
            logger.info(f"Starting batch deployment {batch_id} in {processing_mode} mode")
            
            # Update batch status
            batch = DeploymentBatch.query.filter_by(batch_id=batch_id).first()
            if not batch:
                raise DeploymentError(f"Batch {batch_id} not found")
            
            batch.status = DeploymentStatus.PROCESSING
            db.session.commit()
            
            # Extract deployment information
            deployments_data = self.yaml_processor.extract_deployment_info(deployment_config)
            
            # Create deployment records
            deployment_records = []
            for deployment_data in deployments_data:
                deployment = Deployment(
                    batch_id=batch_id,
                    pillar=Pillar(deployment_data['pillar']),
                    service_name=deployment_data['service_name'],
                    docker_artifact_type=deployment_data['docker_artifact_type'],
                    docker_image_version=deployment_data['docker_image_version'],
                    environment_id=deployment_data['environment_id'],
                    infrastructure_id=deployment_data['infrastructure_id']
                )
                
                # Get K8s object info
                k8s_info = self.k8s_client.get_k8s_object_info(
                    deployment_data['pillar'], 
                    deployment_data['service_name']
                )
                deployment.k8s_object_type = k8s_info['type']
                deployment.k8s_object_name = k8s_info['name']
                
                db.session.add(deployment)
                deployment_records.append(deployment)
            
            db.session.commit()
            
            # Process deployments based on mode
            if processing_mode == 'parallel':
                results = self._process_parallel_deployments(deployment_records)
            else:
                results = self._process_sequential_deployments(deployment_records)
            
            # Update batch status based on results
            successful = sum(1 for result in results if result['success'])
            failed = len(results) - successful
            
            batch.successful_deployments = successful
            batch.failed_deployments = failed
            batch.status = DeploymentStatus.SUCCESS if failed == 0 else DeploymentStatus.FAILED
            db.session.commit()
            
            logger.info(f"Batch deployment {batch_id} completed: {successful} successful, {failed} failed")
            
        except Exception as e:
            logger.error(f"Error processing batch deployment {batch_id}: {str(e)}")
            batch = DeploymentBatch.query.filter_by(batch_id=batch_id).first()
            if batch:
                batch.status = DeploymentStatus.FAILED
                db.session.commit()
            raise
    
    def _process_parallel_deployments(self, deployments: List[Deployment]) -> List[Dict[str, Any]]:
        """Process deployments in parallel"""
        logger.info(f"Processing {len(deployments)} deployments in parallel")
        
        results = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all deployment tasks
            future_to_deployment = {
                executor.submit(self._process_single_deployment, deployment): deployment
                for deployment in deployments
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_deployment):
                deployment = future_to_deployment[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    logger.error(f"Error in parallel deployment {deployment.id}: {str(e)}")
                    deployment.status = DeploymentStatus.FAILED
                    deployment.error_message = str(e)
                    db.session.commit()
                    results.append({'success': False, 'error': str(e), 'deployment_id': deployment.id})
        
        return results
    
    def _process_sequential_deployments(self, deployments: List[Deployment]) -> List[Dict[str, Any]]:
        """Process deployments sequentially"""
        logger.info(f"Processing {len(deployments)} deployments sequentially")
        
        results = []
        for deployment in deployments:
            try:
                result = self._process_single_deployment(deployment)
                results.append(result)
                
                # If deployment failed and we're in sequential mode, decide whether to continue
                if not result['success']:
                    logger.warning(f"Sequential deployment {deployment.id} failed, continuing with next")
                    
            except Exception as e:
                logger.error(f"Error in sequential deployment {deployment.id}: {str(e)}")
                deployment.status = DeploymentStatus.FAILED
                deployment.error_message = str(e)
                db.session.commit()
                results.append({'success': False, 'error': str(e), 'deployment_id': deployment.id})
        
        return results
    
    def _process_single_deployment(self, deployment: Deployment) -> Dict[str, Any]:
        """Process a single deployment"""
        try:
            logger.info(f"Processing deployment {deployment.id}: {deployment.pillar.value}/{deployment.service_name}")
            
            # Update status to processing
            deployment.status = DeploymentStatus.PROCESSING
            db.session.commit()
            
            # Prepare deployment data
            deployment_data = {
                'service_name': deployment.service_name,
                'docker_artifact_type': deployment.docker_artifact_type,
                'docker_image_version': deployment.docker_image_version,
                'environment_id': deployment.environment_id,
                'infrastructure_id': deployment.infrastructure_id
            }
            
            # Trigger Harness deployment
            harness_result = self.harness_client.trigger_deployment(
                deployment.pillar.value,
                deployment_data
            )
            
            if not harness_result['success']:
                raise DeploymentError(f"Harness deployment failed: {harness_result.get('error', 'Unknown error')}")
            
            deployment.harness_execution_id = harness_result['execution_id']
            db.session.commit()
            
            # Wait for deployment to complete and validate
            validation_result = self._wait_and_validate_deployment(deployment)
            
            if validation_result['success']:
                deployment.status = DeploymentStatus.SUCCESS
                logger.info(f"Deployment {deployment.id} completed successfully")
            else:
                deployment.status = DeploymentStatus.FAILED
                deployment.error_message = validation_result.get('error', 'Validation failed')
                logger.error(f"Deployment {deployment.id} validation failed: {deployment.error_message}")
            
            db.session.commit()
            
            return {
                'success': validation_result['success'],
                'deployment_id': deployment.id,
                'execution_id': deployment.harness_execution_id,
                'error': validation_result.get('error')
            }
            
        except Exception as e:
            logger.error(f"Error processing deployment {deployment.id}: {str(e)}")
            deployment.status = DeploymentStatus.FAILED
            deployment.error_message = str(e)
            db.session.commit()
            
            return {
                'success': False,
                'deployment_id': deployment.id,
                'error': str(e)
            }
    
    def _wait_and_validate_deployment(self, deployment: Deployment) -> Dict[str, Any]:
        """Wait for deployment to complete and validate using Kubernetes API"""
        start_time = time.time()
        
        # Wait for deployment with timeout
        while time.time() - start_time < self.deployment_timeout:
            # Check Harness execution status
            if deployment.harness_execution_id:
                harness_status = self.harness_client.get_execution_status(deployment.harness_execution_id)
                
                if harness_status['success']:
                    status = harness_status.get('status', '').lower()
                    if status in ['success', 'succeeded']:
                        break
                    elif status in ['failed', 'aborted', 'expired']:
                        return {
                            'success': False,
                            'error': f'Harness execution failed with status: {status}'
                        }
            
            # Wait before next check
            time.sleep(30)
        else:
            return {
                'success': False,
                'error': 'Deployment timeout'
            }
        
        # Validate using Kubernetes API with retries
        for attempt in range(self.validation_retry_count):
            try:
                k8s_namespace = deployment.infrastructure_id  # Assuming infrastructure_id maps to namespace
                validation_result = self.k8s_client.validate_deployment(
                    deployment.pillar.value,
                    deployment.service_name,
                    k8s_namespace
                )
                
                if validation_result['success'] and validation_result.get('ready', False):
                    logger.info(f"Kubernetes validation successful for deployment {deployment.id}")
                    return {'success': True}
                elif validation_result['success']:
                    logger.info(f"Deployment {deployment.id} exists but not ready yet, retrying...")
                else:
                    logger.warning(f"Kubernetes validation failed for deployment {deployment.id}: {validation_result.get('error')}")
                
                if attempt < self.validation_retry_count - 1:
                    time.sleep(self.validation_retry_delay)
                    
            except Exception as e:
                logger.error(f"Error validating deployment {deployment.id} (attempt {attempt + 1}): {str(e)}")
                if attempt < self.validation_retry_count - 1:
                    time.sleep(self.validation_retry_delay)
        
        return {
            'success': False,
            'error': f'Kubernetes validation failed after {self.validation_retry_count} attempts'
        }
    
    def rollback_batch(self, batch_id: str) -> Dict[str, Any]:
        """Rollback a failed batch deployment"""
        try:
            logger.info(f"Starting rollback for batch {batch_id}")
            
            batch = DeploymentBatch.query.filter_by(batch_id=batch_id).first()
            if not batch:
                return {'success': False, 'error': 'Batch not found'}
            
            # Get successful deployments to rollback
            successful_deployments = Deployment.query.filter_by(
                batch_id=batch_id,
                status=DeploymentStatus.SUCCESS
            ).all()
            
            if not successful_deployments:
                return {'success': False, 'error': 'No successful deployments to rollback'}
            
            # Cancel any ongoing Harness executions
            for deployment in successful_deployments:
                if deployment.harness_execution_id:
                    cancel_result = self.harness_client.cancel_execution(deployment.harness_execution_id)
                    if cancel_result['success']:
                        logger.info(f"Cancelled execution {deployment.harness_execution_id}")
                
                deployment.status = DeploymentStatus.ROLLBACK
            
            batch.status = DeploymentStatus.ROLLBACK
            db.session.commit()
            
            logger.info(f"Rollback initiated for batch {batch_id}")
            return {'success': True, 'message': f'Rollback initiated for {len(successful_deployments)} deployments'}
            
        except Exception as e:
            logger.error(f"Error rolling back batch {batch_id}: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def get_deployment_status(self, batch_id: str) -> Dict[str, Any]:
        """Get comprehensive status for a deployment batch"""
        batch = DeploymentBatch.query.filter_by(batch_id=batch_id).first()
        if not batch:
            return {'success': False, 'error': 'Batch not found'}
        
        deployments = Deployment.query.filter_by(batch_id=batch_id).all()
        
        status_counts = {}
        for status in DeploymentStatus:
            status_counts[status.value] = sum(1 for d in deployments if d.status == status)
        
        return {
            'success': True,
            'batch_status': batch.status.value,
            'total_deployments': batch.total_deployments,
            'status_counts': status_counts,
            'deployments': [
                {
                    'id': d.id,
                    'pillar': d.pillar.value,
                    'service_name': d.service_name,
                    'status': d.status.value,
                    'error_message': d.error_message,
                    'harness_execution_id': d.harness_execution_id
                }
                for d in deployments
            ]
        }
