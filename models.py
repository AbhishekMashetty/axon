from datetime import datetime
from app import db
from sqlalchemy import Enum as SQLEnum
import enum

class DeploymentStatus(enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLBACK = "rollback"

class Pillar(enum.Enum):
    CLEARING = "clearing"
    RISK = "risk"
    DATA = "data"
    SHARED = "shared"

class Deployment(db.Model):
    __tablename__ = 'deployments'
    
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.String(64), nullable=False, index=True)
    pillar = db.Column(SQLEnum(Pillar), nullable=False)
    service_name = db.Column(db.String(128), nullable=False)
    docker_artifact_type = db.Column(db.String(64), nullable=False)
    docker_image_version = db.Column(db.String(128), nullable=False)
    environment_id = db.Column(db.String(64), nullable=False)
    infrastructure_id = db.Column(db.String(64), nullable=False)
    status = db.Column(SQLEnum(DeploymentStatus), default=DeploymentStatus.PENDING)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    harness_execution_id = db.Column(db.String(128))
    k8s_object_type = db.Column(db.String(64))
    k8s_object_name = db.Column(db.String(128))
    error_message = db.Column(db.Text)
    rollback_data = db.Column(db.Text)  # JSON string for rollback information

class DeploymentBatch(db.Model):
    __tablename__ = 'deployment_batches'
    
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.String(64), unique=True, nullable=False)
    yaml_filename = db.Column(db.String(256), nullable=False)
    total_deployments = db.Column(db.Integer, nullable=False)
    successful_deployments = db.Column(db.Integer, default=0)
    failed_deployments = db.Column(db.Integer, default=0)
    status = db.Column(SQLEnum(DeploymentStatus), default=DeploymentStatus.PENDING)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    processing_mode = db.Column(db.String(32), default="parallel")  # parallel or sequential
