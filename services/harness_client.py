import os
import requests
import logging
import time
from typing import Dict, Any, Optional
from urllib.parse import urljoin
from utils.exceptions import DeploymentError

logger = logging.getLogger(__name__)

class HarnessClient:
    """Client for interacting with Harness webhooks and APIs"""
    
    def __init__(self):
        self.base_url = os.getenv('HARNESS_BASE_URL', 'https://app.harness.io')
        self.api_token = os.getenv('HARNESS_API_TOKEN', 'default-token')
        self.webhook_urls = {
            'clearing': os.getenv('HARNESS_CLEARING_WEBHOOK', 'https://webhook.site/clearing'),
            'risk': os.getenv('HARNESS_RISK_WEBHOOK', 'https://webhook.site/risk'),
            'data': os.getenv('HARNESS_DATA_WEBHOOK', 'https://webhook.site/data'),
            'shared': os.getenv('HARNESS_SHARED_WEBHOOK', 'https://webhook.site/shared')
        }
        self.timeout = 30
        self.max_retries = 3
    
    def trigger_deployment(self, pillar: str, deployment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Trigger deployment via Harness webhook"""
        if pillar not in self.webhook_urls:
            raise DeploymentError(f"Unknown pillar: {pillar}")
        
        webhook_url = self.webhook_urls[pillar]
        
        # Prepare payload for Harness
        payload = {
            'service_name': deployment_data['service_name'],
            'docker_artifact_type': deployment_data['docker_artifact_type'],
            'docker_image_version': deployment_data['docker_image_version'],
            'environment_id': deployment_data['environment_id'],
            'infrastructure_id': deployment_data['infrastructure_id'],
            'pillar': pillar,
            'metadata': deployment_data.get('metadata', {}),
            'timestamp': int(time.time())
        }
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_token}',
            'User-Agent': 'BatchDeploymentSystem/1.0'
        }
        
        # Retry mechanism
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Triggering deployment for {pillar}/{deployment_data['service_name']} (attempt {attempt + 1})")
                
                response = requests.post(
                    webhook_url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    result = response.json()
                    execution_id = result.get('executionId') or result.get('execution_id') or f"exec_{int(time.time())}"
                    
                    logger.info(f"Successfully triggered deployment: {execution_id}")
                    return {
                        'success': True,
                        'execution_id': execution_id,
                        'response': result
                    }
                elif response.status_code == 202:
                    # Accepted - deployment queued
                    result = response.json() if response.content else {}
                    execution_id = result.get('executionId') or result.get('execution_id') or f"exec_{int(time.time())}"
                    
                    logger.info(f"Deployment queued: {execution_id}")
                    return {
                        'success': True,
                        'execution_id': execution_id,
                        'response': result
                    }
                else:
                    error_msg = f"HTTP {response.status_code}: {response.text}"
                    logger.warning(f"Deployment trigger failed (attempt {attempt + 1}): {error_msg}")
                    
                    if attempt == self.max_retries - 1:
                        raise DeploymentError(f"Failed to trigger deployment after {self.max_retries} attempts: {error_msg}")
                    
                    time.sleep(2 ** attempt)  # Exponential backoff
                    
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout triggering deployment (attempt {attempt + 1})")
                if attempt == self.max_retries - 1:
                    raise DeploymentError(f"Deployment trigger timed out after {self.max_retries} attempts")
                time.sleep(2 ** attempt)
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request error triggering deployment (attempt {attempt + 1}): {str(e)}")
                if attempt == self.max_retries - 1:
                    raise DeploymentError(f"Request failed after {self.max_retries} attempts: {str(e)}")
                time.sleep(2 ** attempt)
        
        raise DeploymentError("Unexpected error in deployment trigger")
    
    def get_execution_status(self, execution_id: str) -> Dict[str, Any]:
        """Get deployment execution status from Harness"""
        try:
            url = f"{self.base_url}/gateway/pipeline/api/pipelines/execution/{execution_id}"
            headers = {
                'Authorization': f'Bearer {self.api_token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(url, headers=headers, timeout=self.timeout)
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'success': True,
                    'status': data.get('status', 'unknown'),
                    'data': data
                }
            else:
                logger.warning(f"Failed to get execution status: {response.status_code} - {response.text}")
                return {
                    'success': False,
                    'error': f"HTTP {response.status_code}: {response.text}"
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting execution status: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def cancel_execution(self, execution_id: str) -> Dict[str, Any]:
        """Cancel a running deployment execution"""
        try:
            url = f"{self.base_url}/gateway/pipeline/api/pipelines/execution/{execution_id}/interrupt"
            headers = {
                'Authorization': f'Bearer {self.api_token}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'interruptType': 'ABORT_ALL'
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
            
            if response.status_code in [200, 202]:
                return {
                    'success': True,
                    'message': 'Execution cancellation requested'
                }
            else:
                return {
                    'success': False,
                    'error': f"HTTP {response.status_code}: {response.text}"
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error cancelling execution: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def validate_webhook_connectivity(self) -> Dict[str, bool]:
        """Test connectivity to all webhook endpoints"""
        results = {}
        
        for pillar, webhook_url in self.webhook_urls.items():
            try:
                # Send a simple GET request to test connectivity
                response = requests.get(webhook_url, timeout=10)
                results[pillar] = response.status_code < 500
                logger.info(f"Webhook connectivity test for {pillar}: {'PASS' if results[pillar] else 'FAIL'}")
            except Exception as e:
                results[pillar] = False
                logger.warning(f"Webhook connectivity test for {pillar} failed: {str(e)}")
        
        return results
