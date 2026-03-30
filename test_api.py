"""
Test scenarios for CI/CD Failure Prediction API
Run with: python test_api.py (after starting the Flask server)
"""

import requests
import json
import sys

BASE_URL = "http://localhost:5000"

# Test data scenarios
test_scenarios = [
    {
        "name": "Low Risk - Small, Well-Tested Commit",
        "data": {
            "commit_size": 20,
            "files_changed": 2,
            "test_coverage": 95.0,
            "past_failures": 0,
            "dependency_changes": 0,
            "author_experience": 180,
            "time_of_commit": 14,
            "build_time": 150.0
        },
        "expected": "PASS"
    },
    {
        "name": "Medium Risk - Moderate Commit with Some Changes",
        "data": {
            "commit_size": 100,
            "files_changed": 5,
            "test_coverage": 75.0,
            "past_failures": 2,
            "dependency_changes": 0,
            "author_experience": 60,
            "time_of_commit": 14,
            "build_time": 350.0
        },
        "expected": "MEDIUM"
    },
    {
        "name": "High Risk - Large Commit with Dependency Changes",
        "data": {
            "commit_size": 300,
            "files_changed": 15,
            "test_coverage": 45.0,
            "past_failures": 5,
            "dependency_changes": 1,
            "author_experience": 20,
            "time_of_commit": 2,
            "build_time": 800.0
        },
        "expected": "FAIL"
    },
    {
        "name": "Critical Risk - Very Large Commit with High Failure History",
        "data": {
            "commit_size": 500,
            "files_changed": 40,
            "test_coverage": 30.0,
            "past_failures": 10,
            "dependency_changes": 1,
            "author_experience": 5,
            "time_of_commit": 0,
            "build_time": 1500.0
        },
        "expected": "FAIL"
    }
]

def print_header(text):
    print("\n" + "="*70)
    print(f"  {text}")
    print("="*70)

def test_health():
    """Test health check endpoint"""
    print_header("TEST 1: Health Check")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"✅ Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_features():
    """Test feature importance endpoint"""
    print_header("TEST 2: Feature Importance")
    try:
        response = requests.get(f"{BASE_URL}/features", timeout=5)
        print(f"✅ Status: {response.status_code}")
        data = response.json()
        print(f"Features: {', '.join(data['features'])}")
        print(f"\nImportance:")
        for feature, importance in sorted(data['importance'].items(), key=lambda x: x[1], reverse=True):
            print(f"  {feature:25s}: {importance:.4f}")
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_predictions():
    """Test prediction scenarios"""
    print_header("TEST 3: Prediction Scenarios")
    
    results = []
    for i, scenario in enumerate(test_scenarios, 1):
        print(f"\nScenario {i}: {scenario['name']}")
        print("-" * 70)
        
        try:
            response = requests.post(
                f"{BASE_URL}/predict",
                json=scenario['data'],
                timeout=5
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Format output
                prediction = result['prediction']
                risk = result['risk_level']
                prob = result['failure_probability']
                conf = result['confidence']
                recommendation = result['recommendation']
                
                print(f"Input commit metrics:")
                print(f"  Commit size: {scenario['data']['commit_size']} lines")
                print(f"  Files changed: {scenario['data']['files_changed']}")
                print(f"  Test coverage: {scenario['data']['test_coverage']}%")
                print(f"  Past failures: {scenario['data']['past_failures']}")
                print(f"  Dependency changes: {scenario['data']['dependency_changes']}")
                
                print(f"\nPrediction Result:")
                print(f"  {recommendation}")
                print(f"  Prediction: {prediction}")
                print(f"  Risk Level: {risk}")
                print(f"  Failure Probability: {prob:.2%}")
                print(f"  Confidence: {conf:.2%}")
                
                results.append({
                    'scenario': scenario['name'],
                    'prediction': prediction,
                    'status': '✅ PASS' if prediction == scenario['expected'] else '⚠️  UNEXPECTED'
                })
            else:
                print(f"❌ Error: {response.status_code}")
                print(f"Response: {response.text}")
                results.append({
                    'scenario': scenario['name'],
                    'status': '❌ FAILED'
                })
                
        except Exception as e:
            print(f"❌ Exception: {e}")
            results.append({
                'scenario': scenario['name'],
                'status': f'❌ {str(e)}'
            })
    
    return results

def test_batch_prediction():
    """Test batch prediction"""
    print_header("TEST 4: Batch Prediction")
    
    batch_data = [
        {
            "commit_id": "abc123",
            "commit_size": 30,
            "files_changed": 2,
            "test_coverage": 90.0,
            "past_failures": 0,
            "dependency_changes": 0,
            "author_experience": 150,
            "time_of_commit": 12,
            "build_time": 200.0
        },
        {
            "commit_id": "def456",
            "commit_size": 250,
            "files_changed": 12,
            "test_coverage": 50.0,
            "past_failures": 3,
            "dependency_changes": 1,
            "author_experience": 30,
            "time_of_commit": 14,
            "build_time": 700.0
        }
    ]
    
    try:
        response = requests.post(
            f"{BASE_URL}/predict-batch",
            json=batch_data,
            timeout=5
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Batch prediction successful")
            print(f"Processed {len(result['predictions'])} commits:")
            for pred in result['predictions']:
                print(f"  {pred['commit_id']}: {pred['prediction']} (prob: {pred['failure_probability']:.2%})")
            return True
        else:
            print(f"❌ Error: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False

def test_invalid_input():
    """Test error handling"""
    print_header("TEST 5: Error Handling")
    
    # Missing required field
    print("\nTest 5a: Missing required field")
    invalid_data = {
        "commit_size": 50,
        "files_changed": 3
        # Missing other required fields
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/predict",
            json=invalid_data,
            timeout=5
        )
        if response.status_code != 200:
            print(f"✅ Correctly rejected invalid input: {response.status_code}")
            print(f"   Error: {response.json()['error']}")
        else:
            print(f"❌ Should have rejected invalid input")
    except Exception as e:
        print(f"Exception: {e}")
    
    # Empty JSON
    print("\nTest 5b: Empty JSON")
    try:
        response = requests.post(
            f"{BASE_URL}/predict",
            json={},
            timeout=5
        )
        if response.status_code != 200:
            print(f"✅ Correctly rejected empty input: {response.status_code}")
        else:
            print(f"❌ Should have rejected empty input")
    except Exception as e:
        print(f"Exception: {e}")

def main():
    print("\n" + "█" * 70)
    print("█  ML-Based CI/CD Pipeline Failure Prediction - API Tests")
    print("█" * 70)
    
    # Check if server is running
    try:
        requests.get(f"{BASE_URL}/health", timeout=2)
    except:
        print("\n❌ ERROR: Flask server not running!")
        print("   Start the server with: python app.py")
        sys.exit(1)
    
    # Run tests
    test_health()
    test_features()
    prediction_results = test_predictions()
    test_batch_prediction()
    test_invalid_input()
    
    # Summary
    print_header("TEST SUMMARY")
    print("\nPrediction Test Results:")
    for result in prediction_results:
        print(f"  {result['scenario']:50s} {result['status']}")
    
    print("\n" + "█" * 70)
    print("█  All tests completed!")
    print("█" * 70 + "\n")

if __name__ == "__main__":
    main()


