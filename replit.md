# Deployment System

## Overview

This is a Flask-based batch deployment system designed for managing Kubernetes application deployments across different pillars (clearing, risk, data, shared). The system processes YAML configuration files containing deployment specifications and orchestrates deployments through Harness webhooks and Kubernetes API validation. It provides a web interface for uploading deployment configurations, monitoring batch progress, and viewing deployment status with real-time updates.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Core Framework
- **Flask Web Application**: Serves as the main web framework with SQLAlchemy ORM for database operations
- **Database Layer**: SQLAlchemy with support for both SQLite (development) and PostgreSQL (production) through environment configuration
- **Model Design**: Uses enum-based status tracking (PENDING, PROCESSING, SUCCESS, FAILED, ROLLBACK) and pillar categorization

### Data Models
- **Deployment**: Individual deployment records with status tracking, service metadata, and error handling
- **DeploymentBatch**: Groups related deployments with batch-level status and progress tracking
- **Status Enums**: Structured status management using Python enums for deployment states and pillar types

### Service Architecture
- **YAMLProcessor**: Handles YAML parsing, JSON schema validation, and business rule enforcement
- **DeploymentManager**: Orchestrates batch deployments with parallel/sequential processing modes and thread pool management
- **HarnessClient**: Manages webhook-based deployment triggers to Harness CD platform with retry logic
- **KubernetesClient**: Provides deployment validation and status checking through Kubernetes API

### Configuration Management
- **JSON Schema Validation**: Strict YAML structure validation with deployment-specific rules
- **Service Mappings**: JSON-based mapping of services to Kubernetes objects and namespaces
- **Environment-based Configuration**: Flexible configuration through environment variables for different deployment environments

### Frontend Architecture
- **Bootstrap-based UI**: Dark theme interface with responsive design
- **JavaScript Enhancement**: Real-time status updates, form validation, and deployment monitoring
- **Template System**: Jinja2 templates with modular design for reusable components

### Processing Modes
- **Parallel Processing**: Concurrent deployment execution using ThreadPoolExecutor
- **Sequential Processing**: Ordered deployment execution with dependency awareness
- **Status Monitoring**: Real-time progress tracking with automatic refresh capabilities

### Error Handling
- **Custom Exception Hierarchy**: Structured error handling with specific exception types for validation, deployment, and system errors
- **Rollback Support**: Built-in rollback data storage and recovery mechanisms
- **Comprehensive Logging**: Multi-level logging with file rotation and console output

## External Dependencies

### Deployment Orchestration
- **Harness CD Platform**: Primary deployment orchestration through webhook integration
- **Kubernetes API**: Direct cluster interaction for deployment validation and status verification

### Database Systems
- **SQLite**: Default development database with file-based storage
- **PostgreSQL**: Production database support through DATABASE_URL environment variable

### Frontend Libraries
- **Bootstrap**: UI framework with dark theme support
- **Feather Icons**: Icon library for consistent visual elements
- **JavaScript**: Enhanced user experience with real-time updates

### Python Libraries
- **Flask & Extensions**: Web framework with SQLAlchemy ORM and proxy middleware
- **PyYAML**: YAML file parsing and processing
- **jsonschema**: Configuration validation against defined schemas
- **requests**: HTTP client for external service communication
- **kubernetes**: Official Kubernetes Python client library

### Development & Testing
- **pytest**: Testing framework with fixtures and mocking capabilities
- **unittest.mock**: Mock objects for isolated unit testing
- **tempfile**: Temporary file handling for test scenarios

### Infrastructure Integration
- **Docker**: Containerized deployment artifact management
- **Helm/Kustomize**: Support for different Kubernetes deployment patterns
- **Webhook Services**: External webhook endpoints for deployment triggering