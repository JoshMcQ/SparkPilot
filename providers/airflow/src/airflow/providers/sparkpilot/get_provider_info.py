def get_provider_info() -> dict[str, object]:
    return {
        "package-name": "apache-airflow-providers-sparkpilot",
        "name": "SparkPilot",
        "description": "Apache Airflow provider for SparkPilot control plane APIs.",
        "state": "ready",
        "versions": ["0.1.0"],
        "hooks": [
            {
                "integration-name": "SparkPilot",
                "python-modules": ["airflow.providers.sparkpilot.hooks.sparkpilot"],
            }
        ],
        "operators": [
            {
                "integration-name": "SparkPilot",
                "python-modules": ["airflow.providers.sparkpilot.operators.sparkpilot"],
            }
        ],
        "sensors": [
            {
                "integration-name": "SparkPilot",
                "python-modules": ["airflow.providers.sparkpilot.sensors.sparkpilot"],
            }
        ],
        "triggers": [
            {
                "integration-name": "SparkPilot",
                "python-modules": ["airflow.providers.sparkpilot.triggers.sparkpilot"],
            }
        ],
        "connection-types": [
            {
                "connection-type": "sparkpilot",
                "hook-class-name": "airflow.providers.sparkpilot.hooks.sparkpilot.SparkPilotHook",
            }
        ],
    }

