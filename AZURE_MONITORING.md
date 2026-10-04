# Market Forecaster Azure Monitor alerts

Market Forecaster already has hourly secretless GitHub production smoke checks for the public UI and dedicated API. This workflow adds the next layer: Azure-native metric alerts with email notification.

## Workflow

GitHub Actions workflow:

`.github/workflows/provision_azure_monitor_alerts.yml`

A push that changes the workflow only validates that the required Azure metrics exist. It does **not** create Azure Monitor resources.

To create or update the alerts, run **Prepare Azure Monitor alerts** manually with:

`apply = true`

## Required repository secret

Before applying, configure:

`MARKET_FORECASTER_AZURE_ALERT_EMAIL`

The workflow masks the value before using it and does not include the address in the job summary.

## Alerts

The workflow creates one Azure Monitor action group and six metric alert rules:

| Alert | Scope | Trigger |
| --- | --- | --- |
| marketforecaster-ui-5xx | Streamlit Web App | total HTTP 5xx > 5 over 5 minutes |
| marketforecaster-api-5xx | FastAPI Web App | total HTTP 5xx > 3 over 5 minutes |
| marketforecaster-ui-latency | Streamlit Web App | average response time > 5 seconds over 5 minutes |
| marketforecaster-api-latency | FastAPI Web App | average response time > 3 seconds over 5 minutes |
| marketforecaster-plan-cpu | App Service plan | average CPU > 85% over 10 minutes |
| marketforecaster-plan-memory | App Service plan | average memory > 85% over 10 minutes |

The alert definitions are idempotent: rerunning the workflow updates the same named rules rather than creating a second naming scheme.

## Why the workflow is manual

Azure Monitor alert rules and notification actions can affect Azure billing. The repository therefore validates the metric definitions automatically but requires an explicit manual `apply=true` run before creating Azure resources.

## Follow-up operations work

After the six metric alerts are active, the next alerting items are:

- app restart / container startup failure visibility
- failed deployment notification
- API quota exhaustion visibility
- Stripe webhook failure visibility

The existing GitHub production smoke monitor should remain enabled even after Azure Monitor alerts are active because it provides outside-in checks from a separate control plane.
