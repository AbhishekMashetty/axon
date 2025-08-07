#!/usr/bin/env python3
"""
DevOps Deployment Automation Flask Application

This application handles:
1. YAML deployment configuration parsing
2. Harness webhook triggering
3. Kubernetes deployment validation
4. Multi-pillar service management

Author: DevOps Automation Team
"""

import os
import time
import logging
import asyncio
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import yaml
import requests
from flask import Flask, request, jsonify, Response
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
import threading
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# Configuration and Constants
# =============================================================================

class ResourceType(Enum):
    """Kubernetes resource types"""
    DEPLOYMENT = "Deployment"
    JOB = "Job"
    POD = "Pod"
    CRD = "CustomResource"
    SERVICE = "Service"
    INGRESS = "Ingress"

# Service to Kubernetes resource mapping
SERVICE_RESOURCE_MAPPING = {
    # Clearing pillar - uses CRDs
    "service A": [ResourceType.CRD, ResourceType.POD, ResourceType.SERVICE, ResourceType.INGRESS],
    "service B": [ResourceType.CRD, ResourceType.POD, ResourceType.SERVICE],
    
    # Risk pillar - mainly deployments
    "RISK A": [ResourceType.DEPLOYMENT],
    "risk-calculator": [ResourceType.DEPLOYMENT],
    "risk-monitor": [ResourceType.JOB],
    
    # Data pillar - mixed resources
    "data-platform": [ResourceType.DEPLOYMENT, ResourceType.SERVICE],
    "data-ingester": [ResourceType.JOB],
    "data-processor": [ResourceType.POD],
    
    # Shared pillar - common services
    "auth-service": [ResourceType.DEPLOYMENT, ResourceType.SERVICE],
    "logging-service": [ResourceType.DEPLOYMENT],
}

# Configuration constants
DEPLOYMENT_TIMEOUT = 600  # 10 minutes
VALIDATION_RETRY_COUNT = 10
VALIDATION_RETRY_DELAY = 30  # seconds
FIXED_ENVIRONMENT_ID = "prod-env-001"
FIXED_INFRASTRUCTURE_ID = "k8s-cluster-001"

# =============================================================================
# Data Models
# =============================================================================

@dataclass
class ServiceConfig:
    """Represents a single service configuration"""
    service_name: str
    docker_artifact_type: str
    docker_artifact_version: str
    pipeline_webhook: Optional[str] = None

@dataclass
class PillarConfig:
    """Represents a pillar configuration with services"""
    name: str
    pipeline_webhook: Optional[str]
    services: List[ServiceConfig]

@dataclass
class DeploymentResult:
    """Represents the result of a deployment operation"""
    service_name: str
    success: bool
    webhook_response: Optional[Dict] = None
    validation_results: Optional[Dict] = None
    error_message: Optional[str] = None
    deployment_time: Optional[datetime] = None

# =============================================================================
# YAML Parser
# =============================================================================

class YamlParser:
    """Handles parsing and normalization of YAML deployment configurations"""
    
    @staticmethod
    def parse_yaml_content(yaml_content: str) -> List[PillarConfig]:
        """
        Parse YAML content and return normalized pillar configurations
        
        Args:
            yaml_content: Raw YAML string
            
        Returns:
            List of PillarConfig objects
            
        Raises:
            ValueError: If YAML is invalid or malformed
        """
        try:
            data = yaml.safe_load(yaml_content)
            pillars = []
            
            for pillar_name, pillar_data in data.items():
                if not isinstance(pillar_data, dict):
                    continue
                    
                # Extract webhook URL (can be at root or per service)
                pillar_webhook = pillar_data.get('pipeline_webhook')
                services_data = pillar_data.get('services', [])
                
                services = []
                for service_data in services_data:
                    # Service-level webhook takes precedence
                    service_webhook = service_data.get('pipeline_url') or pillar_webhook
                    
                    service = ServiceConfig(
                        service_name=service_data['service_name'],
                        docker_artifact_type=service_data['docker_artifact_type'],
                        docker_artifact_version=str(service_data['docker_artifact_version']),
                        pipeline_webhook=service_webhook
                    )
                    services.append(service)
                
                pillar = PillarConfig(
                    name=pillar_name,
                    pipeline_webhook=pillar_webhook,
                    services=services
                )
                pillars.append(pillar)
            
            return pillars
            
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML format: {str(e)}")
        except KeyError as e:
            raise ValueError(f"Missing required field: {str(e)}")

# =============================================================================
# Harness Webhook Manager
# =============================================================================

class HarnessWebhookManager:
    """Manages interactions with Harness webhooks"""
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()
    
    def construct_payload(self, service: ServiceConfig) -> Dict[str, Any]:
        """
        Construct JSON payload for Harness webhook
        
        Args:
            service: ServiceConfig object
            
        Returns:
            Dictionary containing the webhook payload
        """
        return {
            "service_name": service.service_name,
            "docker_artifact_type": service.docker_artifact_type,
            "docker_artifact_version": service.docker_artifact_version,
            "environment_id": FIXED_ENVIRONMENT_ID,
            "infrastructure_id": FIXED_INFRASTRUCTURE_ID,
            "triggered_at": datetime.utcnow().isoformat(),
            "triggered_by": "deployment-automation"
        }
    
    def trigger_deployment(self, service: ServiceConfig) -> Tuple[bool, Dict]:
        """
        Trigger deployment via Harness webhook
        
        Args:
            service: ServiceConfig object
            
        Returns:
            Tuple of (success_bool, response_dict)
        """
        if not service.pipeline_webhook:
            return False, {"error": "No webhook URL provided"}
        
        payload = self.construct_payload(service)
        
        try:
            logger.info(f"Triggering deployment for {service.service_name}")
            response = self.session.post(
                service.pipeline_webhook,
                json=payload,
                timeout=self.timeout,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "deployment-automation/1.0"
                }
            )
            
            response.raise_for_status()
            
            return True, {
                "status_code": response.status_code,
                "response": response.json() if response.text else {},
                "execution_id": response.json().get("executionId") if response.text else None
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Webhook trigger failed for {service.service_name}: {str(e)}")
            return False, {"error": str(e)}

# =============================================================================
# Kubernetes Validator
# =============================================================================

class KubernetesValidator:
    """Handles Kubernetes API interactions and deployment validation"""
    
    def __init__(self):
        self._initialize_k8s_client()
    
    def _initialize_k8s_client(self):
        """Initialize Kubernetes client"""
        try:
            # Try in-cluster config first
            config.load_incluster_config()
            logger.info("Using in-cluster Kubernetes configuration")
        except config.ConfigException:
            try:
                # Fall back to local kubeconfig
                config.load_kube_config()
                logger.info("Using local kubeconfig")
            except config.ConfigException:
                logger.error("Could not load Kubernetes configuration")
                raise
        
        self.v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        self.batch_v1 = client.BatchV1Api()
        self.extensions_v1beta1 = client.ExtensionsV1beta1Api()
    
    def _get_service_namespace(self, service_name: str, pillar: str) -> str:
        """
        Determine namespace for a service based on naming conventions
        
        Args:
            service_name: Name of the service
            pillar: Pillar name (clearing, risk, shared, data)
            
        Returns:
            Kubernetes namespace name
        """
        # Common namespace mapping logic
        namespace_mapping = {
            "clearing": "clearing-ns",
            "risk": "risk-ns", 
            "shared": "shared-services",
            "data": "data-platform"
        }
        
        return namespace_mapping.get(pillar.lower(), f"{pillar.lower()}-ns")
    
    def _validate_deployment(self, service_name: str, namespace: str) -> bool:
        """Validate Kubernetes Deployment resource"""
        try:
            deployment = self.apps_v1.read_namespaced_deployment(
                name=service_name, namespace=namespace
            )
            
            # Check if deployment is ready
            if deployment.status.ready_replicas:
                return deployment.status.ready_replicas > 0
            return False
            
        except ApiException as e:
            if e.status == 404:
                logger.warning(f"Deployment {service_name} not found in namespace {namespace}")
            else:
                logger.error(f"Error validating deployment {service_name}: {str(e)}")
            return False
    
    def _validate_job(self, service_name: str, namespace: str) -> bool:
        """Validate Kubernetes Job resource"""
        try:
            job = self.batch_v1.read_namespaced_job(
                name=service_name, namespace=namespace
            )
            
            # Job is considered successful if it has succeeded
            return job.status.succeeded and job.status.succeeded > 0
            
        except ApiException as e:
            if e.status == 404:
                logger.warning(f"Job {service_name} not found in namespace {namespace}")
            else:
                logger.error(f"Error validating job {service_name}: {str(e)}")
            return False
    
    def _validate_pod(self, service_name: str, namespace: str) -> bool:
        """Validate Kubernetes Pod resource"""
        try:
            # Look for pods with labels matching the service
            pods = self.v1.list_namespaced_pod(
                namespace=namespace,
                label_selector=f"app={service_name}"
            )
            
            if not pods.items:
                return False
            
            # Check if at least one pod is running
            for pod in pods.items:
                if pod.status.phase == "Running":
                    return True
            
            return False
            
        except ApiException as e:
            logger.error(f"Error validating pods for {service_name}: {str(e)}")
            return False
    
    def _validate_crd_resources(self, service_name: str, namespace: str) -> Dict[str, bool]:
        """
        Validate Custom Resource Definition deployment (Clearing pillar specific)
        
        Returns:
            Dictionary with validation results for different resource types
        """
        results = {}
        
        # For CRDs, we need to validate multiple resulting resources
        expected_resources = SERVICE_RESOURCE_MAPPING.get(service_name, [])
        
        for resource_type in expected_resources:
            if resource_type == ResourceType.CRD:
                # Skip direct CRD validation, focus on resulting resources
                continue
            elif resource_type == ResourceType.POD:
                results[resource_type.value] = self._validate_pod(service_name, namespace)
            elif resource_type == ResourceType.SERVICE:
                results[resource_type.value] = self._validate_service(service_name, namespace)
            elif resource_type == ResourceType.INGRESS:
                results[resource_type.value] = self._validate_ingress(service_name, namespace)
        
        return results
    
    def _validate_service(self, service_name: str, namespace: str) -> bool:
        """Validate Kubernetes Service resource"""
        try:
            service = self.v1.read_namespaced_service(
                name=service_name, namespace=namespace
            )
            return service is not None
            
        except ApiException as e:
            if e.status != 404:
                logger.error(f"Error validating service {service_name}: {str(e)}")
            return False
    
    def _validate_ingress(self, service_name: str, namespace: str) -> bool:
        """Validate Kubernetes Ingress resource"""
        try:
            ingress = self.extensions_v1beta1.read_namespaced_ingress(
                name=service_name, namespace=namespace
            )
            return ingress is not None
            
        except ApiException as e:
            if e.status != 404:
                logger.error(f"Error validating ingress {service_name}: {str(e)}")
            return False
    
    def validate_service_deployment(self, service_name: str, pillar: str) -> Dict[str, Any]:
        """
        Validate deployment of a service based on its expected resources
        
        Args:
            service_name: Name of the service
            pillar: Pillar name
            
        Returns:
            Dictionary with validation results
        """
        namespace = self._get_service_namespace(service_name, pillar)
        expected_resources = SERVICE_RESOURCE_MAPPING.get(service_name, [ResourceType.DEPLOYMENT])
        
        validation_results = {
            "service_name": service_name,
            "namespace": namespace,
            "expected_resources": [r.value for r in expected_resources],
            "validations": {},
            "overall_success": False
        }
        
        success_count = 0
        total_validations = 0
        
        for resource_type in expected_resources:
            if resource_type == ResourceType.DEPLOYMENT:
                result = self._validate_deployment(service_name, namespace)
                validation_results["validations"]["deployment"] = result
                
            elif resource_type == ResourceType.JOB:
                result = self._validate_job(service_name, namespace)
                validation_results["validations"]["job"] = result
                
            elif resource_type == ResourceType.POD:
                result = self._validate_pod(service_name, namespace)
                validation_results["validations"]["pod"] = result
                
            elif resource_type == ResourceType.CRD:
                # Handle CRD validation specially
                crd_results = self._validate_crd_resources(service_name, namespace)
                validation_results["validations"].update(crd_results)
                # For CRD, count individual resource validations
                for crd_result in crd_results.values():
                    if crd_result:
                        success_count += 1
                    total_validations += 1
                continue
            
            # Count regular resource validations
            if result:
                success_count += 1
            total_validations += 1
        
        # Overall success if majority of resources are validated successfully
        validation_results["overall_success"] = success_count >= (total_validations * 0.5)
        validation_results["success_rate"] = success_count / total_validations if total_validations > 0 else 0
        
        return validation_results

# =============================================================================
# Deployment Orchestrator
# =============================================================================

class DeploymentOrchestrator:
    """Orchestrates the entire deployment process"""
    
    def __init__(self):
        self.webhook_manager = HarnessWebhookManager()
        self.k8s_validator = KubernetesValidator()
        self.deployment_results = {}
    
    def deploy_service(self, service: ServiceConfig, pillar_name: str) -> DeploymentResult:
        """
        Deploy a single service and validate the deployment
        
        Args:
            service: ServiceConfig object
            pillar_name: Name of the pillar
            
        Returns:
            DeploymentResult object
        """
        start_time = datetime.utcnow()
        
        logger.info(f"Starting deployment for {service.service_name} in {pillar_name} pillar")
        
        # Step 1: Trigger Harness webhook
        webhook_success, webhook_response = self.webhook_manager.trigger_deployment(service)
        
        if not webhook_success:
            return DeploymentResult(
                service_name=service.service_name,
                success=False,
                webhook_response=webhook_response,
                error_message="Webhook trigger failed",
                deployment_time=start_time
            )
        
        # Step 2: Wait for deployment to propagate
        logger.info(f"Webhook triggered successfully for {service.service_name}, waiting for deployment...")
        time.sleep(VALIDATION_RETRY_DELAY)
        
        # Step 3: Validate deployment with retries
        validation_results = None
        for attempt in range(VALIDATION_RETRY_COUNT):
            try:
                validation_results = self.k8s_validator.validate_service_deployment(
                    service.service_name, pillar_name
                )
                
                if validation_results["overall_success"]:
                    logger.info(f"Deployment validation successful for {service.service_name}")
                    break
                else:
                    logger.warning(
                        f"Deployment validation failed for {service.service_name}, "
                        f"attempt {attempt + 1}/{VALIDATION_RETRY_COUNT}"
                    )
                    
                    if attempt < VALIDATION_RETRY_COUNT - 1:
                        time.sleep(VALIDATION_RETRY_DELAY)
                        
            except Exception as e:
                logger.error(f"Validation attempt {attempt + 1} failed: {str(e)}")
                if attempt < VALIDATION_RETRY_COUNT - 1:
                    time.sleep(VALIDATION_RETRY_DELAY)
        
        # Determine overall success
        deployment_success = (
            webhook_success and 
            validation_results and 
            validation_results["overall_success"]
        )
        
        result = DeploymentResult(
            service_name=service.service_name,
            success=deployment_success,
            webhook_response=webhook_response,
            validation_results=validation_results,
            error_message=None if deployment_success else "Deployment validation failed",
            deployment_time=start_time
        )
        
        # Store result for tracking
        self.deployment_results[service.service_name] = result
        
        return result
    
    def deploy_pillar(self, pillar: PillarConfig) -> List[DeploymentResult]:
        """
        Deploy all services in a pillar
        
        Args:
            pillar: PillarConfig object
            
        Returns:
            List of DeploymentResult objects
        """
        logger.info(f"Starting deployment for {pillar.name} pillar with {len(pillar.services)} services")
        
        results = []
        
        # Deploy services sequentially to avoid overwhelming the system
        for service in pillar.services:
            try:
                result = self.deploy_service(service, pillar.name)
                results.append(result)
                
                # Brief pause between service deployments
                time.sleep(5)
                
            except Exception as e:
                logger.error(f"Deployment failed for {service.service_name}: {str(e)}")
                results.append(DeploymentResult(
                    service_name=service.service_name,
                    success=False,
                    error_message=str(e),
                    deployment_time=datetime.utcnow()
                ))
        
        return results
    
    def deploy_all(self, pillars: List[PillarConfig], parallel: bool = False) -> Dict[str, List[DeploymentResult]]:
        """
        Deploy services across all pillars
        
        Args:
            pillars: List of PillarConfig objects
            parallel: Whether to deploy pillars in parallel
            
        Returns:
            Dictionary mapping pillar names to deployment results
        """
        all_results = {}
        
        if parallel:
            # Deploy pillars in parallel using threading
            threads = []
            thread_results = {}
            
            def deploy_pillar_thread(pillar_config):
                thread_results[pillar_config.name] = self.deploy_pillar(pillar_config)
            
            for pillar in pillars:
                thread = threading.Thread(target=deploy_pillar_thread, args=(pillar,))
                threads.append(thread)
                thread.start()
            
            # Wait for all threads to complete
            for thread in threads:
                thread.join()
            
            all_results = thread_results
            
        else:
            # Deploy pillars sequentially
            for pillar in pillars:
                all_results[pillar.name] = self.deploy_pillar(pillar)
        
        return all_results

# =============================================================================
# Flask Application
# =============================================================================

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Global orchestrator instance
orchestrator = DeploymentOrchestrator()

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    })

@app.route('/deploy', methods=['POST'])
def deploy():
    """
    Main deployment endpoint
    
    Accepts YAML configuration and triggers deployments
    """
    try:
        # Get deployment mode
        parallel_mode = request.args.get('parallel', 'false').lower() == 'true'
        
        # Parse YAML from request
        if request.content_type == 'application/x-yaml' or request.content_type == 'text/yaml':
            yaml_content = request.data.decode('utf-8')
        elif request.content_type == 'application/json':
            data = request.get_json()
            yaml_content = data.get('yaml_content')
            if not yaml_content:
                return jsonify({"error": "yaml_content field required"}), 400
        else:
            # Try to get from form data or files
            if 'yaml_file' in request.files:
                file = request.files['yaml_file']
                yaml_content = file.read().decode('utf-8')
            else:
                return jsonify({"error": "Invalid content type. Use application/x-yaml, text/yaml, or application/json"}), 400
        
        # Parse and validate YAML
        try:
            pillars = YamlParser.parse_yaml_content(yaml_content)
        except ValueError as e:
            return jsonify({"error": f"YAML parsing failed: {str(e)}"}), 400
        
        if not pillars:
            return jsonify({"error": "No valid pillars found in YAML"}), 400
        
        # Start deployment process
        logger.info(f"Starting deployment process for {len(pillars)} pillars")
        deployment_results = orchestrator.deploy_all(pillars, parallel=parallel_mode)
        
        # Prepare response
        response_data = {
            "deployment_id": f"deploy-{int(time.time())}",
            "status": "completed",
            "timestamp": datetime.utcnow().isoformat(),
            "parallel_mode": parallel_mode,
            "results": {}
        }
        
        overall_success = True
        total_services = 0
        successful_services = 0
        
        for pillar_name, results in deployment_results.items():
            pillar_summary = {
                "services_count": len(results),
                "successful_count": sum(1 for r in results if r.success),
                "failed_count": sum(1 for r in results if not r.success),
                "services": []
            }
            
            for result in results:
                service_data = {
                    "service_name": result.service_name,
                    "success": result.success,
                    "deployment_time": result.deployment_time.isoformat() if result.deployment_time else None,
                    "error_message": result.error_message
                }
                
                if result.webhook_response:
                    service_data["webhook_response"] = result.webhook_response
                
                if result.validation_results:
                    service_data["validation_results"] = result.validation_results
                
                pillar_summary["services"].append(service_data)
                
                total_services += 1
                if result.success:
                    successful_services += 1
                else:
                    overall_success = False
            
            response_data["results"][pillar_name] = pillar_summary
        
        response_data["overall_success"] = overall_success
        response_data["total_services"] = total_services
        response_data["successful_services"] = successful_services
        response_data["success_rate"] = successful_services / total_services if total_services > 0 else 0
        
        status_code = 200 if overall_success else 207  # 207 for partial success
        return jsonify(response_data), status_code
        
    except Exception as e:
        logger.error(f"Deployment endpoint error: {str(e)}")
        return jsonify({
            "error": "Internal server error",
            "message": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }), 500

@app.route('/status/<deployment_id>', methods=['GET'])
def get_deployment_status(deployment_id):
    """Get status of a specific deployment"""
    # This is a placeholder for deployment tracking
    # In a production system, you'd store deployment status in a database
    return jsonify({
        "deployment_id": deployment_id,
        "status": "completed",
        "message": "Status tracking not implemented in this version"
    })

@app.route('/services/validate', methods=['POST'])
def validate_services():
    """
    Endpoint to validate services without deploying
    """
    try:
        data = request.get_json()
        services = data.get('services', [])
        pillar = data.get('pillar', 'unknown')
        
        if not services:
            return jsonify({"error": "services list required"}), 400
        
        results = []
        for service_name in services:
            validation_result = orchestrator.k8s_validator.validate_service_deployment(service_name, pillar)
            results.append(validation_result)
        
        return jsonify({
            "validation_results": results,
            "timestamp": datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Validation endpoint error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.errorhandler(413)
def request_entity_too_large(error):
    """Handle file size exceeded error"""
    return jsonify({"error": "File too large. Maximum size is 16MB"}), 413

@app.errorhandler(500)
def internal_server_error(error):
    """Handle internal server errors"""
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({
        "error": "Internal server error",
        "timestamp": datetime.utcnow().isoformat()
    }), 500

# =============================================================================
# Application Entry Point
# =============================================================================

if __name__ == '__main__':
    # Configuration from environment variables
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    
    logger.info(f"Starting DevOps Deployment Automation Flask App on {host}:{port}")
    app.run(host=host, port=port, debug=debug)
