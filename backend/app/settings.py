from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Release Quality Management Platform"
    env: str = "dev"

    database_url: str = "sqlite:///./qms.db"
    jwt_secret: str = "change_me"
    jwt_expire_min: int = 1440

    upload_dir: str = "./uploads"
    upload_public_prefix: str = "/uploads/"

    cors_origins: str = "http://localhost:5173"

    frigate_dynamic_streamlit_url: str = "http://10.10.131.192:8501"
    frigate_dynamic_build_machine_ip: str = "10.10.131.192"
    frigate_dynamic_deploy_target_ip: str = "10.10.33.56"
    frigate_dynamic_probe_timeout_sec: float = 1.5
    frigate_dynamic_live_enabled: bool = False
    frigate_dynamic_ssh_host: str = "10.10.131.192"
    frigate_dynamic_ssh_port: int = 22
    frigate_dynamic_ssh_user: str = "hyperchain"
    frigate_dynamic_ssh_password: str = ""
    frigate_dynamic_ssh_timeout_sec: float = 10.0
    frigate_dynamic_remote_root: str = "/home/hyperchain/dev_workspace/frigate-dynamic/frigateDynamic"
    frigate_dynamic_remote_container_name: str = "frigate-dynamic-web"
    frigate_dynamic_remote_container_workdir: str = "/workspace/frigateDynamic"
    frigate_dynamic_remote_python_bin: str = "python3"

    cicd_live_enabled: bool = False
    cicd_build_ssh_host: str = "172.22.67.76"
    cicd_build_ssh_port: int = 22
    cicd_build_ssh_user: str = "jinpeng"
    cicd_build_ssh_password: str = ""
    cicd_build_ssh_timeout_sec: float = 10.0
    cicd_build_root_dir: str = "/data/jinpeng/go-project-build"
    cicd_clone_repo_dir_name: str = "go-hyperchain"
    cicd_target_ssh_host: str = ""
    cicd_target_ssh_port: int = 22
    cicd_target_ssh_user: str = ""
    cicd_target_ssh_password: str = ""
    cicd_target_ssh_timeout_sec: float = 10.0
    cicd_target_deploy_dir: str = "/home/hyperchain/dev_workspace/frigate-dynamic/bin_assets/new-hyperchain"

    hypersonic_live_enabled: bool = False
    hypersonic_ssh_host: str = "172.22.67.76"
    hypersonic_ssh_port: int = 22
    hypersonic_ssh_user: str = "hyperchain"
    hypersonic_ssh_password: str = ""
    hypersonic_ssh_timeout_sec: float = 10.0
    hypersonic_runner_image: str = "harbor.hyperchain.cn/hub/hyper-test:hypersonic-centos7"
    hypersonic_max_parallel: int = 2
    hypersonic_remote_base_dir: str = "/workspace/qms-hypersonic-runs"
    hypersonic_remote_repo_dir: str = "/workspace/hypersonic"
    hypersonic_remote_python_bin: str = "python3"
    hypersonic_exec_container_name: str = ""
    hypersonic_ci_list_path: str = (
        "/Users/zhangliangchen/PycharmProjects/hypersonic-dev/hypersonic/scripts/ci_list.json"
    )
    hypersonic_default_timeout_sec: int = 7200
    hypersonic_report_retention_days: int = 14

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def upload_path(self) -> Path:
        return Path(self.upload_dir).resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
