from veadk.cloud.cloud_app import CloudApp

def main() -> None:
    cloud_app = CloudApp(vefaas_application_name="{{cookiecutter.vefaas_application_name}}")
    cloud_app.delete_self()

    
if __name__ == "__main__":
    main()