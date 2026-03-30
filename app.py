"""
ML-Based CI/CD Pipeline Failure Prediction Service
Flask REST API for predicting build outcomes before execution
"""

from flask import Flask, request, jsonify
import joblib
import numpy as np
import pandas as pd
from datetime import datetime
import logging

# Initialize Flask app
app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load pre-trained model and preprocessing objects
try:
    model = joblib.load('random_forest_model.pkl')
    scaler = joblib.load('scaler.pkl')
    label_encoder = joblib.load('label_encoder.pkl')
    with open('feature_names.txt', 'r') as f:
        feature_names = f.read().strip().split(',')
    logger.info("✅ Model and preprocessing objects loaded successfully")
except Exception as e:
    logger.error(f"❌ Failed to load model: {e}")
    model = None
    scaler = None
    label_encoder = None
    feature_names = []


def encode_time_of_commit(value):
    """Encode commit hour while accepting both numeric and string input."""
    try:
        hour = int(value)
    except (TypeError, ValueError):
        raise ValueError("time_of_commit must be an integer hour between 0 and 23")

    if hour < 0 or hour > 23:
        raise ValueError("time_of_commit must be between 0 and 23")

    if label_encoder is None:
        return hour

    # Handle models trained with int classes as well as string classes.
    for candidate in (hour, str(hour)):
        try:
            return int(label_encoder.transform([candidate])[0])
        except Exception:
            continue

    # Fallback for pipelines trained directly on numeric hour.
    return hour

# ============ HEALTH CHECK ============
@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "CI/CD Failure Predictor",
        "timestamp": datetime.now().isoformat()
    }), 200

# ============ PREDICTION ENDPOINT ============
@app.route('/predict', methods=['POST'])
def predict():
    """
    Predict CI/CD build outcome
    
    Input JSON:
    {
        "commit_size": 50,
        "files_changed": 3,
        "test_coverage": 85.5,
        "past_failures": 2,
        "dependency_changes": 0,
        "author_experience": 120,
        "time_of_commit": 14,
        "build_time": 350.5
    }
    
    Output:
    {
        "prediction": "PASS",
        "risk_level": "LOW",
        "failure_probability": 0.23,
        "confidence": 0.92
    }
    """
    try:
        data = request.get_json()
        
        # Validate input
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        # Check for required features
        missing_features = [f for f in feature_names if f not in data]
        if missing_features:
            return jsonify({
                "error": f"Missing features: {', '.join(missing_features)}"
            }), 400
        
        # Prepare data for prediction
        input_data = []
        for feature in feature_names:
            value = data[feature]
            if feature == 'time_of_commit':
                value = encode_time_of_commit(value)
            input_data.append(value)
        
        # Create DataFrame with feature names
        X = pd.DataFrame([input_data], columns=feature_names)
        
        # Scale features
        X_scaled = scaler.transform(X)
        
        # Get prediction and probability
        prediction = model.predict(X_scaled)[0]
        probability = model.predict_proba(X_scaled)[0]
        
        # Calculate risk level
        failure_prob = probability[1]
        if failure_prob < 0.25:
            risk_level = "LOW"
        elif failure_prob < 0.50:
            risk_level = "MEDIUM"
        elif failure_prob < 0.75:
            risk_level = "HIGH"
        else:
            risk_level = "CRITICAL"
        
        # Prediction result
        prediction_label = "FAIL" if prediction == 1 else "PASS"
        confidence = max(probability)
        
        response = {
            "prediction": prediction_label,
            "risk_level": risk_level,
            "failure_probability": round(failure_prob, 4),
            "pass_probability": round(probability[0], 4),
            "confidence": round(confidence, 4),
            "recommendation": "🔴 STOP PIPELINE" if prediction == 1 else "🟢 CONTINUE PIPELINE",
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"Prediction: {prediction_label} (risk: {risk_level}, prob: {failure_prob:.4f})")
        return jsonify(response), 200
        
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except KeyError as e:
        return jsonify({"error": f"Invalid feature: {str(e)}"}), 400
    except Exception as e:
        logger.error(f"Prediction error: {e}")
        return jsonify({"error": str(e)}), 500

# ============ BATCH PREDICTION ============
@app.route('/predict-batch', methods=['POST'])
def predict_batch():
    """
    Predict for multiple commits at once
    
    Input: Array of commit metadata objects
    Output: Array of predictions
    """
    try:
        data = request.get_json()
        if not isinstance(data, list):
            return jsonify({"error": "Input must be a list of commits"}), 400
        
        results = []
        for commit_data in data:
            # Prepare data
            input_data = []
            for feature in feature_names:
                value = commit_data.get(feature)
                if value is None:
                    return jsonify({"error": f"Missing feature: {feature}"}), 400
                if feature == 'time_of_commit':
                    value = encode_time_of_commit(value)
                input_data.append(value)
            
            # Predict
            X = pd.DataFrame([input_data], columns=feature_names)
            X_scaled = scaler.transform(X)
            prediction = model.predict(X_scaled)[0]
            probability = model.predict_proba(X_scaled)[0]
            
            results.append({
                "commit_id": commit_data.get("commit_id", "unknown"),
                "prediction": "FAIL" if prediction == 1 else "PASS",
                "failure_probability": round(probability[1], 4)
            })
        
        return jsonify({"predictions": results}), 200
        
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Batch prediction error: {e}")
        return jsonify({"error": str(e)}), 500

# ============ FEATURE IMPORTANCE ============
@app.route('/features', methods=['GET'])
def features():
    """Get feature information and importance"""
    try:
        importance_dict = dict(zip(feature_names, model.feature_importances_))
        return jsonify({
            "features": feature_names,
            "importance": importance_dict
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============ ERROR HANDLERS ============
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    if model is not None:
        print("\n" + "=" * 60)
        print("🚀 CI/CD Failure Prediction API")
        print("=" * 60)
        print(f"Features: {', '.join(feature_names)}")
        print("\nEndpoints:")
        print("  POST /predict          - Single prediction")
        print("  POST /predict-batch    - Batch predictions")
        print("  GET  /health           - Health check")
        print("  GET  /features         - Feature importance")
        print("\nStarting server on http://0.0.0.0:5000")
        print("=" * 60 + "\n")
        
        app.run(host='0.0.0.0', port=5000, debug=False)
    else:
        print("❌ Model failed to load. Cannot start API.")
