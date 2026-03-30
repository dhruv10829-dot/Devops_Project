"""
ML-Based CI/CD Pipeline Failure Prediction Service
Flask REST API for predicting build outcomes before execution
"""
 
from flask import Flask, request, jsonify
from flask_cors import CORS
import joblib
import numpy as np
import pandas as pd
from datetime import datetime
import logging
import json
import os
from groq import Groq
from dotenv import load_dotenv
 
# Load environment variables from .env file
load_dotenv()
 
# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Allow frontend (HTML file) to call this API
 
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
 
PREDICTION_LOG_FILE = "predictions_log.json"
 
# Initialize Groq client (reads GROQ_API_KEY from .env automatically)
groq_client = Groq()

# Initialize Redis cache
from redis_cache import get_cache
cache = get_cache()
 
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
 
    for candidate in (hour, str(hour)):
        try:
            return int(label_encoder.transform([candidate])[0])
        except Exception:
            continue
 
    return hour
 
 
def append_prediction_log(entry):
    """Append a prediction entry to the JSON log file in the project root."""
    log_data = []
 
    if os.path.exists(PREDICTION_LOG_FILE):
        try:
            with open(PREDICTION_LOG_FILE, 'r', encoding='utf-8') as f:
                existing = json.load(f)
                if isinstance(existing, list):
                    log_data = existing
        except Exception as e:
            logger.warning(f"Could not read existing prediction log. Starting a new file: {e}")
 
    log_data.append(entry)
 
    with open(PREDICTION_LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(log_data, f, indent=2)
 
 
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

        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        missing_features = [f for f in feature_names if f not in data]
        if missing_features:
            return jsonify({
                "error": f"Missing features: {', '.join(missing_features)}"
            }), 400

        # Check cache first
        cached_result = cache.get(data)
        if cached_result:
            cached_result["cached"] = True
            cached_result["timestamp"] = datetime.now().isoformat()
            logger.info(f"Returning cached prediction: {cached_result.get('prediction')}")
            return jsonify(cached_result), 200

        input_data = []
        for feature in feature_names:
            value = data[feature]
            if feature == 'time_of_commit':
                value = encode_time_of_commit(value)
            input_data.append(value)
 
        X = pd.DataFrame([input_data], columns=feature_names)
        X_scaled = scaler.transform(X)
 
        prediction = model.predict(X_scaled)[0]
        probability = model.predict_proba(X_scaled)[0]
 
        failure_prob = probability[1]
        if failure_prob < 0.25:
            risk_level = "LOW"
        elif failure_prob < 0.50:
            risk_level = "MEDIUM"
        elif failure_prob < 0.75:
            risk_level = "HIGH"
        else:
            risk_level = "CRITICAL"
 
        prediction_label = "FAIL" if prediction == 1 else "PASS"
        confidence = max(probability)
 
        response = {
            "prediction": prediction_label,
            "risk_level": risk_level,
            "failure_probability": round(failure_prob, 4),
            "pass_probability": round(probability[0], 4),
            "confidence": round(confidence, 4),
            "recommendation": "🔴 STOP PIPELINE" if prediction == 1 else "🟢 CONTINUE PIPELINE",
            "timestamp": datetime.now().isoformat(),
            "cached": False
        }

        # Store in cache
        cache.set(data, response, ttl=3600)

        try:
            append_prediction_log({
                "endpoint": "/predict",
                "timestamp": response["timestamp"],
                "input": data,
                "output": response
            })
        except Exception as e:
            logger.warning(f"Prediction generated but failed to write JSON log: {e}")
 
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
            input_data = []
            for feature in feature_names:
                value = commit_data.get(feature)
                if value is None:
                    return jsonify({"error": f"Missing feature: {feature}"}), 400
                if feature == 'time_of_commit':
                    value = encode_time_of_commit(value)
                input_data.append(value)
 
            X = pd.DataFrame([input_data], columns=feature_names)
            X_scaled = scaler.transform(X)
            prediction = model.predict(X_scaled)[0]
            probability = model.predict_proba(X_scaled)[0]
 
            results.append({
                "commit_id": commit_data.get("commit_id", "unknown"),
                "prediction": "FAIL" if prediction == 1 else "PASS",
                "failure_probability": round(probability[1], 4)
            })
 
        try:
            append_prediction_log({
                "endpoint": "/predict-batch",
                "timestamp": datetime.now().isoformat(),
                "input": data,
                "output": {"predictions": results}
            })
        except Exception as e:
            logger.warning(f"Batch prediction generated but failed to write JSON log: {e}")
 
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
 
 
# ============ PREDICTIONS LOG ============
@app.route('/predictions-log', methods=['GET'])
def predictions_log():
    """Read stored predictions from JSON log file."""
    try:
        if not os.path.exists(PREDICTION_LOG_FILE):
            return jsonify({"entries": [], "count": 0}), 200

        with open(PREDICTION_LOG_FILE, 'r', encoding='utf-8') as f:
            entries = json.load(f)

        if not isinstance(entries, list):
            entries = []

        return jsonify({"entries": entries, "count": len(entries)}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============ CACHE STATS ============
@app.route('/cache-stats', methods=['GET'])
def cache_stats():
    """Get Redis cache statistics."""
    try:
        stats = cache.get_stats()
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/cache-clear', methods=['POST'])
def cache_clear():
    """Clear all prediction caches."""
    try:
        success = cache.clear_all()
        if success:
            return jsonify({"message": "Cache cleared successfully"}), 200
        else:
            return jsonify({"error": "Cache not available"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============ GROQ AI ANALYSIS ============
@app.route('/analyze', methods=['POST'])
def analyze():
    """
    Generate AI-powered analysis using Groq LLM.
 
    Input JSON:
    {
        "prediction": { ...output from /predict... },
        "input": { ...original commit metadata... }
    }
 
    Output:
    {
        "summary": "2-sentence risk analysis",
        "steps": ["step1", "step2", "step3", "step4"]
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
 
        prediction = data.get('prediction', {})
        input_data = data.get('input', {})
 
        prompt = f"""You are a senior DevOps engineer reviewing a CI/CD pipeline risk prediction.
 
Prediction Result:
- Outcome: {prediction.get('prediction')}
- Risk Level: {prediction.get('risk_level')}
- Failure Probability: {round(prediction.get('failure_probability', 0) * 100, 1)}%
- Confidence: {round(prediction.get('confidence', 0) * 100, 1)}%
 
Commit Metadata:
- commit_size: {input_data.get('commit_size')} lines changed
- files_changed: {input_data.get('files_changed')}
- test_coverage: {input_data.get('test_coverage')}%
- past_failures: {input_data.get('past_failures')}
- dependency_changes: {'Yes' if input_data.get('dependency_changes') == 1 else 'No'}
- author_experience: {input_data.get('author_experience')} past commits
- time_of_commit: {input_data.get('time_of_commit')}:00h
- build_time: {input_data.get('build_time')}s
 
Write a brief 2-sentence summary of the risk, then provide exactly 4 specific and actionable steps the developer should take before or after running the pipeline.
 
Respond ONLY with valid JSON in this exact format, no markdown, no explanation:
{{"summary": "your 2 sentence summary here", "steps": ["step 1", "step 2", "step 3", "step 4"]}}"""
 
        chat = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.4
        )
 
        raw = chat.choices[0].message.content.strip()
        # Strip markdown fences if model wraps in ```json
        raw = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)
 
        logger.info("✅ Groq analysis generated successfully")
        return jsonify(result), 200
 
    except json.JSONDecodeError as e:
        logger.error(f"Groq returned invalid JSON: {e}")
        return jsonify({"error": "AI returned invalid response, try again"}), 500
    except Exception as e:
        logger.error(f"Groq analysis error: {e}")
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
        print("  POST /analyze          - Groq AI analysis")
        print("  GET  /health           - Health check")
        print("  GET  /features         - Feature importance")
        print("  GET  /predictions-log  - View prediction history")
        print("\nStarting server on http://0.0.0.0:5000")
        print("=" * 60 + "\n")
 
        app.run(host='0.0.0.0', port=5000, debug=False)
    else:
        print("❌ Model failed to load. Cannot start API.")
 
