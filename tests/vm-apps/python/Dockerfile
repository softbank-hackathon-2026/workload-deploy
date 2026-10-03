# Image for the vm-container check in validate.yml. app.py reads PORT, which the playbook sets.
FROM python:3.12-slim
WORKDIR /app
COPY app.py .
EXPOSE 8080
CMD ["python", "app.py"]
