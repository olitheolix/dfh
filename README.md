[![](https://img.shields.io/badge/license-Apache%202-blue.svg)]()
[![](https://img.shields.io/badge/3.12-blue.svg)]()
[![](https://github.com/olitheolix/dfh/workflows/build/badge.svg)]()
![Codecov](https://img.shields.io/codecov/c/github/olitheolix/dfh)



# Deployments For Humans

## Usage
Create a `backend/.env` file to tell DFH where to find the credentials and
which label scheme to use. Example:

    KUBECONFIG="/tmp/kind-kubeconf.yaml"
    KUBECONTEXT="kind-kind"
    DFH_MANAGED_BY=dfh
    DFH_ENV_LABEL=env


Start the frontend and backend. Optionally, import the resources from the
integration test cluster if you have it running.

    # Start frontend API.
    cd frontend
    npm install
    npm run dev

    # Start Backend API.
    cd backend
    pipenv install --dev
    pipenv run python -m dfh

    # Import apps from KinD cluster.
    cd backend
    PYTHONPATH=`pwd` pipenv run python scripts/import_existing_apps.py

## Testing
Make sure you start the [integration test cluster](integration-test-cluster/). Then run `pytest` as usual:

    cd backend
    pipenv run pytest --cov --cov-report=html --cov-report=term-missing
