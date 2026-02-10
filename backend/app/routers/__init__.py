from . import auth, automation, cases, cicd, config, dashboard, files, health, issues, users, versions

all_routers = [
    health.router,
    auth.router,
    config.router,
    users.router,
    versions.router,
    cases.router,
    issues.router,
    automation.router,
    cicd.router,
    dashboard.router,
    files.router,
]
