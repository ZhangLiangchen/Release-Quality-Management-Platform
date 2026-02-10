from . import auth, cases, config, dashboard, files, health, issues, users, versions

all_routers = [
    health.router,
    auth.router,
    config.router,
    users.router,
    versions.router,
    cases.router,
    issues.router,
    dashboard.router,
    files.router,
]
