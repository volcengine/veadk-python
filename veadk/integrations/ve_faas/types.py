from pydantic import BaseModel


class TemplateVariables(BaseModel):
    local_dir_name: str = "veadk_vefaas_proj"

    app_name: str = "weather-report"

    agent_module_name: str = "weather_agent"

    requirement_file_path: str = "./weather_agent/requirements.txt"

    short_term_memory_backend: str = "local"

    vefaas_application_name: str = "weather-reporter"

    veapig_instance_name: str = ""

    veapig_service_name: str = ""

    veapig_upstream_name: str = ""

    use_adk_web: bool = False
