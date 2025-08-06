import os
import uuid
import logging
from flask import render_template, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename
from app import app, db
from models import Deployment, DeploymentBatch, DeploymentStatus
from services.yaml_processor import YAMLProcessor
from services.deployment_manager import DeploymentManager
from utils.exceptions import ValidationError, DeploymentError

logger = logging.getLogger(__name__)

# Allowed file extensions
ALLOWED_EXTENSIONS = {'yaml', 'yml'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    """Main dashboard showing recent deployments and batch status"""
    recent_batches = DeploymentBatch.query.order_by(DeploymentBatch.created_at.desc()).limit(10).all()
    return render_template('index.html', recent_batches=recent_batches)

@app.route('/upload')
def upload_form():
    """Show the YAML upload form"""
    return render_template('upload.html')

@app.route('/upload', methods=['POST'])
def upload_yaml():
    """Handle YAML file upload and batch deployment creation"""
    try:
        # Check if the post request has the file part
        if 'yaml_file' not in request.files:
            flash('No file selected', 'error')
            return redirect(request.url)
        
        file = request.files['yaml_file']
        processing_mode = request.form.get('processing_mode', 'parallel')
        
        # If user does not select file, browser submits empty part without filename
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(request.url)
        
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            batch_id = str(uuid.uuid4())
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"{batch_id}_{filename}")
            file.save(filepath)
            
            # Process YAML file
            yaml_processor = YAMLProcessor()
            try:
                deployment_config = yaml_processor.parse_and_validate(filepath)
                
                # Create deployment batch
                batch = DeploymentBatch(
                    batch_id=batch_id,
                    yaml_filename=filename,
                    total_deployments=len(deployment_config.get('deployments', [])),
                    processing_mode=processing_mode
                )
                db.session.add(batch)
                db.session.commit()
                
                # Start deployment process
                deployment_manager = DeploymentManager()
                deployment_manager.process_batch_deployment(batch_id, deployment_config, processing_mode)
                
                flash(f'Deployment batch {batch_id} created successfully', 'success')
                return redirect(url_for('deployment_status', batch_id=batch_id))
                
            except ValidationError as e:
                flash(f'YAML validation error: {str(e)}', 'error')
                os.remove(filepath)  # Clean up invalid file
                return redirect(request.url)
            except Exception as e:
                logger.error(f"Error processing YAML file: {str(e)}")
                flash(f'Error processing file: {str(e)}', 'error')
                if os.path.exists(filepath):
                    os.remove(filepath)
                return redirect(request.url)
        else:
            flash('Invalid file type. Please upload a YAML file.', 'error')
            return redirect(request.url)
            
    except Exception as e:
        logger.error(f"Unexpected error in upload_yaml: {str(e)}")
        flash('An unexpected error occurred', 'error')
        return redirect(request.url)

@app.route('/status/<batch_id>')
def deployment_status(batch_id):
    """Show deployment status for a specific batch"""
    batch = DeploymentBatch.query.filter_by(batch_id=batch_id).first_or_404()
    deployments = Deployment.query.filter_by(batch_id=batch_id).all()
    
    return render_template('status.html', batch=batch, deployments=deployments)

@app.route('/api/status/<batch_id>')
def api_deployment_status(batch_id):
    """API endpoint for real-time deployment status updates"""
    batch = DeploymentBatch.query.filter_by(batch_id=batch_id).first_or_404()
    deployments = Deployment.query.filter_by(batch_id=batch_id).all()
    
    deployment_data = []
    for deployment in deployments:
        deployment_data.append({
            'id': deployment.id,
            'pillar': deployment.pillar.value,
            'service_name': deployment.service_name,
            'docker_artifact_type': deployment.docker_artifact_type,
            'docker_image_version': deployment.docker_image_version,
            'status': deployment.status.value,
            'error_message': deployment.error_message,
            'updated_at': deployment.updated_at.isoformat() if deployment.updated_at else None
        })
    
    return jsonify({
        'batch_id': batch.batch_id,
        'status': batch.status.value,
        'total_deployments': batch.total_deployments,
        'successful_deployments': batch.successful_deployments,
        'failed_deployments': batch.failed_deployments,
        'deployments': deployment_data
    })

@app.route('/rollback/<batch_id>', methods=['POST'])
def rollback_deployment(batch_id):
    """Rollback a failed deployment batch"""
    try:
        batch = DeploymentBatch.query.filter_by(batch_id=batch_id).first_or_404()
        
        deployment_manager = DeploymentManager()
        result = deployment_manager.rollback_batch(batch_id)
        
        if result['success']:
            flash(f'Rollback initiated for batch {batch_id}', 'success')
        else:
            flash(f'Rollback failed: {result["error"]}', 'error')
            
    except Exception as e:
        logger.error(f"Error initiating rollback: {str(e)}")
        flash('Error initiating rollback', 'error')
    
    return redirect(url_for('deployment_status', batch_id=batch_id))

@app.route('/validate-yaml', methods=['POST'])
def validate_yaml():
    """API endpoint to validate YAML without processing"""
    try:
        if 'yaml_file' not in request.files:
            return jsonify({'valid': False, 'error': 'No file provided'})
        
        file = request.files['yaml_file']
        if file.filename == '' or not allowed_file(file.filename):
            return jsonify({'valid': False, 'error': 'Invalid file type'})
        
        # Save temporary file for validation
        temp_filename = secure_filename(f"temp_{uuid.uuid4()}_{file.filename}")
        temp_filepath = os.path.join(app.config['UPLOAD_FOLDER'], temp_filename)
        file.save(temp_filepath)
        
        try:
            yaml_processor = YAMLProcessor()
            deployment_config = yaml_processor.parse_and_validate(temp_filepath)
            
            # Clean up temp file
            os.remove(temp_filepath)
            
            return jsonify({
                'valid': True,
                'deployment_count': len(deployment_config.get('deployments', [])),
                'pillars': list(set([d.get('pillar') for d in deployment_config.get('deployments', [])]))
            })
            
        except ValidationError as e:
            os.remove(temp_filepath)
            return jsonify({'valid': False, 'error': str(e)})
        except Exception as e:
            os.remove(temp_filepath)
            return jsonify({'valid': False, 'error': f'Validation error: {str(e)}'})
            
    except Exception as e:
        logger.error(f"Error in validate_yaml: {str(e)}")
        return jsonify({'valid': False, 'error': 'Validation failed'})

@app.errorhandler(404)
def not_found_error(error):
    return render_template('error.html', error_code=404, error_message="Page not found"), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {str(error)}")
    return render_template('error.html', error_code=500, error_message="Internal server error"), 500
