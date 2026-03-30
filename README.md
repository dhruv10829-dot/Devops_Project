# ML-Based CI/CD Failure Prediction

This project predicts whether a CI/CD build is likely to pass or fail before the full pipeline runs.

It includes:
- A Flask API for single and batch predictions
- A trained Random Forest model and preprocessing artifacts
- A sample GitHub Actions workflow for using prediction as a gate
- Docker support for local or server deployment

## What Problem This Solves

In many teams, builds fail after spending time on install/test/build steps. This service tries to estimate failure risk early using commit-level metadata so teams can:
- Get fast feedback
- Avoid unnecessary build runs
- Use compute resources more efficiently

## Project Structure

```text
.
├── app.py
├── requirements.txt
├── Dockerfile
├── ci_cd_workflow.yml
├── ci_cd_build_dataset.csv
├── random_forest_model.pkl
├── scaler.pkl
├── label_encoder.pkl
├── feature_names.txt
├── test_api.py
├── PROJECT_REPORT.docx
├── VIVA_PREPARATION.docx
└── README.md
```

## Prerequisites

- Python 3.9+
- pip
- Git
- Docker (optional)

## Local Setup

```bash
git clone https://github.com/practicalClerk/Devops_Project.git
cd Devops_Project

python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

## Run the API

```bash
python app.py
```

Server starts on `http://0.0.0.0:5000`.

## API Endpoints

### GET /health
Returns service status.

Example response:

```json
{
  "status": "healthy",
  "service": "CI/CD Failure Predictor",
  "timestamp": "2026-03-29T10:20:30.123456"
}
```

### POST /predict
Predicts one commit/build sample.

Request:

```json
{
  "commit_size": 100,
  "files_changed": 5,
  "test_coverage": 75.0,
  "past_failures": 2,
  "dependency_changes": 0,
  "author_experience": 60,
  "time_of_commit": 14,
  "build_time": 350.0
}
```

Response shape:

```json
{
  "prediction": "PASS",
  "risk_level": "MEDIUM",
  "failure_probability": 0.3421,
  "pass_probability": 0.6579,
  "confidence": 0.7654,
  "recommendation": "CONTINUE PIPELINE",
  "timestamp": "2026-03-29T10:20:30.123456"
}
```

### POST /predict-batch
Predicts a list of commit/build samples.

Request:

```json
[
  {
    "commit_id": "abc123",
    "commit_size": 30,
    "files_changed": 2,
    "test_coverage": 90.0,
    "past_failures": 0,
    "dependency_changes": 0,
    "author_experience": 120,
    "time_of_commit": 11,
    "build_time": 180.0
  }
]
```

Response shape:

```json
{
  "predictions": [
    {
      "commit_id": "abc123",
      "prediction": "PASS",
      "failure_probability": 0.1234
    }
  ]
}
```

### GET /features
Returns feature names and model feature importance.

## Quick API Test

In another terminal:

```bash
python test_api.py
```

## Docker Usage

```bash
docker build -t ml-cicd-predictor:latest .
docker run -p 5000:5000 ml-cicd-predictor:latest
```

Health check:

```bash
curl http://localhost:5000/health
```

## GitHub Actions Workflow

A sample workflow is provided in `ci_cd_workflow.yml`. The idea is:
1. Extract commit metadata.
2. Call prediction logic.
3. Continue build/test only if risk decision allows it.

To use it:

```bash
mkdir -p .github/workflows
cp ci_cd_workflow.yml .github/workflows/ci_cd_workflow.yml
```

Then adjust paths and secrets for your own repository.

## Model Notes

- Dataset: 2,000 samples
- Input features: 8
- Classes: PASS and FAIL
- Trained model artifact: `random_forest_model.pkl`

Important: this is a course project model trained on available dataset features. It should be retrained with real pipeline history before production use.

## Known Limitations

- Predictions are only as good as training data quality.
- Some failures are still missed.
- This should support, not replace, normal CI checks.

## References

- https://scikit-learn.org/stable/
- https://flask.palletsprojects.com/
- https://docs.github.com/en/actions
- https://docs.docker.com/

## License

For academic use unless your team defines a separate license.

## Author

Ayush
Emerging Tools and Technologies Lab
