"""Custom exceptions for the deployment system"""

class DeploymentSystemError(Exception):
    """Base exception for all deployment system errors"""
    
    def __init__(self, message: str, error_code: str = None, details: dict = None):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)
    
    def to_dict(self):
        return {
            'error': self.message,
            'error_code': self.error_code,
            'details': self.details
        }

class ValidationError(DeploymentSystemError):
    """Raised when validation fails"""
    
    def __init__(self, message: str, field: str = None, value=None):
        self.field = field
        self.value = value
        details = {}
        if field:
            details['field'] = field
        if value is not None:
            details['value'] = str(value)
        
        super().__init__(message, 'VALIDATION_ERROR', details)

class YAMLParsingError(ValidationError):
    """Raised when YAML parsing fails"""
    
    def __init__(self, message: str, line_number: int = None, column: int = None):
        self.line_number = line_number
        self.column = column
        
        details = {}
        if line_number:
            details['line_number'] = line_number
        if column:
            details['column'] = column
            
        super().__init__(message, 'yaml_content', None)
        self.error_code = 'YAML_PARSING_ERROR'
        self.details.update(details)

class SchemaValidationError(ValidationError):
    """Raised when schema validation fails"""
    
    def __init__(self, message: str, schema_path: str = None, invalid_value=None):
        self.schema_path = schema_path
        self.invalid_value = invalid_value
        
        details = {}
        if schema_path:
            details['schema_path'] = schema_path
        if invalid_value is not None:
            details['invalid_value'] = str(invalid_value)
            
        super().__init__(message, schema_path, invalid_value)
        self.error_code = 'SCHEMA_VALIDATION_ERROR'
        self.details.update(details)

class DeploymentError(DeploymentSystemError):
    """Raised when deployment operations fail"""
    
    def __init__(self, message: str, deployment_id: str = None, service_name: str = None, pillar: str = None):
        self.deployment_id = deployment_id
        self.service_name = service_name
        self.pillar = pillar
        
        details = {}
        if deployment_id:
            details['deployment_id'] = deployment_id
        if service_name:
            details['service_name'] = service_name
        if pillar:
            details['pillar'] = pillar
            
        super().__init__(message, 'DEPLOYMENT_ERROR', details)

class HarnessError(DeploymentError):
    """Raised when Harness operations fail"""
    
    def __init__(self, message: str, execution_id: str = None, webhook_url: str = None, 
                 http_status: int = None, response_body: str = None):
        self.execution_id = execution_id
        self.webhook_url = webhook_url
        self.http_status = http_status
        self.response_body = response_body
        
        details = {}
        if execution_id:
            details['execution_id'] = execution_id
        if webhook_url:
            details['webhook_url'] = webhook_url
        if http_status:
            details['http_status'] = http_status
        if response_body:
            details['response_body'] = response_body
            
        super().__init__(message)
        self.error_code = 'HARNESS_ERROR'
        self.details.update(details)

class KubernetesError(DeploymentError):
    """Raised when Kubernetes operations fail"""
    
    def __init__(self, message: str, namespace: str = None, resource_type: str = None, 
                 resource_name: str = None, api_version: str = None):
        self.namespace = namespace
        self.resource_type = resource_type
        self.resource_name = resource_name
        self.api_version = api_version
        
        details = {}
        if namespace:
            details['namespace'] = namespace
        if resource_type:
            details['resource_type'] = resource_type
        if resource_name:
            details['resource_name'] = resource_name
        if api_version:
            details['api_version'] = api_version
            
        super().__init__(message)
        self.error_code = 'KUBERNETES_ERROR'
        self.details.update(details)

class ConfigurationError(DeploymentSystemError):
    """Raised when configuration is invalid"""
    
    def __init__(self, message: str, config_key: str = None, config_value: str = None):
        self.config_key = config_key
        self.config_value = config_value
        
        details = {}
        if config_key:
            details['config_key'] = config_key
        if config_value:
            details['config_value'] = config_value
            
        super().__init__(message, 'CONFIGURATION_ERROR', details)

class ServiceMappingError(DeploymentSystemError):
    """Raised when service mapping operations fail"""
    
    def __init__(self, message: str, pillar: str = None, service_name: str = None):
        self.pillar = pillar
        self.service_name = service_name
        
        details = {}
        if pillar:
            details['pillar'] = pillar
        if service_name:
            details['service_name'] = service_name
            
        super().__init__(message, 'SERVICE_MAPPING_ERROR', details)

class BatchProcessingError(DeploymentSystemError):
    """Raised when batch processing fails"""
    
    def __init__(self, message: str, batch_id: str = None, failed_deployments: list = None):
        self.batch_id = batch_id
        self.failed_deployments = failed_deployments or []
        
        details = {}
        if batch_id:
            details['batch_id'] = batch_id
        if failed_deployments:
            details['failed_deployments'] = failed_deployments
            
        super().__init__(message, 'BATCH_PROCESSING_ERROR', details)

class TimeoutError(DeploymentSystemError):
    """Raised when operations timeout"""
    
    def __init__(self, message: str, timeout_seconds: int = None, operation: str = None):
        self.timeout_seconds = timeout_seconds
        self.operation = operation
        
        details = {}
        if timeout_seconds:
            details['timeout_seconds'] = timeout_seconds
        if operation:
            details['operation'] = operation
            
        super().__init__(message, 'TIMEOUT_ERROR', details)

class AuthenticationError(DeploymentSystemError):
    """Raised when authentication fails"""
    
    def __init__(self, message: str, service: str = None, endpoint: str = None):
        self.service = service
        self.endpoint = endpoint
        
        details = {}
        if service:
            details['service'] = service
        if endpoint:
            details['endpoint'] = endpoint
            
        super().__init__(message, 'AUTHENTICATION_ERROR', details)

class RollbackError(DeploymentSystemError):
    """Raised when rollback operations fail"""
    
    def __init__(self, message: str, batch_id: str = None, deployment_ids: list = None):
        self.batch_id = batch_id
        self.deployment_ids = deployment_ids or []
        
        details = {}
        if batch_id:
            details['batch_id'] = batch_id
        if deployment_ids:
            details['deployment_ids'] = deployment_ids
            
        super().__init__(message, 'ROLLBACK_ERROR', details)

# Exception mapping for HTTP status codes
HTTP_EXCEPTION_MAP = {
    400: ValidationError,
    401: AuthenticationError,
    403: AuthenticationError,
    404: ServiceMappingError,
    408: TimeoutError,
    422: ValidationError,
    500: DeploymentSystemError,
    502: HarnessError,
    503: DeploymentSystemError,
    504: TimeoutError
}

def get_exception_for_http_status(status_code: int, message: str, **kwargs):
    """Get appropriate exception class for HTTP status code"""
    exception_class = HTTP_EXCEPTION_MAP.get(status_code, DeploymentSystemError)
    return exception_class(message, **kwargs)
