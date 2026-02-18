from . import auth, automation, cases, cicd, config, dashboard, files, health, issues, plans, runs, suites, users, versions

all_routers = [
    health.router,
    auth.router,
    config.router,
    users.router,
    versions.router,
    cases.router,
    suites.router,
    plans.router,
    runs.router,
    issues.router,
    automation.router,
    cicd.router,
    dashboard.router,
    files.router,
]
